import os
import requests
from datetime import datetime
from flask import Flask, request, Response, jsonify
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
from pydub import AudioSegment
from dotenv import load_dotenv

# Load environment variables from dev.env
load_dotenv("dev.env")

# ------------------- Config -------------------
DOWNLOAD_DIR = "recordings"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Twilio credentials from dev.env
ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")
NGROK_URL = os.getenv("NGROK_URL") 

if not all([ACCOUNT_SID, AUTH_TOKEN, TWILIO_NUMBER, NGROK_URL]):
    raise ValueError("Missing required environment variables: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_NUMBER, or NGROK_URL")

client = Client(ACCOUNT_SID, AUTH_TOKEN)
app = Flask(__name__)

DEFAULT_QUESTIONS = [
    "Please say your name.",
    "Please say your age.",
    "Do you want to book an appointment?"
]

# In-memory state for local testing
call_questions = {}  # {call_sid: {"questions": [...], "current": 0, "to_number": str, "call_ended": bool}}

# ------------------- Helpers -------------------
def generate_filename(phone_number):
    ts = datetime.now().strftime("%d_%m_%Y_%H_%M_%S")
    return os.path.join(DOWNLOAD_DIR, f"{phone_number}_{ts}.mp3")

def download_recording(recording_url, file_name):
    url = f"{recording_url}.mp3"
    try:
        r = requests.get(url, auth=(ACCOUNT_SID, AUTH_TOKEN), stream=True)
        if r.status_code == 200:
            temp_file = file_name + ".temp"
            with open(temp_file, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            audio = AudioSegment.from_mp3(temp_file)
            audio = audio + 5  # Boost volume
            audio.export(file_name, format="mp3", bitrate="192k")
            os.remove(temp_file)
            print(f"✅ Recording saved: {file_name}")
            return True
        else:
            print(f"❌ Failed to download recording: HTTP {r.status_code}, Response: {r.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ Error downloading recording: {str(e)}")
        return False

# ------------------- Endpoints -------------------
@app.route("/test", methods=["GET"])
def test():
    return "Flask is working ✅", 200

@app.route("/start_call", methods=["POST"])
def start_call():
    data = request.json
    to_number = data.get("to")
    questions = data.get("questions", DEFAULT_QUESTIONS)

    if not to_number:
        print("❌ Missing 'to' number in request")
        return jsonify({"error": "Missing 'to' number"}), 400

    try:
        call = client.calls.create(
            to=to_number,
            from_=TWILIO_NUMBER,
            url=f"{NGROK_URL}/voice",
            record=True,
            recording_channels="dual",
            recording_status_callback=f"{NGROK_URL}/recording_status",
            recording_status_callback_method="POST"
        )
        call_questions[call.sid] = {
            "questions": questions,
            "current": 0,
            "to_number": to_number,
            "call_ended": False
        }
        print(f"📞 Call started: {call.sid} to {to_number}, State: {call_questions[call.sid]}")
        return jsonify({"message": "Call started", "call_sid": call.sid})
    except Exception as e:
        print(f"❌ Error starting call: {str(e)}")
        return jsonify({"error": "Failed to start call"}), 500

@app.route("/voice", methods=["GET", "POST"])
def voice():
    call_sid = request.values.get("CallSid")
    state = call_questions.get(call_sid)
    resp = VoiceResponse()

    if not state:
        resp.say("No questions configured. Goodbye!", voice="Polly.Joanna")
        resp.hangup()
        print(f"❌ No state for CallSid: {call_sid}, State dict: {call_questions}")
        return Response(str(resp), mimetype="application/xml")

    if state["current"] == 0:
        resp.say("Please find a quiet place and answer each question after the beep.", voice="Polly.Joanna")

    current_index = state["current"]
    question = state["questions"][current_index]
    resp.say(question, voice="Polly.Joanna")
    resp.record(
        action=f"{NGROK_URL}/handle_answer?call_sid={call_sid}",
        max_length=10,
        play_beep=True,
        timeout=3,  # Reduced for faster transitions
        trim="trim-silence"  # Trim trailing silence
    )

    print(f"📜 Asking question {current_index + 1} ('{question}') for CallSid: {call_sid}, State: {state}")
    return Response(str(resp), mimetype="application/xml")

@app.route("/handle_answer", methods=["GET", "POST"])
def handle_answer():
    start_time = datetime.now()
    call_sid = request.args.get("call_sid")
    state = call_questions.get(call_sid)
    resp = VoiceResponse()

    if not state:
        resp.say("Error. Goodbye!", voice="Polly.Joanna")
        resp.hangup()
        print(f"❌ No state for CallSid: {call_sid}, State dict: {call_questions}, Request: {request.values}")
        return Response(str(resp), mimetype="application/xml")

    recording_duration = request.values.get("RecordingDuration", "0")
    duration = float(recording_duration) if recording_duration.replace(".", "").isdigit() else 0
    recording_url = request.values.get("RecordingUrl", "None")
    call_status = request.values.get("CallStatus", "unknown")
    print(f"📜 Answer for question {state['current'] + 1} ('{state['questions'][state['current']]}'): Duration={duration}s, RecordingUrl={recording_url}, CallStatus={call_status}, State: {state}, Request: {request.values}")

    state["current"] += 1

    if state["current"] < len(state["questions"]):
        question = state["questions"][state["current"]]
        resp.say(question, voice="Polly.Joanna")
        resp.record(
            action=f"{NGROK_URL}/handle_answer?call_sid={call_sid}",
            max_length=10,
            play_beep=True,
            timeout=3,
            trim="trim-silence"
        )
    else:
        resp.say("Thank you. Goodbye!", voice="Polly.Joanna")
        resp.hangup()
        state["call_ended"] = True

    duration_log = (datetime.now() - start_time).total_seconds()
    print(f"📜 handle_answer took {duration_log:.3f} seconds for CallSid: {call_sid}")
    return Response(str(resp), mimetype="application/xml")

@app.route("/recording_status", methods=["GET", "POST"])
def recording_status():
    print(f"📜 Recording status callback: {request.values}")
    recording_status = request.values.get("RecordingStatus")
    if recording_status != "completed":
        print(f"ℹ️ Recording status: {recording_status}, skipping download")
        return "ok", 200

    recording_url = request.values.get("RecordingUrl")
    call_sid = request.values.get("CallSid")
    state = call_questions.get(call_sid)

    if not state:
        print(f"⚠️ No state found for CallSid: {call_sid}, State dict: {call_questions}")
        if recording_url and call_sid:
            final_file = generate_filename(f"unknown_{call_sid}")
            success = download_recording(recording_url, final_file)
            if not success:
                print(f"❌ Failed to save recording for CallSid: {call_sid}")
        return "ok", 200

    to_number = state["to_number"]
    final_file = generate_filename(to_number)

    if recording_url:
        success = download_recording(recording_url, final_file)
        if not success:
            print(f"❌ Failed to save recording for CallSid: {call_sid}")
    else:
        print(f"❌ No RecordingUrl provided for CallSid: {call_sid}")

    if state.get("call_ended", False):
        call_questions.pop(call_sid, None)
        print(f"🗑️ Cleaned up state for CallSid: {call_sid}")

    return "ok", 200

@app.route("/status", methods=["POST"])
def status():
    print("📞 Call Status Update:", dict(request.form))
    return "ok", 200

# ------------------- Run Flask -------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)