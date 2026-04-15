from sqlalchemy.orm import Session
from datetime import datetime, date

from app.config import settings


def generate_asset_tag(db: Session) -> str:
    from app.models.asset import Asset
    year = datetime.now().year
    prefix = f"{settings.ASSET_TAG_PREFIX}-{year}-"

    last = (
        db.query(Asset)
        .filter(Asset.asset_tag.like(f"{prefix}%"))
        .order_by(Asset.id.desc())
        .first()
    )
    if last:
        try:
            last_num = int(last.asset_tag.split("-")[-1])
        except ValueError:
            last_num = 0
        next_num = last_num + 1
    else:
        next_num = 1

    return f"{prefix}{next_num:05d}"
