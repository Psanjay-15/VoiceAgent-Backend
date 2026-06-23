from fastapi import FastAPI
from app.core.logging import get_logger
app = FastAPI()
log = get_logger(__name__)

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

