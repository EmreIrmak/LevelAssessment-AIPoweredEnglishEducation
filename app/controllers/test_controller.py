from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models import TestSession, Question, Response, ModuleType, QuestionType
from app.services.nlp_service import NLPService
from app.services.adaptive_service import AdaptiveService
import json

test_bp = Blueprint("test", __name__)

# 1. DEĞİŞİKLİK: Sadece Grammar, Vocabulary ve Reading kaldı.
MODULE_ORDER = [ModuleType.GRAMMAR, ModuleType.VOCABULARY, ModuleType.READING]

# Test aşaması için her modülden 5 soru (İstersen 10 yapabilirsin)
QUESTIONS_PER_MODULE = 5


@test_bp.route("/start_exam")
@login_required
def start_exam():
    session = TestSession(user_id=current_user.id)
    db.session.add(session)
    db.session.commit()
    return redirect(url_for("test.get_question", session_id=session.id))


@test_bp.route("/exam/<int:session_id>", methods=["GET", "POST"])
@login_required
def get_question(session_id):
    session = TestSession.query.get_or_404(session_id)

    # --- POST: Cevap Verme Kısmı ---
    if request.method == "POST":
        question_id = request.form.get("question_id")
        user_answer = request.form.get("option") or request.form.get("text_answer")

        question = Question.query.get(question_id)

        # Basit hata önlemi: Eğer soru silinmişse veya yoksa
        if not question:
            flash("Soru bulunamadı, bir sonrakine geçiliyor.", "warning")
            return redirect(url_for("test.get_question", session_id=session.id))

        is_correct = False
        if question.question_type == QuestionType.MULTIPLE_CHOICE:
            is_correct = user_answer == question.correct_answer
        else:
            is_correct = NLPService.evaluate_open_ended(
                question.text, user_answer, session.current_difficulty.value
            )

        resp = Response(
            session_id=session.id,
            question_id=question.id,
            selected_option=user_answer
            if question.question_type == QuestionType.MULTIPLE_CHOICE
            else None,
            text_answer=user_answer
            if question.question_type == QuestionType.OPEN_ENDED
            else None,
            is_correct=is_correct,
        )
        db.session.add(resp)

        session.current_question_index += 1

        # Modül Bitti mi?
        if session.current_question_index >= QUESTIONS_PER_MODULE:
            try:
                curr_idx = MODULE_ORDER.index(session.current_module)
                if curr_idx + 1 < len(MODULE_ORDER):
                    session.current_module = MODULE_ORDER[curr_idx + 1]
                    session.current_question_index = 0
                else:
                    db.session.commit()
                    return redirect(
                        url_for("report.show_result", session_id=session.id)
                    )
            except ValueError:
                # Eğer veritabanında eski bir modül kaldıysa (örn: Listening), manuel olarak sonlandır
                db.session.commit()
                return redirect(url_for("report.show_result", session_id=session.id))

        session.current_difficulty = AdaptiveService.calculate_next_level(session)
        db.session.commit()
        return redirect(url_for("test.get_question", session_id=session.id))

    # --- GET: Soru Getirme Kısmı ---

    # Bu oturumda (session) daha önce çözülen soruların ID'lerini al
    solved_question_ids = db.session.query(Response.question_id).filter(
        Response.session_id == session.id
    )

    # 1. Önce Veritabanına Bak (Çözülmemiş soru var mı?)
    existing_q = Question.query.filter(
        Question.module == session.current_module,
        Question.difficulty == session.current_difficulty,
        ~Question.id.in_(solved_question_ids),  # "NOT IN" filtresi
    ).first()

    new_q = None
    if existing_q:
        new_q = existing_q
    else:
        # 2. Yoksa AI Üretsin
        # 2. DEĞİŞİKLİK: Aynı soruyu tekrar üretmeyi engelleme döngüsü
        max_retries = 3  # 3 kere dene, olmazsa pes et
        for _ in range(max_retries):
            q_data = NLPService.generate_adaptive_question(
                session.current_module.value, session.current_difficulty.value
            )

            if q_data and q_data.get("text"):
                # KONTROL: Bu soru metni veritabanında zaten var mı?
                duplicate_check = Question.query.filter_by(text=q_data["text"]).first()

                if duplicate_check:
                    # Soru zaten varmış!
                    # Peki kullanıcı bunu bu sınavda çözmüş mü?
                    # Eğer çözdüyse -> Döngü başa döner, yeni soru üretiriz.
                    # Eğer çözmediyse -> Harika! Bunu kullanalım (Yeni kayıt açmaya gerek yok)

                    # Bu ID çözülenler listesinde mi?
                    is_solved = (
                        db.session.query(Response)
                        .filter_by(
                            session_id=session.id, question_id=duplicate_check.id
                        )
                        .first()
                    )

                    if not is_solved:
                        new_q = duplicate_check
                        break  # Döngüden çık, soruyu bulduk
                    else:
                        print(
                            "AI aynı soruyu üretti ve kullanıcı bunu zaten çözmüş. Tekrar deneniyor..."
                        )
                        continue
                else:
                    # Soru veritabanında yok, yepyeni bir soru! Kaydet.
                    new_q = Question(
                        text=q_data["text"],
                        module=session.current_module,
                        difficulty=session.current_difficulty,
                        question_type=QuestionType[q_data["question_type"]],
                        options=json.dumps(q_data.get("options"))
                        if q_data.get("options")
                        else None,
                        correct_answer=q_data.get("correct_answer"),
                    )
                    db.session.add(new_q)
                    db.session.commit()
                    break  # Döngüden çık

    if not new_q:
        # Eğer soru bulunamazsa (çok nadir), kullanıcıyı bekletmemek için Dashboard'a at veya geçici hata ver
        flash(
            "Soru üretilirken bağlantı sorunu yaşandı. Lütfen tekrar deneyin.", "danger"
        )
        return redirect(url_for("auth.dashboard"))

    # HTML'e göndermek için Options ayarı
    options_dict = None
    if new_q.options:
        try:
            options_dict = (
                json.loads(new_q.options)
                if isinstance(new_q.options, str)
                else new_q.options
            )
        except:
            pass

    return render_template(
        "exam.html",
        question=new_q,
        options=options_dict,
        session=session,
        index=session.current_question_index + 1,
        total=QUESTIONS_PER_MODULE,
    )
