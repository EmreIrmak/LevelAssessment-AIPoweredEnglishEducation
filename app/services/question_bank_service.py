import json
from flask import current_app
from app.extensions import db
from app.models import Question, ModuleType, QuestionType, CEFRLevel
from app.services.nlp_service import NLPService
import pathlib
import re
from flask import current_app


class QuestionBankService:
    @staticmethod
    def _ensure_writing_word_range(text: str) -> str:
        """Ensure Writing prompts clearly request a 150–200 word response."""
        raw = (text or "").strip()
        if not raw:
            return raw

        # Remove noisy labels and sentence-count constraints (keep the topic).
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        normalized_lines: list[str] = []
        for line in lines:
            line = re.sub(r"^\s*writing\s*:\s*", "", line, flags=re.IGNORECASE)
            line = re.sub(
                r"\bwrite\s+\d+\s*(?:-|–|to)\s*\d+\s*sentences?\s*",
                "Write ",
                line,
                flags=re.IGNORECASE,
            ).strip()
            # Remove "Write 3 to 5 sentences" style (with words instead of symbols)
            line = re.sub(
                r"\bwrite\s+\d+\s+to\s+\d+\s+sentences?\s*",
                "Write ",
                line,
                flags=re.IGNORECASE,
            ).strip()
            line = re.sub(
                r"\b(?:answer|respond|write)\s+in\s+\d+\s*(?:-|–|to|\s+to\s+)\d+\s*sentences?\b\s*",
                "",
                line,
                flags=re.IGNORECASE,
            ).strip()
            # Remove standalone "(3-5 sentences)" or similar patterns
            line = re.sub(
                r"\(\s*\d+\s*(?:-|–|to|\s+to\s+)\d+\s*sentences?\s*\)",
                "",
                line,
                flags=re.IGNORECASE,
            ).strip()
            if line:
                normalized_lines.append(line)

        raw = "\n\n".join(normalized_lines).strip() or raw

        # If prompt already mentions the target range, keep as-is.
        has_range = re.search(r"150\s*(?:-|–|to)\s*200\s*words?", raw, re.IGNORECASE)
        if not has_range:
            has_range = re.search(r"\b150\b.*\b200\b.*\bwords?\b", raw, re.IGNORECASE | re.DOTALL)

        if has_range:
            return raw

        suffix = "Write 150–200 words. Include a clear thesis and at least 2 supporting points."
        return f"{raw}\n\n{suffix}"

    @staticmethod
    def _exists(text: str, module: ModuleType, difficulty: CEFRLevel) -> bool:
        return (
            Question.query.filter_by(text=text, module=module, difficulty=difficulty).first()
            is not None
        )

    @staticmethod
    def add_questions(module: ModuleType, difficulty: CEFRLevel, questions: list[dict]) -> int:
        created = 0
        for q in questions:
            if not q or not q.get("text"):
                continue

            text = q["text"].strip()
            if not text:
                continue

            if module == ModuleType.WRITING:
                text = QuestionBankService._ensure_writing_word_range(text)

            if QuestionBankService._exists(text, module, difficulty):
                continue

            # Enforce OPEN_ENDED for Writing; otherwise use provided type/default MCQ
            if module == ModuleType.WRITING:
                q_type = QuestionType.OPEN_ENDED
                options_json = None
                correct = None
            else:
                q_type_str = q.get("question_type") or "MULTIPLE_CHOICE"
                try:
                    q_type = QuestionType[q_type_str]
                except Exception:
                    q_type = QuestionType.MULTIPLE_CHOICE

                options = q.get("options")
                options_json = json.dumps(options) if isinstance(options, dict) else None
                correct = q.get("correct_answer")

            new_q = Question(
                text=text,
                module=module,
                difficulty=difficulty,
                question_type=q_type,
                options=options_json,
                correct_answer=correct,
            )
            db.session.add(new_q)
            created += 1

        if created:
            db.session.commit()
        return created

    @staticmethod
    def _parse_reading_questions(md_path: pathlib.Path) -> list[dict]:
        """
        Parse reading questions in format:
        N. Question text...
        (ANSWER: X)  [optional]
            a. option
            b. option
            c. option
            d. option
        """
        if not md_path.exists():
            current_app.logger.warning(f"Reading questions file not found: {md_path}")
            return []
        text = md_path.read_text(encoding="utf-8")
        lines = [l.strip() for l in text.splitlines()]
        items = []
        current = None
        for line in lines:
            if not line:
                continue
            m_q = re.match(r"^(\d+)\.\s*(.+)", line)
            if m_q:
                if current:
                    items.append(current)
                current = {"text": m_q.group(2).strip(), "options": {}, "answer": None}
                continue
            if current is None:
                continue
            m_ans = re.match(r"^\(?\s*ANSWER\s*:\s*([A-D])\s*\)?$", line, re.IGNORECASE)
            if m_ans:
                current["answer"] = m_ans.group(1).upper()
                continue
            m_opt = re.match(r"^[a-dA-D]\.\s*(.+)", line)
            if m_opt:
                letter = line.split(".")[0].strip().upper()
                val = line.split(".", 1)[1].strip()
                current["options"][letter] = val
                continue
        if current:
            items.append(current)

        parsed = []
        for it in items:
            if not it.get("text") or not it.get("options"):
                continue
            parsed.append(
                {
                    "text": it["text"],
                    "options": it["options"],
                    "correct_answer": it.get("answer"),
                    "question_type": "MULTIPLE_CHOICE",
                }
            )
        return parsed

    @staticmethod
    def ensure_reading_from_files(difficulty: CEFRLevel = CEFRLevel.B2) -> dict:
        base_dir = pathlib.Path(current_app.root_path).parent / "data" / "reading"
        questions_path = base_dir / "reading_questions"

        questions = QuestionBankService._parse_reading_questions(questions_path)
        created = 0
        for q in questions:
            text = (q.get("text") or "").strip()
            if not text:
                continue
            exists = Question.query.filter_by(module=ModuleType.READING, text=text).first()
            correct = (q.get("correct_answer") or "").strip().upper() if q.get("correct_answer") else None
            if correct and correct not in ("A", "B", "C", "D"):
                correct = None

            options_json = json.dumps(q.get("options")) if isinstance(q.get("options"), dict) else None

            if exists:
                changed = False
                if options_json and (exists.options or "") != options_json:
                    exists.options = options_json
                    changed = True
                if correct and (exists.correct_answer or "") != correct:
                    exists.correct_answer = correct
                    changed = True
                if changed:
                    # Don't touch difficulty/question_type for existing rows.
                    db.session.commit()
                continue
            new_q = Question(
                text=text,
                module=ModuleType.READING,
                difficulty=difficulty,
                question_type=QuestionType.MULTIPLE_CHOICE,
                options=options_json,
                correct_answer=correct,
            )
            db.session.add(new_q)
            created += 1
        if created:
            db.session.commit()
        existing = Question.query.filter_by(module=ModuleType.READING).count()
        return {"ok": True, "created": created, "existing": existing}

    @staticmethod
    def ensure_module_level_pool(module: ModuleType, difficulty: CEFRLevel, min_count: int) -> dict:
        """
        Ensures there are at least min_count questions in DB for given module+level.
        If Groq is not available, returns without generating.
        """
        existing = Question.query.filter_by(module=module, difficulty=difficulty).count()
        if existing >= min_count:
            return {"ok": True, "created": 0, "existing": existing, "target": min_count}

        client = NLPService._get_client()
        if not client:
            return {"ok": False, "created": 0, "existing": existing, "target": min_count, "error": "AI unavailable"}

        created_total = 0
        # Writing: always open-ended, generate smaller batches
        if module == ModuleType.WRITING:
            while existing < min_count:
                remaining = max(1, min_count - existing)
                batch = NLPService.generate_writing_set(count=remaining, difficulty=difficulty.value)
                if not batch:
                    break
                created_total += QuestionBankService.add_questions(module, difficulty, batch)
                existing = Question.query.filter_by(module=module, difficulty=difficulty).count()
        elif module == ModuleType.READING:
            # Reading: load from local files (no AI)
            result = QuestionBankService.ensure_reading_from_files(difficulty=CEFRLevel.B2)
            created_total += result.get("created", 0)
            existing = Question.query.filter_by(module=module).count()
        elif module == ModuleType.GRAMMAR:
            while existing < min_count:
                remaining = max(1, min_count - existing)
                batch = NLPService.generate_example_guided_mcq(
                    module="Grammar",
                    difficulty=difficulty.value,
                    count=remaining,
                    examples=NLPService.GRAMMAR_EXAMPLES,
                )
                if not batch:
                    batch = NLPService.generate_10_mcq_for_module(module.value, difficulty=difficulty.value)
                created_total += QuestionBankService.add_questions(module, difficulty, batch)
                existing = Question.query.filter_by(module=module, difficulty=difficulty).count()
        elif module == ModuleType.VOCABULARY:
            while existing < min_count:
                remaining = max(1, min_count - existing)
                batch = NLPService.generate_example_guided_mcq(
                    module="Vocabulary",
                    difficulty=difficulty.value,
                    count=remaining,
                    examples=NLPService.VOCAB_EXAMPLES,
                )
                if not batch:
                    batch = NLPService.generate_10_mcq_for_module(module.value, difficulty=difficulty.value)
                created_total += QuestionBankService.add_questions(module, difficulty, batch)
                existing = Question.query.filter_by(module=module, difficulty=difficulty).count()
        elif module == ModuleType.SPEAKING:
            while existing < min_count:
                remaining = max(1, min_count - existing)
                batch = NLPService.generate_speaking_set(count=remaining, difficulty=difficulty.value)
                if not batch:
                    break
                created_total += QuestionBankService.add_questions(module, difficulty, batch)
                existing = Question.query.filter_by(module=module, difficulty=difficulty).count()
        else:
            # Generate in batches of 10 MCQ using the ETS prompt
            max_batches = max(1, (min_count - existing + 9) // 10)
            for _ in range(max_batches):
                batch = NLPService.generate_10_mcq_for_module(module.value, difficulty=difficulty.value)
                created_total += QuestionBankService.add_questions(module, difficulty, batch)
                existing = Question.query.filter_by(module=module, difficulty=difficulty).count()
                if existing >= min_count:
                    break

        return {"ok": True, "created": created_total, "existing": existing, "target": min_count}

    # --- Listening specific: load from markdown pools ---
    @staticmethod
    def _parse_md_questions(md_path: pathlib.Path) -> list[dict]:
        """
        Parse markdown blocks in the format:
        N. Question text...
        (ANSWER: X)
            a. option
            b. option
            c. option
        [optional d.]
        """
        if not md_path.exists():
            current_app.logger.warning(f"Listening file not found: {md_path}")
            return []
        text = md_path.read_text(encoding="utf-8")
        lines = [l.strip() for l in text.splitlines()]
        items = []
        current = None
        for line in lines:
            if not line:
                continue
            m_q = re.match(r"^(\d+)\.\s*(.+)", line)
            if m_q:
                # start new question
                if current:
                    items.append(current)
                current = {
                    "text": m_q.group(2).strip(),
                    "options": {},
                    "answer": None,
                }
                continue
            if current is None:
                continue
            m_ans = re.match(r"^\(ANSWER:\s*([A-D])\)", line, re.IGNORECASE)
            if m_ans:
                current["answer"] = m_ans.group(1).upper()
                continue
            m_opt = re.match(r"^[a-dA-D]\.\s*(.+)", line)
            if m_opt:
                letter = line.split(".")[0].strip().upper()
                val = line.split(".", 1)[1].strip()
                current["options"][letter] = val
                continue
        if current:
            items.append(current)

        parsed = []
        for it in items:
            if not it.get("text") or not it.get("answer") or not it.get("options"):
                continue
            # ensure 3+ options
            parsed.append(
                {
                    "text": it["text"],
                    "options": it["options"],
                    "correct_answer": it["answer"],
                    "question_type": "MULTIPLE_CHOICE",
                }
            )
        return parsed

    @staticmethod
    def ensure_listening_pool(pool: int, audio_filename: str, base_dir: pathlib.Path | None = None) -> dict:
        """
        Load listening questions from md files for a given pool.
        pool: 1 or 2
        audio_filename: e.g., 'listeningaudio1.mp3'
        """
        base_dir = base_dir or pathlib.Path(current_app.root_path).parent / "data" / "listening"
        part1 = base_dir / f"pool{pool}_part1.md"
        part2 = base_dir / f"pool{pool}_part2.md"

        questions = []
        for md_file in (part1, part2):
            questions.extend(QuestionBankService._parse_md_questions(md_file))

        created = 0
        for idx, q in enumerate(questions, start=1):
            if QuestionBankService._exists(q["text"], ModuleType.LISTENING, CEFRLevel.B2):
                continue
            options_json = json.dumps(q.get("options")) if isinstance(q.get("options"), dict) else None
            new_q = Question(
                text=q["text"],
                module=ModuleType.LISTENING,
                difficulty=CEFRLevel.B2,
                question_type=QuestionType.MULTIPLE_CHOICE,
                options=options_json,
                correct_answer=q.get("correct_answer"),
                audio_url=f"/static/audio/{audio_filename}",
            )
            db.session.add(new_q)
            created += 1
        if created:
            db.session.commit()
        existing = Question.query.filter_by(module=ModuleType.LISTENING).count()
        return {"ok": True, "created": created, "existing": existing}

    @staticmethod
    def ensure_listening_pools():
        """
        Load both pools (audio1/2) from markdown if not already present.
        """
        results = []
        results.append(QuestionBankService.ensure_listening_pool(1, "listeningaudio1.mp3"))
        results.append(QuestionBankService.ensure_listening_pool(2, "listeningaudio2.mp3"))
        return results


