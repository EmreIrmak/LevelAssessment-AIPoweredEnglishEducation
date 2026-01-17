import os
from groq import Groq
from flask import current_app
import json
import re
import math
from collections import Counter


class NLPService:
    _client = None
    _client_key = None
    # Example guidance (from user-provided samples)
    GRAMMAR_EXAMPLES = (
        "Good evening and welcome to News Channel. I’m Jake Purple bringing you the latest news stories of the day. "
        "The most well-known museum of Istanbul, Topkapi Palace, has been robbed. The shocking robbery, (16) ____ occurred late last night...\n"
        "16. a) that  b) when  c) which  d) where\n"
        "17. a) had stolen  b) steal  c) have stolen  d) was stealing\n"
        "18. a) preserve  b) preserved  c) preserving  d) to preserve"
    )

    VOCAB_EXAMPLES = (
        "Jenny will stay in hospital for more ten days, so her parents are afraid she will ____ with her classes.\n"
        "a) pick up  b) fall behind  c) call back  d) get along\n"
        "Sally talks behind people’s backs and these days she is ____ gossip about Tom and Laura.\n"
        "a) talking  b) cheating  c) spreading  d) giving\n"
        "If people ____ with each other, they talk to each other and work together etc.\n"
        "a) concentrate  b) prohibit  c) interact  d) attack\n"
        "I haven’t seen my friend in a long time, so we are planning to meet up this weekend to ____ on each other’s lives.\n"
        "a) copy in  b) call back  c) catch up  d) fill in"
    )

    READING_EXAMPLE = (
        "As the people we interact with become more diverse, code switching becomes more common in everyday conversation...\n"
        "[4–5 paragraphs, ~400–500 words]\n"
        "Questions sample: title, inference, reference, vocabulary in context, main idea"
    )

    WRITING_EXAMPLES = (
        "Some people believe that students should be required to take classes outside their major field of study...\n"
        "Which view do you agree with? Use specific reasons and examples to support your answer.\n"
        "Some people think that living in a big city offers more advantages, while others believe that living in a small town is better...\n"
        "Which do you prefer? Explain your choice with reasons and examples."
    )

    SPEAKING_EXAMPLES = (
        "Do you think universities should require students to attend classes, or should attendance be optional?\n"
        "Support your answer with reasons and examples.\n"
        "Describe a challenge you have faced in your life. Explain how you dealt with it and what you learned."
    )
    @staticmethod
    def _get_client():
        api_key = current_app.config.get("GROQ_API_KEY")
        if not api_key:
            # If this is None, no Groq calls will happen (usage will stay at 0)
            current_app.logger.warning("GROQ_API_KEY is missing; Groq client not initialized.")
            return None
        if NLPService._client and NLPService._client_key == api_key:
            return NLPService._client
        NLPService._client_key = api_key
        NLPService._client = Groq(api_key=api_key)
        return NLPService._client

    @staticmethod
    def _ai_enabled() -> bool:
        return bool(current_app.config.get("PREFER_AI_QUESTIONS", True))

    @staticmethod
    def generate_adaptive_question(module, difficulty):
        if not NLPService._ai_enabled():
            return None
        client = NLPService._get_client()
        if not client:
            return None

        # ETS-style high-stakes diagnostic prompt (JSON-only output)
        system_prompt = """
You are a Senior Assessment Developer for ETS (creators of TOEFL).
Your ONLY job is to output valid JSON. Do NOT write explanations. Do NOT write code blocks.
        """.strip()

        module_instructions = module
        if module == "Listening":
            module_instructions = (
                "Listening (Provide an academic mini-lecture transcript inside the question stem. "
                "Start the stem with 'Audio Script:' and then ask a comprehension question.)"
            )
        elif module == "Speaking":
            module_instructions = (
                "Speaking (Provide an academic speaking prompt; the student will respond orally. "
                "Ask for an organized response with examples.)"
            )
        elif module == "Writing":
            module_instructions = (
                "Writing (Provide an academic short essay prompt. Require 150–200 words. Require a clear thesis and at least 2 supporting points.)"
            )

        user_prompt = f"""
ROLE: You are a Senior Assessment Developer for ETS (creators of TOEFL). Your task is to write high-stakes diagnostic questions.

TASK: Create 1 question for the module below at CEFR level {difficulty}. Avoid trivial/A1-style items; require reasoning or nuanced understanding suitable for the stated level.
Module: {module_instructions}

CRITICAL DESIGN RULES:
1) Academic Tone: Use formal, university-level English. Avoid conversational slang.
2) Distractor Quality (MOST IMPORTANT): Wrong options must be plausible to a lower-level student, grammatically consistent, and clearly incorrect to a proficient reader based on logic/nuance. Avoid easy fillers (e.g., 'None of the above') and avoid obviously wrong cues.
3) Difficulty: Require reasoning/nuance; avoid keyword matching. Do NOT use simplistic vocabulary/grammar; the item should feel like a B2+ academic task when difficulty is B2 or higher.

OUTPUT REQUIREMENTS:
- Output ONLY valid JSON.
- For MULTIPLE_CHOICE: provide 4 options A-D and a single correct_answer letter.
- For OPEN_ENDED: set options to null and correct_answer to null.

REQUIRED JSON FORMAT:
{{
  "text": "Question stem...",
  "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}}, 
  "correct_answer": "A",
  "question_type": "MULTIPLE_CHOICE" 
}}
        """.strip()

        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model="llama-3.3-70b-versatile",  # Groq fast model
                temperature=0.3,
            )

            response_content = chat_completion.choices[0].message.content.strip()

            # Sometimes the model wraps output in ```json fences; strip them
            if "```" in response_content:
                response_content = re.sub(r"```json\s*|\s*```", "", response_content)

            # Clean JSON (the model may append extra text; keep only the { ... } block)
            json_match = re.search(r"\{.*\}", response_content, re.DOTALL)
            if json_match:
                response_content = json_match.group(0)

            parsed = json.loads(response_content)

            # Hard rule: Writing must be OPEN_ENDED (no options, no correct_answer)
            if module == "Writing":
                parsed["question_type"] = "OPEN_ENDED"
                parsed["options"] = None
                parsed["correct_answer"] = None

            return parsed

        except Exception as e:
            print(f"Groq API Error: {e}")
            return None

    @staticmethod
    def generate_10_mcq_for_module(module: str, difficulty: str = "B2"):
        """
        Creates 10 multiple-choice questions for a single module using the requested ETS prompt.
        Returns a list[dict] with items in the same JSON schema as generate_adaptive_question.
        """
        if not NLPService._ai_enabled():
            return []
        client = NLPService._get_client()
        if not client:
            return []

        system_prompt = """
You are a Senior Assessment Developer for ETS (creators of TOEFL).
Your ONLY job is to output valid JSON. Do NOT write explanations. Do NOT write code blocks.
        """.strip()

        user_prompt = f"""
ROLE: You are a Senior Assessment Developer for ETS (creators of TOEFL). Your task is to write high-stakes diagnostic questions.

TASK: Create 10 multiple-choice questions for the module "{module}" at averagely {difficulty} CEFR proficiency level.

CRITICAL DESIGN RULES:
1) Academic Tone: Use formal, university-level English. Avoid conversational slang.
2) Distractor Quality (MOST IMPORTANT): The wrong options (distractors) must be:
   - Plausible to a lower-level student.
   - Grammatically consistent with the stem.
   - Clearly incorrect to a native or proficient speaker based on logic or nuance.
   - AVOID easy fillers like "None of the above".
3) Difficulty: Since the level is {difficulty}, the question should require critical thinking, not just keyword matching.

OUTPUT REQUIREMENTS:
- Output ONLY valid JSON.
- Output a JSON array of exactly 10 items.
- Each item must match this schema:
  {{
    "text": "Question stem...",
    "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
    "correct_answer": "A",
    "question_type": "MULTIPLE_CHOICE"
  }}
        """.strip()

        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.4,
            )

            response_content = chat_completion.choices[0].message.content.strip()
            if "```" in response_content:
                response_content = re.sub(r"```json\s*|\s*```", "", response_content)

            json_match = re.search(r"\[.*\]", response_content, re.DOTALL)
            if json_match:
                response_content = json_match.group(0)

            data = json.loads(response_content)
            if isinstance(data, list):
                # Best-effort filter to valid items
                out = []
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    if not item.get("text"):
                        continue
                    if not isinstance(item.get("options"), dict):
                        continue
                    if item.get("question_type") != "MULTIPLE_CHOICE":
                        item["question_type"] = "MULTIPLE_CHOICE"
                    out.append(item)
                return out[:10]
            return []
        except Exception as e:
            print(f"Groq API Error: {e}")
            return []

    @staticmethod
    def generate_writing_set(count: int = 5, difficulty: str = "B2"):
        """
        Generates open-ended writing prompts; always OPEN_ENDED (options null, correct_answer null).
        """
        return NLPService.generate_example_guided_open_ended(
            module="Writing",
            difficulty=difficulty,
            count=max(1, count),
            examples=NLPService.WRITING_EXAMPLES,
        )

    @staticmethod
    def generate_speaking_set(count: int = 5, difficulty: str = "B2") -> list[dict]:
        """
        Generates speaking prompts similar in style/level to provided examples.
        """
        return NLPService.generate_example_guided_open_ended(
            module="Speaking",
            difficulty=difficulty,
            count=max(1, count),
            examples=NLPService.SPEAKING_EXAMPLES,
        )

    @staticmethod
    def generate_example_guided_open_ended(module: str, difficulty: str, count: int, examples: str) -> list[dict]:
        if not NLPService._ai_enabled():
            return []
        client = NLPService._get_client()
        if not client:
            return []

        system_prompt = "You are an expert English assessment writer. Output ONLY valid JSON."
        user_prompt = f"""
Use the examples below ONLY as style/level guidance (vocabulary, tone, length). Create NEW prompts.

Examples:
{examples}

Task:
- Module: {module}
- Difficulty: {difficulty}
- Count: {count}
- Output short, clear prompts similar in style to the examples.

Output JSON array of objects with keys: text
Example:
[{{"text":"..."}}]
""".strip()

        try:
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.4,
                max_tokens=800,
            )
            content = resp.choices[0].message.content if resp and resp.choices else ""
            if not content:
                return []

            data = NLPService._safe_json_load(content)
            out = []
            for item in data[:count]:
                text = (item.get("text") or "").strip()
                if not text:
                    continue
                out.append(
                    {
                        "text": text,
                        "options": None,
                        "correct_answer": None,
                        "question_type": "OPEN_ENDED",
                    }
                )
            return out
        except Exception:
            return []

    @staticmethod
    def generate_example_guided_mcq(module: str, difficulty: str, count: int, examples: str) -> list[dict]:
        if not NLPService._ai_enabled():
            return []
        client = NLPService._get_client()
        if not client:
            return []

        system_prompt = "You are an expert English assessment writer. Output ONLY valid JSON."
        style_note = "Use fill-in-the-blank (____) sentence completion style." if module in ("Grammar", "Vocabulary") else ""

        user_prompt = f"""
Use the examples below ONLY as style/level guidance (vocabulary, tone, length). Create NEW questions.

Examples:
{examples}

Task:
- Module: {module}
- Difficulty: {difficulty}
- Count: {count}
- Provide balanced, not-too-easy MCQs with 4 options and exactly 1 correct answer.
    - {style_note}

Output JSON array of objects with keys:
question (string), options (object A-D), correct_answer ("A"|"B"|"C"|"D")
""".strip()

        try:
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.4,
                max_tokens=1200,
            )

            content = resp.choices[0].message.content if resp and resp.choices else ""
            if not content:
                return []

            data = NLPService._safe_json_load(content)
            out = []
            for item in data[:count]:
                q_text = (item.get("question") or "").strip()
                opts = item.get("options") or {}
                ans = (item.get("correct_answer") or "").strip().upper()
                if not q_text or not isinstance(opts, dict) or ans not in ["A", "B", "C", "D"]:
                    continue
                if module == "Vocabulary" and "____" not in q_text:
                    continue
                out.append(
                    {
                        "text": q_text,
                        "options": opts,
                        "correct_answer": ans,
                        "question_type": "MULTIPLE_CHOICE",
                    }
                )
            return out
        except Exception:
            return []

    @staticmethod
    def _safe_json_load(s: str):
        try:
            return json.loads(s)
        except Exception:
            match = re.search(r"\{[\s\S]*\}", s)
            if match:
                return json.loads(match.group(0))
            match = re.search(r"\[[\s\S]*\]", s)
            if match:
                return json.loads(match.group(0))
            raise

    @staticmethod
    def generate_reading_set(count: int = 5, difficulty: str = "B2") -> list[dict]:
        """
        Generate a single 400–500 word reading passage (4–5 paragraphs) plus N MCQ questions.
        Each question will be returned as a dict with text/options/correct_answer.
        """
        if not NLPService._ai_enabled():
            return []
        client = NLPService._get_client()
        if not client:
            return []

        example_text = NLPService.READING_EXAMPLE

        system_prompt = (
            "You are an expert English assessment writer. Output ONLY valid JSON. No code fences."
        )

        user_prompt = f"""
Use the following example only as a STYLE reference (vocabulary level, length, paragraphing), not for content reuse:
{example_text}

Task: Create a NEW reading passage (400–500 words) in 4–5 paragraphs on a DIFFERENT topic.
Difficulty: {difficulty}. Avoid being too easy or too hard. Keep natural academic tone.

Then create {count} multiple-choice questions about the passage. Questions should be balanced and logical.
Each question must have 4 options (A-D) and one correct answer.

Output JSON with this schema:
{{
  "passage": "...4-5 paragraphs...",
  "questions": [
    {{"question": "...", "options": {{"A":"...","B":"...","C":"...","D":"..."}}, "correct_answer": "A"}}
  ]
}}
""".strip()

        try:
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.4,
                max_tokens=1500,
            )

            content = resp.choices[0].message.content if resp and resp.choices else ""
            if not content:
                return []

            def _safe_json_load(s: str) -> dict:
                try:
                    return json.loads(s)
                except Exception:
                    match = re.search(r"\{[\s\S]*\}", s)
                    if match:
                        return json.loads(match.group(0))
                    raise

            data = _safe_json_load(content)
            passage = (data.get("passage") or "").strip()
            questions = data.get("questions") or []

            if not passage or not isinstance(questions, list):
                return []

            out = []
            for q in questions[:max(1, count)]:
                q_text = (q.get("question") or "").strip()
                opts = q.get("options") or {}
                ans = (q.get("correct_answer") or "").strip().upper()
                if not q_text or not isinstance(opts, dict) or ans not in ["A", "B", "C", "D"]:
                    continue

                full_text = f"READING:\n{passage}\n\nQuestion: {q_text}"
                out.append(
                    {
                        "text": full_text,
                        "options": opts,
                        "correct_answer": ans,
                        "question_type": "MULTIPLE_CHOICE",
                    }
                )

            return out
        except Exception:
            return []

    @staticmethod
    def analyze_writing_response(text: str, prompt: str | None = None) -> dict:
        """
        Lightweight NLP analysis for writing responses.
        Returns a dict with sentence count, word count, TF-IDF similarity (if prompt provided),
        keyword coverage, and tense distribution.
        """
        raw = (text or "").strip()
        prompt_text = (prompt or "").strip()

        if not raw:
            return {
                "word_count": 0,
                "sentence_count": 0,
                "avg_sentence_len": 0,
                "tfidf_similarity": 0.0,
                "top_keywords": [],
                "tense": "unknown",
                "tense_distribution": {"past": 0, "present": 0, "future": 0},
                "warnings": ["Answer is empty."],
            }

        # Basic sentence and word metrics
        sentences = [s.strip() for s in re.split(r"[.!?]+", raw) if s.strip()]
        sentence_count = len(sentences)

        words = re.findall(r"[A-Za-z']+", raw.lower())
        word_count = len(words)
        avg_sentence_len = int(round(word_count / max(1, sentence_count)))

        # Minimal stopwords (avoid heavy dependencies)
        stopwords = {
            "the", "a", "an", "and", "or", "but", "if", "is", "are", "was", "were", "am",
            "to", "of", "in", "on", "for", "with", "as", "at", "by", "from", "this", "that",
            "these", "those", "it", "its", "be", "been", "being", "i", "you", "he", "she",
            "we", "they", "them", "my", "your", "our", "their", "me", "him", "her", "us",
            "do", "does", "did", "have", "has", "had", "will", "would", "can", "could", "should",
        }

        # TF-IDF (prompt vs response) with a small corpus of 2 docs
        def _tokenize(doc: str) -> list[str]:
            toks = re.findall(r"[A-Za-z']+", (doc or "").lower())
            return [t for t in toks if t and t not in stopwords]

        response_tokens = _tokenize(raw)
        prompt_tokens = _tokenize(prompt_text) if prompt_text else []

        def _tf(tokens: list[str]) -> Counter:
            return Counter(tokens)

        def _tfidf_vector(tokens: list[str], idf: dict) -> dict:
            tf = _tf(tokens)
            if not tf:
                return {}
            max_tf = max(tf.values())
            vec = {}
            for term, freq in tf.items():
                vec[term] = (freq / max_tf) * idf.get(term, 0.0)
            return vec

        # Compute IDF across prompt+response
        corpus = [response_tokens, prompt_tokens] if prompt_tokens else [response_tokens]
        df = Counter()
        for doc in corpus:
            for term in set(doc):
                df[term] += 1
        N = len(corpus)
        idf = {term: math.log((N + 1) / (df_val + 1)) + 1 for term, df_val in df.items()}

        resp_vec = _tfidf_vector(response_tokens, idf)
        prompt_vec = _tfidf_vector(prompt_tokens, idf) if prompt_tokens else {}

        def _cosine(a: dict, b: dict) -> float:
            if not a or not b:
                return 0.0
            # dot product
            dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in set(a) | set(b))
            norm_a = math.sqrt(sum(v * v for v in a.values()))
            norm_b = math.sqrt(sum(v * v for v in b.values()))
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot / (norm_a * norm_b)

        tfidf_similarity = _cosine(resp_vec, prompt_vec) if prompt_tokens else 0.0

        # Top keywords by TF-IDF in response
        top_keywords = sorted(resp_vec.items(), key=lambda x: x[1], reverse=True)[:6]
        top_keywords = [k for k, _ in top_keywords]

        # Tense heuristic checks
        past_markers = re.findall(r"\b(was|were|had|did|went|said|made|took|saw|came|got|gave|used)\b", raw.lower())
        past_ed = re.findall(r"\b\w+ed\b", raw.lower())
        present_markers = re.findall(r"\b(is|am|are|do|does|have|has|go|goes|think|know|like)\b", raw.lower())
        future_markers = re.findall(r"\b(will|shall|going\s+to)\b", raw.lower())

        past_count = len(past_markers) + len(past_ed)
        present_count = len(present_markers)
        future_count = len(future_markers)

        tense_distribution = {
            "past": past_count,
            "present": present_count,
            "future": future_count,
        }

        if max(past_count, present_count, future_count) == 0:
            tense = "unknown"
        else:
            if past_count > present_count and past_count > future_count:
                tense = "past"
            elif present_count > past_count and present_count > future_count:
                tense = "present"
            elif future_count > past_count and future_count > present_count:
                tense = "future"
            else:
                tense = "mixed"

        warnings = []
        if word_count < 80:
            warnings.append(f"Answer is short ({word_count} words).")
        if sentence_count < 2:
            warnings.append("Very few sentences; consider adding structure (intro–body–conclusion).")
        if prompt_tokens and tfidf_similarity < 0.1:
            warnings.append("Low relevance to the prompt (topic drift possible).")

        return {
            "word_count": word_count,
            "sentence_count": sentence_count,
            "avg_sentence_len": avg_sentence_len,
            "tfidf_similarity": round(tfidf_similarity, 3),
            "top_keywords": top_keywords,
            "tense": tense,
            "tense_distribution": tense_distribution,
            "warnings": warnings,
        }

    @staticmethod
    def format_writing_analysis(analysis: dict) -> str:
        """Convert analysis dict to a readable string for UI."""
        if not analysis:
            return ""

        parts = []
        parts.append(
            f"Words: {analysis.get('word_count', 0)} | Sentences: {analysis.get('sentence_count', 0)} | "
            f"Avg sentence length: {analysis.get('avg_sentence_len', 0)}"
        )

        if analysis.get("tfidf_similarity", 0) and analysis.get("tfidf_similarity") > 0:
            parts.append(f"Topic relevance (TF-IDF): {analysis.get('tfidf_similarity')}")

        if analysis.get("top_keywords"):
            parts.append(f"Top keywords: {', '.join(analysis.get('top_keywords'))}")

        tense = analysis.get("tense", "unknown")
        if tense:
            parts.append(f"Dominant tense: {tense}")

        if analysis.get("warnings"):
            parts.append("Warnings: " + " ".join(analysis.get("warnings")))

        return "<ul><li>" + "</li><li>".join(parts) + "</li></ul>"

    @staticmethod
    def analyze_writing_response_ai(text: str, prompt: str | None = None) -> dict:
        """
        AI-assisted writing analysis using Groq. Returns same schema as analyze_writing_response.
        Falls back to local analysis when AI is unavailable or fails.
        """
        raw = (text or "").strip()
        prompt_text = (prompt or "").strip()

        # Always provide a local fallback for resilience
        fallback = NLPService.analyze_writing_response(text=raw, prompt=prompt_text)

        # Skip AI analysis for very short answers to reduce calls
        if len(raw.split()) < 15:
            return fallback

        if not NLPService._ai_enabled():
            return fallback
        client = NLPService._get_client()
        if not client:
            return fallback

        if not raw:
            return fallback

        system_prompt = (
            "You are a strict NLP analysis engine. Output ONLY valid JSON."
        )

        user_prompt = f"""
Analyze the student's writing and output JSON with these keys ONLY:
tfidf_similarity (number 0..1), sentence_count (int), avg_sentence_len (int), tense ("past"|"present"|"future"|"mixed"|"unknown"), tense_distribution (object with past/present/future ints), warnings (array of strings), top_keywords (array of up to 6 strings), word_count (int).

Rules:
- tfidf_similarity should reflect topic relevance between prompt and response.
- sentence_count: split by . ! ?
- avg_sentence_len: word_count / max(1, sentence_count), rounded to int.
- tense_distribution: count obvious tense markers; if unclear set all 0 and tense "unknown".
- warnings: include issues like short length, very few sentences, low relevance.

Prompt:
{prompt_text}

Response:
{raw}
""".strip()

        try:
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=300,
            )

            content = resp.choices[0].message.content if resp and resp.choices else ""
            if not content:
                return fallback

            data = json.loads(content)

            # Basic schema safeguards
            data.setdefault("word_count", fallback.get("word_count", 0))
            data.setdefault("sentence_count", fallback.get("sentence_count", 0))
            data.setdefault("avg_sentence_len", fallback.get("avg_sentence_len", 0))
            data.setdefault("tfidf_similarity", fallback.get("tfidf_similarity", 0.0))
            data.setdefault("top_keywords", fallback.get("top_keywords", []))
            data.setdefault("tense", fallback.get("tense", "unknown"))
            data.setdefault("tense_distribution", fallback.get("tense_distribution", {"past": 0, "present": 0, "future": 0}))
            data.setdefault("warnings", fallback.get("warnings", []))

            return data
        except Exception:
            return fallback

    @staticmethod
    def analyze_speaking_response_ai(transcript: str, prompt: str | None = None) -> dict:
        """
        AI-assisted speaking analysis based on transcript and prompt.
        Returns dict with summary, strengths, improvements, score_suggestion, and warnings.
        """
        raw = (transcript or "").strip()
        prompt_text = (prompt or "").strip()

        if not raw:
            return {
                "summary": "No transcript available.",
                "strengths": [],
                "improvements": ["Provide a spoken response to receive feedback."],
                "score_suggestion": None,
                "warnings": ["Speech-to-text transcript is empty."],
            }

        # Skip AI analysis for very short transcripts to reduce calls
        if len(raw.split()) < 6:
            return {
                "summary": "Transcript is too short for reliable analysis.",
                "strengths": [],
                "improvements": ["Provide a longer response to receive feedback."],
                "score_suggestion": None,
                "warnings": ["Transcript too short."],
            }

        if not NLPService._ai_enabled():
            return {
                "summary": "AI feedback unavailable (missing API key).",
                "strengths": [],
                "improvements": ["Try again later or enable AI feedback."],
                "score_suggestion": None,
                "warnings": ["AI feedback disabled."],
            }
        client = NLPService._get_client()
        if not client:
            return {
                "summary": "AI feedback unavailable (missing API key).",
                "strengths": [],
                "improvements": ["Try again later or enable AI feedback."],
                "score_suggestion": None,
                "warnings": ["GROQ_API_KEY is missing."],
            }

        system_prompt = "You are a speaking assessment assistant. Output ONLY valid JSON. No code fences. Use list-style phrasing in arrays."
        user_prompt = f"""
Evaluate the student's spoken response using the transcript. Output JSON with keys:
summary (string), strengths (array of strings), improvements (array of strings), score_suggestion (0-100 number or null), warnings (array of strings).

Consider: coherence, vocabulary range, grammar accuracy, fluency indicators from text (filler, repetition), relevance to prompt.
If transcript seems too short or off-topic, add warnings.

Prompt:
{prompt_text}

Transcript:
{raw}
""".strip()

        try:
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=350,
            )

            content = resp.choices[0].message.content if resp and resp.choices else ""
            if not content:
                raise ValueError("Empty AI response")

            def _safe_json_load(s: str) -> dict:
                try:
                    return json.loads(s)
                except Exception:
                    # Try to extract JSON object from the response
                    match = re.search(r"\{[\s\S]*\}", s)
                    if match:
                        return json.loads(match.group(0))
                    raise

            data = _safe_json_load(content)
            data.setdefault("summary", "")
            data.setdefault("strengths", [])
            data.setdefault("improvements", [])
            data.setdefault("score_suggestion", None)
            data.setdefault("warnings", [])
            return data
        except Exception:
            return {
                "summary": "AI feedback could not be generated.",
                "strengths": [],
                "improvements": ["Please try again later."],
                "score_suggestion": None,
                "warnings": ["AI feedback error."],
            }

    @staticmethod
    def format_speaking_analysis(analysis: dict) -> str:
        if not analysis:
            return ""
        parts = []
        if analysis.get("summary"):
            parts.append(f"Summary: {analysis.get('summary')}")
        if analysis.get("strengths"):
            parts.append("Strengths: " + "; ".join(analysis.get("strengths")))
        if analysis.get("improvements"):
            parts.append("Improvements: " + "; ".join(analysis.get("improvements")))
        if analysis.get("score_suggestion") is not None:
            parts.append(f"Suggested score: {analysis.get('score_suggestion')}")
        if analysis.get("warnings"):
            parts.append("Warnings: " + " ".join(analysis.get("warnings")))
        return "<ul><li>" + "</li><li>".join(parts) + "</li></ul>"

    @staticmethod
    def generate_question_bank(modules, difficulty="B2", count_per_module=10):
        """
        Generate a question bank using the requested ETS prompt.
        Returns: { "Grammar": [q,...], ... }
        """
        bank = {}
        for m in modules:
            # Writing must always be open-ended
            if m.lower() == "writing":
                bank[m] = NLPService.generate_writing_set(count=count_per_module, difficulty=difficulty)
                continue

            if int(count_per_module) == 10:
                bank[m] = NLPService.generate_10_mcq_for_module(m, difficulty=difficulty)
            else:
                # fallback: generate one-by-one
                items = []
                for _ in range(count_per_module):
                    q = NLPService.generate_adaptive_question(m, difficulty)
                    if q:
                        items.append(q)
                bank[m] = items
        return bank

    @staticmethod
    def evaluate_open_ended(question_text, user_answer, current_level):
        if not NLPService._ai_enabled():
            return True
        client = NLPService._get_client()
        if not client:
            return True

        system_prompt = (
            'You are an expert English teacher and CEFR evaluator. '
            'Evaluate using contemporary standard English usage (2020s), focusing on communicative adequacy, '
            'clarity, coherence, and appropriate vocabulary/grammar for the target CEFR level. '
            'Be reasonably tolerant of minor mistakes that do not impede meaning. '
            'Output ONLY valid JSON: {"passed": true} or {"passed": false}.'
        )

        user_prompt = f"""
        Question: {question_text}
        Student Answer: {user_answer}
        Target Level: {current_level}
        
        Is this answer acceptable for the target level in contemporary English?
        """

        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model="llama3-8b-8192",
                temperature=0.1,
            )

            text = chat_completion.choices[0].message.content.strip()
            # Clean JSON: extract only the JSON object from the response
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                text = json_match.group(0)

            parsed = json.loads(text)
            return parsed.get("passed", False)
        except Exception as e:
            current_app.logger.error(f"Error evaluating open-ended response for '{question_text[:50]}...': {e}")
            # Default to True (pass) if evaluation fails, to be lenient
            return True
