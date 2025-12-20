from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import UserRole
from app.services.admin_service import AdminService

admin_bp = Blueprint('admin', __name__)

# Admin yetkisi kontrolü için basit bir decorator (helper)
def admin_required(func):
    from functools import wraps
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != UserRole.ADMIN:
            flash("Bu sayfaya erişim yetkiniz yok!", "danger")
            return redirect(url_for('auth.dashboard'))
        return func(*args, **kwargs)
    return decorated_view

@admin_bp.route('/admin/users')
@login_required
@admin_required
def user_list():
    # Tüm kullanıcıları getir
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