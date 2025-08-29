import logging
import sqlite3
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from openai import OpenAI

from app.agent import UtilityAgent
from app.routes.auth import get_current_user
from app.utilities.instances import (
    get_admin_db_manager,
    get_db_manager,
    get_tts,
)

api_router = APIRouter()

logger = logging.getLogger(__name__)
agent = UtilityAgent()


# Pydantic models for request/response
class ChatRequest(BaseModel):
    message: str
    phone_number: str
    session_id: Optional[str] = None
    use_tts: bool = False


class ChatResponse(BaseModel):
    response: str
    audio_url: Optional[str] = None


class ClearDataRequest(BaseModel):
    phone_number: str
    session_id: Optional[str] = None


class ClearDataResponse(BaseModel):
    message: str


class TranscribeRequest(BaseModel):
    phone_number: str


class TranscribeResponse(BaseModel):
    text: str


class VerifyPhoneRequest(BaseModel):
    phone_number: str


class VerifyPhoneResponse(BaseModel):
    verified: bool
    customer_data: Optional[dict] = None
    message: str


@api_router.post("/chat", response_model=ChatResponse)
async def chat(
    request_data: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    try:
        user_message = request_data.message
        phone_number = request_data.phone_number
        session_id = request_data.session_id
        use_tts = request_data.use_tts

        if not user_message:
            logger.error("No message provided in request")
            raise HTTPException(status_code=400, detail="No message provided")
        if not phone_number:
            logger.error("No phone number provided in request")
            raise HTTPException(status_code=400, detail="No phone number provided")

        logger.info(f"=== Processing message with phone number: {phone_number} ===")
        logger.info(f"Session ID: {session_id}")
        logger.debug(f"Input message: {user_message}")

        try:
            response = agent.process_message(user_message, phone_number, session_id)
            logger.info("Successfully processed message")

            if use_tts:
                audio_data = get_tts().convert_text_to_speech(response)
                audio_bytes = b"".join(chunk for chunk in audio_data)

                with tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=".mp3",
                ) as temp_file:
                    temp_file.write(audio_bytes)
                    temp_filename = temp_file.name

                return ChatResponse(
                    response=response,
                    audio_url=f"/api/audio/{Path(temp_filename).name}"
                )

            return ChatResponse(response=response)
        except ValueError as ve:
            logger.error(f"Validation error: {ve!s}", exc_info=True)
            raise HTTPException(status_code=400, detail=str(ve))
        except sqlite3.Error as dbe:
            logger.error(f"Database error: {dbe!s}", exc_info=True)
            raise HTTPException(status_code=500, detail="Database error occurred. Please try again.")
        except Exception as e:
            logger.error(f"Error processing message: {e!s}", exc_info=True)
            raise HTTPException(status_code=500, detail="An unexpected error occurred. Please try again.")
    except Exception as e:
        logger.error(f"Unexpected error in chat route: {e!s}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred. Please try again.")


@api_router.get("/audio/{filename}")
async def get_audio(
    filename: str,
    current_user: dict = Depends(get_current_user)
):
    """Serve the audio file."""
    file_path = Path(tempfile.gettempdir()) / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(
        path=file_path,
        media_type="audio/mpeg",
        filename=filename
    )


@api_router.post("/clear-data", response_model=ClearDataResponse)
async def clear_data(
    request_data: ClearDataRequest,
    current_user: dict = Depends(get_current_user)
):
    try:
        phone_number = request_data.phone_number
        session_id = request_data.session_id

        logger.info(f"=== Clearing data for phone number: {phone_number} ===")
        logger.info(f"Session ID: {session_id}")

        # Clear agent memory
        agent.clear_memory(session_id)
        logger.info("Successfully cleared memory")

        # Clear phone verification records for this session
        if phone_number:
            db_manager = get_db_manager()
            db_manager.clear_phone_verifications_by_session(session_id)
            logger.info(f"Cleared phone verification records for session: {session_id}")

        return ClearDataResponse(message="Chat state reset successfully")

    except Exception as e:
        logger.error(f"Error clearing memory: {e!s}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while clearing memory. Please try again."
        )


@api_router.post("/clear-phone-verifications", response_model=ClearDataResponse)
async def clear_phone_verifications(
    current_user: dict = Depends(get_current_user)
):
    """Clear all phone verification records - called when browser tab closes"""
    try:
        logger.info("=== Clearing all phone verification records ===")
        
        db_manager = get_db_manager()
        db_manager.clear_all_phone_verifications()
        logger.info("Successfully cleared all phone verification records")

        return ClearDataResponse(message="Phone verification records cleared successfully")

    except Exception as e:
        logger.error(f"Error clearing phone verifications: {e!s}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while clearing phone verifications. Please try again."
        )


@api_router.delete("/delete-outage/{reference_number}")
async def delete_outage(
    reference_number: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        success = get_db_manager().delete_outage(reference_number)
        if success:
            return {"message": "Outage deleted successfully"}
        raise HTTPException(status_code=404, detail="Outage not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/delete-account/{account_id}")
async def delete_account(
    account_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        success = get_db_manager().delete_customer(account_id)
        if success:
            return {"message": "Account deleted successfully"}
        raise HTTPException(status_code=404, detail="Account not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/delete-admin/{email}")
async def delete_admin(
    email: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        success = get_admin_db_manager().delete_admin(email)
        if success:
            return {"message": "Admin deleted successfully"}
        raise HTTPException(status_code=404, detail="Admin not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/verify-phone", response_model=VerifyPhoneResponse)
async def verify_phone(
    request_data: VerifyPhoneRequest
):
    """Verify if a phone number exists in the database"""
    try:
        phone_number = request_data.phone_number
        
        if not phone_number:
            raise HTTPException(status_code=400, detail="No phone number provided")
        
        # Validate phone number format
        if not phone_number.isdigit() or len(phone_number) != 10:
            return VerifyPhoneResponse(
                verified=False,
                message="Please provide a valid 10-digit phone number"
            )
        
        # Check if phone number exists in database and verify it
        db_manager = get_db_manager()
        logger.info(f"Checking database for phone number: {phone_number}")
        customer = db_manager.get_customer_by_phone(phone_number)
        logger.info(f"Database result: {customer}")
        
        if customer:
            # Verify the phone number in the database
            verification_success = db_manager.verify_phone_number(phone_number)
            logger.info(f"Phone verification result: {verification_success}")
            
            if not verification_success:
                return VerifyPhoneResponse(
                    verified=False,
                    message="Failed to verify phone number in database"
                )
            # Get billing information
            billing_info = db_manager.get_billing_by_customer_id(customer.account_id)
            
            # Prepare customer data
            customer_data = {
                "name": customer.name,
                "phone": customer.phone,
                "account_id": customer.account_id,
                "account_type": customer.account_type,
                "status": customer.status,
                "language": customer.language,
                "recovery_rate": customer.recovery_rate,
                "tax_jurisdiction_mapping_code": customer.tax_jurisdiction_mapping_code,
                "address": customer.address,
                "zip_code": customer.zip_code,
                "created_at": customer.created_at.isoformat() if customer.created_at else None,
                "billing_info": {
                    "current_balance": billing_info.current_balance if billing_info else None,
                    "raw_balance": billing_info.raw_balance if billing_info else None,
                    "unpaid_debt_recovery": billing_info.unpaid_debt_recovery if billing_info else None,
                    "days_left": billing_info.days_left if billing_info else None,
                    "last_payment_date": billing_info.last_payment_date.isoformat() if billing_info and billing_info.last_payment_date else None,
                    "last_payment_amount": billing_info.last_payment_amount if billing_info else None
                } if billing_info else None
            }
            
            logger.info(f"Phone number {phone_number} verified successfully for customer {customer.name}")
            return VerifyPhoneResponse(
                verified=True,
                customer_data=customer_data,
                message=f"Phone number verified successfully for {customer.name}"
            )
        else:
            logger.info(f"Phone number {phone_number} not found in database")
            return VerifyPhoneResponse(
                verified=False,
                message="Phone number not found in our system. Please check the number or contact support."
            )
            
    except Exception as e:
        logger.error(f"Error verifying phone number: {e!s}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while verifying the phone number. Please try again."
        )


@api_router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    audio: UploadFile = File(...),
    phone_number: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    try:
        if not audio:
            raise HTTPException(status_code=400, detail="No audio file provided")

        if not phone_number:
            raise HTTPException(status_code=400, detail="No phone number provided")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            content = await audio.read()
            temp_file.write(content)
            temp_filename = temp_file.name

        try:
            client = OpenAI()
            with Path(temp_filename).open("rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text",
                )
                logger.info(f"Transcription completed: {transcription}")
                return TranscribeResponse(text=transcription)
        finally:
            Path(temp_filename).unlink()

    except Exception as e:
        logger.error(f"Error in transcription: {e!s}", exc_info=True)
        raise HTTPException(status_code=500, detail="An error occurred during transcription")
