from app import db
from app.models import TestSession, Question, Response, CEFRLevel, ModuleType, QuestionType
from app.services.nlp_service import NLPService
from app.services.score_calculator import ScoreCalculator
from datetime import datetime
from app.services.nlp_service import NLPService
from app.models import ModuleType  # We'll use the ModuleType enum
import random  # Random module is also required

class TestService:
    @staticmethod
    def create_session(student_id):
        # Start a new exam session
        # Sequence Diagram 1.3: create TestSession(studentId)
        session = TestSession(student_id=student_id)
        db.session.add(session)
        db.session.commit()
        return session

    @staticmethod
    def get_questions_for_level(level=CEFRLevel.A1):
        # 1. Check existing questions in the database first
        existing_questions = Question.query.filter_by(difficulty=level).all()
        
        # Increased limit: require at least 10 questions
        if len(existing_questions) >= 10:
            import random
            return random.sample(existing_questions, 10)
            
        # 2. If there are not enough questions, ask AI to generate them
        print(
            f"Database has {len(existing_questions)} questions, which is insufficient. Generating 10 new questions via AI..."
        )
        
        # Request 10 fresh questions from AI
        generated_data = NLPService.generate_questions(level.value, count=10)
        
        new_questions = []
        for q_data in generated_data:
            try:
                mod_enum = ModuleType[q_data['module']]
                # QuestionType enum conversion (with error handling)
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
        
        # Merge newly generated questions with any existing ones
        all_questions = existing_questions + new_questions
        # If there are more than 10 total, pick 10 randomly
        if len(all_questions) > 10:
            import random
            return random.sample(all_questions, 10)
        return all_questions

    @staticmethod
    def submit_answer(session_id, question_id, selected_option, text_answer=None):
        # Save the answer to the database
        response = Response(
            session_id=session_id,
            question_id=question_id,
            selected_option=selected_option,
            text_answer=text_answer,
            is_correct=False  # Scoring will be done later
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
            
            # NEW: generate the report as soon as the exam ends
            ScoreCalculator.calculate_score(session)