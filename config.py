import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'guvenli-anahtar-123'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # API keys should come from environment variables
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
    # Speech-to-text model on Groq (Whisper family)
    GROQ_STT_MODEL = os.environ.get("GROQ_STT_MODEL") or "whisper-large-v3"

    # Per-module time limits (seconds) for the level assessment
    MODULE_TIME_LIMITS = {
        "Grammar": int(os.environ.get("TIME_LIMIT_GRAMMAR", "300")),
        "Vocabulary": int(os.environ.get("TIME_LIMIT_VOCABULARY", "300")),
        "Reading": int(os.environ.get("TIME_LIMIT_READING", "420")),
        "Writing": int(os.environ.get("TIME_LIMIT_WRITING", "600")),
        # Listening is fixed to audio-based session; default 25 minutes (1500s)
        "Listening": int(os.environ.get("TIME_LIMIT_LISTENING", "1500")),
        "Speaking": int(os.environ.get("TIME_LIMIT_SPEAKING", "420")),
    }

    # Per-section question counts (Listening is handled separately via fixed pools)
    QUESTIONS_PER_SECTION = {
        "Vocabulary": int(os.environ.get("QUESTIONS_VOCABULARY", "10")),
        "Grammar": int(os.environ.get("QUESTIONS_GRAMMAR", "10")),
        "Reading": int(os.environ.get("QUESTIONS_READING", "10")),
        "Writing": int(os.environ.get("QUESTIONS_WRITING", "1")),
        "Speaking": int(os.environ.get("QUESTIONS_SPEAKING", "3")),
    }

    # Backward-compatibility (legacy): used only if some template still references it
    QUESTIONS_PER_MODULE = int(os.environ.get("QUESTIONS_PER_MODULE", str(QUESTIONS_PER_SECTION["Vocabulary"])))

    # Speaking module timing (in seconds)
    SPEAKING_PREP_SECONDS = int(os.environ.get("SPEAKING_PREP_SECONDS", "20"))
    SPEAKING_RESPONSE_SECONDS = int(os.environ.get("SPEAKING_RESPONSE_SECONDS", "60"))

    # Invite codes for non-student registration (optional but recommended)
    INSTRUCTOR_INVITE_CODE = os.environ.get("INSTRUCTOR_INVITE_CODE")
    ADMIN_INVITE_CODE = os.environ.get("ADMIN_INVITE_CODE")

    # Prefer AI-generated questions for every new slot (falls back to DB if AI is unavailable)
    PREFER_AI_QUESTIONS = os.environ.get("PREFER_AI_QUESTIONS", "1").lower() in ("1", "true", "yes", "y")

    # Start difficulty for placement exam (more realistic than A1-only)
    DEFAULT_START_LEVEL = os.environ.get("DEFAULT_START_LEVEL", "B2")