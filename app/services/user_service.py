from app.models import User


class UserService:
    @staticmethod
    def authenticate(email, password):
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            return user
        return None

    @staticmethod
    def get_user_by_id(user_id):
        return User.query.get(user_id)
