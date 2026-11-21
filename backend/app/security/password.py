"""
password.py — Secure Password Hashing & Transparent Rehash Migration
Features:
- Primary Scheme: bcrypt with salt rounds >= 12 (OWASP recommended minimum).
- Constant-time hash and legacy password verification using hmac.compare_digest.
- Transparent migration on next login (upgrades plain-text, MD5, SHA-1, SHA-256,
  or older bcrypt < 12 rounds to bcrypt-12).
- Zero-exposure policy: never logs or serializes passwords in logs.
"""

import hmac
import hashlib
from typing import Tuple, Optional
from passlib.context import CryptContext

# Salt rounds strictly set to 12 as per OWASP / industry standards
BCRYPT_ROUNDS = 12

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=BCRYPT_ROUNDS,
)


def hash_password(plain_password: str) -> str:
    """
    Hash a plain-text password using bcrypt with salt rounds=12.
    """
    if not plain_password:
        raise ValueError("Password cannot be empty")
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Standard constant-time password verification against a bcrypt hash.
    """
    valid, _, _ = verify_and_upgrade_password(plain_password, hashed_password)
    return valid


def verify_and_upgrade_password(
    plain_password: str,
    stored_hash: str
) -> Tuple[bool, bool, Optional[str]]:
    """
    Verify a password against stored credentials using constant-time comparison.
    If valid but weakly hashed (e.g. plain-text, MD5, SHA-1, or bcrypt < 12 rounds),
    returns (is_valid=True, needs_upgrade=True, new_hash=new_bcrypt_12_hash)
    for seamless just-in-time rehashing on login.

    Returns:
        (is_valid, needs_upgrade, new_hash)
    """
    if not plain_password or not stored_hash:
        return False, False, None

    # 1. Primary: Verify against standard bcrypt hash
    try:
        if pwd_context.identify(stored_hash):
            is_valid = pwd_context.verify(plain_password, stored_hash)
            if is_valid:
                needs_update = pwd_context.needs_update(stored_hash)
                new_hash = hash_password(plain_password) if needs_update else None
                return True, needs_update, new_hash
            return False, False, None
    except Exception:
        pass

    # 2. Legacy Check: Plain-text password stored directly
    # CRITICAL: Always use hmac.compare_digest for constant-time comparison
    if hmac.compare_digest(plain_password.encode("utf-8"), stored_hash.encode("utf-8")):
        return True, True, hash_password(plain_password)

    # 3. Legacy Check: MD5 hash (32 hex characters)
    plain_md5 = hashlib.md5(plain_password.encode("utf-8")).hexdigest()
    if hmac.compare_digest(plain_md5.lower(), stored_hash.lower()):
        return True, True, hash_password(plain_password)

    # 4. Legacy Check: SHA-1 hash (40 hex characters)
    plain_sha1 = hashlib.sha1(plain_password.encode("utf-8")).hexdigest()
    if hmac.compare_digest(plain_sha1.lower(), stored_hash.lower()):
        return True, True, hash_password(plain_password)

    # 5. Legacy Check: SHA-256 unsalted hash (64 hex characters)
    plain_sha256 = hashlib.sha256(plain_password.encode("utf-8")).hexdigest()
    if hmac.compare_digest(plain_sha256.lower(), stored_hash.lower()):
        return True, True, hash_password(plain_password)

    # Constant-time dummy comparison to prevent side-channel timing attacks
    hmac.compare_digest(plain_password.encode("utf-8"), b"dummy_constant_time_comparison")
    return False, False, None
