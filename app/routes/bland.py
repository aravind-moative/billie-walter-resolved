import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agent import UtilityAgent

bland_router = APIRouter()

agent = UtilityAgent()


class BlandWebhookRequest(BaseModel):
    user_input: str


class BlandWebhookResponse(BaseModel):
    reply: str


@bland_router.post("/webhook/bland", response_model=BlandWebhookResponse)
async def bland_webhook(request_data: BlandWebhookRequest):
    user_input = request_data.user_input
    phone_number = "7550026048"  # Hardcoded phone number

    try:
        response = agent.process_message(user_input, phone_number, "1234567890")
        return BlandWebhookResponse(reply=response)
    except Exception as e:
        logging.error(f"Error processing message: {e!s}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing the message"
        )
