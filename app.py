from flask import Flask, render_template, request, jsonify, session, redirect, url_for
# Veritabanı modellerini config_models.py'den çekiyoruz
from config_models import db, Config, Student, Question, Response, Material, Report

# Repository'leri 'repositories.py' dosyasından çekmeliyiz
from repositories import UserRepository, ResultRepository

# Servisleri 'services.py' dosyasından çekmeliyiz
from services import TestService, AnalysisService, QuestionGeneratorService

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

# --- VERİTABANI KURULUM FONKSİYONU (DÜZELTİLDİ) ---
def setup_database():
    """
    Uygulama ilk çalıştığında veritabanını oluşturur ve
    içini boş kalmasın diye örnek verilerle doldurur.
    Flask 2.3+ uyumlu olması için manuel çağrılır.
    """
    with app.app_context():
        db.create_all()
        
        # Soru tablosu boşsa AI ile doldur
        if not Question.query.first():
            print("Veritabanı hazırlanıyor... (Faz 1: Vocab, Grammar, Reading)")
            
            # Writing, Listening ve Speaking şimdilik devre dışı (Faz 2)
            # SRS Sıralaması: Vocabulary -> Grammar -> Reading
            
            generation_tasks = [
                # --- Vocabulary (Kelime Bilgisi) ---
                {"level": "A2", "module": "Vocabulary", "count": 2},
                {"level": "B2", "module": "Vocabulary", "count": 2},
                
                # --- Grammar (Dil Bilgisi) ---
                {"level": "A2", "module": "Grammar", "count": 2},
                {"level": "C1", "module": "Grammar", "count": 2},
                
                # --- Reading (Okuma) ---
                {"level": "B1", "module": "Reading", "count": 2},
                {"level": "C1", "module": "Reading", "count": 1} 
            ]
            
            total = 0
            for task in generation_tasks:
                print(f"--> {task['level']} {task['module']} üretiliyor...")
                # services.py'ye eklediğimiz TOEFL/Academic prompt fonksiyonunu çağırıyoruz
                questions = QuestionGeneratorService.generate_toefl_questions(
                    level=task['level'], 
                    module=task['module'], 
                    count=task['count']
                )
                if questions:
                    db.session.add_all(questions)
                    total += len(questions)
            
            db.session.commit()
            print(f"Faz 1 Kurulumu Tamamlandı! Toplam {total} soru eklendi.")

# --- ROUTES (Web Sayfaları) ---

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email')
    name = request.form.get('name')
    if not email: return redirect('/')
    
    user = Student.query.filter_by(email=email).first()
    if not user:
        user = Student(name=name, email=email, password="123", role="student")
        UserRepository.save(user)
    
    session['user_id'] = user.user_id
    return redirect(url_for('exam_page'))

@app.route('/exam')
def exam_page():
    if 'user_id' not in session: return redirect('/')
    user = Student.query.get(session['user_id'])
    return render_template('exam.html', user=user)

@app.route('/result/<int:test_id>')
def result_page(test_id):
    report = ResultRepository.find_report_by_test(test_id)
    if not report: return "Rapor oluşturuluyor...", 404
    
    # Report nesnesi üzerinden session'a ve oradan öğrenciye ulaşıyoruz
    session_obj = Report.query.get(report.report_id).session
    user = Student.query.get(session_obj.student_id)
    
    return render_template('result.html', report=report, user=user)

# --- API (JSON Yanıtlar) ---

@app.route('/api/start', methods=['POST'])
def start():
    user_id = session.get('user_id')
    # Oturumu başlat
    test_id = TestService.initialize_session(user_id)
    
    # Tüm soruları çek
    all_questions = TestService.fetch_questions()
    
    # --- SIRALAMA ALGORİTMASI ---
    # Modüllerin sınavdaki sırasını belirliyoruz
    module_order = {
        "Vocabulary": 1,
        "Grammar": 2,
        "Reading": 3,
        # Faz 2'de eklenecekler:
        "Writing": 4,
        "Listening": 5,
        "Speaking": 6
    }
    
    # Soruları bu sıraya göre diziyoruz (Python sort fonksiyonu)
    # x.module sözlükte yoksa (örn. hata varsa) en sona (99) atar.
    sorted_questions = sorted(all_questions, key=lambda x: module_order.get(x.module, 99))
    
    # Frontend'e gönderilecek veriyi hazırla
    q_data = []
    for q in sorted_questions:
        q_data.append({
            "id": q.question_id,
            "text": q.text,
            "options": q.options,
            "module": q.module
        })
        
    return jsonify({
        "testId": test_id, 
        "questions": q_data,
        "info": "Sorular Vocabulary -> Grammar -> Reading sırasıyla yüklenmiştir."
    })

@app.route('/api/submit', methods=['POST'])
def submit():
    data = request.json
    test_id = data.get('testId')
    answers = data.get('answers')
    
    for ans in answers:
        resp = Response(test_id=test_id, question_id=ans['q_id'], student_answer=ans['answer'])
        ResultRepository.save_response(resp)
        
    AnalysisService.generate_final_report(test_id)
    return jsonify({"status": "success", "testId": test_id})

if __name__ == '__main__':
    # DÜZELTME: setup_database() fonksiyonunu burada, uygulama başlatılmadan hemen önce çağırıyoruz.
    setup_database()
    app.run(debug=True)