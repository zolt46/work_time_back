# File: /backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models
from app.config import get_settings
from app.deps import engine
from app.routers import admin, auth, requests, schedule, users

settings = get_settings()
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.PROJECT_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(schedule.router)
app.include_router(requests.router)
app.include_router(admin.router)


@app.get("/")
def root():
    return {"message": "Dasan Shift Manager API"}
