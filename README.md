# LevelAssessment-AIPoweredEnglishEducation

This is a Flask-based **English proficiency level assessment** application.
Roles: **Student / Instructor / Admin**.

## Requirements

- Windows 10/11
- Python 3.10+
- PowerShell

## 1) Run the project (first-time setup)

Open PowerShell and navigate to the project folder:

```powershell
cd "C:\path\to\LevelAssessment-AIPoweredEnglishEducation"
```

### 1.1) Create a virtualenv (if you don't have one)

```powershell
python -m venv venv
```

### 1.2) Activate the virtualenv

```powershell
.\venv\Scripts\Activate.ps1
```

If you get a “script execution is disabled” error:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then run `Activate.ps1` again.

### 1.3) Install dependencies

```powershell
pip install -r requirements.txt
```

## 2) Required / optional configuration (Environment Variables)

### 2.1) Groq API Key (for AI)

Required for AI question generation and reports.

```powershell
$env:GROQ_API_KEY="<YOUR_GROQ_API_KEY>"
```

### 2.2) (Optional) Speech-to-text model

```powershell
$env:GROQ_STT_MODEL="whisper-large-v3"
```

### 2.3) (Optional) Admin/Instructor registration invite codes

Admin/Instructor registration pages are disabled unless invite codes are set.

```powershell
$env:ADMIN_INVITE_CODE="ADM123"
$env:INSTRUCTOR_INVITE_CODE="INS123"
```

### 2.4) (Optional) Exam settings

```powershell
$env:QUESTIONS_VOCABULARY="10"
$env:QUESTIONS_GRAMMAR="10"
$env:QUESTIONS_READING="10"
$env:QUESTIONS_WRITING="1"
$env:QUESTIONS_SPEAKING="3"
# Listening question count is pool/audio-driven (not configured via env)
# Legacy fallback (optional):
# $env:QUESTIONS_PER_MODULE="10"
$env:TIME_LIMIT_GRAMMAR="300"
$env:TIME_LIMIT_VOCABULARY="300"
$env:TIME_LIMIT_READING="420"
$env:TIME_LIMIT_WRITING="600"
$env:TIME_LIMIT_LISTENING="420"
$env:TIME_LIMIT_SPEAKING="420"

# Speaking module timing (in seconds)
$env:SPEAKING_PREP_SECONDS="20"
$env:SPEAKING_RESPONSE_SECONDS="60"
```

## 3) Initialize the database / seed data (recommended)

```powershell
python seed.py
```

## 4) Start the application

```powershell
python run.py
```

Open in your browser:
- `http://127.0.0.1:5000`

## 5) Login / Register URLs (role-based)

### Login
- Student: `http://127.0.0.1:5000/login/student`
- Instructor: `http://127.0.0.1:5000/login/instructor`
- Admin: `http://127.0.0.1:5000/login/admin`

### Register
- Student: `http://127.0.0.1:5000/register/student`
- Instructor: `http://127.0.0.1:5000/register/instructor` (invite code required)
- Admin: `http://127.0.0.1:5000/register/admin` (invite code required)

## 6) Test accounts included by seeding (optional)

If you created the DB using `seed.py`:
- Admin: `admin@englishai.com` / `admin123`
- Instructor: `instructor@englishai.com` / `instructor123`
- Student: `user@test.com` / `123456`

## 7) Admin utilities

- **System Status**: `http://127.0.0.1:5000/admin/system_status`
  - `GROQ_API_KEY present: YES/NO`
  - Groq connectivity check via `models.list()`

- **Generate question bank (B2, 10 questions/module)**:
  - Use the “Generate Question Bank (B2)” button on the Admin dashboard
  - Requires Groq to be configured.

## 8) Common issues

### 8.1) `ModuleNotFoundError: No module named 'flask'`

The virtualenv is not active or dependencies are not installed.

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

### 8.2) “Registration is closed for this role…”

Invite codes are not set.

```powershell
$env:ADMIN_INVITE_CODE="ADM123"
$env:INSTRUCTOR_INVITE_CODE="INS123"
```

Restart the server:

```powershell
taskkill /F /IM python.exe /T
python run.py
```

### 8.3) AI is not working (Groq usage 0)

Most commonly, the server process cannot see `GROQ_API_KEY`.

```powershell
$env:GROQ_API_KEY="<YOUR_GROQ_API_KEY>"
taskkill /F /IM python.exe /T
python run.py
```

Then check: `http://127.0.0.1:5000/admin/system_status`