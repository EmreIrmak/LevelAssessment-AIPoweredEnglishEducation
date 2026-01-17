from app.models import Response, Question, get_level_score, get_level_from_score
from sqlalchemy import desc

class AdaptiveService:
    @staticmethod
    def calculate_next_level(session):
        # Take only the last 3 answers in the current module
        recent_responses = session.responses.join(Response.question).filter(
            Question.module == session.current_module
        ).order_by(desc(Response.id)).limit(3).all()

        if not recent_responses:
            return session.current_difficulty

        current_score = get_level_score(session.current_difficulty)
        # More stable adaptation:
        # - Increase only on 2 consecutive correct answers
        # - Decrease only on 2 consecutive incorrect answers
        last = recent_responses[0]
        prev = recent_responses[1] if len(recent_responses) >= 2 else None

        if prev is not None and last.is_correct is True and prev.is_correct is True:
            new_score = min(6, current_score + 1)
        elif prev is not None and last.is_correct is False and prev.is_correct is False:
            new_score = max(1, current_score - 1)
        else:
            new_score = current_score
                
        return get_level_from_score(new_score)