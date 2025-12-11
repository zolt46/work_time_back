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

# 🔥 CORS 허용할 origin을 여기서 직접 지정
origins = [
    "https://zolt46.github.io",  # GitHub Pages 프론트
    "http://localhost:5500",     # 로컬 테스트용 (쓰면 두고, 아니면 지워도 됨)
    "http://127.0.0.1:5500",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,     # ← settings 말고 위에 정의한 origins 사용
    allow_credentials=False,   # 쿠키 안 쓰면 False로 두는 게 안전/간단
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
