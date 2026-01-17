from app import db
from app.models import LearningPlan, ModuleType

class LearningPlanService:
    # For the MVP we keep resources in a static dictionary.
    # Later, these could be loaded from a 'MaterialRepository' table.
    MATERIAL_DATABASE = {
        "GRAMMAR": [
            {"title": "BBC Learning English - Basic Grammar", "url": "https://www.bbc.co.uk/learningenglish/basic-grammar"},
            {"title": "Video: English Grammar Basics in 10 Minutes", "url": "https://www.youtube.com/watch?v=surpriz_video"}
        ],
        "VOCABULARY": [
            {"title": "Oxford 3000 - Essential Words", "url": "https://www.oxfordlearnersdictionaries.com/wordlists/oxford3000-5000"},
            {"title": "Quizlet - Beginner Vocabulary Flashcards", "url": "https://quizlet.com"}
        ],
        "READING": [
            {"title": "News in Levels - Simplified News", "url": "https://www.newsinlevels.com/"},
            {"title": "British Council - A1 Reading Skills", "url": "https://learnenglish.britishcouncil.org/skills/reading/a1-reading"}
        ],
        "WRITING": [
            {"title": "Write & Improve with Cambridge", "url": "https://writeandimprove.com/"}
        ],
        "LISTENING": [
            {"title": "6 Minute English Podcast", "url": "https://www.bbc.co.uk/learningenglish/features/6-minute-english"}
        ],
        "SPEAKING": [
            {"title": "TalkEnglish - Speaking Basics", "url": "https://www.talkenglish.com/"}
        ]
    }

    @staticmethod
    def create_plan(student, weak_topics):
        """
        Selects materials based on the student's weak topics and saves them to the database.
        """
        recommended_materials = []
        
        # If there are no weak topics, recommend general improvement areas
        topics_to_cover = weak_topics if weak_topics else ["READING", "LISTENING"]

        for topic in topics_to_cover:
            # Fetch suitable materials from the dictionary
            materials = LearningPlanService.MATERIAL_DATABASE.get(topic, [])
            recommended_materials.extend(materials)

        # Convert plan to a DB object
        new_plan = LearningPlan(
            student_id=student.id,
            weak_areas=topics_to_cover,  # Stored as JSON
            recommended_materials=recommended_materials  # Stored as JSON
        )

        db.session.add(new_plan)
        db.session.commit()
        
        return new_plan