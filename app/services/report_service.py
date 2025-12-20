from app.extensions import db
# Question ve Response modellerini buraya ekledik 👇
from app.models import Report, ModuleType, CEFRLevel, Question, Response 
from app.services.nlp_service import NLPService
import json

class ReportService:
    @staticmethod
    def generate_report(session):
        # 1. Genel İstatistikleri Hesapla
        total_questions = session.responses.count()
        
        # 'is_correct' True olanları say
        correct_answers = session.responses.filter(Response.is_correct == True).count()
        
        score_percentage = (correct_answers / total_questions * 100) if total_questions > 0 else 0
        
        # 2. Modül Bazlı İstatistikler (Hata veren yer burasıydı, düzelttik)
        module_stats = {}
        for module in ModuleType:
            # Mantık: Bu oturumun cevaplarını al -> Question tablosuyla birleştir -> Modüle göre filtrele
            base_query = session.responses.join(Question).filter(Question.module == module)
            
            m_total = base_query.count()
            m_correct = base_query.filter(Response.is_correct == True).count()
            
            if m_total > 0:
                module_stats[module.value] = round((m_correct / m_total) * 100, 1)
            else:
                module_stats[module.value] = 0

        # 3. Nihai Seviyeyi Belirle (Sınavın sonundaki zorluk seviyesi)
        final_level = session.current_difficulty.value

        # 4. AI'dan Yol Haritası İste
        ai_feedback = ReportService._get_ai_roadmap(final_level, module_stats, score_percentage)

        # 5. Veritabanına Kaydet
        report = Report(
            session_id=session.id,
            score=score_percentage,
            level_result=session.current_difficulty,
            ai_feedback=ai_feedback
        )
        db.session.add(report)
        db.session.commit()
        
        return report

    @staticmethod
    def _get_ai_roadmap(level, stats, score):
        client = NLPService._get_client()
        if not client: return "AI servisine ulaşılamadı."

        prompt = f"""
        ACT AS: An expert English Teacher.
        TASK: Create a personalized study roadmap for a student in TURKISH.
        
        STUDENT DATA:
        - Level Result: {level}
        - Total Score: {score}%
        - Module Performance: {json.dumps(stats)}
        
        REQUIREMENTS:
        1. Analyze strengths and weaknesses based on module stats.
        2. Create a 3-step actionable roadmap to reach the NEXT level.
        3. Recommend specific topics.
        4. Use HTML formatting (<h3>, <ul>, <li>, <strong>). No markdown blocks.
        """

        try:
            chat = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.7
            )
            return chat.choices[0].message.content
        except Exception as e:
            return f"Rapor oluşturulurken hata: {e}"