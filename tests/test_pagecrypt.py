import base64

import pytest

from watch import pagecrypt


def test_encrypt_returns_base64_fields_and_no_plaintext():
    blob = pagecrypt.encrypt("aliathon-secret", "hunter2 passphrase")
    assert set(blob) == {"salt", "iv", "ct", "iter"}
    for k in ("salt", "iv", "ct"):
        base64.b64decode(blob[k], validate=True)
    assert blob["iter"] >= 600_000
    assert "aliathon-secret" not in str(blob)


def test_roundtrip():
    blob = pagecrypt.encrypt("aliathon-secret", "hunter2 passphrase")
    assert pagecrypt.decrypt(blob, "hunter2 passphrase") == "aliathon-secret"


def test_wrong_password_fails():
    blob = pagecrypt.encrypt("aliathon-secret", "hunter2 passphrase")
    with pytest.raises(ValueError):
        pagecrypt.decrypt(blob, "wrong")


def test_fresh_salt_each_call():
    a = pagecrypt.encrypt("t", "p")
    b = pagecrypt.encrypt("t", "p")
    assert a["salt"] != b["salt"] and a["ct"] != b["ct"]
