from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app, session as flask_session, jsonify
from flask_login import login_required, current_user
from app.extensions import db
import re
import pathlib
from app.models import (
    TestSession,
    Question,
    Response,
    ModuleType,
    QuestionType,
    CEFRLevel,
    SessionModuleAttempt,
    SessionQuestion,
    SessionQuestionStatus,
    ModuleAttemptStatus,
)


def _ensure_writing_word_range(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return raw

    # Remove noisy labels and sentence-count constraints (keep the topic).
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    normalized_lines: list[str] = []
    for line in lines:
        line = re.sub(r"^\s*writing\s*:\s*", "", line, flags=re.IGNORECASE)

        # Convert "Write 3–5 sentences ..." -> "Write ..." (preserve the rest).
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

        # Remove other variants like "Answer in 3-5 sentences" or "in 3 to 5 sentences"
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

    normalized = "\n\n".join(normalized_lines).strip() or raw

    # Ensure the prompt explicitly requests the 150–200 word range.
    has_range = re.search(r"150\s*(?:-|–|to)\s*200\s*words?", normalized, re.IGNORECASE)
    if not has_range:
        has_range = re.search(r"\b150\b.*\b200\b.*\bwords?\b", normalized, re.IGNORECASE | re.DOTALL)
    if has_range:
        return normalized

    return f"{normalized}\n\nWrite 150–200 words. Include a clear thesis and at least 2 supporting points."

from app.services.nlp_service import NLPService
from app.services.adaptive_service import AdaptiveService
from app.services.question_bank_service import QuestionBankService
import json
from datetime import datetime, timedelta
from sqlalchemy import func
from app.models import CEFRLevel

test_bp = Blueprint("test", __name__)

# Full assessment order
MODULE_ORDER = [
    ModuleType.GRAMMAR,
    ModuleType.VOCABULARY,
    ModuleType.READING,
    ModuleType.WRITING,
    ModuleType.LISTENING,
    ModuleType.SPEAKING,
]
LISTENING_BLOCK_SIZE = 8

# Choose listening pool (1 or 2). Uses env override LISTENING_POOL_FORCE, otherwise sticks per exam.
def _get_listening_pool(session_id: int) -> int:
    force = current_app.config.get("LISTENING_POOL_FORCE")
    if force in ("1", "2", 1, 2):
        return int(force)
    key = f"listening_pool_{session_id}"
    if key in flask_session:
        try:
            return int(flask_session[key])
        except Exception:
            pass
    import random
    choice = random.choice([1, 2])
    flask_session[key] = choice
    return choice

def _module_position(session: TestSession) -> tuple[int, int]:
    total = len(MODULE_ORDER)
    try:
        idx = MODULE_ORDER.index(session.current_module)
    except ValueError:
        idx = 0
    return idx, total

def _overall_progress_percent(session: TestSession) -> int:
    # Step 1: Calculate TOTAL questions across all 6 modules dynamically from config
    total_questions = 0
    for mod in MODULE_ORDER:
        total_questions += _questions_for_module(mod, session)
    
    # Step 2: Calculate completed questions up to current module
    completed_questions = 0
    for mod in MODULE_ORDER:
        m_total = _questions_for_module(mod, session)
        if mod == session.current_module:
            # For current module, count questions up to current index
            completed_questions += min(session.current_question_index, m_total)
            break
        else:
            # For completed modules, count all questions
            completed_questions += m_total
    
    return int((completed_questions / max(1, total_questions)) * 100)


def _split_reading_text(text: str) -> tuple[str, str]:
    raw = (text or "").strip()
    if not raw:
        return "", ""

    # Remove leading "READING:" label
    raw = re.sub(r"^\s*reading\s*:\s*", "", raw, flags=re.IGNORECASE)

    # Split on "Question:" if present
    parts = re.split(r"\n\s*Question\s*:\s*", raw, flags=re.IGNORECASE, maxsplit=1)
    if len(parts) > 1:
        passage = parts[0].strip()
        question = parts[1].strip()
        return passage, question

    # If text is too short, treat it as question-only (no passage embedded)
    if len(raw) < 300:
        return "", raw

    # Otherwise treat the whole text as passage
    return raw, ""


def _reading_passage_key(session_id: int) -> str:
    return f"reading_passage_{session_id}"


def _get_reading_passage(session_id: int) -> str | None:
    return flask_session.get(_reading_passage_key(session_id))


def _set_reading_passage(session_id: int, passage: str) -> None:
    if passage:
        flask_session[_reading_passage_key(session_id)] = passage


def _clear_reading_passage(session_id: int) -> None:
    flask_session.pop(_reading_passage_key(session_id), None)


def _parse_reading_questions_file(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        current_app.logger.warning(f"Reading questions file not found: {path}")
        return []

    text = path.read_text(encoding="utf-8")
    lines = [l.strip() for l in text.splitlines()]
    items: list[dict] = []
    current: dict | None = None

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

    parsed: list[dict] = []
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


def _load_reading_materials() -> tuple[str, list[dict]]:
    base_dir = pathlib.Path(current_app.root_path).parent / "data" / "reading"
    passage_path = base_dir / "reading_passage"
    questions_path = base_dir / "reading_questions"

    passage = ""
    if passage_path.exists():
        passage = passage_path.read_text(encoding="utf-8").strip()
    else:
        current_app.logger.warning(f"Reading passage file not found: {passage_path}")

    questions = _parse_reading_questions_file(questions_path)
    return passage, questions


def _get_or_create_reading_question(qdata: dict, difficulty: CEFRLevel) -> Question | None:
    text = (qdata.get("text") or "").strip()
    if not text:
        return None

    existing = Question.query.filter_by(module=ModuleType.READING, text=text).first()
    correct = (qdata.get("correct_answer") or "").strip().upper() if qdata.get("correct_answer") else None
    if correct and correct not in ("A", "B", "C", "D"):
        correct = None

    options_json = json.dumps(qdata.get("options")) if isinstance(qdata.get("options"), dict) else None

    if existing:
        changed = False
        if options_json and (existing.options or "") != options_json:
            existing.options = options_json
            changed = True
        if correct and (existing.correct_answer or "") != correct:
            existing.correct_answer = correct
            changed = True
        if changed:
            db.session.commit()
        return existing

    new_q = Question(
        text=text,
        module=ModuleType.READING,
        difficulty=difficulty,
        question_type=QuestionType.MULTIPLE_CHOICE,
        options=options_json,
        correct_answer=correct,
    )
    db.session.add(new_q)
    db.session.commit()
    return new_q


def _questions_for_module(module: ModuleType, session: TestSession | None = None) -> int:
    if module == ModuleType.READING:
        passage, questions = _load_reading_materials()
        if questions:
            return len(questions)
        # If no file-based questions, fall back to config to avoid blocking.
    if module == ModuleType.LISTENING:
        # Listening is fixed by the preloaded listening pools; do not override by env.
        if session is None:
            return 0
        return int(_get_listening_total(session) or 0)

    counts = current_app.config.get("QUESTIONS_PER_SECTION") or {}
    raw = counts.get(module.value)
    try:
        n = int(raw)
    except Exception:
        n = 10
    return max(1, n)


def _get_time_limit_seconds(module: ModuleType) -> int:
    limits = current_app.config.get("MODULE_TIME_LIMITS") or {}
    return int(limits.get(module.value, 0) or 0)


def _get_or_create_attempt(session: TestSession) -> SessionModuleAttempt:
    attempt = SessionModuleAttempt.query.filter_by(
        session_id=session.id, module=session.current_module
    ).first()
    if not attempt:
        attempt = SessionModuleAttempt(
            session_id=session.id,
            module=session.current_module,
            time_limit_seconds=_get_time_limit_seconds(session.current_module),
            status=ModuleAttemptStatus.IN_PROGRESS,
        )
        db.session.add(attempt)
        db.session.commit()
    return attempt

# Listening block helpers
def _get_listening_total(session: TestSession) -> int:
    ordered = _get_listening_ordered_questions(session)
    if ordered:
        return len(ordered)
    pool = _get_listening_pool(session.id)
    return Question.query.filter(
        Question.module == ModuleType.LISTENING,
        Question.audio_url.ilike(f"%listeningaudio{pool}%"),
    ).count()

def _get_listening_block_bounds(session: TestSession):
    total = _get_listening_total(session)
    start = (session.current_question_index // LISTENING_BLOCK_SIZE) * LISTENING_BLOCK_SIZE
    end = min(start + LISTENING_BLOCK_SIZE, total)
    return start, end, total

def _fetch_listening_question(
    session: TestSession,
    question_index: int,
    served_question_ids: set[int],
    ordered_questions: list[Question],
):
    if ordered_questions:
        if 0 <= question_index < len(ordered_questions):
            return ordered_questions[question_index]
        return None

    base_query = Question.query.filter(
        Question.module == ModuleType.LISTENING,
        ~Question.id.in_(served_question_ids),
    )
    pool = _get_listening_pool(session.id)
    base_query = base_query.filter(Question.audio_url.ilike(f"%listeningaudio{pool}%"))
    return base_query.order_by(func.random()).first()

def _get_listening_ordered_questions(session: TestSession) -> list[Question]:
    pool = _get_listening_pool(session.id)
    base_dir = pathlib.Path(current_app.root_path).parent / "data" / "listening"
    part1 = base_dir / f"pool{pool}_part1.md"
    part2 = base_dir / f"pool{pool}_part2.md"

    parsed = []
    for md_file in (part1, part2):
        parsed.extend(QuestionBankService._parse_md_questions(md_file))

    if not parsed:
        return []

    texts = [q["text"] for q in parsed if q.get("text")]
    if not texts:
        return []

    db_questions = Question.query.filter(
        Question.module == ModuleType.LISTENING,
        Question.audio_url.ilike(f"%listeningaudio{pool}%"),
        Question.text.in_(texts),
    ).all()
    by_text: dict[str, Question] = {}
    for q in db_questions:
        if q.text not in by_text:
            by_text[q.text] = q

    ordered_questions = [by_text[t] for t in texts if t in by_text]
    return ordered_questions

def _render_listening_block(session: TestSession, attempt: SessionModuleAttempt, remaining: int | None):
    start, end, total = _get_listening_block_bounds(session)
    if total == 0:
        flash("Listening question pool is empty. Please inform an administrator.", "danger")
        return redirect(url_for("auth.dashboard"))
    ordered_questions = _get_listening_ordered_questions(session)
    served_question_ids = db.session.query(SessionQuestion.question_id).filter(
        SessionQuestion.session_id == session.id
    )
    served_ids = {row[0] for row in served_question_ids}

    questions = []
    audio_url = None
    pool = _get_listening_pool(session.id)
    part_index = (start // LISTENING_BLOCK_SIZE) + 1  # 1-based
    part_start_sec = 0
    if pool == 1 and part_index == 2:
        part_start_sec = 13 * 60 + 45  # 825s
    elif pool == 2 and part_index == 2:
        part_start_sec = 12 * 60 + 24  # 744s

    for idx in range(start, end):
        sq = SessionQuestion.query.filter_by(
            session_id=session.id,
            module=session.current_module,
            question_index=idx,
        ).first()
        if sq:
            q = sq.question
        else:
            q = _fetch_listening_question(session, idx, served_ids, ordered_questions)
            if not q:
                continue
            sq = SessionQuestion(
                session_id=session.id,
                module=session.current_module,
                question_index=idx,
                question_id=q.id,
                status=SessionQuestionStatus.SERVED,
            )
            db.session.add(sq)
            db.session.commit()
            served_ids.add(q.id)
        if not audio_url:
            audio_url = q.audio_url
        existing_response = (
            Response.query.filter_by(session_id=session.id, question_id=q.id)
            .order_by(Response.id.desc())
            .first()
        )
        options_dict = None
        if q.options:
            try:
                options_dict = (
                    json.loads(q.options)
                    if isinstance(q.options, str)
                    else q.options
                )
            except Exception:
                options_dict = None
        questions.append({"sq": sq, "question": q, "response": existing_response, "options": options_dict})

    context = dict(
        session=session,
        attempt=attempt,
        questions=questions,
        remaining_seconds=remaining,
        block_start=start,
        block_end=end,
        total=total,
        overall_progress=_overall_progress_percent(session),
        audio_url=audio_url,
        audio_start_sec=part_start_sec,
    )

    # AJAX partial render
    if request.headers.get("X-Listen-Ajax"):
        html = render_template("partials/listening_block.html", **context)
        return jsonify({"ok": True, "html": html, "audio_start_sec": part_start_sec})

    return render_template("exam_listening.html", **context)

def _handle_listening_block(session: TestSession, attempt: SessionModuleAttempt):
    start, end, total = _get_listening_block_bounds(session)
    if total == 0:
        flash("Listening question pool is empty. Please inform an administrator.", "danger")
        return redirect(url_for("auth.dashboard"))

    action = request.form.get("action", "next")
    if action == "prev_block":
        session.current_question_index = max(0, start - LISTENING_BLOCK_SIZE)
        db.session.commit()
        if request.headers.get("X-Listen-Ajax"):
            remaining = _remaining_seconds(attempt)
            return _render_listening_block(session, attempt, remaining)
        return redirect(url_for("test.get_question", session_id=session.id))

    # Gather current block questions
    questions = []
    for idx in range(start, end):
        sq = SessionQuestion.query.filter_by(
            session_id=session.id,
            module=session.current_module,
            question_index=idx,
        ).first()
        if not sq:
            continue
        questions.append(sq)

    # Process answers
    for sq in questions:
        qid = sq.question_id
        field = f"q_{qid}"
        user_answer = (request.form.get(field) or "").strip()
        if not user_answer:
            sq.status = SessionQuestionStatus.SKIPPED
            db.session.commit()
            continue

        question = sq.question
        is_correct = user_answer == question.correct_answer

        resp = (
            Response.query.filter_by(session_id=session.id, question_id=question.id)
            .order_by(Response.id.desc())
            .first()
        )
        if not resp:
            resp = Response(session_id=session.id, question_id=question.id)
            db.session.add(resp)

        resp.selected_option = user_answer
        resp.text_answer = None
        resp.is_correct = is_correct
        resp.audio_filename = resp.audio_filename
        resp.transcript = resp.transcript
        resp.stt_provider = resp.stt_provider
        resp.stt_status = resp.stt_status

        sq.status = SessionQuestionStatus.ANSWERED
        sq.answered_at = datetime.utcnow()
        db.session.commit()

    # advance to next block or finish
    session.current_question_index = end
    if end >= total:
        # Last block: before leaving Listening, ensure audio has completed
        audio_completed = request.form.get("audio_completed", "0")
        if audio_completed != "1":
            if request.headers.get("X-Listen-Ajax"):
                return jsonify({
                    "ok": False, 
                    "error": "Listening section not finished"
                })
            return redirect(url_for("test.get_question", session_id=session.id))
        
        attempt.ended_at = datetime.utcnow()
        attempt.status = ModuleAttemptStatus.COMPLETED
        db.session.commit()
        
        # Advance to next module
        try:
            curr_idx = MODULE_ORDER.index(session.current_module)
            if curr_idx + 1 < len(MODULE_ORDER):
                if session.current_module == ModuleType.READING:
                    _clear_reading_passage(session.id)
                session.current_module = MODULE_ORDER[curr_idx + 1]
                session.current_question_index = 0
                db.session.commit()
                next_url = url_for("test.get_question", session_id=session.id)
            else:
                session.end_time = datetime.utcnow()
                session.is_completed = True
                db.session.commit()
                next_url = url_for("test.report_options", session_id=session.id)
        except ValueError:
            session.end_time = datetime.utcnow()
            session.is_completed = True
            db.session.commit()
            next_url = url_for("test.report_options", session_id=session.id)
        
        # For AJAX requests, return redirect URL
        if request.headers.get("X-Listen-Ajax"):
            return jsonify({"ok": True, "redirect": next_url})
        
        return redirect(next_url)

    db.session.commit()
    if request.headers.get("X-Listen-Ajax"):
        remaining = _remaining_seconds(attempt)
        return _render_listening_block(session, attempt, remaining)
    return redirect(url_for("test.get_question", session_id=session.id))


def _get_next_module_url(session: TestSession):
    """Get next module URL without actually advancing"""
    try:
        curr_idx = MODULE_ORDER.index(session.current_module)
        if curr_idx + 1 < len(MODULE_ORDER):
            return url_for("test.get_question", session_id=session.id)
    except ValueError:
        pass
    return url_for("test.report_options", session_id=session.id)


def _remaining_seconds(attempt: SessionModuleAttempt) -> int | None:
    if not attempt.started_at or not attempt.time_limit_seconds:
        return None
    elapsed = datetime.utcnow() - attempt.started_at
    remaining = int(attempt.time_limit_seconds - elapsed.total_seconds())
    return max(0, remaining)


def _advance_module(session: TestSession):
    # move to next module (or finish exam)
    try:
        curr_idx = MODULE_ORDER.index(session.current_module)
        if curr_idx + 1 < len(MODULE_ORDER):
            if session.current_module == ModuleType.READING:
                _clear_reading_passage(session.id)
            session.current_module = MODULE_ORDER[curr_idx + 1]
            session.current_question_index = 0
            db.session.commit()
            return redirect(url_for("test.get_question", session_id=session.id))
    except ValueError:
        pass

    session.end_time = datetime.utcnow()
    session.is_completed = True
    db.session.commit()
    # Before report generation, ask student how to generate the report.
    return redirect(url_for("test.report_options", session_id=session.id))


@test_bp.route("/exam/<int:session_id>/report_options", methods=["GET", "POST"])
@login_required
def report_options(session_id: int):
    session = TestSession.query.get_or_404(session_id)
    if session.user_id != current_user.id:
        return "Unauthorized", 403

    # must have finished exam
    if not session.is_completed:
        return redirect(url_for("test.get_question", session_id=session.id))

    from app.models import Report
    from app.services.report_service import ReportService

    report = Report.query.filter_by(session_id=session.id).first()
    if report:
        return redirect(url_for("report.show_result", session_id=session.id))

    if request.method == "POST":
        report_mode = (request.form.get("report_mode") or "results").strip()
        goal_prompt = (request.form.get("goal_prompt") or "").strip()

        if report_mode == "goal" and not goal_prompt:
            flash("To generate a goal-based report, please enter your goal.", "danger")
            return redirect(request.url)

        goal_note = goal_prompt if report_mode == "goal" else None
        ReportService.generate_report(session, goal_note=goal_note)
        return redirect(url_for("report.show_result", session_id=session.id))

    return render_template("exam_report_options.html", session=session)


@test_bp.route("/exam/<int:session_id>/goal", methods=["GET", "POST"])
@login_required
def goal(session_id: int):
    session = TestSession.query.get_or_404(session_id)
    if session.user_id != current_user.id:
        return "Unauthorized", 403

    # must have finished exam
    if not session.is_completed:
        return redirect(url_for("test.get_question", session_id=session.id))

    from app.models import Report, CEFRLevel
    from app.services.report_service import ReportService

    report = Report.query.filter_by(session_id=session.id).first()

    if request.method == "POST":
        target_level_str = request.form.get("target_level")
        target_weeks = request.form.get("target_weeks", type=int)
        goal_note = (request.form.get("goal_note") or "").strip()

        target_level = None
        try:
            if target_level_str:
                target_level = CEFRLevel[target_level_str]
        except Exception:
            target_level = None

        # Goal is optional: allow "skip" submission with empty fields.
        if not target_level_str and not target_weeks and not goal_note:
            return redirect(url_for("report.show_result", session_id=session.id))

        # If user starts filling the goal, require both fields to keep data consistent.
        if not target_level:
            flash("Please select a target level.", "danger")
            return redirect(request.url)
        if not target_weeks or target_weeks < 1 or target_weeks > 104:
            flash("Please enter a target timeframe (weeks) between 1 and 104.", "danger")
            return redirect(request.url)

        if not report:
            report = ReportService.generate_report(
                session,
                target_level=target_level,
                target_weeks=target_weeks,
                goal_note=goal_note,
            )
        else:
            # update goal fields and regenerate learning plan async if needed
            report.target_level = target_level
            report.target_weeks = target_weeks
            report.goal_note = goal_note
            db.session.commit()
            ReportService.enrich_learning_plan_async(report.id)

        return redirect(url_for("report.show_result", session_id=session.id))

    # GET
    return render_template(
        "exam_goal.html",
        session=session,
        report=report,
        levels=["A1", "A2", "B1", "B2", "C1", "C2"],
    )

def _difficulty_candidates(target: CEFRLevel):
    order = [CEFRLevel.A1, CEFRLevel.A2, CEFRLevel.B1, CEFRLevel.B2, CEFRLevel.C1, CEFRLevel.C2]
    try:
        idx = order.index(target)
    except ValueError:
        idx = 0
    candidates = [order[idx]]
    for step in range(1, len(order)):
        lo = idx - step
        hi = idx + step
        if lo >= 0:
            candidates.append(order[lo])
        if hi < len(order):
            candidates.append(order[hi])
    return candidates

def _prefer_ai_questions() -> bool:
    return bool(current_app.config.get("PREFER_AI_QUESTIONS", True))

@test_bp.route("/start_exam")
@login_required
def start_exam():
    start_level_str = (current_app.config.get("DEFAULT_START_LEVEL") or "B2").upper()
    try:
        start_level = CEFRLevel[start_level_str]
    except Exception:
        start_level = CEFRLevel.B2

    session = TestSession(user_id=current_user.id, current_difficulty=start_level)
    db.session.add(session)
    db.session.commit()

    # Ensure listening pools are loaded from markdown/audio (idempotent)
    try:
        QuestionBankService.ensure_listening_pools()
    except Exception as e:
        current_app.logger.warning(f"Listening pool load failed: {e}")

    # Pre-generate questions for all non-listening modules so the exam can run offline.
    max_needed = max(
        (_questions_for_module(mod, session) for mod in MODULE_ORDER if mod != ModuleType.LISTENING),
        default=10,
    )
    min_pool = max_needed * 2
    for mod in MODULE_ORDER:
        # Listening uses pre-provided audio/questions; skip AI generation
        if mod == ModuleType.LISTENING:
            continue
        try:
            QuestionBankService.ensure_module_level_pool(
                module=mod,
                difficulty=start_level,
                min_count=min_pool,
            )
        except Exception as e:
            current_app.logger.warning(f"Pool prefill failed for {mod.value}: {e}")

    return redirect(url_for("test.get_question", session_id=session.id))


@test_bp.route("/exam/<int:session_id>/start_module", methods=["POST"])
@login_required
def start_module(session_id: int):
    session = TestSession.query.get_or_404(session_id)
    if session.user_id != current_user.id:
        return "Unauthorized", 403

    attempt = _get_or_create_attempt(session)
    if not attempt.started_at:
        # Pre-generate/ensure question pool in DB for this module+level.
        # This avoids calling AI on every next question.
        if session.current_module != ModuleType.LISTENING:
            try:
                QuestionBankService.ensure_module_level_pool(
                    module=session.current_module,
                    difficulty=session.current_difficulty,
                    min_count=_questions_for_module(session.current_module, session) * 2,
                )
            except Exception:
                # Don't block exam start if AI is unavailable
                pass
        attempt.started_at = datetime.utcnow()
        attempt.status = ModuleAttemptStatus.IN_PROGRESS
        db.session.commit()
    return redirect(url_for("test.get_question", session_id=session.id))


@test_bp.route("/exam/<int:session_id>/finish_module", methods=["POST"])
@login_required
def finish_module(session_id: int):
    session = TestSession.query.get_or_404(session_id)
    if session.user_id != current_user.id:
        return "Unauthorized", 403

    attempt = _get_or_create_attempt(session)
    attempt.ended_at = datetime.utcnow()
    attempt.status = ModuleAttemptStatus.COMPLETED
    db.session.commit()
    return _advance_module(session)


@test_bp.route("/exam/<int:session_id>", methods=["GET", "POST"])
@login_required
def get_question(session_id):
    session = TestSession.query.get_or_404(session_id)
    if session.user_id != current_user.id:
        return "Unauthorized", 403

    attempt = _get_or_create_attempt(session)

    # Timer enforcement
    remaining = _remaining_seconds(attempt)
    if remaining == 0 and attempt.started_at and attempt.status == ModuleAttemptStatus.IN_PROGRESS:
        attempt.ended_at = datetime.utcnow()
        attempt.status = ModuleAttemptStatus.EXPIRED
        db.session.commit()
        flash(f"{session.current_module.value} time is up. Moving to the next section.", "warning")
        return _advance_module(session)

    # --- POST: Handle answering ---
    if request.method == "POST":
        # Listening: handle block submit
        if session.current_module == ModuleType.LISTENING:
            return _handle_listening_block(session, attempt)

        action = request.form.get("action", "next")
        # allow navigation actions without answering
        if action == "prev":
            session.current_question_index = max(0, session.current_question_index - 1)
            db.session.commit()
            return redirect(url_for("test.get_question", session_id=session.id))

        question_id = request.form.get("question_id")
        user_answer = (request.form.get("option") or request.form.get("text_answer") or "").strip()
        audio_filename = request.form.get("audio_filename")

        question = Question.query.get(question_id)

        # Defensive check: question may have been deleted or missing
        if not question:
            flash("Question not found; moving to the next one.", "warning")
            return redirect(url_for("test.get_question", session_id=session.id))

        # If user clicked Next without answering, treat as unanswered and allow navigation.
        # For Speaking, require a transcript (from STT); for Writing, allow empty and warn user
        if not user_answer:
            if session.current_module == ModuleType.SPEAKING:
                # This shouldn't happen due to client-side validation, but defensive check
                current_app.logger.warning(f"Empty speaking answer submitted for session {session.id}")
                # Don't redirect - let the answer be processed as-is (NLPService will handle empty text)
                pass
            else:
                sq = SessionQuestion.query.filter_by(
                    session_id=session.id,
                    module=session.current_module,
                    question_index=session.current_question_index,
                ).first()
                if sq and sq.status != SessionQuestionStatus.ANSWERED:
                    sq.status = SessionQuestionStatus.SKIPPED
                    db.session.commit()

                total_q = _questions_for_module(session.current_module, session)
                session.current_question_index = min(total_q, session.current_question_index + 1)
                db.session.commit()
                return redirect(url_for("test.get_question", session_id=session.id))

        is_correct = False
        if session.current_module in (ModuleType.WRITING, ModuleType.SPEAKING):
            is_correct = NLPService.evaluate_open_ended(
                question.text, user_answer, session.current_difficulty.value
            )
        elif question.question_type == QuestionType.MULTIPLE_CHOICE:
            is_correct = user_answer == question.correct_answer
        else:
            is_correct = NLPService.evaluate_open_ended(
                question.text, user_answer, session.current_difficulty.value
            )

        # Upsert: if user navigates back and changes an answer, update the existing row instead of inserting duplicates
        resp = (
            Response.query.filter_by(session_id=session.id, question_id=question.id)
            .order_by(Response.id.desc())
            .first()
        )
        if not resp:
            resp = Response(session_id=session.id, question_id=question.id)
            db.session.add(resp)

        resp.selected_option = (
            None
            if session.current_module in (ModuleType.WRITING, ModuleType.SPEAKING)
            else (user_answer if question.question_type == QuestionType.MULTIPLE_CHOICE else None)
        )
        resp.text_answer = (
            user_answer
            if (session.current_module in (ModuleType.WRITING, ModuleType.SPEAKING) or question.question_type == QuestionType.OPEN_ENDED)
            else None
        )
        resp.is_correct = is_correct
        resp.audio_filename = audio_filename or resp.audio_filename
        resp.transcript = user_answer if session.current_module == ModuleType.SPEAKING else resp.transcript
        resp.stt_provider = "groq" if (audio_filename or resp.audio_filename) else None
        resp.stt_status = "ok" if (audio_filename or resp.audio_filename) else resp.stt_status

        sq = SessionQuestion.query.filter_by(
            session_id=session.id,
            module=session.current_module,
            question_index=session.current_question_index,
        ).first()
        if sq:
            sq.status = SessionQuestionStatus.ANSWERED
            sq.answered_at = datetime.utcnow()

        session.current_question_index += 1

        # Is the module finished?
        total_q = _questions_for_module(session.current_module, session)
        if session.current_question_index >= total_q:
            attempt.ended_at = datetime.utcnow()
            attempt.status = ModuleAttemptStatus.COMPLETED

        session.current_difficulty = AdaptiveService.calculate_next_level(session)
        db.session.commit()
        if session.current_question_index >= total_q:
            return redirect(url_for("test.get_question", session_id=session.id))
        return redirect(url_for("test.get_question", session_id=session.id))

    # --- GET: Fetch question ---
    if session.current_module == ModuleType.LISTENING:
        return _render_listening_block(session, attempt, remaining)

    # intro screen (per module) until started
    if not attempt.started_at:
        midx, mtotal = _module_position(session)
        return render_template(
            "exam_intro.html",
            session=session,
            attempt=attempt,
            time_limit_seconds=attempt.time_limit_seconds,
            module_index=midx,
            module_total=mtotal,
            overall_progress=_overall_progress_percent(session),
        )

    # navigation: allow jumping within already-generated questions for this module
    # IMPORTANT: must run BEFORE the review-screen check so the "return to skipped" buttons work.
    # (Disabled for Listening blocks to keep block navigation consistent)
    if session.current_module != ModuleType.LISTENING:
        req_i = request.args.get("i", type=int)
        total_q = _questions_for_module(session.current_module, session)
        if req_i is not None and 0 <= req_i < total_q:
            existing_sq = SessionQuestion.query.filter_by(
                session_id=session.id, module=session.current_module, question_index=req_i
            ).first()
            if existing_sq:
                session.current_question_index = req_i
                db.session.commit()

        # module end / review screen
        if session.current_question_index >= total_q:
            skipped = (
                SessionQuestion.query.filter_by(session_id=session.id, module=session.current_module)
                .filter(SessionQuestion.status == SessionQuestionStatus.SKIPPED)
                .order_by(SessionQuestion.question_index.asc())
                .all()
            )
            midx, mtotal = _module_position(session)
            return render_template(
                "exam_review.html",
                session=session,
                attempt=attempt,
                skipped=skipped,
                total=total_q,
                remaining_seconds=remaining,
                module_index=midx,
                module_total=mtotal,
                overall_progress=_overall_progress_percent(session),
            )

    # 1. Check the database first (is there an unsolved question?)
    sq = SessionQuestion.query.filter_by(
        session_id=session.id,
        module=session.current_module,
        question_index=session.current_question_index,
    ).first()

    # already generated for this index?
    if sq:
        new_q = sq.question
        # Reading: keep DB question in sync with file answer key (important if file was updated after session generation)
        if session.current_module == ModuleType.READING and new_q:
            try:
                _passage, file_questions = _load_reading_materials()
                if file_questions and 0 <= session.current_question_index < len(file_questions):
                    qdata = file_questions[session.current_question_index]
                    correct = (qdata.get("correct_answer") or "").strip().upper() if qdata.get("correct_answer") else None
                    if correct and correct in ("A", "B", "C", "D"):
                        changed = False
                        if (new_q.correct_answer or "") != correct:
                            new_q.correct_answer = correct
                            changed = True
                        options_json = (
                            json.dumps(qdata.get("options"))
                            if isinstance(qdata.get("options"), dict)
                            else None
                        )
                        if options_json and (new_q.options or "") != options_json:
                            new_q.options = options_json
                            changed = True
                        if changed:
                            db.session.commit()
            except Exception:
                # If sync fails for any reason, fall back to existing DB question.
                pass
    else:
        served_question_ids = db.session.query(SessionQuestion.question_id).filter(
            SessionQuestion.session_id == session.id
        )

        # Exam flow: DB-first (questions are pre-generated and stored).
        new_q = None
        existing_q = None
        base_query = Question.query.filter(
            Question.module == session.current_module,
            ~Question.id.in_(served_question_ids),
        )
        # Reading: use file-based questions in order
        if session.current_module == ModuleType.READING:
            passage, file_questions = _load_reading_materials()
            if file_questions and 0 <= session.current_question_index < len(file_questions):
                qdata = file_questions[session.current_question_index]
                new_q = _get_or_create_reading_question(qdata, session.current_difficulty)
                stored_passage = _get_reading_passage(session.id)
                if not stored_passage and passage:
                    _set_reading_passage(session.id, passage)
                if stored_passage or passage:
                    reading_passage = stored_passage or passage
                    reading_paragraphs = [p.strip() for p in reading_passage.split("\n\n") if p.strip()]
                reading_question = (qdata.get("text") or "").strip()
            # If file is missing or index out of range, fall back to DB selection below.
        # Writing/Speaking must not use MC questions
        if session.current_module in (ModuleType.WRITING, ModuleType.SPEAKING):
            base_query = base_query.filter(Question.question_type != QuestionType.MULTIPLE_CHOICE)

        if session.current_module == ModuleType.LISTENING:
            pool = _get_listening_pool(session.id)
            base_query = base_query.filter(Question.audio_url.ilike(f"%listeningaudio{pool}%"))
            existing_q = base_query.order_by(func.random()).first()
        else:
            for diff in _difficulty_candidates(session.current_difficulty):
                existing_q = base_query.filter(Question.difficulty == diff).order_by(func.random()).first()
                if existing_q:
                    break
            if not existing_q:
                existing_q = base_query.order_by(func.random()).first()
        if not new_q:
            new_q = existing_q

        # 3) Last-resort fallback: if AI is down and pool is exhausted, allow repeats instead of hard-failing.
        if not new_q:
            fallback_query = Question.query.filter(Question.module == session.current_module)
            if session.current_module in (ModuleType.WRITING, ModuleType.SPEAKING):
                fallback_query = fallback_query.filter(Question.question_type != QuestionType.MULTIPLE_CHOICE)
            if session.current_module == ModuleType.LISTENING:
                pool = _get_listening_pool(session.id)
                fallback_query = fallback_query.filter(Question.audio_url.ilike(f"%listeningaudio{pool}%"))
            repeat_any = fallback_query.order_by(func.random()).first()
            if repeat_any:
                new_q = repeat_any
                current_app.logger.warning(
                    "Question pool exhausted for module=%s; using repeat fallback. "
                    "Consider generating more questions or lowering per-section question counts.",
                    session.current_module.value,
                )

    if not new_q:
        # If a question cannot be retrieved (rare), avoid blocking the user: redirect to dashboard with an error.
        flash(
            "A connection issue occurred while generating a question. Please try again.", "danger"
        )
        return redirect(url_for("auth.dashboard"))

    # Force writing/speaking as open-ended (never MC)
    if session.current_module in (ModuleType.WRITING, ModuleType.SPEAKING):
        new_q.question_type = QuestionType.OPEN_ENDED
        new_q.options = None
        new_q.correct_answer = None

    question_text = None
    reading_passage = None
    reading_question = None
    reading_paragraphs = None
    if session.current_module == ModuleType.WRITING:
        question_text = _ensure_writing_word_range(getattr(new_q, "text", ""))
    if session.current_module == ModuleType.READING:
        passage, _file_questions = _load_reading_materials()
        stored_passage = _get_reading_passage(session.id)
        if not stored_passage and passage:
            _set_reading_passage(session.id, passage)
            stored_passage = passage
        reading_passage = stored_passage or passage
        reading_question = getattr(new_q, "text", "") or ""
        reading_paragraphs = [p.strip() for p in (reading_passage or "").split("\n\n") if p.strip()]

    # persist question for navigation within this module
    if not sq:
        sq = SessionQuestion(
            session_id=session.id,
            module=session.current_module,
            question_index=session.current_question_index,
            question_id=new_q.id,
            status=SessionQuestionStatus.SERVED,
        )
        db.session.add(sq)
        db.session.commit()

    # Options to send to the template
    options_dict = None
    if session.current_module not in (ModuleType.WRITING, ModuleType.SPEAKING) and new_q.options:
        try:
            options_dict = (
                json.loads(new_q.options)
                if isinstance(new_q.options, str)
                else new_q.options
            )
        except:
            pass

    existing_response = (
        Response.query.filter_by(session_id=session.id, question_id=new_q.id)
        .order_by(Response.id.desc())
        .first()
    )

    return render_template(
        "exam.html",
        question=new_q,
        question_text=question_text,
        options=options_dict,
        session=session,
        index=session.current_question_index + 1,
        total=_questions_for_module(session.current_module, session),
        remaining_seconds=remaining,
        attempt=attempt,
        speaking_prep_seconds=current_app.config.get("SPEAKING_PREP_SECONDS", 20),
        speaking_response_seconds=current_app.config.get("SPEAKING_RESPONSE_SECONDS", 60),
        sq=sq,
        existing_response=existing_response,
        module_index=_module_position(session)[0],
        module_total=_module_position(session)[1],
        overall_progress=_overall_progress_percent(session),
        reading_passage=reading_passage,
        reading_question=reading_question,
        reading_paragraphs=reading_paragraphs,
    )
