"""
Enterprise Rate Limiter & Account Lockout Engine for GioTag.

Features:
- IP-based Sliding/Fixed Window Rate Limiting (max 10 req/min per IP on /login).
- Consecutive Failed Login Tracking with Account Lockout (15 min after 5 failed attempts).
- Progressive Exponential Backoff Delay (increases with each failed attempt).
- Pluggable Cache Backends: High-performance Thread-Safe In-Memory Cache with TTL &
  automatic eviction, or Redis / Upstash Redis when configured.
- Timing-Attack Defense: Uniform timing & identical responses to prevent user enumeration.
"""
import time
import threading
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict, Any
from fastapi import Request, HTTPException, status

from app.config import settings
from app.security.password import verify_password

logger = logging.getLogger("rate_limiter")

# Constant-time dummy bcrypt hash for timing attack mitigation
DUMMY_BCRYPT_HASH = "$2b$10$e8wF5qH6zD6YvW9H7L.pje7.y9zFp/VwZ2aD2hQkU6X4e2X4qH4Y."


# ─── 1. Abstract Cache Backend & Implementations ─────────────────────────────

class BaseCacheBackend(ABC):
    """Abstract Cache Interface supporting Redis, Upstash, or In-Memory storage."""

    @abstractmethod
    def get(self, key: str) -> Optional[str]:
        """Retrieve key value if present and unexpired."""
        pass

    @abstractmethod
    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Store key value with time-to-live in seconds."""
        pass

    @abstractmethod
    def incr(self, key: str, ttl_seconds: int) -> int:
        """Atomically increment integer value, setting TTL if key is new."""
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete key from cache."""
        pass


class InMemoryCacheBackend(BaseCacheBackend):
    """
    Thread-safe In-Memory Cache with TTL and automatic memory cleanup.
    Requires no external dependencies, zero-config, highly performant.
    """

    def __init__(self, max_keys: int = 50000):
        self._store: Dict[str, Tuple[str, float]] = {}
        self._lock = threading.RLock()
        self._max_keys = max_keys

    def _purge_expired_locked(self) -> None:
        """Remove expired keys when cache approaches size threshold."""
        now = time.time()
        expired = [k for k, (_, exp) in self._store.items() if now >= exp]
        for k in expired:
            self._store.pop(k, None)

    def get(self, key: str) -> Optional[str]:
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            val, exp = entry
            if now >= exp:
                self._store.pop(key, None)
                return None
            return val

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        now = time.time()
        exp = now + max(1, ttl_seconds)
        with self._lock:
            if len(self._store) >= self._max_keys:
                self._purge_expired_locked()
            self._store[key] = (str(value), exp)

    def incr(self, key: str, ttl_seconds: int) -> int:
        now = time.time()
        with self._lock:
            if len(self._store) >= self._max_keys:
                self._purge_expired_locked()
            entry = self._store.get(key)
            if entry and now < entry[1]:
                try:
                    new_val = int(entry[0]) + 1
                except ValueError:
                    new_val = 1
                self._store[key] = (str(new_val), entry[1])
                return new_val
            else:
                exp = now + max(1, ttl_seconds)
                self._store[key] = ("1", exp)
                return 1

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)


class RedisCacheBackend(BaseCacheBackend):
    """Redis / Upstash Redis Client Backend with native INCR and EXPIRE."""

    def __init__(self, redis_client: Any):
        self.client = redis_client

    def get(self, key: str) -> Optional[str]:
        try:
            val = self.client.get(key)
            if val is None:
                return None
            return val.decode("utf-8") if isinstance(val, bytes) else str(val)
        except Exception as e:
            logger.warning(f"Redis get failed for {key}: {e}")
            return None

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        try:
            self.client.set(key, str(value), ex=max(1, ttl_seconds))
        except Exception as e:
            logger.warning(f"Redis set failed for {key}: {e}")

    def incr(self, key: str, ttl_seconds: int) -> int:
        try:
            pipe = self.client.pipeline()
            pipe.incr(key)
            pipe.expire(key, max(1, ttl_seconds))
            res = pipe.execute()
            return int(res[0])
        except Exception as e:
            logger.warning(f"Redis incr failed for {key}: {e}")
            return 1

    def delete(self, key: str) -> None:
        try:
            self.client.delete(key)
        except Exception as e:
            logger.warning(f"Redis delete failed for {key}: {e}")


# ─── 2. Cache Backend Factory ────────────────────────────────────────────────

_cache_backend_instance: Optional[BaseCacheBackend] = None

def get_cache_backend() -> BaseCacheBackend:
    """Returns singleton cache backend: Redis/Upstash if configured, otherwise In-Memory."""
    global _cache_backend_instance
    if _cache_backend_instance is None:
        redis_target = settings.REDIS_URL or settings.UPSTASH_REDIS_URL
        if redis_target:
            try:
                import redis
                client = redis.Redis.from_url(redis_target, decode_responses=True)
                client.ping()
                _cache_backend_instance = RedisCacheBackend(client)
                logger.info(f"Initialized Redis/Upstash cache backend from {redis_target.split('@')[-1]}")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis ({e}). Falling back to InMemoryCacheBackend.")
                _cache_backend_instance = InMemoryCacheBackend()
        else:
            _cache_backend_instance = InMemoryCacheBackend()
            logger.info("Initialized High-Performance Thread-Safe In-Memory Cache Backend.")
    return _cache_backend_instance


# ─── 3. IP Helper & Rate Limiting ────────────────────────────────────────────

def get_client_ip(request: Request) -> str:
    """Extract real client IP respecting X-Forwarded-For reverse proxy headers."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # First IP in list is client's true IP
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    if request.client and request.client.host:
        return request.client.host.strip()
    return "127.0.0.1"


def check_ip_rate_limit(
    request: Request,
    max_requests: int = 10,
    window_seconds: int = 60
) -> None:
    """
    Enforces IP-based rate limiting on sensitive routes (e.g. max 10 requests per minute).
    Raises HTTP 429 Too Many Requests if threshold is exceeded.
    """
    cache = get_cache_backend()
    client_ip = get_client_ip(request)
    cache_key = f"rl:login:ip:{client_ip}"

    current_requests = cache.incr(cache_key, ttl_seconds=window_seconds)
    if current_requests > max_requests:
        logger.warning(f"Rate limit exceeded for IP {client_ip} on /login: {current_requests}/{max_requests}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts from this IP address. Please wait a minute before trying again.",
            headers={"Retry-After": str(window_seconds)}
        )


# ─── 4. Account Lockout & Progressive Delay ──────────────────────────────────

def normalize_identifier(identifier: str) -> str:
    """Normalize username/email to lowercase stripped key."""
    return (identifier or "").strip().lower()


def is_account_locked(identifier: str) -> bool:
    """Checks whether the specified account is currently in a 15-minute lockout state."""
    norm = normalize_identifier(identifier)
    if not norm:
        return False
    cache = get_cache_backend()
    val = cache.get(f"auth:locked:{norm}")
    return val is not None


def get_failed_attempts(identifier: str) -> int:
    """Get current consecutive failed login attempts for an account."""
    norm = normalize_identifier(identifier)
    if not norm:
        return 0
    cache = get_cache_backend()
    val = cache.get(f"auth:failed:{norm}")
    return int(val) if val and val.isdigit() else 0


def record_failed_attempt(identifier: str) -> Tuple[int, bool]:
    """
    Records a failed login attempt for the specified account.
    Returns (total_failed_count, is_locked_now).
    Locks account for 15 minutes when attempts reach 5.
    """
    norm = normalize_identifier(identifier)
    if not norm:
        return 0, False

    cache = get_cache_backend()
    lockout_secs = settings.ACCOUNT_LOCKOUT_MINUTES * 60  # 900 seconds (15 minutes)

    # Failed attempts expire after the lockout window
    failed_count = cache.incr(f"auth:failed:{norm}", ttl_seconds=lockout_secs)

    is_locked = False
    if failed_count >= settings.ACCOUNT_LOCKOUT_MAX_ATTEMPTS:
        cache.set(f"auth:locked:{norm}", "1", ttl_seconds=lockout_secs)
        is_locked = True
        logger.warning(f"Account locked: '{norm}' exceeded {settings.ACCOUNT_LOCKOUT_MAX_ATTEMPTS} failed attempts for {settings.ACCOUNT_LOCKOUT_MINUTES}m.")

    return failed_count, is_locked


def reset_failed_attempts(identifier: str) -> None:
    """Resets failed attempt count and unlocks account upon successful authentication."""
    norm = normalize_identifier(identifier)
    if not norm:
        return
    cache = get_cache_backend()
    cache.delete(f"auth:failed:{norm}")
    cache.delete(f"auth:locked:{norm}")


def calculate_progressive_delay(failed_attempts: int) -> float:
    """
    Calculates progressive backoff delay (in seconds):
    1st failure: 0.5s
    2nd failure: 1.0s
    3rd failure: 2.0s
    4th failure: 4.0s
    5th failure: 8.0s (account locks)
    """
    if failed_attempts <= 0:
        return 0.0
    delay = min(10.0, 0.5 * float(2 ** (failed_attempts - 1)))
    return delay


async def apply_progressive_delay(failed_attempts: int) -> None:
    """
    Asynchronously suspends execution by the progressive backoff delay.
    Does not block FastAPI event loop while drastically slowing brute-force attackers.
    """
    delay = calculate_progressive_delay(failed_attempts)
    if delay > 0:
        await asyncio.sleep(delay)


def perform_dummy_verification() -> None:
    """
    Performs constant-time bcrypt check against dummy hash.
    Ensures identical response time when account does NOT exist,
    preventing username enumeration via timing analysis.
    """
    verify_password("dummy_password_timing_check", DUMMY_BCRYPT_HASH)
