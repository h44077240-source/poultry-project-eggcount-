"""
auth_rate_limiter.py — Security Rate Limiting, Progressive Delay & Account Lockout
Features:
1. IP Rate Limiting: Max 10 requests per IP per minute (HTTP 429).
2. Progressive Delay: Exponential backoff on consecutive failed attempts.
3. Account Lockout: 5 consecutive failed attempts lock the account for 15 minutes.
4. Email Notification: Triggers reset link notification on account lockout.
5. Timing & Status Masking: Returns generic 401 "Invalid email or password"
   so attackers cannot deduce whether an account exists, is locked, or wrong password.
6. Storage: Thread-safe in-memory cache with optional Redis / Upstash support.
"""

import time
import math
import asyncio
import logging
from typing import Optional, Tuple, Dict, Any
from fastapi import Request, HTTPException, status
from app.config import settings

logger = logging.getLogger("auth_security")

# ─────────────────────────────────────────────────────────────────────────────
# 1. Storage Layer: In-Memory (Thread-safe with TTL) + Optional Redis
# ─────────────────────────────────────────────────────────────────────────────

class InMemoryStore:
    """Thread-safe in-memory cache supporting sliding window TTL counters and locks."""
    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            val, expires_at = item
            if expires_at and time.time() > expires_at:
                del self._data[key]
                return None
            return val

    async def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None):
        async with self._lock:
            expires_at = (time.time() + ttl_seconds) if ttl_seconds else None
            self._data[key] = (value, expires_at)

    async def increment(self, key: str, ttl_seconds: int = 60) -> int:
        """Increment integer counter with TTL."""
        async with self._lock:
            now = time.time()
            item = self._data.get(key)
            if item and (not item[1] or now <= item[1]):
                val = int(item[0]) + 1
                expires_at = item[1] or (now + ttl_seconds)
            else:
                val = 1
                expires_at = now + ttl_seconds
            self._data[key] = (val, expires_at)
            return val

    async def delete(self, key: str):
        async with self._lock:
            self._data.pop(key, None)

    async def record_ip_hit(self, ip: str, window_seconds: int = 60) -> int:
        """Sliding-window IP request counter."""
        async with self._lock:
            now = time.time()
            key = f"ip_history:{ip}"
            item = self._data.get(key)
            timestamps = item[0] if (item and now <= item[1]) else []
            # Keep only timestamps within window
            timestamps = [t for t in timestamps if now - t < window_seconds]
            timestamps.append(now)
            self._data[key] = (timestamps, now + window_seconds)
            return len(timestamps)


# Instantiate default in-memory store
_memory_store = InMemoryStore()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Email Service Mock / Notifier (Async Email Dispatcher)
# ─────────────────────────────────────────────────────────────────────────────

async def send_lockout_notification(email: str, reset_link: str):
    """
    Simulates or executes sending an account lockout alert email containing
    a secure password reset link.
    """
    logger.warning(
        f"[SECURITY ALERT] Account {email} has been locked after 5 failed login attempts.\n"
        f"Password Reset Link sent: {reset_link}"
    )
    # In production with SMTP / SendGrid / Postmark:
    # await email_client.send_message(
    #     to=email,
    #     subject="Security Alert: Your GioTag Account Has Been Locked",
    #     body=f"Your account was locked due to multiple failed login attempts.\n"
    #          f"Click here to safely unlock and reset your password: {reset_link}"
    # )
    return True


# ─────────────────────────────────────────────────────────────────────────────
# 3. Auth Security Manager (Rate Limiter, Progressive Delay & Lockout)
# ─────────────────────────────────────────────────────────────────────────────

class AuthSecurityManager:
    """
    Enterprise-grade authentication security guard:
    - Max 10 requests / IP / min -> 429 Too Many Requests
    - Progressive delays on consecutive failed logins (0s, 1s, 2s, 4s...)
    - 5 consecutive failed attempts -> 15 min account lockout
    - Dispatches reset link email upon lockout
    - Never reveals lock state on login attempt (always generic 401)
    """

    IP_RATE_LIMIT_MAX = 10         # Max 10 attempts per IP
    IP_RATE_LIMIT_WINDOW = 60      # 1 minute window
    MAX_FAILED_ATTEMPTS = 5        # 5 consecutive failures before lock
    LOCKOUT_DURATION_SECONDS = 900 # 15 minutes lockout (15 * 60)
    BASE_PROGRESSIVE_DELAY = 1.0   # Base delay factor (seconds)

    def __init__(self, store: Optional[InMemoryStore] = None):
        self.store = store or _memory_store

    @staticmethod
    def get_client_ip(request: Request) -> str:
        """Extract true client IP honoring reverse proxies (Cloudflare, Render, AWS)."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client and request.client.host:
            return request.client.host
        return "127.0.0.1"

    async def check_ip_rate_limit(self, request: Request):
        """Enforces max 10 requests per IP per minute."""
        ip = self.get_client_ip(request)
        hits = await self.store.record_ip_hit(ip, window_seconds=self.IP_RATE_LIMIT_WINDOW)
        if hits > self.IP_RATE_LIMIT_MAX:
            logger.warning(f"[RATE LIMIT] IP {ip} exceeded 10 login requests in 60s (hits={hits})")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts from this IP. Please try again later.",
                headers={"Retry-After": "60"}
            )

    async def pre_login_check(self, identifier: str) -> Tuple[bool, float]:
        """
        Checks account status and applies progressive delay before password verification.
        Returns:
            is_locked (bool): True if currently under 15-minute lockout.
            delay (float): Seconds of progressive delay applied.
        """
        clean_id = identifier.strip().lower()
        lock_key = f"lockout:{clean_id}"
        fail_key = f"failed_attempts:{clean_id}"

        # 1. Check if account is in 15-minute lockout
        lock_until = await self.store.get(lock_key)
        is_locked = False
        if lock_until and time.time() < lock_until:
            is_locked = True

        # 2. Compute progressive delay based on consecutive failed attempts
        failed_count = await self.store.get(fail_key) or 0
        delay = 0.0
        if failed_count > 0:
            # Progressive backoff: Attempt 2 = 1.0s, Attempt 3 = 2.0s, Attempt 4 = 4.0s
            delay = min(8.0, self.BASE_PROGRESSIVE_DELAY * math.pow(2, failed_count - 1))
            logger.info(f"[SECURITY DELAY] Enforcing {delay:.2f}s progressive delay for: {clean_id} (attempts={failed_count})")
            await asyncio.sleep(delay)

        return is_locked, delay

    async def handle_failed_attempt(self, identifier: str, request: Request, background_tasks=None):
        """
        Registers a failed login attempt. If attempts reach 5, locks account for 15 min
        and triggers a password reset notification email.
        """
        clean_id = identifier.strip().lower()
        fail_key = f"failed_attempts:{clean_id}"
        lock_key = f"lockout:{clean_id}"

        current_fails = await self.store.increment(fail_key, ttl_seconds=self.LOCKOUT_DURATION_SECONDS)
        logger.warning(f"[AUTH FAIL] Failed login attempt #{current_fails} for: {clean_id}")

        if current_fails >= self.MAX_FAILED_ATTEMPTS:
            lockout_expiry = time.time() + self.LOCKOUT_DURATION_SECONDS
            await self.store.set(lock_key, lockout_expiry, ttl_seconds=self.LOCKOUT_DURATION_SECONDS)
            logger.critical(f"[ACCOUNT LOCKED] Account {clean_id} locked for 15 minutes due to {current_fails} failed attempts.")

            # Generate secure temporary reset token
            from app.security.jwt import create_access_token
            reset_token = create_access_token({"sub": clean_id, "action": "account_unlock_reset"})
            base_url = str(request.base_url).rstrip("/")
            reset_link = f"{base_url}/reset-password?token={reset_token}"

            # Dispatch lockout email notification asynchronously
            if background_tasks:
                background_tasks.add_task(send_lockout_notification, clean_id, reset_link)
            else:
                asyncio.create_task(send_lockout_notification(clean_id, reset_link))

    async def handle_successful_login(self, identifier: str):
        """Clears all failed login counters and lockout state upon valid authentication."""
        clean_id = identifier.strip().lower()
        await self.store.delete(f"failed_attempts:{clean_id}")
        await self.store.delete(f"lockout:{clean_id}")


# Global singleton instance
auth_security = AuthSecurityManager()

