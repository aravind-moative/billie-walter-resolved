import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, Form, Response
from fastapi.responses import PlainTextResponse
from twilio.twiml.voice_response import Gather, VoiceResponse

from app.agent import UtilityAgent
from app.config import config
from app.utilities.instances import get_tts

twilio_router = APIRouter()

agent = UtilityAgent()


def save_audio_to_file(audio_data, filename="out.mp3"):
    path = Path("static") / filename
    with Path(path).open("wb") as f:
        for chunk in audio_data:
            f.write(chunk)
    return f"/static/{filename}"


def log_call_to_csv(from_number, call_sid, duration, status):
    csv_path = Path("logs") / "call_logs.csv"
    Path("logs").mkdir(exist_ok=True)

    # Check if file exists to determine if we need to write headers
    file_exists = Path(csv_path).is_file()

    with Path(csv_path).open("a", newline="") as csvfile:
        fieldnames = ["timestamp", "from_number", "call_sid", "duration", "status"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        writer.writerow(
            {
                "timestamp": datetime.now().isoformat(),
                "from_number": from_number,
                "call_sid": call_sid,
                "duration": duration,
                "status": status,
            },
        )


@twilio_router.post("/phone")
async def voice(
    From: str = Form(...),
    CallSid: Optional[str] = Form(None)
):
    from_number = From
    print(f"Incoming call from: {from_number}")

    response = VoiceResponse()
    gather = Gather(input="speech", action="/gather", method="POST", timeout=5)

    # Generate audio for welcome message
    audio_data = get_tts().convert_text_to_speech(
        "Hi there, this is Billie. How can I help you today?",
    )
    audio_url = save_audio_to_file(audio_data)

    gather.play(f"{config.BASE_URL}{audio_url}")
    response.append(gather)
    response.redirect("/voice")
    return PlainTextResponse(str(response), media_type="application/xml")


@twilio_router.post("/gather")
async def gather(
    SpeechResult: Optional[str] = Form(None),
    From: str = Form(...)
):
    user_input = SpeechResult or ""
    phone_number = From.replace("+91", "").replace("+1", "").strip()

    print(f"User ({phone_number}) said: {user_input}")
    response_text = agent.process_message(user_input, phone_number, "1234567890")

    # Generate audio for response
    audio_data = get_tts().convert_text_to_speech(response_text)
    audio_url = save_audio_to_file(audio_data)

    if "quit" in user_input.lower():
        response = VoiceResponse()
        response.play(f"{config.BASE_URL}{audio_url}")
        response.hangup()
        return PlainTextResponse(str(response), media_type="application/xml")

    response = VoiceResponse()
    response.play(f"{config.BASE_URL}{audio_url}")

    gather = Gather(input="speech", action="/gather", method="POST", timeout=5)
    response.append(gather)

    return PlainTextResponse(str(response), media_type="application/xml")


@twilio_router.post("/call-status")
async def call_status(
    From: Optional[str] = Form(None),
    CallSid: Optional[str] = Form(None),
    CallDuration: Optional[str] = Form(None),
    CallStatus: Optional[str] = Form(None)
):
    from_number = From
    call_sid = CallSid
    duration = CallDuration  # Only available when CallStatus is 'completed'
    status = CallStatus
    print(f"Call {call_sid} ended with status {status} and duration {duration} seconds")

    # Log the call data to CSV
    log_call_to_csv(from_number, call_sid, duration, status)

    return Response(status_code=204)
