import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.encryption import CompanyKeyDecryptionError

logger = logging.getLogger(__name__)

from app.routers import auth, activity, notifications, docvault, auditease, auditor_engagements, compliance, users, custom_fields, assets, asset_masters, asset_acquisitions, asset_documents, sales, kra, company, company_smtp, health, financial_years, depreciation, asset_reports, leads

app = FastAPI(
    title="Kubera V1",
    description="Backend API for Kubera — docVault, AuditEase, SecretarialEase, ROC Compliance",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Explicit origins only. With `allow_origins=["*"]` and `allow_credentials=True`,
# Starlette reflects the caller's Origin back in Access-Control-Allow-Origin — a
# request from https://evil.example was answered with
# `access-control-allow-origin: https://evil.example` and
# `access-control-allow-credentials: true`.
#
# In production the SPA is served from the same origin as the API, so nothing here
# is needed for normal operation; it exists for the Vite dev server, which is why
# CORS_ALLOWED_ORIGINS is the only way to widen it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins(),
    allow_credentials=True,
    allow_methods=["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"],
    allow_headers=["Authorization", "Content-Type", "X-Internal-API-Key"],
)

app.include_router(health.router)
app.include_router(leads.router)
app.include_router(auth.router)
app.include_router(company.router)
app.include_router(company_smtp.router)
app.include_router(users.router)
app.include_router(custom_fields.router)
app.include_router(financial_years.router)
app.include_router(depreciation.router)
app.include_router(asset_reports.router)
app.include_router(asset_masters.router)
app.include_router(assets.router)
app.include_router(asset_acquisitions.router)
app.include_router(asset_documents.router)
app.include_router(sales.router)
app.include_router(kra.router)
app.include_router(activity.router)
app.include_router(notifications.router)
app.include_router(docvault.router)
app.include_router(auditease.router)
app.include_router(auditor_engagements.router)
app.include_router(compliance.secretarial_router)
app.include_router(compliance.roc_router)


@app.exception_handler(CompanyKeyDecryptionError)
async def _company_key_decryption_error_handler(request: Request, exc: CompanyKeyDecryptionError):
    # A KEK mismatch is a server misconfiguration, not a client mistake — surface
    # it as a 500 with an actionable message, and log it loudly server-side rather
    # than letting it look like a generic unhandled exception.
    logger.error("company KEK decryption failed on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=500, content={"detail": str(exc)})
