"""
Database Password Audit & Migration Utility.

Usage:
    python -m scripts.migrate_passwords             # Audit current database password hashes
    python -m scripts.migrate_passwords --rehash-known # Immediately upgrade known development/seed passwords

Functionality:
- Scans all users in the database.
- Audits password hashing algorithms (bcrypt rounds >= 12, legacy rounds < 12, MD5, SHA-1, plaintext).
- Reports security status of all stored credentials.
- Prepares accounts for zero-downtime, on-login automatic migration to bcrypt rounds=12.
"""
import sys
import os
import re
import argparse
from typing import Dict, Any

# Ensure backend root is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.database.session import SessionLocal
from app.database.models import User
from app.security.password import (
    BCRYPT_ROUNDS, hash_password, needs_rehash, verify_and_check_rehash
)


def classify_hash(hash_val: str) -> str:
    """Classifies a stored password hash into security categories."""
    if not hash_val:
        return "EMPTY"
    
    if hash_val.startswith(("$2b$", "$2a$", "$2y$")):
        match = re.match(r"^\$2[aby]\$(\d+)\$", hash_val)
        if match:
            rounds = int(match.group(1))
            if rounds >= BCRYPT_ROUNDS:
                return f"SECURE_BCRYPT_ROUNDS_{rounds}"
            return f"WEAK_BCRYPT_ROUNDS_{rounds}"
        return "WEAK_BCRYPT_UNKNOWN"

    if hash_val.startswith("$argon2"):
        return "SECURE_ARGON2"

    if len(hash_val) == 32 and re.match(r"^[a-fA-F0-9]{32}$", hash_val):
        return "WEAK_MD5"

    if len(hash_val) == 40 and re.match(r"^[a-fA-F0-9]{40}$", hash_val):
        return "WEAK_SHA1"

    return "PLAINTEXT_OR_UNKNOWN"


KNOWN_PASSWORDS = {
    "admin@giotag.gov": "Admin@123!",
    "deptadmin@giotag.gov": "DeptAdmin@123!",
    "officer1@giotag.gov": "Officer@123!",
    "officer2@giotag.gov": "Officer@123!",
    "viewer@giotag.gov": "Viewer@123!",
}


def audit_and_migrate(rehash_known: bool = False):
    db = SessionLocal()
    print("=" * 75)
    print("🔐 DATABASE PASSWORD SECURITY AUDIT & MIGRATION")
    print(f"Target Policy: bcrypt with salt rounds >= {BCRYPT_ROUNDS} (or Argon2id)")
    print("=" * 75)

    try:
        users = db.query(User).filter(User.deleted_at == None).all()
        print(f"Total active users in database: {len(users)}\n")

        classification_counts: Dict[str, int] = {}
        users_needing_migration = []

        print(f"{'User Email':<32} {'Role':<16} {'Classification':<24} {'Needs Re-hash?'}")
        print("-" * 75)

        for u in users:
            category = classify_hash(u.hashed_password)
            classification_counts[category] = classification_counts.get(category, 0) + 1
            weak = needs_rehash(u.hashed_password)

            if weak:
                users_needing_migration.append(u)

            status_mark = "⚠️ YES (on next login)" if weak else "✅ Secure"
            print(f"{u.email:<32} {str(u.role.value if hasattr(u.role, 'value') else u.role):<16} {category:<24} {status_mark}")

        print("-" * 75)
        print("\n📊 Summary Breakdown:")
        for cat, cnt in classification_counts.items():
            print(f"  • {cat:<26}: {cnt} user(s)")

        print(f"\nTotal users requiring migration: {len(users_needing_migration)} / {len(users)}")

        if rehash_known and users_needing_migration:
            print("\n🔄 Re-hashing known default development/seed accounts immediately...")
            migrated_count = 0
            for u in users_needing_migration:
                email_lower = u.email.lower()
                if email_lower in KNOWN_PASSWORDS:
                    pwd = KNOWN_PASSWORDS[email_lower]
                    u.hashed_password = hash_password(pwd)
                    migrated_count += 1
                    print(f"  [UPGRADED] {u.email} -> bcrypt rounds={BCRYPT_ROUNDS}")

            if migrated_count > 0:
                db.commit()
                print(f"✅ Successfully upgraded {migrated_count} account(s) to bcrypt rounds={BCRYPT_ROUNDS}.")

        print("\n🛡️ Automatic On-Login Migration Status:")
        print("  All remaining weakly hashed or plaintext accounts will be automatically")
        print("  and transparently re-hashed to bcrypt rounds=12 upon their next successful login.")
        print("=" * 75)

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Password Audit & Migration")
    parser.add_argument("--rehash-known", action="store_true", help="Immediately upgrade known default dev passwords")
    args = parser.parse_args()
    audit_and_migrate(rehash_known=args.rehash_known)
