from config_models import db, User, Student, Question, TestSession, Response, Report, LearningPlan, Material

class UserRepository:
    @staticmethod
    def save(user):
        db.session.add(user)
        db.session.commit()
        return user
    
    @staticmethod
    def find_by_email(email):
        return User.query.filter_by(email=email).first()

class ResultRepository:
    @staticmethod
    def save_session(session):
        db.session.add(session)
        db.session.commit()
        return session.test_id

    @staticmethod
    def save_response(response):
        db.session.add(response)
        db.session.commit()

    @staticmethod
    def save_report(report):
        db.session.add(report)
        db.session.commit()
        return report.report_id
    
    @staticmethod
    def find_report_by_test(test_id):
        return Report.query.filter_by(test_id=test_id).first()

class MaterialRepository:
    @staticmethod
    def find_by_skill(skill):
        return Material.query.filter_by(skill_tag=skill).all()

class PlanRepository:
    @staticmethod
    def save_plan(plan):
        db.session.add(plan)
        db.session.commit()
        return plan.plan_id

class QuestionRepository:
    @staticmethod
    def get_all():
        return Question.query.all()