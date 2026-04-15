from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.config import settings
from app.database import engine, Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (dev convenience; use Alembic in production)
    Base.metadata.create_all(bind=engine)
    # Ensure data directory exists for SQLite
    Path("data").mkdir(exist_ok=True)
    Path("data/qr_codes").mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for QR codes
app.mount("/static", StaticFiles(directory="data"), name="static")

# Import and register routers
from app.api.v1 import (
    assets,
    categories,
    licenses,
    subscriptions,
    ip_addresses,
    certificates,
    consumables,
    maintenance,
    racks,
    dashboard,
    notifications,
    import_export,
    qr,
    auth,
    locations,
    departments,
    vendors,
    audit_logs,
)

api_prefix = settings.API_V1_PREFIX

app.include_router(auth.router, prefix=api_prefix, tags=["Auth"])
app.include_router(dashboard.router, prefix=api_prefix, tags=["Dashboard"])
app.include_router(assets.router, prefix=api_prefix, tags=["Assets"])
app.include_router(categories.router, prefix=api_prefix, tags=["Categories"])
app.include_router(locations.router, prefix=api_prefix, tags=["Locations"])
app.include_router(departments.router, prefix=api_prefix, tags=["Departments"])
app.include_router(vendors.router, prefix=api_prefix, tags=["Vendors"])
app.include_router(licenses.router, prefix=api_prefix, tags=["Licenses"])
app.include_router(subscriptions.router, prefix=api_prefix, tags=["Subscriptions"])
app.include_router(ip_addresses.router, prefix=api_prefix, tags=["IP Addresses"])
app.include_router(certificates.router, prefix=api_prefix, tags=["Certificates"])
app.include_router(consumables.router, prefix=api_prefix, tags=["Consumables"])
app.include_router(maintenance.router, prefix=api_prefix, tags=["Maintenance"])
app.include_router(racks.router, prefix=api_prefix, tags=["Racks"])
app.include_router(notifications.router, prefix=api_prefix, tags=["Notifications"])
app.include_router(import_export.router, prefix=api_prefix, tags=["Import/Export"])
app.include_router(qr.router, prefix=api_prefix, tags=["QR Codes"])
app.include_router(audit_logs.router, prefix=api_prefix, tags=["Audit Logs"])


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
