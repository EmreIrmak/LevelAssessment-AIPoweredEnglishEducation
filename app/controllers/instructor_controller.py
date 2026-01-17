from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from flask_login import login_required, current_user
from functools import wraps
from io import BytesIO
from datetime import datetime

from app.extensions import db
from app.models import UserRole, Student, TestSession, Report, SessionQuestion, Response, ModuleType, Question
from app.services.instructor_dashboard_service import InstructorDashboardService

from reportlab.lib.pagesizes import landscape, letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

import json

instructor_bp = Blueprint("instructor", __name__)


def instructor_required(func):
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if current_user.role not in (UserRole.ADMIN, UserRole.INSTRUCTOR):
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for("auth.dashboard"))
        return func(*args, **kwargs)

    return decorated_view


@instructor_bp.route("/instructor/reports")
@login_required
@instructor_required
def all_reports():
    students = Student.query.order_by(Student.id.desc()).all()

    # Latest report per student (simple N+1 is ok for small SQLite demo)
    student_rows = []
    for s in students:
        last_session = (
            TestSession.query.filter_by(user_id=s.id).order_by(TestSession.start_time.desc()).first()
        )
        last_report = Report.query.filter_by(session_id=last_session.id).first() if last_session else None
        student_rows.append({"student": s, "session": last_session, "report": last_report})

    return render_template("instructor_reports.html", rows=student_rows)


@instructor_bp.route("/instructor/leaderboard/export.pdf")
@login_required
@instructor_required
def export_leaderboard_pdf():
    def _norm(s: object) -> str:
        return str(s or "").strip().lower()

    # Keep in sync with the dashboard's timeframe selector.
    try:
        days = int(request.args.get("days", 7))
    except Exception:
        days = 7
    days = max(1, min(365, days))

    # Optional filters coming from the dashboard UI.
    q = _norm(request.args.get("q", ""))
    level_filter = str(request.args.get("level", "") or "").strip()
    status_filter = str(request.args.get("status", "") or "").strip()

    try:
        max_rows = int(request.args.get("max", 200))
    except Exception:
        max_rows = 200
    max_rows = max(1, min(500, max_rows))

    data = InstructorDashboardService.build(days=days, max_rows=max_rows)
    leaderboard = list(data.leaderboard or [])

    filtered: list[dict[str, object]] = []
    for r in leaderboard:
        stud = r.get("student") or {}
        rep = r.get("report") or {}

        name = str(stud.get("name") or "")
        email = str(stud.get("email") or "")

        rep_level = str(rep.get("level") or "").strip()
        stud_level = str(stud.get("level") or "").strip()
        display_level = rep_level or stud_level

        rep_status = str(rep.get("status") or "No report").strip()

        if q and (q not in _norm(name) and q not in _norm(email)):
            continue
        if level_filter and display_level != level_filter:
            continue
        if status_filter and rep_status != status_filter:
            continue

        filtered.append(r)

    # Build PDF
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(letter),
        leftMargin=24,
        rightMargin=24,
        topMargin=24,
        bottomMargin=24,
    )

    styles = getSampleStyleSheet()
    elements: list[object] = []

    elements.append(Paragraph("Results Leaderboard", styles["Title"]))
    subtitle = f"Exported: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} | Timeframe: last {days} days"
    elements.append(Paragraph(subtitle, styles["Normal"]))

    active_filters = []
    if level_filter:
        active_filters.append(f"Level={level_filter}")
    if status_filter:
        active_filters.append(f"Status={status_filter}")
    if q:
        active_filters.append(f"Search={q}")
    if active_filters:
        elements.append(Paragraph("Filters: " + ", ".join(active_filters), styles["Normal"]))
    else:
        elements.append(Paragraph("Filters: None", styles["Normal"]))

    elements.append(Spacer(1, 12))

    table_data: list[list[str]] = [["Student", "Email", "Last Attempt", "Level", "Overall", "Status"]]
    for r in filtered:
        stud = r.get("student") or {}
        rep = r.get("report") or {}
        last_attempt = r.get("last_attempt")

        rep_level = str(rep.get("level") or "").strip()
        stud_level = str(stud.get("level") or "").strip()
        display_level = rep_level or stud_level

        overall = rep.get("overall")
        status = str(rep.get("status") or "No report")

        if isinstance(last_attempt, datetime):
            last_attempt_text = last_attempt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            last_attempt_text = str(last_attempt or "-")

        overall_text = f"{float(overall):.1f}%" if isinstance(overall, (int, float)) else "-"

        table_data.append(
            [
                str(stud.get("name") or "-"),
                str(stud.get("email") or "-"),
                last_attempt_text,
                str(display_level or "-"),
                overall_text,
                status,
            ]
        )

    tbl = Table(
        table_data,
        colWidths=[160, 190, 170, 60, 70, 90],
        repeatRows=1,
    )
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0ea5e9")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("ALIGN", (3, 1), (4, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("FONTSIZE", (0, 1), (-1, -1), 9),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elements.append(tbl)

    doc.build(elements)
    buf.seek(0)

    filename = f"leaderboard_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=filename)


@instructor_bp.route("/instructor/student/<int:student_id>/reports")
@login_required
@instructor_required
def student_reports(student_id: int):
    student = Student.query.get_or_404(student_id)
    sessions = TestSession.query.filter_by(user_id=student.id).order_by(TestSession.start_time.desc()).all()
    reports = []
    for sess in sessions:
        reports.append({"session": sess, "report": Report.query.filter_by(session_id=sess.id).first()})
    return render_template("instructor_student_reports.html", student=student, rows=reports)


@instructor_bp.route("/instructor/session/<int:session_id>/review")
@login_required
@instructor_required
def review_session(session_id: int):
    session = TestSession.query.get_or_404(session_id)
    student = Student.query.get(session.user_id)

    # Collect latest response per question
    responses = (
        Response.query.filter_by(session_id=session.id)
        .order_by(Response.id.desc())
        .all()
    )
    response_by_qid: dict[int, Response] = {}
    for r in responses:
        if r.question_id not in response_by_qid:
            response_by_qid[r.question_id] = r

    module_order = [
        ModuleType.GRAMMAR,
        ModuleType.VOCABULARY,
        ModuleType.READING,
        ModuleType.WRITING,
        ModuleType.LISTENING,
        ModuleType.SPEAKING,
    ]
    module_rank = {m: i for i, m in enumerate(module_order)}

    session_questions = SessionQuestion.query.filter_by(session_id=session.id).all()

    def _options_list(q) -> list[tuple[str, str]]:
        if not q or not q.options:
            return []
        try:
            opts = json.loads(q.options) if isinstance(q.options, str) else q.options
        except Exception:
            return []
        if isinstance(opts, dict):
            ordered = []
            for k in ("A", "B", "C", "D", "E", "F"):
                if k in opts:
                    ordered.append((k, str(opts.get(k))))
            # include any extra keys deterministically
            for k in sorted([k for k in opts.keys() if k not in {"A", "B", "C", "D", "E", "F"}]):
                ordered.append((str(k), str(opts.get(k))))
            return ordered
        if isinstance(opts, list):
            letters = ["A", "B", "C", "D", "E", "F"]
            out = []
            for i, val in enumerate(opts[: len(letters)]):
                out.append((letters[i], str(val)))
            return out
        return []

    def _option_text(q, letter: str | None) -> str | None:
        if not q or not letter:
            return None
        for k, v in _options_list(q):
            if k == letter:
                return v
        return None

    items = []

    if session_questions:
        for sq in session_questions:
            q = sq.question
            resp = response_by_qid.get(sq.question_id)
            items.append(
                {
                    "module": q.module.value if q and q.module else (sq.module.value if sq.module else ""),
                    "module_enum": q.module if q and q.module else sq.module,
                    "question_index": sq.question_index,
                    "question": q,
                    "sq": sq,
                    "response": resp,
                    "options": _options_list(q),
                    "correct_letter": (q.correct_answer if q else None),
                    "correct_text": _option_text(q, q.correct_answer if q else None),
                }
            )
    else:
        # Fallback: if the session has responses but no session_questions, still show what we can.
        # Order is best-effort (module, then question id).
        fallback_resps = (
            Response.query.join(Question, Response.question_id == Question.id)
            .filter(Response.session_id == session.id)
            .order_by(Question.module.asc(), Question.id.asc(), Response.id.desc())
            .all()
        )
        if not fallback_resps:
            fallback_resps = responses
        for idx, r in enumerate(fallback_resps):
            q = r.question
            items.append(
                {
                    "module": q.module.value if q and q.module else "",
                    "module_enum": q.module if q and q.module else None,
                    "question_index": idx,
                    "question": q,
                    "sq": None,
                    "response": r,
                    "options": _options_list(q),
                    "correct_letter": (q.correct_answer if q else None),
                    "correct_text": _option_text(q, q.correct_answer if q else None),
                }
            )

    items.sort(
        key=lambda it: (
            module_rank.get(it.get("module_enum"), 999),
            int(it.get("question_index") or 0),
            int(getattr(it.get("question"), "id", 0) or 0),
        )
    )

    return render_template(
        "instructor_exam_review.html",
        student=student,
        session=session,
        items=items,
    )


