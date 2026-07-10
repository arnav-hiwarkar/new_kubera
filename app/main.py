from fastapi import FastAPI

from app.routers import auth, activity, notifications, docvault, auditease, auditor_engagements, compliance, users, custom_fields, assets, sales, kra

app = FastAPI(
    title="Kubera V1",
    description="Backend API for Kubera — docVault, AuditEase, SecretarialEase, ROC Compliance",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(custom_fields.router)
app.include_router(assets.router)
app.include_router(sales.router)
app.include_router(kra.router)
app.include_router(activity.router)
app.include_router(notifications.router)
app.include_router(docvault.router)
app.include_router(auditease.router)
app.include_router(auditor_engagements.router)
app.include_router(compliance.secretarial_router)
app.include_router(compliance.roc_router)
