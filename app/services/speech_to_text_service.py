from flask import current_app
from groq import Groq


class SpeechToTextService:
    @staticmethod
    def transcribe(filepath: str) -> dict:
        """
        Transcribes an audio file and returns:
        {"status": "ok"|"no_key"|"error", "transcript": str|None, "error": str|None}
        """
        api_key = current_app.config.get("GROQ_API_KEY")
        if not api_key:
            return {
                "status": "no_key",
                "transcript": None,
                "error": "GROQ_API_KEY is not configured.",
            }

        try:
            model = current_app.config.get("GROQ_STT_MODEL") or "whisper-large-v3"
            client = Groq(api_key=api_key)
            with open(filepath, "rb") as f:
                resp = client.audio.transcriptions.create(model=model, file=f)
            transcript = getattr(resp, "text", None) or (
                resp.get("text") if isinstance(resp, dict) else None
            )
            return {"status": "ok", "transcript": transcript, "error": None}
        except Exception as e:
            return {"status": "error", "transcript": None, "error": str(e)}


