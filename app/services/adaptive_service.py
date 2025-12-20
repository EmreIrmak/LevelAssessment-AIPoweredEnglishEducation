from app.models import Response, Question, get_level_score, get_level_from_score
from sqlalchemy import desc

class AdaptiveService:
    @staticmethod
    def calculate_next_level(session):
        # Sadece mevcut modüldeki son 3 cevabı al
        recent_responses = session.responses.join(Response.question).filter(
            Question.module == session.current_module
        ).order_by(desc(Response.id)).limit(3).all()

        if not recent_responses:
            return session.current_difficulty

        current_score = get_level_score(session.current_difficulty)
        last_response = recent_responses[0]
        
        if last_response.is_correct:
            # Doğruysa seviye artır (Max C2)
            new_score = min(6, current_score + 1)
        else:
            # Yanlışsa...
            # Eğer son 2 soru yanlışsa düşür
            if len(recent_responses) >= 2 and not recent_responses[1].is_correct:
                new_score = max(1, current_score - 1)
            else:
                # Sadece son soru yanlışsa seviyeyi koru
                new_score = current_score 
                
        return get_level_from_score(new_score)