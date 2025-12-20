from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.services.user_service import UserService
from app.models import UserRole
from app.services.admin_service import AdminService
from app.extensions import db
from app.models import User, UserRole, CEFRLevel # Modeller eklendi
from app.models import Student

# Blueprint tanımlıyoruz (URL ön eki yok, direkt /login, /dashboard)
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('auth.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # UserService üzerinden doğrulama
        user = UserService.authenticate(email, password)
        
        if user:
            login_user(user)
            return redirect(url_for('auth.dashboard'))
        else:
            flash('Geçersiz e-posta veya şifre.', 'danger')

    return render_template('login.html')

@auth_bp.route('/dashboard')
@login_required
def dashboard():
    users = None
    # Eğer giren kişi ADMIN ise, kullanıcı listesini çek
    if current_user.role == UserRole.ADMIN:
        users = AdminService.get_all_users()
        
    return render_template('dashboard.html', user=current_user, users=users)

@auth_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('auth.dashboard'))

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # 1. E-posta kontrolü: Zaten var mı?
        user = User.query.filter_by(email=email).first()
        if user:
            flash('Bu e-posta adresi zaten kayıtlı.', 'danger')
            return redirect(url_for('auth.register'))
        
        # 2. Yeni kullanıcı oluştur
        new_user = Student( # Varsayılan olarak Öğrenci (Student) oluşturuyoruz
            name=name,
            email=email,
            role=UserRole.STUDENT,
            current_level=CEFRLevel.A1 # Başlangıç seviyesi
        )
        new_user.set_password(password) # Şifreyi hashle
        
        # 3. Veritabanına kaydet
        db.session.add(new_user)
        db.session.commit()
        
        flash('Kayıt başarılı! Şimdi giriş yapabilirsiniz.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('register.html')