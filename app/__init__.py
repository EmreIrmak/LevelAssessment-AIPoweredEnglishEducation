from flask import Flask, redirect, url_for
from config import Config
# NEW: import db and login_manager from extensions
from app.extensions import db, login_manager, migrate

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialization
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    login_manager.login_view = 'auth.login'

    # Load models (importing here is the safest option)
    from app.models import User
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register controllers (Blueprints)
    from app.controllers.auth_controller import auth_bp
    from app.controllers.test_controller import test_bp
    from app.controllers.admin_controller import admin_bp
    from app.controllers.report_controller import report_bp
    from app.controllers.api_controller import api_bp
    from app.controllers.instructor_controller import instructor_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(test_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(instructor_bp)

    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    return app