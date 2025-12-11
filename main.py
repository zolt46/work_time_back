# File: main.py  (work_time_back 레포 루트에 있는 그 main.py 기준)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models
from app.config import get_settings
from app.deps import engine
from app.routers import admin, auth, requests, schedule, users

settings = get_settings()
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.PROJECT_NAME)

# ✅ CORS: 일단 * 전체 허용 + credentials 안 씀
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # <- 일단 전부 허용
    allow_credentials=False,
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

@app.get("/cors-test")
def cors_test():
    return {"cors": "ok"}