from app import db
from app.models import TestSession, Question, Response, CEFRLevel, ModuleType, QuestionType
from app.services.nlp_service import NLPService
from app.services.score_calculator import ScoreCalculator
from datetime import datetime
from app.services.nlp_service import NLPService
from app.models import ModuleType # ModuleType enum'ını kullanacağız
import random # Random modülü de gerekli olacak

class TestService:
    @staticmethod
    def create_session(student_id):
        # Yeni bir sınav oturumu başlat
        # Sequence Diagram 1.3: create TestSession(studentId)
        session = TestSession(student_id=student_id)
        db.session.add(session)
        db.session.commit()
        return session

    @staticmethod
    def get_questions_for_level(level=CEFRLevel.A1):
        # 1. Önce veritabanındaki mevcut sorulara bak
        existing_questions = Question.query.filter_by(difficulty=level).all()
        
        # LİMİTİ ARTTIRDIK: Artık en az 10 soru istiyoruz
        if len(existing_questions) >= 10:
            import random
            return random.sample(existing_questions, 10)
            
        # 2. Soru yoksa veya azsa, AI'dan üretmesini iste
        print(f"Veritabanında {len(existing_questions)} soru var, yetersiz. AI 10 yeni soru üretiyor...")
        
        # AI'dan 10 tane taze soru iste
        generated_data = NLPService.generate_questions(level.value, count=10)
        
        new_questions = []
        for q_data in generated_data:
            try:
                mod_enum = ModuleType[q_data['module']]
                # QuestionType enum çevrimi (Hata yönetimi ile)
                q_type_str = q_data.get('question_type', 'MULTIPLE_CHOICE')
                type_enum = QuestionType[q_type_str]
            except:
                mod_enum = ModuleType.GRAMMAR
                type_enum = QuestionType.MULTIPLE_CHOICE
            
            new_q = Question(
                text=q_data['text'],
                module=mod_enum,
                difficulty=level,
                question_type=type_enum,
                options=q_data.get('options'),
                correct_answer=q_data.get('correct_answer')
            )
            db.session.add(new_q)
            new_questions.append(new_q)
            
        db.session.commit()
        
        # Yeni üretilenleri ve varsa eskileri birleştirip döndür
        all_questions = existing_questions + new_questions
        # Eğer toplam 10'dan fazlaysa rastgele 10 tane seç
        if len(all_questions) > 10:
            import random
            return random.sample(all_questions, 10)
        return all_questions

    @staticmethod
    def submit_answer(session_id, question_id, selected_option, text_answer=None):
        # Cevabı veritabanına kaydet
        response = Response(
            session_id=session_id,
            question_id=question_id,
            selected_option=selected_option,
            text_answer=text_answer,
            is_correct=False # Puanlama daha sonra yapılacak
        )
        db.session.add(response)
        db.session.commit()

    @staticmethod
    
    @staticmethod
    def finish_session(session_id):
        session = TestSession.query.get(session_id)
        if session:
            session.end_time = datetime.utcnow()
            session.is_completed = True
            db.session.commit()
            
            # YENİ: Sınav bittiği an raporu oluştur
            ScoreCalculator.calculate_score(session)