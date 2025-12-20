from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

# Veritabanı ve Giriş yöneticisini burada oluşturuyoruz (Tertemiz bir sayfa)
db = SQLAlchemy()
login_manager = LoginManager()