from fastapi import FastAPI

from app.routers import auth, activity, notifications, docvault

app = FastAPI(
    title="Kubera V1",
    description="Backend API for Kubera — docVault, AuditEase, SecretarialEase, ROC Compliance",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(auth.router)
app.include_router(activity.router)
app.include_router(notifications.router)
app.include_router(docvault.router)
