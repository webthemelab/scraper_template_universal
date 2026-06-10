# config/settings.py
# ─────────────────────────────────────────────────────────────
# Single source of truth for all configuration.
# All values come from environment variables (never hardcoded).
# Import `settings` anywhere in the codebase — never use os.getenv directly.
# ─────────────────────────────────────────────────────────────

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    """Raise a clear error if a required env var is missing."""
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(
            f"Required environment variable '{key}' is missing. "
            f"Copy .env.example to .env and fill in the value."
        )
    return val


def _bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).lower() in ("1", "true", "yes")


@dataclass
class DatabaseSettings:
    host:     str = field(default_factory=lambda: os.getenv("PGHOST", "localhost"))
    port:     int = field(default_factory=lambda: int(os.getenv("PGPORT", "5432")))
    name:     str = field(default_factory=lambda: os.getenv("PGDATABASE", "scraper_db"))
    user:     str = field(default_factory=lambda: os.getenv("PGUSER", "postgres"))
    password: str = field(default_factory=lambda: os.getenv("PGPASSWORD", ""))
    sslmode:  str = field(default_factory=lambda: os.getenv("PGSSLMODE", "prefer"))
    pool_min: int = field(default_factory=lambda: int(os.getenv("DB_POOL_MIN", "2")))
    pool_max: int = field(default_factory=lambda: int(os.getenv("DB_POOL_MAX", "10")))

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
            f"?sslmode={self.sslmode}"
        )


@dataclass
class RedisSettings:
    host:     str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    port:     int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    password: str = field(default_factory=lambda: os.getenv("REDIS_PASSWORD", ""))
    db:       int = field(default_factory=lambda: int(os.getenv("REDIS_DB", "0")))

    @property
    def url(self) -> str:
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


@dataclass
class ProxySettings:
    # Provider endpoint for rotating proxies (e.g. Bright Data, Oxylabs)
    gateway_url:  str  = field(default_factory=lambda: os.getenv("PROXY_GATEWAY_URL", ""))
    username:     str  = field(default_factory=lambda: os.getenv("PROXY_USERNAME", ""))
    password:     str  = field(default_factory=lambda: os.getenv("PROXY_PASSWORD", ""))
    # Comma-separated list of static fallback proxies
    static_list:  str  = field(default_factory=lambda: os.getenv("PROXY_STATIC_LIST", ""))
    # Preferred country code for geo-targeted proxies (e.g. "US", "JP")
    country_code: str  = field(default_factory=lambda: os.getenv("PROXY_COUNTRY", ""))
    enabled:      bool = field(default_factory=lambda: _bool("PROXY_ENABLED", True))
    rotation_every: int = field(default_factory=lambda: int(os.getenv("PROXY_ROTATE_EVERY", "10")))

    @property
    def static_proxies(self) -> list[str]:
        if not self.static_list:
            return []
        return [p.strip() for p in self.static_list.split(",") if p.strip()]


@dataclass
class ScraperSettings:
    # Concurrency
    workers:         int   = field(default_factory=lambda: int(os.getenv("SCRAPER_WORKERS", "4")))
    # Delay between requests (seconds)
    delay_min:       float = field(default_factory=lambda: float(os.getenv("SCRAPER_DELAY_MIN", "1.0")))
    delay_max:       float = field(default_factory=lambda: float(os.getenv("SCRAPER_DELAY_MAX", "4.0")))
    # Retry
    max_retries:     int   = field(default_factory=lambda: int(os.getenv("SCRAPER_MAX_RETRIES", "3")))
    retry_backoff:   float = field(default_factory=lambda: float(os.getenv("SCRAPER_RETRY_BACKOFF", "2.0")))
    # Request timeout (seconds)
    timeout:         int   = field(default_factory=lambda: int(os.getenv("SCRAPER_TIMEOUT", "30")))
    # Whether to run browsers in headless mode
    headless:        bool  = field(default_factory=lambda: _bool("SCRAPER_HEADLESS", True))
    # Respect robots.txt (ALWAYS keep True in production)
    respect_robots:  bool  = field(default_factory=lambda: _bool("SCRAPER_RESPECT_ROBOTS", True))
    # Page rate limit (max requests per minute per domain)
    rate_limit_rpm:  int   = field(default_factory=lambda: int(os.getenv("SCRAPER_RATE_LIMIT_RPM", "20")))


@dataclass
class LoggingSettings:
    level:      str  = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    dir:        str  = field(default_factory=lambda: os.getenv("LOG_DIR", "logs"))
    rotation:   str  = field(default_factory=lambda: os.getenv("LOG_ROTATION", "1 day"))
    retention:  str  = field(default_factory=lambda: os.getenv("LOG_RETENTION", "30 days"))
    # Set to false to disable sensitive data masking (not recommended)
    mask_secrets: bool = field(default_factory=lambda: _bool("LOG_MASK_SECRETS", True))


@dataclass
class Settings:
    db:      DatabaseSettings = field(default_factory=DatabaseSettings)
    redis:   RedisSettings    = field(default_factory=RedisSettings)
    proxy:   ProxySettings    = field(default_factory=ProxySettings)
    scraper: ScraperSettings  = field(default_factory=ScraperSettings)
    logging: LoggingSettings  = field(default_factory=LoggingSettings)
    env:     str              = field(default_factory=lambda: os.getenv("APP_ENV", "development"))

    @property
    def is_production(self) -> bool:
        return self.env == "production"


# ── Module-level singleton — import this everywhere ──────────
settings = Settings()
