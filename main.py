# File: /backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app import models
from backend.app.deps import engine
from backend.app.routers import auth, users, schedule, requests, admin

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Dasan Shift Manager")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"]);

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(schedule.router)
app.include_router(requests.router)
app.include_router(admin.router)


@app.get("/")
def root():
    return {"message": "Dasan Shift Manager API"}
