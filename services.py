import os
import json
import re
import google.generativeai as genai
from config_models import db, TestSession, Report, LearningPlan, Question
from repositories import QuestionRepository, ResultRepository, PlanRepository, MaterialRepository

# ==========================================
# API KEY AYARI
# ==========================================
GEMINI_KEY = "AIzaSyCJMdOwaUDEQs0Zt6UxChysIaCPwBqvkWU"

class QuestionGeneratorService:
    @staticmethod
    def generate_toefl_questions(level="C1", module="Reading", count=3):
        """
        TOEFL/IELTS standartlarında, çeldiricileri güçlü akademik sorular üretir.
        """
        api_key = GEMINI_KEY 
        if not api_key: return []

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-flash-latest')

        # --- MODÜLE ÖZEL TALİMATLAR ---
        module_instructions = ""
        if module == "Reading":
            module_instructions = """
            - Context: Generate a dense, academic paragraph (100-150 words) on a topic like Anthropology, Astrophysics, or Art History.
            - Question Type: Inference, Rhetorical Purpose, or Sentence Simplification.
            - The question MUST define the 'text' field as: "PASSAGE: [The Paragraph] ... QUESTION: [The Question]"
            """
        elif module == "Vocabulary":
            module_instructions = """
            - Context: Focus on 'tier-2' and 'tier-3' academic words (e.g., 'exacerbate', 'empirical', 'substantiate').
            - Question Type: Contextual meaning. The word should be used in a complex sentence.
            - Distractors: Synonyms that don't fit the specific context or nuance.
            """
        elif module == "Grammar":
            module_instructions = """
            - Context: Focus on Structure and Written Expression.
            - Topics: Inversion, Conditionals, Subjunctive Mood, Parallel Structures, Reduced Clauses.
            - Distractors: Common grammatical errors made by advanced learners (e.g., dangling modifiers).
            """

        # --- KAPSAMLI PROMPT (PROMPT MÜHENDİSLİĞİ) ---
        prompt = f"""
        **ROLE**: You are a Senior Assessment Developer for ETS (creators of TOEFL). Your task is to write high-stakes diagnostic questions.

        **TASK**: Create {count} multiple-choice questions for the '{module}' module at exactly '{level}' CEFR proficiency level.

        **CRITICAL DESIGN RULES**:
        1. **Academic Tone**: Use formal, university-level English. Avoid conversational slang.
        2. **Distractor Quality**: This is the most important rule. The wrong options (distractors) must be:
           - Plausible to a lower-level student.
           - Grammatically consistent with the stem.
           - Clearly incorrect to a native or proficient speaker based on logic or nuance.
           - AVOID easy fillers like "None of the above".
        3. **Difficulty**: Since the level is {level}, the question should require critical thinking, not just keyword matching.
        
        {module_instructions}

        **STRICT OUTPUT FORMAT**:
        Return ONLY a raw JSON array. Do not include markdown formatting (like ```json).
        [
            {{
                "text": "The full question text (and passage if reading)...",
                "options": {{"a": "Distractor 1", "b": "Correct Answer", "c": "Distractor 2", "d": "Distractor 3"}},
                "correct_answer": "b"
            }}
        ]
        """
        
        try:
            # Modelden yanıt al
            response = model.generate_content(prompt)
            
            # JSON Temizliği (Markdown taglerini siler)
            cleaned_json = re.sub(r'```json\s*|```', '', response.text).strip()
            
            questions_data = json.loads(cleaned_json)
            
            generated_objs = []
            for q in questions_data:
                # Veritabanı modeline uygun nesne oluştur
                new_q = Question(
                    text=q['text'],
                    module=module,
                    difficulty=level,
                    options=q['options'],
                    correct_answer=q['correct_answer'].lower()
                )
                generated_objs.append(new_q)
            
            return generated_objs
            
        except Exception as e:
            print(f"TOEFL Soru Üretme Hatası: {e}")
            return []

    @staticmethod
    def _clean_json_string(json_string):
        """
        AI bazen ```json ... ``` şeklinde markdown atar, bunu temizleriz.
        """
        json_string = re.sub(r'^```json\s*', '', json_string, flags=re.MULTILINE)
        json_string = re.sub(r'^```\s*', '', json_string, flags=re.MULTILINE)
        json_string = re.sub(r'\s*```$', '', json_string, flags=re.MULTILINE)
        return json_string.strip()

class TestService:
    @staticmethod
    def initialize_session(student_id):
        """Seq. Diag 3: Oturum Başlatma"""
        new_session = TestSession(student_id=student_id)
        return ResultRepository.save_session(new_session)

    @staticmethod
    def fetch_questions():
        return QuestionRepository.get_all()

class AnalysisService:
    @staticmethod
    def get_gemini_feedback(score, weak_skills, cefr_level):
        """
        Gemini API Kullanarak Geri Bildirim Oluşturur.
        """
        # Önce kodda tanımlı anahtara bak, yoksa environment'tan al
        api_key = GEMINI_KEY
        if not api_key:
             api_key = os.environ.get("GEMINI_API_KEY")

        if not api_key:
             return f"Gemini API Key bulunamadı. Lütfen services.py dosyasına anahtarınızı yapıştırın. Seviyeniz: {cefr_level}. Eksik konular: {', '.join(weak_skills)}"

        try:
            genai.configure(api_key=api_key)
            
            # Daha kararlı model seçimi
            model = genai.GenerativeModel('gemini-flash-latest')
            
            prompt = f"""
            Uzman bir İngilizce öğretmeni gibi davranmanı istiyorum. Bir öğrenci seviye tespit sınavına girdi.
            - Puanı: {score}/100
            - Tahmini Seviyesi: {cefr_level}
            - Zayıf olduğu konular: {', '.join(weak_skills) if weak_skills else 'Yok, hepsi mükemmel'}
            
            Lütfen bu öğrenciye hitaben, motive edici, samimi ve yapıcı bir değerlendirme raporu yaz.
            Zayıf olduğu konulara nasıl çalışması gerektiğine dair 1-2 cümlelik nokta atışı tavsiyeleri liste şeklinde sıralayarak ver.
            Yazı dili Türkçe ve samimi olsun. Sadece tavsiyeleri ve yorumu yaz, başka teknik metin ekleme.
            """
            
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"AI Servisi şu an yanıt vermiyor ({str(e)}). Seviyeniz: {cefr_level}"

    @staticmethod
    def generate_final_report(test_id):
        """Seq. Diag 5: Rapor Oluşturma"""
        session = TestSession.query.get(test_id)
        responses = session.responses
        
        correct_count = 0
        weak_skills = set()
        
        for r in responses:
            q = Question.query.get(r.question_id)
            if r.student_answer == q.correct_answer:
                correct_count += 1
                r.is_correct = True
            else:
                r.is_correct = False
                weak_skills.add(q.module)
        
        db.session.commit()

        total = len(responses) or 1
        score = (correct_count / total) * 100
        
        cefr = "A1"
        if score > 95: cefr = "C2"
        elif score > 85: cefr = "C1"
        elif score > 65: cefr = "B2"
        elif score > 45: cefr = "B1"
        elif score > 25: cefr = "A2"

        # Gemini'den yorum al
        feedback = AnalysisService.get_gemini_feedback(score, list(weak_skills), cefr)

        report = Report(
            test_id=test_id,
            total_score=score,
            cefr_level=cefr,
            feedback_text=feedback
        )
        report_id = ResultRepository.save_report(report)
        
        # Plan oluşturmayı tetikle
        LearningPlanService.create_plan(report_id, list(weak_skills))
        
        return True

class LearningPlanService:
    @staticmethod
    def create_plan(report_id, weak_areas):
        """Seq. Diag 6: Kişisel Plan Oluşturma (Loop Mantığı)"""
        plan = LearningPlan(report_id=report_id, weak_areas=weak_areas)
        
        # DÖNGÜ: Her zayıf alan için materyal bul ve ekle
        for area in weak_areas:
            materials = MaterialRepository.find_by_skill(area)
            for mat in materials:
                plan.materials.append(mat)
        
        PlanRepository.save_plan(plan)