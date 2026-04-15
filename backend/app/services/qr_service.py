import qrcode
import io
from pathlib import Path

from app.config import settings


def generate_qr_code(asset_tag: str, asset_id: int) -> str:
    url = f"{settings.QR_BASE_URL}/assets/{asset_id}"

    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    filename = f"{asset_tag}.png"
    filepath = Path("data/qr_codes") / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(filepath))

    return f"/static/qr_codes/{filename}"


def generate_qr_bytes(asset_tag: str, asset_id: int) -> bytes:
    url = f"{settings.QR_BASE_URL}/assets/{asset_id}"

    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()
