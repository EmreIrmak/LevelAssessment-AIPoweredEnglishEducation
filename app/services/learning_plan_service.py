from app import db
from app.models import LearningPlan, ModuleType

class LearningPlanService:
    # MVP için kaynakları burada sabit bir sözlük olarak tutuyoruz.
    # İleride bunlar 'MaterialRepository' tablosundan çekilebilir.
    MATERIAL_DATABASE = {
        "GRAMMAR": [
            {"title": "BBC Learning English - Basic Grammar", "url": "https://www.bbc.co.uk/learningenglish/basic-grammar"},
            {"title": "Video: 10 Dakikada İngilizce Gramer Temelleri", "url": "https://www.youtube.com/watch?v=sürpriz_video"}
        ],
        "VOCABULARY": [
            {"title": "Oxford 3000 - En Önemli Kelimeler", "url": "https://www.oxfordlearnersdictionaries.com/wordlists/oxford3000-5000"},
            {"title": "Quizlet - Başlangıç Seviyesi Kelime Kartları", "url": "https://quizlet.com"}
        ],
        "READING": [
            {"title": "News in Levels - Basitleştirilmiş Haberler", "url": "https://www.newsinlevels.com/"},
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
        Öğrencinin zayıf konularına göre materyal seçer ve veritabanına kaydeder.
        """
        recommended_materials = []
        
        # Eğer hiç hata yoksa (weak_topics boşsa), genel geliştirme önerelim
        topics_to_cover = weak_topics if weak_topics else ["READING", "LISTENING"]

        for topic in topics_to_cover:
            # Konuya uygun materyalleri sözlükten bul
            materials = LearningPlanService.MATERIAL_DATABASE.get(topic, [])
            recommended_materials.extend(materials)

        # Planı veritabanı nesnesine dönüştür
        new_plan = LearningPlan(
            student_id=student.id,
            weak_areas=topics_to_cover,  # JSON olarak kaydedilecek
            recommended_materials=recommended_materials # JSON olarak kaydedilecek
        )

        db.session.add(new_plan)
        db.session.commit()
        
        return new_plan