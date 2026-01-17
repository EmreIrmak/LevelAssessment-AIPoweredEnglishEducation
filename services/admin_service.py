from app.extensions import db
from app.models import User, UserRole

class AdminService:
    @staticmethod
    def get_all_users():
        # List all users except Admin
        return User.query.filter(User.role != UserRole.ADMIN).all()

    @staticmethod
    def delete_user(user_id):
        # Sequence Diagram 1.2: deleteById(targetUserId)
        user = User.query.get(user_id)
        if user:
            # You may need to delete the user's test results/plans first.
            # If cascade is configured it will be removed automatically; for now we delete manually.
            db.session.delete(user)
            db.session.commit()
            return True, "User deleted successfully."
        return False, "User not found."