from app.core.security import generate_ticket_token, verify_ticket_token


def test_token_shape_and_length():
    t = generate_ticket_token()
    assert len(t) <= 64 and t.count(".") == 1
    assert verify_ticket_token(t)


def test_tokens_are_unique_and_unpredictable():
    tokens = {generate_ticket_token() for _ in range(2000)}
    assert len(tokens) == 2000


def test_tampered_nonce_rejected():
    t = generate_ticket_token()
    flipped = ("A" if t[0] != "A" else "B") + t[1:]
    assert not verify_ticket_token(flipped)


def test_tampered_signature_rejected():
    t = generate_ticket_token()
    nonce, sig = t.split(".")
    assert not verify_ticket_token(f"{nonce}.{'A' * len(sig)}")


def test_garbage_rejected():
    for bad in ["", "abc", "a.b", "x" * 80, "é" * 32 + "." + "é" * 22, None, 123]:
        assert not verify_ticket_token(bad)  # type: ignore[arg-type]


def test_token_signed_with_other_secret_rejected(monkeypatch):
    from app.core import security

    t = generate_ticket_token()
    monkeypatch.setattr(security.get_settings(), "qr_hmac_secret", "another-secret-another-secret-12345")
    assert not verify_ticket_token(t)
