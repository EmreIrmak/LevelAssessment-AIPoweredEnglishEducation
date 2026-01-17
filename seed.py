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
import os

app = create_app()


def seed_database():
    with app.app_context():
        print("[seed] Cleaning database...")
        db.drop_all()
        db.create_all()

        print("[seed] Creating users...")
        admin = User(
            name="System Admin", email="admin@englishai.com", role=UserRole.ADMIN
        )
        admin.set_password("admin123")
        db.session.add(admin)

        instructor = User(
            name="Instructor User",
            email="instructor@englishai.com",
            role=UserRole.INSTRUCTOR,
        )
        instructor.set_password("instructor123")
        db.session.add(instructor)

        student = Student(
            name="Test User",
            email="user@test.com",
            role=UserRole.STUDENT,
            current_level=CEFRLevel.B1,
        )
        student.set_password("123456")
        db.session.add(student)

        seed_questions = os.environ.get("SEED_QUESTIONS", "0").lower() in ("1", "true", "yes", "y")
        if not seed_questions:
            db.session.commit()
            print("[seed] Skipping question seeding (SEED_QUESTIONS=0).")
            print("[seed] You can now start the server with: python run.py")
            return

        print("[seed] Loading question pool...")

        questions_data = [
            # --- B1 GRAMMAR ---
            (
                "I ______ a student.",
                {"A": "is", "B": "are", "C": "am", "D": "be"},
                "C",
                ModuleType.GRAMMAR,
                CEFRLevel.B1,
            ),
            (
                "She ______ in London.",
                {"A": "live", "B": "lives", "C": "living", "D": "lived"},
                "B",
                ModuleType.GRAMMAR,
                CEFRLevel.B1,
            ),
            (
                "They ______ happy today.",
                {"A": "is", "B": "am", "C": "be", "D": "are"},
                "D",
                ModuleType.GRAMMAR,
                CEFRLevel.B1,
            ),
            (
                "We ______ breakfast at 8 a.m.",
                {"A": "has", "B": "have", "C": "having", "D": "had"},
                "B",
                ModuleType.GRAMMAR,
                CEFRLevel.B1,
            ),
            (
                "He ______ TV every evening.",
                {"A": "watch", "B": "watches", "C": "watching", "D": "watched"},
                "B",
                ModuleType.GRAMMAR,
                CEFRLevel.B1,
            ),
            # --- A2 GRAMMAR ---
            (
                "Yesterday, I ______ to the cinema.",
                {"A": "go", "B": "went", "C": "gone", "D": "going"},
                "B",
                ModuleType.GRAMMAR,
                CEFRLevel.A2,
            ),
            # --- B1 VOCABULARY ---
            (
                "Select the animal:",
                {"A": "Car", "B": "Apple", "C": "Cat", "D": "Table"},
                "C",
                ModuleType.VOCABULARY,
                CEFRLevel.B1,
            ),
            (
                "Opposite of 'Hot':",
                {"A": "Cold", "B": "Warm", "C": "Sunny", "D": "Red"},
                "A",
                ModuleType.VOCABULARY,
                CEFRLevel.B1,
            ),
            (
                "Choose the fruit:",
                {"A": "Banana", "B": "Chair", "C": "Phone", "D": "Shoe"},
                "A",
                ModuleType.VOCABULARY,
                CEFRLevel.B1,
            ),
            (
                "Opposite of 'Big':",
                {"A": "Tall", "B": "Small", "C": "Fast", "D": "Long"},
                "B",
                ModuleType.VOCABULARY,
                CEFRLevel.B1,
            ),
            (
                "Choose the color:",
                {"A": "Run", "B": "Blue", "C": "Eat", "D": "Book"},
                "B",
                ModuleType.VOCABULARY,
                CEFRLevel.B1,
            ),
            # --- B1 READING ---
            (
                "READING: 'My name is Sarah. I live in New York.'\nQuestion: Where does Sarah live?",
                {"A": "London", "B": "Paris", "C": "New York", "D": "Tokyo"},
                "C",
                ModuleType.READING,
                CEFRLevel.B1,
            ),
            (
                "READING: 'I like apples and bananas.'\nQuestion: What fruit does the writer like?",
                {"A": "Oranges", "B": "Grapes", "C": "Apples", "D": "Melons"},
                "C",
                ModuleType.READING,
                CEFRLevel.B1,
            ),
            (
                "READING: 'Tom has a dog. The dog is black.'\nQuestion: What color is the dog?",
                {"A": "White", "B": "Black", "C": "Brown", "D": "Gray"},
                "B",
                ModuleType.READING,
                CEFRLevel.B1,
            ),
            (
                "READING: 'Anna goes to school by bus.'\nQuestion: How does Anna go to school?",
                {"A": "By car", "B": "On foot", "C": "By bus", "D": "By train"},
                "C",
                ModuleType.READING,
                CEFRLevel.B1,
            ),
            (
                "READING: 'It is raining today, so I take an umbrella.'\nQuestion: Why does the writer take an umbrella?",
                {"A": "It is sunny", "B": "It is raining", "C": "It is snowing", "D": "It is windy"},
                "B",
                ModuleType.READING,
                CEFRLevel.B1,
            ),
            # --- B1 WRITING (OPEN ENDED) ---
            (
                "WRITING: Write about your daily routine. Use simple present tense.",
                None,
                None,
                ModuleType.WRITING,
                CEFRLevel.B1,
            ),
            (
                "WRITING: Write a short message to invite a friend to coffee this weekend.",
                None,
                None,
                ModuleType.WRITING,
                CEFRLevel.B1,
            ),
            (
                "WRITING: Describe your favorite food. Include at least 2 adjectives.",
                None,
                None,
                ModuleType.WRITING,
                CEFRLevel.B1,
            ),
            (
                "WRITING: Write about your family (who they are, what they do).",
                None,
                None,
                ModuleType.WRITING,
                CEFRLevel.B1,
            ),
            (
                "WRITING: Write about what you do after school/work.",
                None,
                None,
                ModuleType.WRITING,
                CEFRLevel.B1,
            ),
            # --- B1 LISTENING (WITH AUDIO URL) ---
            (
                "LISTENING: Listen to the audio.\nQuestion: What word do you hear?",
                {"A": "goodbye", "B": "hello", "C": "thanks", "D": "sorry"},
                "B",
                ModuleType.LISTENING,
                CEFRLevel.B1,
            ),
            (
                "LISTENING: Listen to the audio.\nQuestion: Which greeting is said?",
                {"A": "hello", "B": "please", "C": "tomorrow", "D": "maybe"},
                "A",
                ModuleType.LISTENING,
                CEFRLevel.B1,
            ),
            (
                "LISTENING: Listen to the audio.\nQuestion: What is the speaker saying?",
                {"A": "hello", "B": "goodnight", "C": "welcome", "D": "excuse me"},
                "A",
                ModuleType.LISTENING,
                CEFRLevel.B1,
            ),
            (
                "LISTENING: Listen to the audio.\nQuestion: Which option matches the audio?",
                {"A": "hello", "B": "pencil", "C": "window", "D": "kitchen"},
                "A",
                ModuleType.LISTENING,
                CEFRLevel.B1,
            ),
            (
                "LISTENING: Listen to the audio.\nQuestion: Choose the word you hear.",
                {"A": "hello", "B": "yellow", "C": "below", "D": "follow"},
                "A",
                ModuleType.LISTENING,
                CEFRLevel.B1,
            ),
            # --- B1 SPEAKING (OPEN ENDED) ---
            (
                "SPEAKING: Introduce yourself in 20-30 seconds (name, where you live, what you like).",
                None,
                None,
                ModuleType.SPEAKING,
                CEFRLevel.B1,
            ),
            (
                "SPEAKING: Describe your day in 20-30 seconds (morning, afternoon, evening).",
                None,
                None,
                ModuleType.SPEAKING,
                CEFRLevel.B1,
            ),
            (
                "SPEAKING: Talk about your favorite hobby for 20-30 seconds.",
                None,
                None,
                ModuleType.SPEAKING,
                CEFRLevel.B1,
            ),
            (
                "SPEAKING: Describe your hometown in 20-30 seconds (weather, places, people).",
                None,
                None,
                ModuleType.SPEAKING,
                CEFRLevel.B1,
            ),
            (
                "SPEAKING: Tell me what you like to eat and drink (20-30 seconds).",
                None,
                None,
                ModuleType.SPEAKING,
                CEFRLevel.B1,
            ),
        ]

        listening_audio_url = "https://upload.wikimedia.org/wikipedia/commons/2/21/En-us-hello.ogg"

        total_added = 0
        for text, options, answer, module, level in questions_data:
            q_type = QuestionType.MULTIPLE_CHOICE if options else QuestionType.OPEN_ENDED

            options_json = json.dumps(options) if options else None

            q = Question(
                text=text,
                options=options_json,
                correct_answer=answer,
                module=module,
                difficulty=level,
                question_type=q_type,
                audio_url=listening_audio_url if module == ModuleType.LISTENING else None,
            )
            db.session.add(q)
            total_added += 1

        # Offline bank loading removed on purpose (use AI-generated pools instead)

        db.session.commit()
        print(f"[seed] Completed successfully! Total questions added: {total_added}")
        print("[seed] You can now start the server with: python run.py")


if __name__ == "__main__":
    seed_database()
