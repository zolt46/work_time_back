# File: main.py  (work_time_back 레포 루트에 있는 그 main.py 기준)

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app import models
from app.config import get_settings
from app.deps import engine
from app.routers import admin, auth, requests, schedule, users, history
from app.routers import system

settings = get_settings()
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.PROJECT_NAME)

# ✅ CORS: 기본적으로 렌더 배포 + GitHub Pages 등 프런트 도메인을 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_fallback_cors(request, call_next):
    """
    예외 등으로 FastAPI 기본 CORS 처리가 건너뛰더라도
    최소한의 CORS 헤더를 보장해 브라우저에서 차단되지 않도록 한다.
    """
    try:
        response = await call_next(request)
    except Exception as exc:  # pragma: no cover - 런타임 방어
        response = JSONResponse({"detail": "internal_server_error"}, status_code=500)
    origin_header = ",".join(settings.CORS_ALLOW_ORIGINS) if settings.CORS_ALLOW_ORIGINS else "*"
    response.headers.setdefault("Access-Control-Allow-Origin", origin_header)
    response.headers.setdefault("Access-Control-Allow-Headers", "*")
    response.headers.setdefault("Access-Control-Allow-Methods", "*")
    if settings.CORS_ALLOW_CREDENTIALS:
        response.headers.setdefault("Access-Control-Allow-Credentials", "true")
    return response

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(schedule.router)
app.include_router(requests.router)
app.include_router(admin.router)
app.include_router(system.router)
app.include_router(history.router)


@app.get("/")
def root():
    return {"message": "Dasan Shift Manager API"}

@app.get("/cors-test")
def cors_test():
    return {"cors": "ok"}
