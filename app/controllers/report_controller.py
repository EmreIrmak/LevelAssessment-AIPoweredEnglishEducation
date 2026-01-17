from flask import Blueprint, render_template, redirect, url_for, jsonify, send_file
from flask_login import login_required, current_user
from app.models import TestSession, Report, UserRole, Response, Question, ModuleType
from app.services.report_service import ReportService
from app.services.learning_plan_service import LearningPlanService
from app.services.nlp_service import NLPService
import json
from io import BytesIO
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from datetime import datetime
import os

report_bp = Blueprint('report', __name__, url_prefix='/report')

def _skill_advice(score: float | int | None) -> tuple[str, list[str], str]:
    """
    Returns: (short_advice, strategies[list], tone)
    tone: 'good' | 'ok' | 'focus'
    """
    try:
        s = float(score) if score is not None else 0.0
    except Exception:
        s = 0.0

    if s >= 80:
        return (
            "Strong performance. Keep consistency and push for nuance.",
            ["Increase difficulty slightly", "Do timed practice", "Focus on accuracy under pressure"],
            "good",
        )
    if s >= 60:
        return (
            "Solid foundation. Improve speed and reduce recurring mistakes.",
            ["Review weak sub-topics", "Practice daily 15–25 min", "Use short self-checklists"],
            "ok",
        )
    return (
        "Needs focused practice. Build habits and close core gaps first.",
        ["Start with basics + repetition", "Use guided exercises", "Track errors and revisit weekly"],
        "focus",
    )


def _module_strategies(module_name: str) -> list[str]:
    strategies_map = {
        "Grammar": ["1 topic/day (10–15 min)", "Write 5 example sentences", "Fix 3 common errors"],
        "Vocabulary": ["Learn 10 words/day", "Use spaced repetition", "Create 3 sentences/word"],
        "Reading": ["Skim → scan technique", "Underline keywords", "Summarize in 2 sentences"],
        "Writing": ["Plan (3 bullets) then write", "Use a checklist (tense/linking)", "Rewrite 1 paragraph"],
        "Listening": ["Shadow 2–3 min audio", "Listen twice: gist → detail", "Note 5 key words"],
        "Speaking": ["Record 60–90s answers", "Use 3-part structure", "Self-review with rubric"],
    }
    return strategies_map.get(module_name, ["Practice little and often", "Review weekly", "Focus on clarity"])


def _module_icon(module_name: str) -> str:
    icons = {
        "Grammar": "fa-solid fa-spell-check",
        "Vocabulary": "fa-solid fa-book",
        "Reading": "fa-solid fa-book-open-reader",
        "Writing": "fa-solid fa-pen-nib",
        "Listening": "fa-solid fa-headphones",
        "Speaking": "fa-solid fa-microphone",
    }
    return icons.get(module_name, "fa-solid fa-circle-info")


@report_bp.route('/result/<int:session_id>')
@login_required
def show_result(session_id):
    session = TestSession.query.get_or_404(session_id)
    
    # A user can only view their own report (unless admin/instructor)
    if session.user_id != current_user.id:
        if current_user.role not in (UserRole.ADMIN, UserRole.INSTRUCTOR):
            return "Unauthorized", 403

    # Has the report already been generated?
    report = Report.query.filter_by(session_id=session.id).first()
    
    # If not generated yet, generate it now (AI enrichment may run async)
    if not report:
        # For the session owner: ask report preference BEFORE generating.
        if session.user_id == current_user.id:
            return redirect(url_for("test.report_options", session_id=session.id))
        # For admin/instructor views: generate directly based on results.
        report = ReportService.generate_report(session)

    module_stats = {}
    try:
        module_stats = json.loads(report.module_stats_json) if report.module_stats_json else {}
    except Exception:
        module_stats = {}

    # Derive weak modules (lowest scores) for showing sample materials
    weak_materials = []
    try:
        if module_stats:
            # pick bottom 2 modules by score
            sorted_mods = sorted(module_stats.items(), key=lambda x: x[1])
            for name, _ in sorted_mods[:2]:
                mats = LearningPlanService.MATERIAL_DATABASE.get(name.upper(), [])
                weak_materials.extend(mats)
    except Exception:
        weak_materials = []

    # Suggested resources cards (full set)
    module_icons = {
        "Grammar": "fa-book",
        "Vocabulary": "fa-language",
        "Reading": "fa-book-open",
        "Listening": "fa-headphones",
        "Writing": "fa-pen-nib",
        "Speaking": "fa-microphone",
    }
    resource_cards = []
    for name in ["Grammar", "Vocabulary", "Reading", "Listening", "Writing", "Speaking"]:
        mats = list(LearningPlanService.MATERIAL_DATABASE.get(name.upper(), []))
        if name == "Reading":
            mats.append({"title": "VOA Learning English", "url": "https://learningenglish.voanews.com/"})
        resource_cards.append(
            {
                "name": name,
                "icon": module_icons.get(name, "fa-book"),
                "materials": mats,
            }
        )

    # Build UI-friendly skill breakdown cards (stable order)
    module_order = ["Vocabulary", "Grammar", "Reading", "Writing", "Listening", "Speaking"]
    skill_breakdown = []
    for m in module_order:
        score = module_stats.get(m, 0)
        advice, generic_strats, tone = _skill_advice(score)
        skill_breakdown.append(
            {
                "name": m,
                "score": score,
                "tone": tone,
                "icon": _module_icon(m),
                "advice": advice,
                "strategies": _module_strategies(m)[:3] or generic_strats,
            }
        )

    # Mistake analysis (incorrect responses)
    wrong_responses = (
        Response.query.join(Question, Response.question_id == Question.id)
        .filter(Response.session_id == session.id)
        .filter(Response.is_correct == False)  # noqa: E712
        .order_by(Question.module.asc(), Question.id.asc())
        .all()
    )

    def _option_text(question: Question, opt_letter: str | None):
        if not question or not opt_letter:
            return None
        try:
            opts = json.loads(question.options) if question.options else {}
            if isinstance(opts, dict):
                return opts.get(opt_letter)
        except Exception:
            return None
        return None

    wrong_details = []
    for wr in wrong_responses:
        q = wr.question
        wrong_details.append(
            {
                "module": q.module.value if q and q.module else "",
                "question_text": q.text if q else "",
                "user_answer": wr.selected_option or wr.text_answer,
                "correct_answer": q.correct_answer if q else None,
                "correct_answer_text": _option_text(q, q.correct_answer),
                "question_id": q.id if q else None,
                "response_id": wr.id,
                "question_type": q.question_type.value if q and q.question_type else "",
            }
        )

    module_error_counts = {}
    for item in wrong_details:
        key = item["module"] or "Unknown"
        module_error_counts[key] = module_error_counts.get(key, 0) + 1
    error_focus = sorted(module_error_counts.items(), key=lambda x: x[1], reverse=True)[:3]

    # Student sees detailed report; Instructor/Admin sees summary version
    if current_user.role == UserRole.STUDENT and session.user_id == current_user.id:
        return render_template(
            'result.html',
            report=report,
            session=session,
            module_stats=module_stats,
            weak_materials=weak_materials,
            resource_cards=resource_cards,
            skill_breakdown=skill_breakdown,
            wrong_details=wrong_details,
            module_error_counts=module_error_counts,
            error_focus=error_focus,
        )
    return render_template(
        'result_summary.html',
        report=report,
        session=session,
        module_stats=module_stats,
        weak_materials=weak_materials,
        resource_cards=resource_cards,
        skill_breakdown=skill_breakdown,
    )


@report_bp.route('/result/<int:session_id>/section/<module_name>')
@login_required
def section_errors(session_id: int, module_name: str):
    session = TestSession.query.get_or_404(session_id)
    if session.user_id != current_user.id and current_user.role not in (UserRole.ADMIN, UserRole.INSTRUCTOR):
        return "Unauthorized", 403

    # normalize module
    mod_enum = None
    try:
        mod_enum = ModuleType[module_name.upper()]
    except Exception:
        # try value match
        for m in ModuleType:
            if m.value.lower() == module_name.lower():
                mod_enum = m
                break
    if not mod_enum:
        return "Invalid module", 404

    base_query = (
        Response.query.join(Question, Response.question_id == Question.id)
        .filter(Response.session_id == session.id)
        .filter(Question.module == mod_enum)
        .order_by(Question.id.asc())
    )

    if mod_enum in (ModuleType.WRITING, ModuleType.SPEAKING):
        wrong_responses = base_query.all()
    else:
        wrong_responses = base_query.filter(Response.is_correct == False).all()  # noqa: E712

    def _option_text(question: Question, opt_letter: str | None):
        if not question or not opt_letter:
            return None
        try:
            opts = json.loads(question.options) if question.options else {}
            if isinstance(opts, dict):
                return opts.get(opt_letter)
        except Exception:
            return None
        return None

    items = []
    for wr in wrong_responses:
        q = wr.question
        opts = {}
        try:
            opts = json.loads(q.options) if q and q.options else {}
        except Exception:
            opts = {}
        analysis = None
        # NLP-based writing analysis (TF-IDF, sentence count, tense check)
        if q and q.module == ModuleType.WRITING:
            text = (wr.text_answer or "").strip()
            prompt_text = (q.text if q else "")
            analysis_data = NLPService.analyze_writing_response_ai(text=text, prompt=prompt_text)
            analysis = NLPService.format_writing_analysis(analysis_data)
        # Speaking: AI report based on transcript
        if q and q.module == ModuleType.SPEAKING and not analysis:
            transcript = (wr.transcript or wr.text_answer or "").strip()
            prompt_text = (q.text if q else "")
            speak_data = NLPService.analyze_speaking_response_ai(transcript=transcript, prompt=prompt_text)
            analysis = NLPService.format_speaking_analysis(speak_data)
        items.append(
            {
                "question": q,
                "response": wr,
                "options": opts if isinstance(opts, dict) else {},
                "user_answer": wr.selected_option or wr.text_answer,
                "correct_answer": q.correct_answer if q else None,
                "correct_answer_text": _option_text(q, q.correct_answer),
                "question_type": q.question_type.value if q and q.question_type else "",
                "analysis": analysis,
            }
        )

    return render_template(
        'result_section_errors.html',
        session=session,
        module=mod_enum.value,
        items=items,
    )


@report_bp.route('/result/<int:session_id>/status.json')
@login_required
def check_report_status(session_id):
    """
    API endpoint that returns the current report status and AI feedback.
    Used by frontend to poll for report readiness without page refresh.
    """
    session = TestSession.query.get_or_404(session_id)
    
    # Verify user can access this report
    if session.user_id != current_user.id:
        if current_user.role not in (UserRole.ADMIN, UserRole.INSTRUCTOR):
            return jsonify({"error": "Unauthorized"}), 403

    report = Report.query.filter_by(session_id=session.id).first()
    
    if not report:
        return jsonify({"error": "Report not found"}), 404
    
    return jsonify({
        "status": report.status.value,
        "ai_feedback": report.ai_feedback,
        "score": report.score,
        "level": report.level_result.value if report.level_result else None,
        "learning_plan": report.learning_plan,
        "learning_plan_error": report.learning_plan_error if hasattr(report, 'learning_plan_error') else None,
    })


@report_bp.route('/result/<int:session_id>/certificate')
@login_required
def generate_certificate(session_id):
    """
    Generate and download a PDF certificate for the user's assessment result.
    """
    session = TestSession.query.get_or_404(session_id)
    
    # Verify user can access this report
    if session.user_id != current_user.id:
        if current_user.role not in (UserRole.ADMIN, UserRole.INSTRUCTOR):
            return "Unauthorized", 403

    report = Report.query.filter_by(session_id=session.id).first()
    
    if not report:
        return "Report not found", 404
    
    # Create PDF in memory
    pdf_buffer = BytesIO()
    
    # Use landscape letter size for certificate
    width, height = landscape(letter)
    
    c = canvas.Canvas(pdf_buffer, pagesize=landscape(letter))
    
    # Set font sizes and colors
    title_font = "Helvetica-Bold"
    # Use bold body text for better readability in the certificate
    text_font = "Helvetica-Bold"
    
    # Background color (light beige)
    c.setFillColor(colors.HexColor("#f5f5f0"))
    c.rect(0, 0, width, height, fill=1, stroke=0)
    
    # Border
    c.setLineWidth(3)
    c.setStrokeColor(colors.HexColor("#6366f1"))
    c.rect(0.5*inch, 0.5*inch, width - inch, height - inch, fill=0, stroke=1)
    
    # Logo section (left side)
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(colors.HexColor("#6366f1"))
    c.drawString(1*inch, height - 1.2*inch, "🎓 English AI")
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(colors.HexColor("#6366f1"))
    c.drawString(1*inch, height - 1.5*inch, "Student Portal")
    
    # Certificate title
    c.setFont(title_font, 48)
    c.setFillColor(colors.HexColor("#1a1a1a"))
    c.drawCentredString(width/2, height - 2.5*inch, "Certificate of Achievement")
    
    # "This certifies that" text
    c.setFont(text_font, 14)
    c.setFillColor(colors.HexColor("#333333"))
    c.drawCentredString(width/2, height - 3.2*inch, "This certifies that")
    
    # User name (large and bold)
    c.setFont(title_font, 36)
    c.setFillColor(colors.HexColor("#1a1a1a"))
    c.drawCentredString(width/2, height - 3.9*inch, current_user.name)
    
    # Achievement text
    c.setFont(text_font, 13)
    c.setFillColor(colors.HexColor("#333333"))
    y_pos = height - 4.7*inch
    achievement_lines = [
        "has successfully completed the",
        "English AI Student Portal English Proficiency Test",
        "and was awarded a certificate in"
    ]
    for line in achievement_lines:
        c.drawCentredString(width/2, y_pos, line)
        y_pos -= 0.3*inch
    
    # Level result (prominent)
    c.setFont(title_font, 32)
    c.setFillColor(colors.HexColor("#6366f1"))
    level_text = f"English Level - {report.level_result.value if report.level_result else 'N/A'}"
    c.drawCentredString(width/2, y_pos - 0.4*inch, level_text)
    
    # Score display
    c.setFont(text_font, 12)
    c.setFillColor(colors.HexColor("#333333"))
    score_text = f"Overall Score: {int(report.score)}%"
    c.drawCentredString(width/2, y_pos - 0.9*inch, score_text)
    
    # Date
    completion_date = session.end_time.strftime("%d.%m.%Y") if session.end_time else datetime.now().strftime("%d.%m.%Y")
    c.setFont(text_font, 11)
    c.setFillColor(colors.HexColor("#333333"))
    c.drawCentredString(width/2 - 2*inch, 1*inch, f"Date: {completion_date}")
    
    # Certificate ID/Serial number
    certificate_id = f"CERT-{session.id}-{current_user.id}"
    c.drawCentredString(width/2 + 2*inch, 1*inch, f"ID: {certificate_id}")
    
    # Finish the PDF
    c.save()
    
    pdf_buffer.seek(0)
    
    # Return as downloadable PDF
    return send_file(
        pdf_buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"Certificate_{current_user.name.replace(' ', '_')}_{session.id}.pdf"
    )