from fastapi import FastAPI
from app.core.logging import get_logger
from app.websocket import router as ws_router

app = FastAPI()
log = get_logger(__name__)
app.include_router(ws_router)


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
