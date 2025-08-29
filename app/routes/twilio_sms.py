from fastapi import APIRouter, Form
from fastapi.responses import PlainTextResponse
from twilio.twiml.messaging_response import MessagingResponse

from app.agent import UtilityAgent

sms_router = APIRouter()

agent = UtilityAgent()


@sms_router.post("/sms")
async def sms_reply(
    From: str = Form(...),
    Body: str = Form(...)
):
    from_number = From.replace("+91", "").replace("+1", "").strip()
    body = Body.strip()
    print(f"SMS from {from_number}: {body}")

    # Get response from your agent
    response_text = agent.process_message(body, from_number, from_number)

    # Build Twilio XML response
    response = MessagingResponse()
    response.message(response_text)

    return PlainTextResponse(str(response), media_type="application/xml")
