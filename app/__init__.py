from flask import Flask, redirect, url_for
from config import Config
# YENİ: db ve login_manager'ı extensions dosyasından alıyoruz
from app.extensions import db, login_manager 

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Başlatma işlemleri
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    # Modelleri yükle (Burada import etmek en güvenlisidir)
    from app.models import User
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Controller'ları (Blueprint) Kaydet
    from app.controllers.auth_controller import auth_bp
    from app.controllers.test_controller import test_bp
    from app.controllers.admin_controller import admin_bp
    from app.controllers.report_controller import report_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(test_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(report_bp)

    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    return app