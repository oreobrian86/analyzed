"""Toàn bộ cấu hình đọc từ environment variables của hosting (KHÔNG hard-code secret)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _s(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _i(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _b(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _list(name: str) -> list[str]:
    return [x.strip().lower() for x in _s(name).split(",") if x.strip()]


# Các giới hạn mặc định cho MỖI user. Có thể ghi đè qua env hoặc profiles.quota_overrides.
LIMIT_KEYS = {
    "max_videos_per_analysis": 20,
    "max_analyses_per_day": 3,
    "max_videos_per_day": 40,
    "max_ai_requests_per_day": 150,
    "max_active_analyses": 1,
    "max_upload_mb": 50,
    "max_upload_bytes_per_day_mb": 300,
    "max_storage_mb": 200,
}


@dataclass
class Settings:
    # --- Supabase ---
    supabase_url: str = field(default_factory=lambda: _s("SUPABASE_URL").rstrip("/"))
    supabase_anon_key: str = field(default_factory=lambda: _s("SUPABASE_ANON_KEY"))
    supabase_service_key: str = field(default_factory=lambda: _s("SUPABASE_SERVICE_ROLE_KEY"))
    database_url: str = field(default_factory=lambda: _s("DATABASE_URL"))

    # --- Truy cập ---
    cors_origins: list[str] = field(default_factory=lambda: [o.strip() for o in _s("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()])
    allowed_emails: list[str] = field(default_factory=lambda: _list("ALLOWED_EMAILS"))
    allowed_email_domains: list[str] = field(default_factory=lambda: _list("ALLOWED_EMAIL_DOMAINS"))
    admin_emails: list[str] = field(default_factory=lambda: _list("ADMIN_EMAILS"))
    public_base_url: str = field(default_factory=lambda: _s("PUBLIC_BASE_URL").rstrip("/"))

    # --- AI ---
    ai_provider: str = field(default_factory=lambda: _s("AI_PROVIDER", "gemini"))
    ai_text_provider: str = field(default_factory=lambda: _s("AI_TEXT_PROVIDER"))  # rỗng = dùng AI_PROVIDER
    embedding_provider: str = field(default_factory=lambda: _s("EMBEDDING_PROVIDER", "gemini"))  # gemini | openai_compat | local
    gemini_api_key: str = field(default_factory=lambda: _s("GEMINI_API_KEY"))
    gemini_video_model: str = field(default_factory=lambda: _s("GEMINI_VIDEO_MODEL", "gemini-3.5-flash"))
    gemini_text_model: str = field(default_factory=lambda: _s("GEMINI_TEXT_MODEL", "gemini-3.5-flash"))
    gemini_embed_model: str = field(default_factory=lambda: _s("GEMINI_EMBED_MODEL", "gemini-embedding-001"))
    gemini_thinking_level: str = field(default_factory=lambda: _s("GEMINI_THINKING_LEVEL", "low"))
    gemini_media_resolution: str = field(default_factory=lambda: _s("GEMINI_MEDIA_RESOLUTION", "MEDIA_RESOLUTION_LOW"))
    openai_base_url: str = field(default_factory=lambda: _s("OPENAI_COMPAT_BASE_URL").rstrip("/"))
    openai_api_key: str = field(default_factory=lambda: _s("OPENAI_COMPAT_API_KEY"))
    openai_text_model: str = field(default_factory=lambda: _s("OPENAI_COMPAT_TEXT_MODEL"))
    openai_vision_model: str = field(default_factory=lambda: _s("OPENAI_COMPAT_VISION_MODEL"))
    openai_transcribe_model: str = field(default_factory=lambda: _s("OPENAI_COMPAT_TRANSCRIBE_MODEL"))
    openai_embed_model: str = field(default_factory=lambda: _s("OPENAI_COMPAT_EMBED_MODEL"))
    ai_rpm: int = field(default_factory=lambda: _i("AI_REQUESTS_PER_MINUTE", 8))
    ai_max_retries: int = field(default_factory=lambda: _i("AI_MAX_RETRIES", 3))
    report_language: str = field(default_factory=lambda: _s("REPORT_LANGUAGE", "Vietnamese"))

    # --- Collector ---
    apify_token: str = field(default_factory=lambda: _s("APIFY_TOKEN"))
    apify_actor: str = field(default_factory=lambda: _s("APIFY_ACTOR_ID", "clockworks~tiktok-scraper"))

    # --- Media ---
    max_video_seconds: int = field(default_factory=lambda: _i("MAX_VIDEO_SECONDS", 180))
    max_download_mb: int = field(default_factory=lambda: _i("MAX_DOWNLOAD_MB", 80))
    max_height: int = field(default_factory=lambda: _i("MAX_VIDEO_HEIGHT", 640))
    keyframes_per_video: int = field(default_factory=lambda: _i("KEYFRAMES_PER_VIDEO", 4))
    scene_threshold: float = field(default_factory=lambda: _f("SCENE_THRESHOLD", 0.30))
    inline_video_max_mb: int = field(default_factory=lambda: _i("INLINE_VIDEO_MAX_MB", 14))

    # --- Worker ---
    run_worker: bool = field(default_factory=lambda: _b("RUN_WORKER", True))
    worker_concurrency: int = field(default_factory=lambda: _i("WORKER_CONCURRENCY", 1))
    max_running_jobs_per_user: int = field(default_factory=lambda: _i("MAX_RUNNING_JOBS_PER_USER", 1))
    job_max_attempts: int = field(default_factory=lambda: _i("JOB_MAX_ATTEMPTS", 3))
    stale_job_seconds: int = field(default_factory=lambda: _i("STALE_JOB_SECONDS", 300))
    keepalive_while_busy: bool = field(default_factory=lambda: _b("KEEPALIVE_WHILE_BUSY", True))

    # --- Retention / global caps ---
    retention_days: int = field(default_factory=lambda: _i("RETENTION_DAYS", 30))
    keyframe_retention_days: int = field(default_factory=lambda: _i("KEYFRAME_RETENTION_DAYS", 14))
    global_max_ai_requests_per_day: int = field(default_factory=lambda: _i("GLOBAL_MAX_AI_REQUESTS_PER_DAY", 600))
    global_max_videos_per_day: int = field(default_factory=lambda: _i("GLOBAL_MAX_VIDEOS_PER_DAY", 200))
    global_max_upload_mb_per_day: int = field(default_factory=lambda: _i("GLOBAL_MAX_UPLOAD_MB_PER_DAY", 1500))
    api_rate_per_minute: int = field(default_factory=lambda: _i("API_RATE_PER_MINUTE", 90))

    default_limits: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.default_limits = {k: _i(k.upper(), v) for k, v in LIMIT_KEYS.items()}

    def missing_required(self) -> list[str]:
        req = {
            "SUPABASE_URL": self.supabase_url,
            "SUPABASE_ANON_KEY": self.supabase_anon_key,
            "SUPABASE_SERVICE_ROLE_KEY": self.supabase_service_key,
            "DATABASE_URL": self.database_url,
        }
        if self.ai_provider == "gemini" or self.embedding_provider == "gemini":
            req["GEMINI_API_KEY"] = self.gemini_api_key
        return [k for k, v in req.items() if not v]


settings = Settings()
