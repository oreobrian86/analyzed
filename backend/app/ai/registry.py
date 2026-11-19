"""Chọn provider theo env + bọc mọi lời gọi AI bằng: quota, rate limit toàn cục, retry giới hạn."""
from __future__ import annotations

import threading
import time
from collections import deque

from .. import quota
from ..config import settings
from .base import AIError, AIProvider, AIResult
from .local_embed import MODEL_NAME as LOCAL_MODEL
from .local_embed import local_embed

_instances: dict[str, AIProvider] = {}
_lock = threading.Lock()


def _make(name: str) -> AIProvider:
    if name == "gemini":
        from .gemini import GeminiProvider
        return GeminiProvider()
    if name == "openai_compat":
        from .openai_compat import OpenAICompatProvider
        return OpenAICompatProvider()
    raise AIError(f"AI provider không hỗ trợ: {name}")


def _get(name: str) -> AIProvider:
    with _lock:
        if name not in _instances:
            _instances[name] = _make(name)
        return _instances[name]


def provider(purpose: str = "video") -> AIProvider:
    return _get(settings.ai_provider if purpose == "video" else (settings.ai_text_provider or settings.ai_provider))


# ---------- Rate limiter toàn cục (requests/phút) ----------
class _RPM:
    def __init__(self, rpm: int):
        self.rpm = max(1, rpm)
        self.q: deque = deque()
        self.lock = threading.Lock()

    def wait(self) -> None:
        while True:
            with self.lock:
                now = time.time()
                while self.q and self.q[0] < now - 60:
                    self.q.popleft()
                if len(self.q) < self.rpm:
                    self.q.append(now)
                    return
                sleep = 60 - (now - self.q[0]) + 0.1
            time.sleep(min(max(sleep, 0.5), 30))


_rpm = _RPM(settings.ai_rpm)


def call_json(user_id: str, user_limit: int, prompt: str, **kw) -> AIResult:
    """Gọi AI có kiểm soát chi phí. Mỗi lần thử (kể cả retry) đều tính 1 request vào quota."""
    purpose = kw.get("purpose", "text")
    p = provider("video" if purpose == "video" else "text")
    last: Exception | None = None
    for attempt in range(settings.ai_max_retries + 1):
        quota.consume(user_id, "ai_requests", 1, user_limit)
        _rpm.wait()
        try:
            res = p.generate_json(prompt, **kw)
            quota.add_tokens(user_id, res.input_tokens, res.output_tokens)
            return res
        except AIError as e:
            last = e
            if not e.retryable or attempt >= settings.ai_max_retries:
                raise
            time.sleep(min(e.retry_after or (5 * 2 ** attempt), 60))
    raise last or AIError("AI call failed")


def embed(user_id: str, user_limit: int, texts: list[str]) -> tuple[list[list[float]], str, str]:
    """Trả (vectors, provider, model). Lỗi/hết quota => fallback local (ghi rõ trong báo cáo)."""
    name = settings.embedding_provider
    if name != "local" and texts:
        try:
            p = _get(name)
            if p.supports_embedding:
                n_calls = (len(texts) + 49) // 50
                quota.consume(user_id, "ai_requests", n_calls, user_limit)
                _rpm.wait()
                vecs, model = p.embed(texts)
                return vecs, p.name, model
        except (AIError, quota.QuotaExceeded, Exception):
            pass
    return local_embed(texts), "local", LOCAL_MODEL


def describe() -> dict:
    out = {"video_provider": settings.ai_provider, "text_provider": settings.ai_text_provider or settings.ai_provider,
           "embedding_provider": settings.embedding_provider}
    if settings.ai_provider == "gemini":
        out.update(video_model=settings.gemini_video_model, text_model=settings.gemini_text_model,
                   embed_model=settings.gemini_embed_model)
    return out
