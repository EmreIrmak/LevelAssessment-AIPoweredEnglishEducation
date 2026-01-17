from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime
import os

from app.extensions import db
from app.models import TestSession, ModuleType, TechnicalEvent, Report, UserRole
from app.services.speech_to_text_service import SpeechToTextService
from app.services.instructor_dashboard_service import InstructorDashboardService

api_bp = Blueprint("api", __name__)


def _iso(dt: datetime | None):
    return dt.isoformat() if dt else None

def _parse_module(module_str: str | None):
    if not module_str:
        return None
    for m in ModuleType:
        if module_str.upper() == m.name:
            return m
        if module_str == m.value:
            return m
    return None


@api_bp.route("/api/technical_event", methods=["POST"])
@login_required
def technical_event():
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    module = payload.get("module")
    event_type = payload.get("event_type")
    message = payload.get("message")

    if not session_id or not event_type:
        return jsonify({"ok": False, "error": "session_id and event_type are required"}), 400

    session = TestSession.query.get(session_id)
    if not session or session.user_id != current_user.id:
        return jsonify({"ok": False, "error": "unauthorized"}), 403

    mod_enum = _parse_module(module)

    evt = TechnicalEvent(
        session_id=session.id,
        module=mod_enum,
        event_type=str(event_type),
        message=str(message) if message is not None else None,
    )
    db.session.add(evt)
    db.session.commit()
    return jsonify({"ok": True})


@api_bp.route("/api/stt/transcribe", methods=["POST"])
@login_required
def stt_transcribe():
    session_id = request.form.get("session_id", type=int)
    question_id = request.form.get("question_id", type=int)
    module = request.form.get("module")
    audio = request.files.get("audio")

    if not session_id or not question_id or not audio:
        return jsonify({"ok": False, "error": "session_id, question_id and audio are required"}), 400

    session = TestSession.query.get(session_id)
    if not session or session.user_id != current_user.id:
        return jsonify({"ok": False, "error": "unauthorized"}), 403

    uploads_dir = os.path.join(current_app.instance_path, "uploads")
    os.makedirs(uploads_dir, exist_ok=True)

    original = secure_filename(audio.filename or "speech.webm")
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    filename = f"s{session_id}_q{question_id}_{ts}_{original}"
    filepath = os.path.join(uploads_dir, filename)
    audio.save(filepath)

    result = SpeechToTextService.transcribe(filepath)
    status = result.get("status")

    return jsonify(
        {
            "ok": status == "ok",
            "status": status,
            "transcript": result.get("transcript"),
            "error": result.get("error"),
            "audio_filename": filename,
            "module": module,
        }
    )


@api_bp.route("/api/report/<int:session_id>", methods=["GET"])
@login_required
def report_status(session_id: int):
    session = TestSession.query.get_or_404(session_id)
    if session.user_id != current_user.id:
        if not getattr(current_user, "role", None) or current_user.role.value not in ("Admin", "Instructor"):
            return jsonify({"ok": False, "error": "unauthorized"}), 403

    report = Report.query.filter_by(session_id=session.id).first()
    if not report:
        return jsonify({"ok": True, "exists": False})

    return jsonify(
        {
            "ok": True,
            "exists": True,
            "status": report.status.value if report.status else None,
            "ai_feedback": report.ai_feedback,
            "ai_error": report.ai_error,
            "learning_plan": report.learning_plan,
            "learning_plan_error": report.learning_plan_error,
            "score": report.score,
            "level_result": report.level_result.value if report.level_result else None,
        }
    )


@api_bp.route("/api/instructor/dashboard", methods=["GET"])
@login_required
def instructor_dashboard_stats():
    if getattr(current_user, "role", None) not in (UserRole.ADMIN, UserRole.INSTRUCTOR):
        return jsonify({"ok": False, "error": "unauthorized"}), 403

    try:
        days = int(request.args.get("days", 7))
    except Exception:
        days = 7
    days = max(1, min(365, days))

    data = InstructorDashboardService.build(days=days, max_rows=12)

    leaderboard = []
    for r in data.leaderboard:
        leaderboard.append(
            {
                "student": r.get("student"),
                "report": r.get("report"),
                "module_scores": r.get("module_scores"),
                "last_attempt": _iso(r.get("last_attempt")),
            }
        )

    return jsonify(
        {
            "ok": True,
            "kpis": data.kpis,
            "charts": data.charts,
            "widgets": data.widgets,
            "leaderboard": leaderboard,
        }
    )


