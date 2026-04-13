import ssl
import certifi

ssl._create_default_https_context = ssl._create_unverified_context

import os, uuid, json, re, threading, wave, struct
from functools import wraps
from flask import Flask, request, jsonify, render_template, send_file, session, redirect, url_for, flash
from flask_cors import CORS
import whisper, pyttsx3
import speech_recognition as sr
from groq import Groq
import database as db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "interview-bot-secret-2024")
CORS(app)

RESPONSE_FOLDER = "responses"
os.makedirs(RESPONSE_FOLDER, exist_ok=True)

# ── Init DB ───────────────────────────────────────────────────────────────────
db.init_db()

# ── Load models ───────────────────────────────────────────────────────────────
print("Loading Whisper ...")
whisper_model = whisper.load_model("base")
print("Whisper ready.")
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY", "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"))

# ── Speech recogniser ─────────────────────────────────────────────────────────
recogniser = sr.Recognizer()
recogniser.energy_threshold         = 300
recogniser.dynamic_energy_threshold = True
recogniser.pause_threshold          = 1.5
mic_lock = threading.Lock()

# ── In-memory interview sessions ──────────────────────────────────────────────
interview_sessions: dict = {}

# ─────────────────────────────────────────────────────────────────────────────
# AUTH DECORATORS
# ─────────────────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            return redirect(url_for("user_dashboard"))
        return f(*args, **kwargs)
    return decorated

# ─────────────────────────────────────────────────────────────────────────────
# AUTH ROUTES
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    if "user_id" in session:
        if session.get("role") == "admin":
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("user_dashboard"))
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user     = db.get_user_by_email(email)
        if not user or not db.check_password(password, user["password"]):
            flash("Invalid email or password.", "error")
            return render_template("login.html")
        session["user_id"] = user["id"]
        session["name"]    = user["name"]
        session["role"]    = user["role"]
        if user["role"] == "admin":
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("user_dashboard"))
    return render_template("login.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name           = request.form.get("name", "").strip()
        email          = request.form.get("email", "").strip().lower()
        password       = request.form.get("password", "")
        phone          = request.form.get("phone", "").strip()
        college        = request.form.get("college", "").strip()
        target_company = request.form.get("target_company", "").strip()

        if not all([name, email, password]):
            flash("Name, email and password are required.", "error")
            return render_template("signup.html")

        ok, err = db.create_user(name, email, password, phone, college, target_company)
        if not ok:
            flash(err, "error")
            return render_template("signup.html")

        flash("Account created! Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("signup.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ─────────────────────────────────────────────────────────────────────────────
# USER ROUTES
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/dashboard")
@login_required
def user_dashboard():
    uid        = session["user_id"]
    user       = db.get_user_by_id(uid)
    stats      = db.get_user_stats(uid)
    interviews = db.get_user_interviews(uid)
    rec        = db.get_recommendation(uid)
    return render_template("user_dashboard.html",
                           user=user, stats=stats,
                           interviews=interviews, recommendation=rec)

@app.route("/interview_detail/<int:iid>")
@login_required
def interview_detail(iid):
    iv = db.get_interview_by_id(iid)
    if not iv or iv["user_id"] != session["user_id"]:
        return redirect(url_for("user_dashboard"))
    return render_template("interview_detail.html", iv=iv)

@app.route("/interview")
@login_required
def interview_page():
    return render_template("interview.html")

# ─────────────────────────────────────────────────────────────────────────────
# ADMIN ROUTES
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/admin")
@admin_required
def admin_dashboard():
    users = db.get_all_users()
    return render_template("admin_dashboard.html", users=users)

@app.route("/admin/user/<int:uid>")
@admin_required
def admin_user_detail(uid):
    user       = db.get_user_by_id(uid)
    interviews = db.get_user_interviews(uid)
    stats      = db.get_user_stats(uid)
    rec        = db.get_recommendation(uid)
    if not user:
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_user.html",
                           user=user, interviews=interviews,
                           stats=stats, recommendation=rec)

@app.route("/admin/recommendation/<int:uid>", methods=["POST"])
@admin_required
def save_recommendation(uid):
    content = request.form.get("content", "")
    db.save_recommendation(uid, content)
    flash("Recommendation saved.", "success")
    return redirect(url_for("admin_user_detail", uid=uid))

@app.route("/admin/delete_user/<int:uid>", methods=["POST"])
@admin_required
def delete_user(uid):
    db.delete_user(uid)
    flash("User deleted.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/export/<int:uid>")
@admin_required
def export_user(uid):
    import json as _json
    user       = db.get_user_by_id(uid)
    interviews = db.get_user_interviews(uid)
    rec        = db.get_recommendation(uid)
    data = {
        "user":            user,
        "recommendation":  rec,
        "interviews":      interviews,
    }
    filename = f"user_{uid}_report.json"
    path     = os.path.join(RESPONSE_FOLDER, filename)
    with open(path, "w") as f:
        _json.dump(data, f, indent=2, default=str)
    return send_file(path, as_attachment=True, download_name=filename)

# ─────────────────────────────────────────────────────────────────────────────
# INTERVIEW API  (same as before, now saves to DB on finish)
# ─────────────────────────────────────────────────────────────────────────────
def llm(system: str, user: str, temperature: float = 0.4) -> str:
    resp = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    return resp.choices[0].message.content.strip()

def generate_question(sess: dict) -> str:
    system = ("You are a professional interviewer. "
              "Generate exactly ONE interview question. "
              "Return only the question — no preamble, no numbering.")
    user   = (f"Role: {sess['job_role']}\nExperience: {sess['experience']}\n"
              f"Test type: {sess['test_type']}\nDifficulty: {sess['difficulty']}\n"
              "Ask a focused question appropriate for this role and difficulty.")
    return llm(system, user, temperature=0.6)

def analyse_and_next(sess: dict, question: str, answer: str) -> dict:
    history_text = "".join(
        f"Q: {h['question']}\nA: {h['answer']}\n\n"
        for h in sess["history"][-3:]
    )
    asked   = len(sess["history"]) + 1
    total_q = sess["total_q"]

    system = """You are an expert AI interview evaluator.
Return ONLY valid JSON — no markdown, no extra text.
Schema:
{
  "sentiment": "positive"|"neutral"|"negative",
  "emotion": "confident"|"nervous"|"confused"|"enthusiastic"|"unsure",
  "quality_score": <1-10>,
  "quality_reason": "<one sentence>",
  "plagiarism_risk": "low"|"medium"|"high",
  "next_difficulty": "easy"|"medium"|"hard",
  "done": true|false,
  "next_question": "<question or empty if done>",
  "brief_acknowledgement": "<1 natural spoken sentence>"
}
Raise difficulty if score>=7, lower if <=4. Set done=true when asked equals total."""

    user = (f"Role: {sess['job_role']} | Exp: {sess['experience']} | "
            f"Type: {sess['test_type']} | Difficulty: {sess['difficulty']}\n"
            f"Asked: {asked}/{total_q}\n\nHistory:\n{history_text}"
            f"Q: {question}\nA: {answer}\n\nReturn JSON only.")

    raw = llm(system, user, temperature=0.3)
    raw = re.sub(r"```[a-z]*", "", raw).strip("` \n")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"sentiment":"neutral","emotion":"unsure","quality_score":5,
                "quality_reason":"Parse error.","plagiarism_risk":"low",
                "next_difficulty":sess["difficulty"],"done":asked>=total_q,
                "next_question":"","brief_acknowledgement":"Thank you."}

def generate_feedback(sess: dict) -> str:
    summary = "".join(
        f"Q{i}: {h['question']}\nScore:{(h.get('analysis') or {}).get('quality_score','?')}/10 "
        f"Sentiment:{(h.get('analysis') or {}).get('sentiment','?')} "
        f"Emotion:{(h.get('analysis') or {}).get('emotion','?')}\n\n"
        for i, h in enumerate(sess["history"], 1)
    )
    return llm(
        "You are a professional interview coach. Give honest spoken feedback in 5-7 sentences. "
        "Cover strengths, one area to improve, and one specific resource. Speak naturally.",
        f"Role:{sess['job_role']} ({sess['experience']}) | Type:{sess['test_type']}\n\n{summary}Give feedback now.",
        temperature=0.5
    )

# ── TTS ───────────────────────────────────────────────────────────────────────
_tts_lock = threading.Lock()

def speak(text: str, filename: str) -> str:
    filepath = os.path.join(RESPONSE_FOLDER, filename)
    with _tts_lock:
        engine = None
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", 150)
            engine.setProperty("volume", 1.0)
            voices = engine.getProperty("voices")
            if voices:
                pick = next(
                    (v for v in voices if any(
                        k in v.name.lower() for k in ("zira","david","english","hazel")
                    )), voices[0])
                engine.setProperty("voice", pick.id)
            engine.save_to_file(text, filepath)
            engine.runAndWait()
        except Exception as e:
            print(f"TTS error: {e}")
            _silent_wav(filepath)
        finally:
            if engine:
                try: engine.stop()
                except: pass
    return filepath

def _silent_wav(path):
    with wave.open(path, "w") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
        wf.writeframes(struct.pack("<"+"h"*16000, *([0]*16000)))

# ── Mic ───────────────────────────────────────────────────────────────────────
def record_and_transcribe():
    tmp_path = os.path.join(RESPONSE_FOLDER, "tmp_recording.wav")
    try:
        with sr.Microphone(sample_rate=16000) as source:
            print("Adjusting for ambient noise …")
            recogniser.adjust_for_ambient_noise(source, duration=0.5)
            print("Listening …")
            audio = recogniser.listen(source, timeout=15, phrase_time_limit=60)

        wav_data = audio.get_wav_data(convert_rate=16000, convert_width=2)
        with open(tmp_path, "wb") as f:
            f.write(wav_data)

        if os.path.getsize(tmp_path) < 1000:
            return "", "Recording too short. Please speak louder."

        result = whisper_model.transcribe(tmp_path, language="en", fp16=False)
        text   = result["text"].strip()
        print(f"Transcribed: '{text}'")

        if not text or text in (".", "...", "you", "Thank you."):
            return "", "Could not hear you clearly. Please try again."
        return text, ""

    except sr.WaitTimeoutError:
        return "", "No speech detected. Please speak after clicking the mic."
    except sr.UnknownValueError:
        return "", "Could not understand. Please try again."
    except Exception as e:
        print(f"record error: {e}")
        return "", f"Recording error: {str(e)}"
    finally:
        try:
            if os.path.exists(tmp_path): os.remove(tmp_path)
        except: pass

# ── Interview API routes ──────────────────────────────────────────────────────
@app.route("/api/start", methods=["POST"])
@login_required
def api_start():
    data = request.get_json() or {}
    if not data.get("job_role"):
        return jsonify({"error": "job_role is required"}), 400

    sess = {
        "id":         str(uuid.uuid4()),
        "user_id":    session["user_id"],
        "job_role":   data.get("job_role"),
        "experience": data.get("experience", "mid"),
        "test_type":  data.get("test_type", "mixed"),
        "total_q":    int(data.get("total_q", 6)),
        "history":    [],
        "difficulty": "medium",
        "finished":   False,
    }
    interview_sessions[sess["id"]] = sess

    question = generate_question(sess)
    sess["history"].append({"question": question, "answer": None, "analysis": None})

    audio_file = f"{sess['id']}_q0.wav"
    speak(f"Welcome. Let us begin your {sess['test_type']} interview "
          f"for the role of {sess['job_role']}. Here is your first question. {question}",
          audio_file)

    return jsonify({"session_id": sess["id"], "question": question,
                    "question_num": 1, "total_q": sess["total_q"],
                    "difficulty": sess["difficulty"],
                    "audio_url": f"/audio/{audio_file}"})

@app.route("/api/record", methods=["POST"])
@login_required
def api_record():
    data       = request.get_json() or {}
    session_id = data.get("session_id")
    if not session_id or session_id not in interview_sessions:
        return jsonify({"error": "Invalid session"}), 400
    if not mic_lock.acquire(blocking=False):
        return jsonify({"error": "Already recording."}), 429
    try:
        text, err = record_and_transcribe()
        if err:
            return jsonify({"error": err}), 200
        return jsonify({"transcription": text})
    finally:
        mic_lock.release()

@app.route("/api/answer", methods=["POST"])
@login_required
def api_answer():
    data       = request.get_json() or {}
    session_id = data.get("session_id")
    text       = (data.get("text") or "").strip()

    if not session_id or session_id not in interview_sessions:
        return jsonify({"error": "Invalid session"}), 400
    if not text:
        return jsonify({"error": "No answer text provided"}), 400

    sess = interview_sessions[session_id]
    if sess["finished"]:
        return jsonify({"error": "Interview already finished"}), 400

    current_q = sess["history"][-1]["question"]
    sess["history"][-1]["answer"] = text

    asked      = len(sess["history"])
    force_done = asked >= sess["total_q"]

    analysis = analyse_and_next(sess, current_q, text)
    if force_done:
        analysis["done"] = True

    sess["history"][-1]["analysis"] = analysis
    sess["difficulty"] = analysis.get("next_difficulty", sess["difficulty"])

    if analysis.get("done"):
        sess["finished"] = True
        feedback   = generate_feedback(sess)
        audio_file = f"{session_id}_feedback.wav"
        speak(feedback, audio_file)

        scores = [h["analysis"].get("quality_score", 5)
                  for h in sess["history"] if h.get("analysis")]
        avg = round(sum(scores) / max(len(scores), 1), 1)

        # ── Auto-save to DB ───────────────────────────────────────────────────
        db.save_interview(
            user_id    = sess["user_id"],
            job_role   = sess["job_role"],
            experience = sess["experience"],
            test_type  = sess["test_type"],
            avg_score  = avg,
            history    = sess["history"],
        )

        return jsonify({"transcription": text, "analysis": analysis,
                        "finished": True, "feedback": feedback,
                        "avg_score": avg, "audio_url": f"/audio/{audio_file}"})

    next_q = analysis.get("next_question") or generate_question(sess)
    sess["history"].append({"question": next_q, "answer": None, "analysis": None})

    ack        = analysis.get("brief_acknowledgement", "Thank you.")
    q_index    = len(sess["history"])
    audio_file = f"{session_id}_q{q_index}.wav"
    speak(f"{ack} {next_q}", audio_file)

    return jsonify({"transcription": text, "analysis": analysis,
                    "finished": False, "next_question": next_q,
                    "question_num": q_index, "total_q": sess["total_q"],
                    "difficulty": sess["difficulty"],
                    "audio_url": f"/audio/{audio_file}"})

@app.route("/audio/<filename>")
@login_required
def audio(filename):
    path = os.path.join(RESPONSE_FOLDER, filename)
    if not os.path.exists(path):
        return jsonify({"error": "Not found"}), 404
    return send_file(path, mimetype="audio/wav")

if __name__ == "__main__":
    print("Starting AI Interview Bot → http://localhost:5000")
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False, threaded=True)
