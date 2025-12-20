from app import create_app
from app.extensions import db
from app.models import (
    User,
    Student,
    Question,
    UserRole,
    CEFRLevel,
    ModuleType,
    QuestionType,
)
import json

app = create_app()


def seed_database():
    with app.app_context():
        print("🗑️  Veritabanı temizleniyor...")
        db.drop_all()
        db.create_all()

        print("👤 Kullanıcılar oluşturuluyor...")
        admin = User(
            name="System Admin", email="admin@englishai.com", role=UserRole.ADMIN
        )
        admin.set_password("admin123")
        db.session.add(admin)

        student = Student(
            name="Test User",
            email="user@test.com",
            role=UserRole.STUDENT,
            current_level=CEFRLevel.A1,
        )
        student.set_password("123456")
        db.session.add(student)

        print("📚 Soru Havuzu (Sadece Grammar, Vocabulary, Reading) Yükleniyor...")

        questions_data = [
            # --- A1 GRAMMAR ---
            (
                "I ______ a student.",
                {"A": "is", "B": "are", "C": "am", "D": "be"},
                "C",
                ModuleType.GRAMMAR,
                CEFRLevel.A1,
            ),
            (
                "She ______ in London.",
                {"A": "live", "B": "lives", "C": "living", "D": "lived"},
                "B",
                ModuleType.GRAMMAR,
                CEFRLevel.A1,
            ),
            (
                "They ______ happy today.",
                {"A": "is", "B": "am", "C": "be", "D": "are"},
                "D",
                ModuleType.GRAMMAR,
                CEFRLevel.A1,
            ),
            # --- A2 GRAMMAR ---
            (
                "Yesterday, I ______ to the cinema.",
                {"A": "go", "B": "went", "C": "gone", "D": "going"},
                "B",
                ModuleType.GRAMMAR,
                CEFRLevel.A2,
            ),
            # --- A1 VOCABULARY ---
            (
                "Select the animal:",
                {"A": "Car", "B": "Apple", "C": "Cat", "D": "Table"},
                "C",
                ModuleType.VOCABULARY,
                CEFRLevel.A1,
            ),
            (
                "Opposite of 'Hot':",
                {"A": "Cold", "B": "Warm", "C": "Sunny", "D": "Red"},
                "A",
                ModuleType.VOCABULARY,
                CEFRLevel.A1,
            ),
            # --- A1 READING ---
            (
                "READING: 'My name is Sarah. I live in New York.'\nQuestion: Where does Sarah live?",
                {"A": "London", "B": "Paris", "C": "New York", "D": "Tokyo"},
                "C",
                ModuleType.READING,
                CEFRLevel.A1,
            ),
            (
                "READING: 'I like apples and bananas.'\nQuestion: What fruit does the writer like?",
                {"A": "Oranges", "B": "Grapes", "C": "Apples", "D": "Melons"},
                "C",
                ModuleType.READING,
                CEFRLevel.A1,
            ),
        ]

        for text, options, answer, module, level in questions_data:
            q_type = QuestionType.MULTIPLE_CHOICE  # Artık hepsi çoktan seçmeli

            options_json = json.dumps(options) if options else None

            q = Question(
                text=text,
                options=options_json,
                correct_answer=answer,
                module=module,
                difficulty=level,
                question_type=q_type,
            )
            db.session.add(q)

        db.session.commit()
        print(f"✅ Başarıyla tamamlandı! Toplam {len(questions_data)} soru eklendi.")
        print("👉 Şimdi 'python run.py' komutu ile sunucuyu başlatabilirsin.")


if __name__ == "__main__":
    seed_database()
