from fastapi import APIRouter, WebSocket

from app.api.v1.transcription import TranscriptionService
from app.services.security import get_email_from_token

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    user_email = get_email_from_token(websocket.query_params.get("token"))
    service = TranscriptionService(websocket, user_email=user_email)
    await service.run()
