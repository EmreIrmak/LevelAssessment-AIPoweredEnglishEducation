import os
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Veritabanı nesnesi
db = SQLAlchemy()

class Config:
    # Güvenlik ve Veritabanı Ayarları
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'seng321_guvenli_anahtar'
    # Test için SQLite kullanıyoruz (Kurulum gerektirmez). 
    SQLALCHEMY_DATABASE_URI = 'sqlite:///level_assessment.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

# --- ENTITY KATMANI (Class Diagram) ---

# 1. Kullanıcılar
class User(db.Model):
    __tablename__ = 'users'
    user_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)

    __mapper_args__ = {
        'polymorphic_identity': 'user',
        'polymorphic_on': role
    }

class Student(User):
    __tablename__ = 'students'
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), primary_key=True)
    proficiency_level = db.Column(db.String(5), default='A1')
    enrollment_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    __mapper_args__ = {'polymorphic_identity': 'student'}
    
    sessions = db.relationship('TestSession', backref='student', lazy=True)

class Admin(User):
    __tablename__ = 'admins'
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), primary_key=True)
    admin_level = db.Column(db.Integer, default=1)
    
    __mapper_args__ = {'polymorphic_identity': 'admin'}

# 2. Sınav Yapısı
class Question(db.Model):
    __tablename__ = 'questions'
    question_id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    module = db.Column(db.String(50), nullable=False) # Vocabulary, Grammar, Reading...
    difficulty = db.Column(db.String(10), default='A1')
    options = db.Column(db.JSON) # {"a": "...", "b": "..."}
    correct_answer = db.Column(db.String(1))

class TestSession(db.Model):
    __tablename__ = 'test_sessions'
    test_id = db.Column(db.Integer, primary_key=True) # Class Diagram: testId
    student_id = db.Column(db.Integer, db.ForeignKey('students.user_id'), nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='active')
    
    responses = db.relationship('Response', backref='session', cascade="all, delete-orphan")
    report = db.relationship('Report', backref='session', uselist=False, cascade="all, delete-orphan")

class Response(db.Model):
    __tablename__ = 'responses'
    response_id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('test_sessions.test_id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.question_id'), nullable=False)
    student_answer = db.Column(db.String(500))
    is_correct = db.Column(db.Boolean, default=False)

# 3. Rapor ve Planlama
class Report(db.Model):
    __tablename__ = 'reports'
    report_id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('test_sessions.test_id'), nullable=False)
    total_score = db.Column(db.Float)
    cefr_level = db.Column(db.String(5))
    feedback_text = db.Column(db.Text) # Gemini AI çıktısı buraya gelecek
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    learning_plan = db.relationship('LearningPlan', backref='report', uselist=False, cascade="all, delete-orphan")

# Plan-Materyal Arasındaki Tablo
plan_materials = db.Table('plan_materials',
    db.Column('plan_id', db.Integer, db.ForeignKey('learning_plans.plan_id')),
    db.Column('material_id', db.Integer, db.ForeignKey('materials.material_id'))
)

class LearningPlan(db.Model):
    __tablename__ = 'learning_plans'
    plan_id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('reports.report_id'), nullable=False)
    weak_areas = db.Column(db.JSON)
    created_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    materials = db.relationship('Material', secondary=plan_materials)

class Material(db.Model):
    __tablename__ = 'materials'
    material_id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    content_url = db.Column(db.String(255))
    skill_tag = db.Column(db.String(50))