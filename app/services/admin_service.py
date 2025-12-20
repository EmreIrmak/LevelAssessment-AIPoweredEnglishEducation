from app.extensions import db
from app.models import User

class AdminService:
    @staticmethod
    def get_all_users():
        # Admin hariç tüm kullanıcıları listele
        return User.query.filter(User.role != 'ADMIN').all()

    @staticmethod
    def delete_user(user_id):
        # Sequence Diagram 1.2: deleteById(targetUserId)
        user = User.query.get(user_id)
        if user:
            # Önce kullanıcının test sonuçlarını ve planlarını silmek gerekebilir
            # Ancak Cascade ayarı varsa otomatik silinir. Şimdilik manuel siliyoruz:
            db.session.delete(user)
            db.session.commit()
            return True, "Kullanıcı başarıyla silindi."
        return False, "Kullanıcı bulunamadı."