from fastapi import APIRouter, WebSocket

from app.api.v1.transcription import TranscriptionService

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    service = TranscriptionService(websocket)
    await service.run()
