from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.auth import router as auth_router
from app.api.v1.google_auth import router as google_auth_router
from app.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.mongodb import close_mongo_connection, connect_to_mongo
from app.websocket import router as ws_router

configure_logging()
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await connect_to_mongo()
    yield
    await close_mongo_connection()


app = FastAPI(lifespan=lifespan)

if settings.cors_origins_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(google_auth_router)
app.include_router(auth_router)
app.include_router(ws_router)


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
