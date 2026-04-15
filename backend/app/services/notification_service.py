from sqlalchemy.orm import Session
from datetime import date, timedelta

from app.models.license import SoftwareLicense
from app.models.certificate import Certificate
from app.models.subscription import CloudSubscription
from app.models.asset import Asset
from app.models.consumable import ConsumableStock
from app.models.maintenance import MaintenanceRecord
from app.models.notification import Notification


def check_and_create_notifications(db: Session):
    today = date.today()
    alert_days = [30, 7, 1]

    # License expiry
    for days in alert_days:
        target_date = today + timedelta(days=days)
        expiring = (
            db.query(SoftwareLicense)
            .filter(SoftwareLicense.expiry_date == target_date)
            .all()
        )
        for lic in expiring:
            existing = (
                db.query(Notification)
                .filter(
                    Notification.entity_type == "license",
                    Notification.entity_id == lic.id,
                    Notification.due_date == target_date,
                )
                .first()
            )
            if not existing:
                asset = db.query(Asset).filter(Asset.id == lic.asset_id).first()
                name = asset.name if asset else f"License #{lic.id}"
                db.add(Notification(
                    type="license_expiry",
                    entity_type="license",
                    entity_id=lic.id,
                    title=f"라이센스 만료 {days}일 전: {name}",
                    message=f"{name}의 라이센스가 {target_date}에 만료됩니다.",
                    due_date=target_date,
                ))

    # Certificate expiry
    for days in alert_days:
        target_date = today + timedelta(days=days)
        expiring = (
            db.query(Certificate)
            .filter(Certificate.expiry_date == target_date)
            .all()
        )
        for cert in expiring:
            existing = (
                db.query(Notification)
                .filter(
                    Notification.entity_type == "certificate",
                    Notification.entity_id == cert.id,
                    Notification.due_date == target_date,
                )
                .first()
            )
            if not existing:
                db.add(Notification(
                    type="cert_expiry",
                    entity_type="certificate",
                    entity_id=cert.id,
                    title=f"인증서 만료 {days}일 전: {cert.domain}",
                    message=f"{cert.domain} 인증서가 {target_date}에 만료됩니다.",
                    due_date=target_date,
                ))

    # Warranty expiry
    for days in alert_days:
        target_date = today + timedelta(days=days)
        expiring = (
            db.query(Asset)
            .filter(Asset.warranty_expiry == target_date)
            .all()
        )
        for asset in expiring:
            existing = (
                db.query(Notification)
                .filter(
                    Notification.entity_type == "asset",
                    Notification.entity_id == asset.id,
                    Notification.due_date == target_date,
                )
                .first()
            )
            if not existing:
                db.add(Notification(
                    type="warranty_expiry",
                    entity_type="asset",
                    entity_id=asset.id,
                    title=f"보증기간 만료 {days}일 전: {asset.name}",
                    message=f"{asset.name}의 보증기간이 {target_date}에 만료됩니다.",
                    due_date=target_date,
                ))

    # Low stock consumables
    low_stocks = (
        db.query(ConsumableStock)
        .filter(ConsumableStock.qty_in_stock <= ConsumableStock.min_stock_level)
        .filter(ConsumableStock.min_stock_level > 0)
        .all()
    )
    for cs in low_stocks:
        existing = (
            db.query(Notification)
            .filter(
                Notification.entity_type == "consumable",
                Notification.entity_id == cs.id,
                Notification.type == "low_stock",
                Notification.is_read == False,
            )
            .first()
        )
        if not existing:
            asset = db.query(Asset).filter(Asset.id == cs.asset_id).first()
            name = asset.name if asset else f"소모품 #{cs.id}"
            db.add(Notification(
                type="low_stock",
                entity_type="consumable",
                entity_id=cs.id,
                title=f"재고 부족: {name}",
                message=f"{name} 재고가 {cs.qty_in_stock}{cs.unit}입니다. (최소: {cs.min_stock_level}{cs.unit})",
                due_date=today,
            ))

    db.commit()
