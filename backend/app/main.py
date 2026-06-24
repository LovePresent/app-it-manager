from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.config import settings
from app.database import engine, Base
from app.models import user, category, common, asset, license, subscription
from app.models import ip_address, certificate, consumable, maintenance
from app.models import rack, network, audit_log, notification, device_inventory, ai_subscription

DATA_DIR = Path("data")
QR_CODES_DIR = DATA_DIR / "qr_codes"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (dev convenience; use Alembic in production)
    Base.metadata.create_all(bind=engine)
    DATA_DIR.mkdir(exist_ok=True)
    QR_CODES_DIR.mkdir(parents=True, exist_ok=True)
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

# Expose only generated QR images. Do not serve the whole data directory,
# because it also contains the SQLite database file.
app.mount("/static/qr_codes", StaticFiles(directory=QR_CODES_DIR), name="qr_codes")

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
    local_auth,
    devices,
    ai_subscriptions,
    locations,
    departments,
    vendors,
    audit_logs,
    users,
    system,
)

api_prefix = settings.API_V1_PREFIX

app.include_router(auth.router, prefix=api_prefix, tags=["Auth"])
if settings.LOCAL_LOGIN_ENABLED:
    app.include_router(local_auth.router, prefix=api_prefix, tags=["Local Auth"])
app.include_router(dashboard.router, prefix=api_prefix, tags=["Dashboard"])
app.include_router(devices.router, prefix=api_prefix, tags=["Devices"])
app.include_router(assets.router, prefix=api_prefix, tags=["Assets"])
app.include_router(categories.router, prefix=api_prefix, tags=["Categories"])
app.include_router(locations.router, prefix=api_prefix, tags=["Locations"])
app.include_router(departments.router, prefix=api_prefix, tags=["Departments"])
app.include_router(vendors.router, prefix=api_prefix, tags=["Vendors"])
app.include_router(licenses.router, prefix=api_prefix, tags=["Licenses"])
app.include_router(subscriptions.router, prefix=api_prefix, tags=["Subscriptions"])
app.include_router(ai_subscriptions.router, prefix=api_prefix, tags=["AI Subscriptions"])
app.include_router(ip_addresses.router, prefix=api_prefix, tags=["IP Addresses"])
app.include_router(certificates.router, prefix=api_prefix, tags=["Certificates"])
app.include_router(consumables.router, prefix=api_prefix, tags=["Consumables"])
app.include_router(maintenance.router, prefix=api_prefix, tags=["Maintenance"])
app.include_router(racks.router, prefix=api_prefix, tags=["Racks"])
app.include_router(notifications.router, prefix=api_prefix, tags=["Notifications"])
app.include_router(import_export.router, prefix=api_prefix, tags=["Import/Export"])
app.include_router(qr.router, prefix=api_prefix, tags=["QR Codes"])
app.include_router(audit_logs.router, prefix=api_prefix, tags=["Audit Logs"])
app.include_router(users.router, prefix=api_prefix, tags=["Users"])
app.include_router(system.router, prefix=api_prefix, tags=["System"])


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
