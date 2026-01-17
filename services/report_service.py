from app.extensions import db
# Imported Question and Response models here 👇
from app.models import Report, ModuleType, CEFRLevel, Question, Response, ReportStatus, SessionQuestion
from app.services.nlp_service import NLPService
import json
from flask import current_app
from threading import Thread
from datetime import date, datetime, timedelta
from html import escape
import re

class ReportService:
    @staticmethod
    def _level_from_percentage(score: float) -> CEFRLevel:
        # Simple, stable mapping to avoid anomalies (e.g., 54% -> B1 not C2)
        if score < 40:
            return CEFRLevel.A1
        if score < 50:
            return CEFRLevel.A2
        if score < 60:
            return CEFRLevel.B1
        if score < 70:
            return CEFRLevel.B2
        if score < 80:
            return CEFRLevel.C1
        return CEFRLevel.C2

    @staticmethod
    def generate_report(session, target_level=None, target_weeks=None, goal_note=None):
        # 1. Compute overall statistics (served total: unanswered lowers score)
        total_served = SessionQuestion.query.filter_by(session_id=session.id).count()
        correct_answers = session.responses.filter(Response.is_correct == True).count()
        score_percentage = (correct_answers / total_served * 100) if total_served > 0 else 0
        
        # 2. Module-level statistics
        module_stats = {}
        for module in ModuleType:
            # Logic: take this session's responses -> join Question -> filter by module
            base_query = session.responses.join(Question).filter(Question.module == module)
            
            m_total = base_query.count()
            m_correct = base_query.filter(Response.is_correct == True).count()
            
            if m_total > 0:
                module_stats[module.value] = round((m_correct / m_total) * 100, 1)
            else:
                module_stats[module.value] = 0

        # 3. Determine final level (score-based, stable)
        level_result = ReportService._level_from_percentage(score_percentage)
        final_level = level_result.value
        module_stats_json = json.dumps(module_stats)

        # 4. Request an AI roadmap
        client = NLPService._get_client()
        if client:
            ai_feedback = (
                "<p><strong>Your AI report is being prepared...</strong></p>"
                "<p class='text-muted'>This usually takes a few seconds. The page will refresh automatically.</p>"
            )
            status = ReportStatus.ENRICHING
        else:
            ai_feedback = "AI service is currently unavailable."
            status = ReportStatus.READY

        # 5. Save to the database
        report = Report(
            session_id=session.id,
            score=score_percentage,
            level_result=level_result,
            ai_feedback=ai_feedback,
            status=status,
            target_level=target_level,
            target_weeks=target_weeks,
            goal_note=goal_note,
            module_stats_json=module_stats_json,
        )
        db.session.add(report)
        db.session.commit()

        # Async enrichment (non-blocking) to keep report generation fast (<10s)
        if status == ReportStatus.ENRICHING:
            app = current_app._get_current_object()

            def _task():
                with app.app_context():
                    r = Report.query.get(report.id)
                    if not r:
                        return
                    try:
                        feedback = ReportService._get_ai_roadmap(
                            final_level,
                            module_stats,
                            score_percentage,
                            goal_note=r.goal_note,
                            target_weeks=r.target_weeks,
                        )
                        r.ai_feedback = feedback
                        # Learning plan removed - using static plan in template
                        r.learning_plan = None
                        r.learning_plan_error = None
                        r.status = ReportStatus.READY
                        r.ai_error = None
                    except Exception as e:
                        r.status = ReportStatus.FAILED
                        r.ai_error = str(e)
                    db.session.commit()

            Thread(target=_task, daemon=True).start()
        
        return report

    @staticmethod
    def enrich_learning_plan_async(report_id: int):
        """
        Re-generate learning plan asynchronously (used when goal is submitted after a report already exists).
        """
        # Learning plan generation disabled - using static template plan
        app = current_app._get_current_object()
        def _task():
            with app.app_context():
                r = Report.query.get(report_id)
                if not r:
                    return
                r.learning_plan = None
                r.learning_plan_error = None
                db.session.commit()
        Thread(target=_task, daemon=True).start()

    @staticmethod
    def _render_calendar_roadmap_html(data: dict, *, start_date: date, days_count: int) -> str:
        title = escape(str(data.get("title") or "Personalized Study Roadmap"))
        summary = escape(str(data.get("summary") or ""))
        strengths = data.get("strengths") if isinstance(data.get("strengths"), list) else []
        weaknesses = data.get("weaknesses") if isinstance(data.get("weaknesses"), list) else []

        calendar = data.get("calendar") if isinstance(data.get("calendar"), dict) else {}
        days = calendar.get("days") if isinstance(calendar.get("days"), list) else []
        items_by_date: dict[str, list] = {}
        for d in days:
            if not isinstance(d, dict):
                continue
            ds = d.get("date")
            if not isinstance(ds, str):
                continue
            items = d.get("items") if isinstance(d.get("items"), list) else []
            items_by_date[ds] = items

        weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        weeks = max(1, days_count // 7)
        end_date = start_date + timedelta(days=days_count - 1)

        def _chip_class(tag: str) -> str:
            t = (tag or "").strip().lower()
            if t.startswith("gram"):
                return "chip-grammar"
            if t.startswith("vocab"):
                return "chip-vocabulary"
            if t.startswith("read"):
                return "chip-reading"
            if t.startswith("writ"):
                return "chip-writing"
            if t.startswith("listen"):
                return "chip-listening"
            if t.startswith("speak"):
                return "chip-speaking"
            if t.startswith("review"):
                return "chip-review"
            if t.startswith("rest"):
                return "chip-rest"
            return "chip-generic"

        def _fmt_range(d1: date, d2: date) -> str:
            if d1.year == d2.year:
                return f"{d1.strftime('%b %d')} – {d2.strftime('%b %d, %Y')}"
            return f"{d1.strftime('%b %d, %Y')} – {d2.strftime('%b %d, %Y')}"

        parts: list[str] = []
        parts.append('<div class="ai-roadmap">')
        parts.append(f'<h3 class="ai-roadmap-title">{title}</h3>')
        if summary:
            parts.append(f'<p class="ai-roadmap-summary">{summary}</p>')

        if strengths or weaknesses:
            parts.append('<div class="ai-roadmap-sw">')
            if strengths:
                parts.append('<div class="ai-roadmap-col"><div class="ai-roadmap-k">Strengths</div><ul>')
                for s in strengths[:5]:
                    parts.append(f"<li>{escape(str(s))}</li>")
                parts.append("</ul></div>")
            if weaknesses:
                parts.append('<div class="ai-roadmap-col"><div class="ai-roadmap-k">Focus Areas</div><ul>')
                for w in weaknesses[:5]:
                    parts.append(f"<li>{escape(str(w))}</li>")
                parts.append("</ul></div>")
            parts.append("</div>")

        parts.append('<div class="ai-cal">')
        parts.append(
            '<div class="ai-cal-header">'
            f'<div class="ai-cal-title">{weeks}-Week Calendar Plan</div>'
            f'<div class="ai-cal-range">{escape(_fmt_range(start_date, end_date))}</div>'
            "</div>"
        )
        parts.append('<div class="ai-cal-wrap">')
        parts.append('<table class="ai-cal-table" role="table">')
        parts.append('<thead><tr>')
        for lab in weekday_labels:
            parts.append(f'<th scope="col">{lab}</th>')
        parts.append('</tr></thead><tbody>')

        cur = start_date
        for _w in range(weeks):
            parts.append('<tr>')
            for _d in range(7):
                iso = cur.isoformat()
                day_items = items_by_date.get(iso, [])
                parts.append(f'<td data-date="{iso}">')
                parts.append('<div class="ai-cal-cell">')
                parts.append(f'<div class="ai-cal-date">{cur.strftime("%b")} <strong>{cur.day}</strong></div>')
                parts.append('<div class="ai-cal-items">')

                shown = 0
                for it in day_items:
                    if not isinstance(it, dict):
                        continue
                    tag = str(it.get("tag") or "")
                    label = str(it.get("label") or "").strip()
                    minutes = it.get("minutes")
                    if not label:
                        continue
                    if shown >= 2:
                        break
                    mins_text = ""
                    if isinstance(minutes, (int, float)) and int(minutes) > 0:
                        mins_text = f" · {int(minutes)}m"
                    cls = _chip_class(tag)
                    parts.append(
                        f'<span class="ai-chip {cls}">'
                        f'{escape(tag) if tag else "Task"}: {escape(label)}{escape(mins_text)}'
                        '</span>'
                    )
                    shown += 1

                if shown == 0:
                    parts.append('<span class="ai-chip chip-rest">Rest / Review</span>')

                parts.append('</div></div></td>')
                cur += timedelta(days=1)
            parts.append('</tr>')

        parts.append('</tbody></table></div></div></div>')
        return "".join(parts)

    def _get_ai_roadmap(level, stats, score, goal_note=None, target_weeks=None):
        client = NLPService._get_client()
        if not client:
            return "AI service is currently unavailable."

        goal_note = (goal_note or "").strip()
        weeks = 4
        if isinstance(target_weeks, int):
            weeks = target_weeks
        try:
            weeks = int(weeks)
        except Exception:
            weeks = 4
        weeks = max(2, min(5, weeks))
        days_count = weeks * 7

        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7
        start_date = today if days_until_monday == 0 else (today + timedelta(days=days_until_monday))

        system_prompt = (
            "You are an expert English teacher and study coach. "
            "Your ONLY job is to output valid JSON. Do NOT write explanations. Do NOT write markdown or code fences. "
            "Write ONLY in English."
        )

        prompt = f"""
ROLE: Expert English teacher and study coach.

TASK: Produce a day-by-day calendar study plan as JSON (English-only).

STUDENT DATA:
- Level Result: {level}
- Total Score: {score}%
- Module Performance: {json.dumps(stats)}
- Student Goal/Constraints (optional): {goal_note if goal_note else "N/A"}

PLAN WINDOW:
- Start date (Monday): {start_date.isoformat()}
- Number of days: {days_count} (exactly {weeks} weeks)

RULES:
1) Use module stats to identify strengths and weaknesses.
2) Create 0–2 items per day; each item is a micro-task with a clear topic and short action.
3) Focus more on weak modules, but include maintenance for strong modules.
4) Keep tasks practical and specific (e.g., "Subject–verb agreement drill", "Main idea + inference practice").
5) If goal/constraints are provided, adapt the daily load (minutes) but do not ignore weaknesses.
6) OUTPUT ONLY valid JSON (no extra text).

REQUIRED JSON SCHEMA:
{{
  "title": "...",
  "summary": "1–2 sentences",
  "strengths": ["..."],
  "weaknesses": ["..."],
  "calendar": {{
    "start_date": "{start_date.isoformat()}",
    "days": [
      {{"date":"YYYY-MM-DD","items":[{{"tag":"Grammar|Vocabulary|Reading|Writing|Listening|Speaking|Review|Rest","label":"...","minutes":15}}]}}
    ]
  }}
}}

IMPORTANT: calendar.days must contain exactly {days_count} entries, one for each consecutive date starting from start_date.
""".strip()

        try:
            chat = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.7
            )
            response_content = (chat.choices[0].message.content or "").strip()

            if "```" in response_content:
                response_content = re.sub(r"```json\s*|\s*```", "", response_content)
            json_match = re.search(r"\{.*\}", response_content, re.DOTALL)
            if json_match:
                response_content = json_match.group(0)

            data = json.loads(response_content)
            if not isinstance(data, dict):
                return "AI roadmap format error."
            return ReportService._render_calendar_roadmap_html(data, start_date=start_date, days_count=days_count)
        except Exception as e:
            return f"Error generating report: {e}"