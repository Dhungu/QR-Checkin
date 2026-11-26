import io

import cv2
import numpy as np
from PIL import Image

from app.core.security import generate_ticket_token
from app.services.qr import decode_qr, render_qr_png, render_qr_svg


def test_png_roundtrip():
    token = generate_ticket_token()
    assert decode_qr(render_qr_png(token)) == token


def test_svg_is_rendered():
    assert render_qr_svg("hello").lstrip().startswith(b"<?xml") or b"<svg" in render_qr_svg("hello")


def test_decode_small_screenshot_scale():
    token = generate_ticket_token()
    img = Image.open(io.BytesIO(render_qr_png(token))).convert("L").resize((180, 180))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    assert decode_qr(buf.getvalue()) == token


def test_decode_with_noise_and_padding():
    token = generate_ticket_token()
    arr = np.array(Image.open(io.BytesIO(render_qr_png(token))).convert("L"))
    arr = cv2.copyMakeBorder(arr, 80, 80, 80, 80, cv2.BORDER_CONSTANT, value=255)
    ok, enc = cv2.imencode(".jpg", arr, [cv2.IMWRITE_JPEG_QUALITY, 60])
    assert ok and decode_qr(enc.tobytes()) == token


def test_no_qr_returns_none():
    buf = io.BytesIO()
    Image.new("RGB", (200, 200), "white").save(buf, format="PNG")
    assert decode_qr(buf.getvalue()) is None
    assert decode_qr(b"not an image") is None
