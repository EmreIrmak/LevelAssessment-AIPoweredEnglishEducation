import os
from groq import Groq
from flask import current_app
import json
import re


class NLPService:
    @staticmethod
    def _get_client():
        api_key = current_app.config.get("GROQ_API_KEY")
        if not api_key:
            return None
        return Groq(api_key=api_key)

    @staticmethod
    def generate_adaptive_question(module, difficulty):
        client = NLPService._get_client()
        if not client:
            return None

        # Modüle göre prompt özelleştirme
        target_prompt = module
        if module == "Listening":
            target_prompt = "Reading (Simulate a listening transcript context, start with 'Audio Script:')"
        elif module == "Speaking":
            target_prompt = (
                "Writing (Simulate a speaking prompt like 'Describe your...')"
            )

        # Llama 3 için Sistem Mesajı (Kuralları buraya yazıyoruz)
        system_prompt = """
        You are an expert English Exam Creator.
        Your ONLY job is to output valid JSON.
        Do NOT write explanations. Do NOT write code blocks. Just raw JSON.
        """

        # Kullanıcı Mesajı (Görevi buraya yazıyoruz)
        user_prompt = f"""
        Create 1 single multiple-choice or open-ended question.
        Level: {difficulty}
        Module: {target_prompt}
        Language: English Only.

        REQUIRED JSON FORMAT:
        {{
            "text": "Question text...",
            "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}}, (null if Writing/Speaking)
            "correct_answer": "A", (null if Writing/Speaking)
            "question_type": "MULTIPLE_CHOICE" (or "OPEN_ENDED")
        }}
        """

        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model="llama-3.3-70b-versatile",  # Çok hızlı ve ücretsiz model
                temperature=0.5,  # Yaratıcılık ayarı (Düşük olması JSON kararlılığını artırır)
            )

            response_content = chat_completion.choices[0].message.content.strip()

            # Bazen ```json etiketi koyar, temizleyelim
            if "```" in response_content:
                response_content = re.sub(r"```json\s*|\s*```", "", response_content)

            # JSON'ı temizle (Llama bazen en sona açıklama ekler, sadece { } arasını alalım)
            json_match = re.search(r"\{.*\}", response_content, re.DOTALL)
            if json_match:
                response_content = json_match.group(0)

            return json.loads(response_content)

        except Exception as e:
            print(f"Groq API Error: {e}")
            return None

    @staticmethod
    def evaluate_open_ended(question_text, user_answer, current_level):
        client = NLPService._get_client()
        if not client:
            return True

        system_prompt = 'You are an English teacher evaluator. Output ONLY JSON: {"passed": true} or {"passed": false}.'

        user_prompt = f"""
        Question: {question_text}
        Student Answer: {user_answer}
        Target Level: {current_level}
        
        Is this answer acceptable?
        """

        try:
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model="llama3-8b-8192",
                temperature=0.1,
            )

            text = chat_completion.choices[0].message.content.strip()
            # Temizlik
            json_match = re.search(r"\{.*\}", text, re.DOTALL)
            if json_match:
                text = json_match.group(0)

            return json.loads(text).get("passed", False)
        except:
            return False
