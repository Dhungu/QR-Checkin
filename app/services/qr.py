"""QR rendering and decoding."""

import io
import logging

import numpy as np
import qrcode
import qrcode.image.svg
from qrcode.constants import ERROR_CORRECT_M

log = logging.getLogger(__name__)


def _qr(data: str, border: int) -> qrcode.QRCode:
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=10, border=border)
    qr.add_data(data)
    qr.make(fit=True)
    return qr


def render_qr_png(data: str, border: int = 2) -> bytes:
    img = _qr(data, border).make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_qr_svg(data: str, border: int = 2) -> bytes:
    img = _qr(data, border).make_image(image_factory=qrcode.image.svg.SvgPathImage)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue()


def _decode_pyzbar(image_bytes: bytes) -> str | None:
    try:
        from PIL import Image
        from pyzbar.pyzbar import ZBarSymbol, decode
    except (ImportError, OSError):  # pyzbar needs the native libzbar
        return None
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            symbols = decode(img.convert("L"), symbols=[ZBarSymbol.QRCODE])
    except Exception:  # noqa: BLE001 - corrupt image, treat as "nothing found"
        return None
    return symbols[0].data.decode("utf-8", errors="replace") if symbols else None


def _decode_opencv(image_bytes: bytes) -> str | None:
    import cv2

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    detector = cv2.QRCodeDetector()
    # Try as-is, then a few scales: phone photos are big, screenshots are small.
    for scale in (1.0, 0.5, 2.0, 0.25):
        candidate = img if scale == 1.0 else cv2.resize(img, None, fx=scale, fy=scale)
        text, _, _ = detector.detectAndDecode(candidate)
        if text:
            return text
    return None


def decode_qr(image_bytes: bytes) -> str | None:
    """Decode the first QR code in an image: pyzbar first, OpenCV as fallback."""
    return _decode_pyzbar(image_bytes) or _decode_opencv(image_bytes)
