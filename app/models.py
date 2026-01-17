from app.extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import enum
from datetime import datetime

# --- ENUMS ---
class UserRole(enum.Enum):
    ADMIN = "Admin"
    STUDENT = "Student"
    INSTRUCTOR = "Instructor"

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

class ModuleAttemptStatus(enum.Enum):
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"
    EXPIRED = "Expired"

class SessionQuestionStatus(enum.Enum):
    SERVED = "Served"
    ANSWERED = "Answered"
    SKIPPED = "Skipped"

class ReportStatus(enum.Enum):
    PENDING = "Pending"
    READY = "Ready"
    ENRICHING = "Enriching"
    FAILED = "Failed"

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
    # Store JSON as Text (to avoid SQLite issues)
    options = db.Column(db.Text, nullable=True) 
    correct_answer = db.Column(db.String(500), nullable=True)
    # Listening questions can point to a playable audio URL (or static file URL)
    audio_url = db.Column(db.Text, nullable=True)

class TestSession(db.Model):
    __tablename__ = 'test_sessions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime)
    is_completed = db.Column(db.Boolean, default=False)
    
    # State Tracking
    current_module = db.Column(db.Enum(ModuleType), default=ModuleType.GRAMMAR)
    current_question_index = db.Column(db.Integer, default=0)
    current_difficulty = db.Column(db.Enum(CEFRLevel), default=CEFRLevel.A1)
    
    responses = db.relationship('Response', backref='session', lazy='dynamic')
    module_attempts = db.relationship('SessionModuleAttempt', backref='session', lazy='dynamic')
    session_questions = db.relationship('SessionQuestion', backref='session', lazy='dynamic')
    technical_events = db.relationship('TechnicalEvent', backref='session', lazy='dynamic')


class SessionModuleAttempt(db.Model):
    __tablename__ = 'session_module_attempts'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('test_sessions.id'), nullable=False, index=True)
    module = db.Column(db.Enum(ModuleType), nullable=False, index=True)
    started_at = db.Column(db.DateTime)
    ended_at = db.Column(db.DateTime)
    time_limit_seconds = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.Enum(ModuleAttemptStatus), default=ModuleAttemptStatus.IN_PROGRESS, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('session_id', 'module', name='uq_session_module_attempt'),
    )


class SessionQuestion(db.Model):
    __tablename__ = 'session_questions'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('test_sessions.id'), nullable=False, index=True)
    module = db.Column(db.Enum(ModuleType), nullable=False, index=True)
    question_index = db.Column(db.Integer, nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    status = db.Column(db.Enum(SessionQuestionStatus), default=SessionQuestionStatus.SERVED, nullable=False)
    served_at = db.Column(db.DateTime, default=datetime.utcnow)
    answered_at = db.Column(db.DateTime)

    question = db.relationship('Question')

    __table_args__ = (
        db.UniqueConstraint('session_id', 'module', 'question_index', name='uq_session_module_qindex'),
    )


class TechnicalEvent(db.Model):
    __tablename__ = 'technical_events'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('test_sessions.id'), nullable=False, index=True)
    module = db.Column(db.Enum(ModuleType), nullable=True, index=True)
    event_type = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

class Response(db.Model):
    __tablename__ = 'responses'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('test_sessions.id'))
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'))
    selected_option = db.Column(db.String(10)) # A, B, C, D
    text_answer = db.Column(db.Text)           # Writing/Speaking answer
    is_correct = db.Column(db.Boolean)
    # Speaking submissions (optional)
    audio_filename = db.Column(db.String(255))
    transcript = db.Column(db.Text)
    stt_provider = db.Column(db.String(50))
    stt_status = db.Column(db.String(50))
    
    question = db.relationship('Question')
    
class Report(db.Model):
    __tablename__ = 'reports'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('test_sessions.id'))
    score = db.Column(db.Float)
    level_result = db.Column(db.Enum(CEFRLevel))
    ai_feedback = db.Column(db.Text)  # Long report written by AI
    status = db.Column(db.Enum(ReportStatus), default=ReportStatus.PENDING, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, onupdate=datetime.utcnow)
    ai_error = db.Column(db.Text)
    learning_plan = db.Column(db.Text)
    learning_plan_error = db.Column(db.Text)
    # Goal setting (asked after exam)
    target_level = db.Column(db.Enum(CEFRLevel))
    target_weeks = db.Column(db.Integer)
    goal_note = db.Column(db.Text)
    # Persist module stats for rendering (detailed student report / summary instructor report)
    module_stats_json = db.Column(db.Text)


class LearningPlan(db.Model):
    __tablename__ = 'learning_plans'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    weak_areas = db.Column(db.Text)  # JSON array of module names
    recommended_materials = db.Column(db.Text)  # JSON array of material objects
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)