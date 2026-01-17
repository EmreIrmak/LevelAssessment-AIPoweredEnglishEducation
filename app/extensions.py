from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate

# Create the database and login manager here (clean separation)
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()