from fastapi import APIRouter, WebSocket

from app.api.v1.transcription import TranscriptionService
from app.config import settings
from app.services.security import get_email_from_token

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    user_email = get_email_from_token(websocket.query_params.get("token"))
    if not user_email:
        user_email = websocket.query_params.get("email")
        user_email = user_email.lower().strip() if user_email else None
    user_email = user_email or settings.default_meeting_email
    service = TranscriptionService(websocket, user_email=user_email)
    await service.run()
