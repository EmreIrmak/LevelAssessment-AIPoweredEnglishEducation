from app.extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import enum
from datetime import datetime

# --- ENUMS ---
class UserRole(enum.Enum):
    ADMIN = "Admin"
    STUDENT = "Student"

class CEFRLevel(enum.Enum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"

class ModuleType(enum.Enum):
    GRAMMAR = "Grammar"
    VOCABULARY = "Vocabulary"
    READING = "Reading"
    WRITING = "Writing"
    LISTENING = "Listening"
    SPEAKING = "Speaking"

class QuestionType(enum.Enum):
    MULTIPLE_CHOICE = "Multiple Choice"
    OPEN_ENDED = "Open Ended"

# --- HELPER FUNCTIONS ---
def get_level_score(level):
    levels = {CEFRLevel.A1: 1, CEFRLevel.A2: 2, CEFRLevel.B1: 3, 
              CEFRLevel.B2: 4, CEFRLevel.C1: 5, CEFRLevel.C2: 6}
    return levels.get(level, 1)

def get_level_from_score(score):
    score = max(1, min(6, score))
    levels = {1: CEFRLevel.A1, 2: CEFRLevel.A2, 3: CEFRLevel.B1, 
              4: CEFRLevel.B2, 5: CEFRLevel.C1, 6: CEFRLevel.C2}
    return levels[score]

# --- MODELLER ---
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True, index=True)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.Enum(UserRole), default=UserRole.STUDENT)
    type = db.Column(db.String(50))

    __mapper_args__ = {'polymorphic_identity': 'user', 'polymorphic_on': type}

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Student(User):
    __tablename__ = 'students'
    id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    current_level = db.Column(db.Enum(CEFRLevel), default=CEFRLevel.A1)
    __mapper_args__ = {'polymorphic_identity': 'student'}

class Question(db.Model):
    __tablename__ = 'questions'
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    module = db.Column(db.Enum(ModuleType), nullable=False)
    difficulty = db.Column(db.Enum(CEFRLevel), nullable=False)
    question_type = db.Column(db.Enum(QuestionType), default=QuestionType.MULTIPLE_CHOICE)
    # JSON verisini Text olarak saklıyoruz (SQLite'ın çökmemesi için)
    options = db.Column(db.Text, nullable=True) 
    correct_answer = db.Column(db.String(500), nullable=True)

class TestSession(db.Model):
    __tablename__ = 'test_sessions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime)
    
    # State Tracking
    current_module = db.Column(db.Enum(ModuleType), default=ModuleType.GRAMMAR)
    current_question_index = db.Column(db.Integer, default=0)
    current_difficulty = db.Column(db.Enum(CEFRLevel), default=CEFRLevel.A1)
    
    responses = db.relationship('Response', backref='session', lazy='dynamic')

class Response(db.Model):
    __tablename__ = 'responses'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('test_sessions.id'))
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'))
    selected_option = db.Column(db.String(10)) # A, B, C, D
    text_answer = db.Column(db.Text)           # Writing/Speaking cevabı
    is_correct = db.Column(db.Boolean)
    
    question = db.relationship('Question')
    
class Report(db.Model):
    __tablename__ = 'reports'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('test_sessions.id'))
    score = db.Column(db.Float)
    level_result = db.Column(db.Enum(CEFRLevel))
    ai_feedback = db.Column(db.Text) # AI'ın yazdığı uzun rapor