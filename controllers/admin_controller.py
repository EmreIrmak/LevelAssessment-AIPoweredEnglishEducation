from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import UserRole
from app.services.admin_service import AdminService
from app.services.nlp_service import NLPService
from app.services.question_bank_service import QuestionBankService
from app.extensions import db
from app.models import Question, ModuleType, QuestionType, CEFRLevel, Response, SessionQuestion
import json
from flask import current_app
from groq import Groq

admin_bp = Blueprint('admin', __name__)

# Simple decorator (helper) to enforce admin access
def admin_required(func):
    from functools import wraps
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != UserRole.ADMIN:
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for('auth.dashboard'))
        return func(*args, **kwargs)
    return decorated_view

@admin_bp.route('/admin/users')
@login_required
@admin_required
def user_list():
    # Fetch all users
    users = AdminService.get_all_users()
    return render_template('admin_dashboard.html', users=users)

@admin_bp.route('/admin/delete/<int:user_id>')
@login_required
@admin_required
def delete_user(user_id):
    # Sequence Diagram 1.2: clickDeleteUser -> deleteAccount
    success, message = AdminService.delete_user(user_id)
    
    if success:
        flash(message, "success")
    else:
        flash(message, "danger")
        
    return redirect(url_for('auth.dashboard'))


@admin_bp.route('/admin/generate_question_bank')
@login_required
@admin_required
def generate_question_bank():
    """
    Generates 10 ETS-style questions per module at ~B2 and stores them to DB.
    (This can take time; keep it simple for MVP.)
    """
    modules = ["Grammar", "Vocabulary", "Reading", "Writing", "Listening", "Speaking"]
    bank = NLPService.generate_question_bank(modules, difficulty="B2", count_per_module=10)

    created = 0
    for module_name, questions in bank.items():
        try:
            mod_enum = ModuleType[module_name.upper()]
        except Exception:
            continue
        for q in questions:
            if not q or not q.get("text"):
                continue
            q_type = q.get("question_type") or "MULTIPLE_CHOICE"
            try:
                qt_enum = QuestionType[q_type]
            except Exception:
                qt_enum = QuestionType.MULTIPLE_CHOICE

            text = q["text"].strip()
            if mod_enum == ModuleType.WRITING:
                text = QuestionBankService._ensure_writing_word_range(text)

            options = q.get("options")
            options_json = json.dumps(options) if isinstance(options, dict) else None
            correct = q.get("correct_answer")

            new_q = Question(
                text=text,
                module=mod_enum,
                difficulty=CEFRLevel.B2,
                question_type=qt_enum,
                options=options_json,
                correct_answer=correct,
            )
            db.session.add(new_q)
            created += 1

    db.session.commit()
    flash(f"AI question bank generated. Questions added: {created}", "success")
    return redirect(url_for('auth.dashboard'))


@admin_bp.route('/admin/system_status')
@login_required
@admin_required
def system_status():
    """
    Shows whether the running Flask process can see env-based secrets (without exposing them),
    and performs a lightweight Groq connectivity check.
    """
    key = current_app.config.get("GROQ_API_KEY")
    stt_model = current_app.config.get("GROQ_STT_MODEL")

    groq_ok = False
    groq_error = None
    models_sample = None
    if key:
        try:
            client = Groq(api_key=key)
            models = client.models.list()
            # Don't dump everything; show just a small sample of IDs if present
            data = getattr(models, "data", None) or []
            models_sample = [getattr(m, "id", None) for m in data[:5]]
            groq_ok = True
        except Exception as e:
            groq_error = str(e)

    return render_template(
        "admin_system_status.html",
        groq_key_present=bool(key),
        groq_key_length=(len(key) if key else 0),
        groq_stt_model=stt_model,
        groq_ok=groq_ok,
        groq_error=groq_error,
        models_sample=models_sample,
    )


@admin_bp.route('/admin/refresh_question_bank')
@login_required
@admin_required
def refresh_question_bank():
    """
    Wipe all questions + related responses/session questions and regenerate fresh AI question pools.
    """
    # Delete dependent rows first to avoid FK issues
    Response.query.delete()
    SessionQuestion.query.delete()
    deleted = Question.query.delete()
    db.session.commit()

    # Regenerate pools using config as minimums (but keep a sensible floor)
    counts = current_app.config.get("QUESTIONS_PER_SECTION") or {}
    default_level = current_app.config.get("DEFAULT_START_LEVEL", "B2")
    try:
        level_enum = CEFRLevel[default_level]
    except Exception:
        level_enum = CEFRLevel.B2

    def _min_for(mod: ModuleType, floor: int) -> int:
        try:
            return max(int(counts.get(mod.value, floor)), floor)
        except Exception:
            return floor

    targets = {
        ModuleType.GRAMMAR: _min_for(ModuleType.GRAMMAR, 10),
        ModuleType.VOCABULARY: _min_for(ModuleType.VOCABULARY, 10),
        ModuleType.READING: _min_for(ModuleType.READING, 10),
        ModuleType.WRITING: _min_for(ModuleType.WRITING, 5),
        ModuleType.SPEAKING: _min_for(ModuleType.SPEAKING, 5),
        ModuleType.LISTENING: _min_for(ModuleType.LISTENING, 10),
    }

    created_total = 0
    results = []
    for mod, target in targets.items():
        res = QuestionBankService.ensure_module_level_pool(mod, level_enum, target)
        created_total += int(res.get("created", 0) or 0)
        results.append(f"{mod.value}: +{res.get('created', 0)} (target {target})")

    flash(
        f"Question bank refreshed. Deleted {deleted} old questions. Created {created_total} new questions."
        f" Details: {', '.join(results)}",
        "success",
    )
    return redirect(url_for('admin.system_status'))