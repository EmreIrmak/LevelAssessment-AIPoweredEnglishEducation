from app import db
from app.models import Report, CEFRLevel, ModuleType
from app.services.nlp_service import NLPService  # <--- Don't forget this import!
from app.services.learning_plan_service import LearningPlanService

class ScoreCalculator:
    @staticmethod
    def calculate_score(session):
        correct_count = 0
        total_questions = 0
        weak_topics = []  # We'll keep track of weak topics
        
        for response in session.responses:
            question = response.question  # Should no longer error :)
            total_questions += 1
            
            if question.question_type.value == 'MULTIPLE_CHOICE':
                if response.selected_option == question.correct_answer:
                    response.is_correct = True
                    correct_count += 1
                else:
                    response.is_correct = False
                    # Add the weak module/topic to the list (e.g., GRAMMAR)
                    if question.module.value not in weak_topics:
                        weak_topics.append(question.module.value)
            else:
                response.is_correct = None 
        
        score = (correct_count / total_questions) * 100 if total_questions > 0 else 0
        
        # --- AI INTEGRATION STARTS HERE ---
        student_level = session.student.current_level.value
        
        # Get feedback from the AI
        ai_feedback = NLPService.generate_feedback(
            student_level=student_level,
            score=score,
            weak_topics=weak_topics
        )
        # ---------------------------------------

        report = Report(
            test_session_id=session.id,
            overall_score=score,
            cefr_level=session.student.current_level,
            feedback_text=ai_feedback  # Now dynamic (not static)
        )
        
        db.session.add(report)
        db.session.commit()
        
        LearningPlanService.create_plan(
        student=session.student,
        weak_topics=weak_topics
    )
        
        return report