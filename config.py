import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'guvenli-anahtar-123'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # BURAYA YENİ GROQ ANAHTARINI YAPIŞTIR
    GROQ_API_KEY = "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"