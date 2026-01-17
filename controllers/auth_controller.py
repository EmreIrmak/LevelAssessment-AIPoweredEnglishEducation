from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.services.user_service import UserService
from app.models import UserRole
from app.services.admin_service import AdminService
from app.extensions import db
from app.models import User, UserRole, CEFRLevel, TestSession, Report
from app.models import Student
from app.services.instructor_dashboard_service import InstructorDashboardService

# Blueprint definition (no URL prefix; direct /login, /dashboard)
auth_bp = Blueprint('auth', __name__)

# Home (Landing Page)
@auth_bp.route('/home')
@auth_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('auth.dashboard'))
    return render_template('index.html')

def _role_from_str(role_str: str | None):
    if not role_str:
        return None
    role_str = role_str.lower().strip()
    if role_str == "student":
        return UserRole.STUDENT
    if role_str == "instructor":
        return UserRole.INSTRUCTOR
    if role_str == "admin":
        return UserRole.ADMIN
    return None

def _login_with_role(role: UserRole):
    if current_user.is_authenticated:
        return redirect(url_for('auth.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = UserService.authenticate(email, password)
        if not user:
            flash('Invalid email or password.', 'danger')
            return redirect(request.url)

        if user.role != role:
            flash(f"This user cannot sign in as '{role.value}'.", 'danger')
            return redirect(request.url)

        login_user(user)
        return redirect(url_for('auth.dashboard'))

    return render_template('login_role.html', role=role)

def _register_with_role(role: UserRole):
    if current_user.is_authenticated:
        return redirect(url_for('auth.dashboard'))

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        invite_code = (request.form.get('invite_code') or "").strip()

        # Instructor/Admin registration requires invite codes (if configured)
        if role in (UserRole.INSTRUCTOR, UserRole.ADMIN):
            expected = (
                current_app.config.get("INSTRUCTOR_INVITE_CODE")
                if role == UserRole.INSTRUCTOR
                else current_app.config.get("ADMIN_INVITE_CODE")
            )
            if not expected:
                flash("Registration for this role is closed. Please contact an administrator.", "danger")
                return redirect(request.url)
            if invite_code != expected:
                flash("Invalid invite code.", "danger")
                return redirect(request.url)

        # Email uniqueness
        existing = User.query.filter_by(email=email).first()
        if existing:
            flash('This email address is already registered.', 'danger')
            return redirect(request.url)

        if role == UserRole.STUDENT:
            new_user = Student(
                name=name,
                email=email,
                role=UserRole.STUDENT,
                current_level=CEFRLevel.A1,
            )
        else:
            new_user = User(
                name=name,
                email=email,
                role=role,
            )

        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        flash('Registration successful! You can now sign in.', 'success')
        # redirect to correct login page
        if role == UserRole.STUDENT:
            return redirect(url_for('auth.login_student'))
        if role == UserRole.INSTRUCTOR:
            return redirect(url_for('auth.login_instructor'))
        return redirect(url_for('auth.login_admin'))

    return render_template('register_role.html', role=role)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # Backward-compatible: old /login acts as Student login
    return _login_with_role(UserRole.STUDENT)

@auth_bp.route('/login/student', methods=['GET', 'POST'])
def login_student():
    return _login_with_role(UserRole.STUDENT)

@auth_bp.route('/login/instructor', methods=['GET', 'POST'])
def login_instructor():
    return _login_with_role(UserRole.INSTRUCTOR)

@auth_bp.route('/login/admin', methods=['GET', 'POST'])
def login_admin():
    return _login_with_role(UserRole.ADMIN)

@auth_bp.route('/dashboard')
@login_required
def dashboard():
    users = None
    student_sessions = None
    instructor_dashboard = None
    # If the logged-in user is ADMIN, fetch the user list
    if current_user.role == UserRole.ADMIN:
        users = AdminService.get_all_users()
    elif current_user.role == UserRole.STUDENT:
        sessions = (
            TestSession.query.filter_by(user_id=current_user.id)
            .order_by(TestSession.start_time.desc())
            .all()
        )
        student_sessions = []
        for s in sessions:
            rep = Report.query.filter_by(session_id=s.id).first()
            student_sessions.append({"session": s, "report": rep})
    elif current_user.role == UserRole.INSTRUCTOR:
        try:
            days = int(request.args.get("days", 7))
        except Exception:
            days = 7
        days = max(1, min(365, days))
        instructor_dashboard = InstructorDashboardService.build(days=days, max_rows=12)
        
    return render_template(
        'dashboard.html',
        user=current_user,
        users=users,
        student_sessions=student_sessions,
        instructor_dashboard=instructor_dashboard,
    )

@auth_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('auth.index'))

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    # Backward-compatible: old /register acts as Student register
    return _register_with_role(UserRole.STUDENT)

@auth_bp.route('/register/student', methods=['GET', 'POST'])
def register_student():
    return _register_with_role(UserRole.STUDENT)

@auth_bp.route('/register/instructor', methods=['GET', 'POST'])
def register_instructor():
    return _register_with_role(UserRole.INSTRUCTOR)

@auth_bp.route('/register/admin', methods=['GET', 'POST'])
def register_admin():
    return _register_with_role(UserRole.ADMIN)