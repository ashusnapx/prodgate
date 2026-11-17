import base64
import hashlib
import hmac
import secrets

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1


def hash_password(password: str) -> str:
    """scrypt$N$r$p$salt$hash, salt and hash base64 without padding."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    enc = lambda b: base64.b64encode(b).decode().rstrip("=")  # noqa: E731
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${enc(salt)}${enc(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    dec = lambda s: base64.b64decode(s + "=" * (-len(s) % 4))  # noqa: E731
    expected = dec(hash_b64)
    actual = hashlib.scrypt(password.encode(), salt=dec(salt_b64), n=int(n), r=int(r), p=int(p), dklen=len(expected))
    return hmac.compare_digest(actual, expected)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def temporary_password() -> str:
    return secrets.token_urlsafe(12)


def normalize_email(email: str) -> str:
    return email.strip().lower()
