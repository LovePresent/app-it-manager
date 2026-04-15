from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func as sqlfunc
from datetime import date, timedelta

from app.database import get_db
from app.models.asset import Asset
from app.models.license import SoftwareLicense
from app.models.subscription import CloudSubscription
from app.models.ip_address import IPAddress
from app.models.certificate import Certificate
from app.models.consumable import ConsumableStock
from app.models.maintenance import MaintenanceRecord
from app.models.audit_log import AuditLog
from app.models.category import AssetCategory
from app.schemas.dashboard import DashboardStats, CategoryCount, StatusCount, ExpiringItem
from app.services.notification_service import check_and_create_notifications

router = APIRouter()


@router.get("/dashboard/stats", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db)):
    today = date.today()
    thirty_days = today + timedelta(days=30)

    total_assets = db.query(sqlfunc.count(Asset.id)).scalar() or 0
    assigned = db.query(sqlfunc.count(Asset.id)).filter(Asset.status == "assigned").scalar() or 0
    in_stock = db.query(sqlfunc.count(Asset.id)).filter(Asset.status == "in_stock").scalar() or 0
    in_maint = db.query(sqlfunc.count(Asset.id)).filter(Asset.status == "in_maintenance").scalar() or 0

    total_lic = db.query(sqlfunc.count(SoftwareLicense.id)).scalar() or 0
    exp_lic = db.query(sqlfunc.count(SoftwareLicense.id)).filter(
        SoftwareLicense.expiry_date <= thirty_days, SoftwareLicense.expiry_date >= today
    ).scalar() or 0

    total_sub = db.query(sqlfunc.count(CloudSubscription.id)).scalar() or 0
    monthly_cost = db.query(sqlfunc.sum(CloudSubscription.monthly_cost)).scalar() or 0.0

    total_ip = db.query(sqlfunc.count(IPAddress.id)).scalar() or 0
    used_ip = db.query(sqlfunc.count(IPAddress.id)).filter(IPAddress.status == "assigned").scalar() or 0

    exp_cert = db.query(sqlfunc.count(Certificate.id)).filter(
        Certificate.expiry_date <= thirty_days, Certificate.expiry_date >= today
    ).scalar() or 0

    low_stock = db.query(sqlfunc.count(ConsumableStock.id)).filter(
        ConsumableStock.qty_in_stock <= ConsumableStock.min_stock_level,
        ConsumableStock.min_stock_level > 0,
    ).scalar() or 0

    upcoming_maint = db.query(sqlfunc.count(MaintenanceRecord.id)).filter(
        MaintenanceRecord.status == "scheduled",
        MaintenanceRecord.scheduled_date <= thirty_days,
    ).scalar() or 0

    week_ago = today - timedelta(days=7)
    recent = db.query(sqlfunc.count(AuditLog.id)).filter(AuditLog.timestamp >= week_ago).scalar() or 0

    # Trigger notification check
    check_and_create_notifications(db)

    return DashboardStats(
        total_assets=total_assets, assigned_assets=assigned, in_stock_assets=in_stock,
        in_maintenance_assets=in_maint, total_licenses=total_lic, expiring_licenses=exp_lic,
        total_subscriptions=total_sub, monthly_subscription_cost=monthly_cost,
        total_ip_addresses=total_ip, used_ip_addresses=used_ip,
        expiring_certificates=exp_cert, low_stock_consumables=low_stock,
        upcoming_maintenance=upcoming_maint, recent_changes=recent,
    )


@router.get("/dashboard/by-category", response_model=list[CategoryCount])
def assets_by_category(db: Session = Depends(get_db)):
    results = (
        db.query(Asset.category_id, AssetCategory.name, sqlfunc.count(Asset.id))
        .join(AssetCategory, Asset.category_id == AssetCategory.id)
        .group_by(Asset.category_id, AssetCategory.name)
        .all()
    )
    return [CategoryCount(category_id=r[0], category_name=r[1], count=r[2]) for r in results]


@router.get("/dashboard/by-status", response_model=list[StatusCount])
def assets_by_status(db: Session = Depends(get_db)):
    results = (
        db.query(Asset.status, sqlfunc.count(Asset.id))
        .group_by(Asset.status)
        .all()
    )
    return [StatusCount(status=r[0], count=r[1]) for r in results]


@router.get("/dashboard/expiring", response_model=list[ExpiringItem])
def expiring_items(days: int = 30, db: Session = Depends(get_db)):
    today = date.today()
    target = today + timedelta(days=days)
    items = []

    # Licenses
    lics = db.query(SoftwareLicense).filter(SoftwareLicense.expiry_date <= target, SoftwareLicense.expiry_date >= today).all()
    for l in lics:
        items.append(ExpiringItem(
            id=l.id, name=l.asset.name if l.asset else f"License #{l.id}", type="license",
            expiry_date=l.expiry_date, days_remaining=(l.expiry_date - today).days,
        ))

    # Certificates
    certs = db.query(Certificate).filter(Certificate.expiry_date <= target, Certificate.expiry_date >= today).all()
    for c in certs:
        items.append(ExpiringItem(
            id=c.id, name=c.domain, type="certificate",
            expiry_date=c.expiry_date, days_remaining=(c.expiry_date - today).days,
        ))

    # Warranties
    assets = db.query(Asset).filter(Asset.warranty_expiry <= target, Asset.warranty_expiry >= today).all()
    for a in assets:
        items.append(ExpiringItem(
            id=a.id, name=a.name, type="warranty",
            expiry_date=a.warranty_expiry, days_remaining=(a.warranty_expiry - today).days,
        ))

    # Subscriptions
    subs = db.query(CloudSubscription).filter(CloudSubscription.renewal_date <= target, CloudSubscription.renewal_date >= today).all()
    for s in subs:
        items.append(ExpiringItem(
            id=s.id, name=s.asset.name if s.asset else f"Sub #{s.id}", type="subscription",
            expiry_date=s.renewal_date, days_remaining=(s.renewal_date - today).days,
        ))

    items.sort(key=lambda x: x.days_remaining)
    return items
