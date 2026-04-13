# AI Voice Interview Bot

## Setup (one time)

```bash
# 1. Install system dependency
sudo apt install ffmpeg        # Linux
brew install ffmpeg            # macOS

# 2. Install Python packages
pip install flask flask-cors openai-whisper pyttsx3 groq pydub soundfile numpy

# 3. Get a FREE Groq API key at console.groq.com → API Keys
export GROQ_API_KEY=gsk_...    # Linux/macOS
set GROQ_API_KEY=gsk_...       # Windows

# 4. Run
python app.py
```

Open http://localhost:5000

## How it works

1. **Setup screen** — pick your job role, experience, test type, question count
2. **Groq (Llama-3.3-70b)** generates a real first question for your role
3. **You answer** by voice (mic) or text
4. **pydub + ffmpeg** converts browser WebM audio → 16kHz WAV (fixes the transcription bug)
5. **Whisper `base`** transcribes your speech to text
6. **Groq** analyses the answer: sentiment, emotion, quality score, plagiarism risk → decides next difficulty → writes next question
7. **pyttsx3** speaks every question and the final feedback aloud
8. After all questions, **Groq** generates personalised spoken feedback + resources

## What's real vs the old version

| Old version | This version |
|---|---|
| Hardcoded question bank | Groq generates questions for YOUR specific role |
| Fake sentiment (DistilBERT on hardcoded text) | Groq reads your actual answer and evaluates it |
| WebM audio → Whisper fails | pydub converts WebM → WAV first |
| Rule-based difficulty | Groq decides difficulty based on answer quality |
| Template feedback | Groq writes personalised feedback |
