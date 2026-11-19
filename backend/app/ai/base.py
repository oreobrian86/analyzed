"""AI provider abstraction. Thêm provider mới = viết 1 class kế thừa AIProvider + đăng ký trong registry."""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


class AIError(Exception):
    """Lỗi gọi AI. retryable=True nếu nên thử lại (429, 5xx, timeout)."""

    def __init__(self, message: str, retryable: bool = False, retry_after: float | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after


@dataclass
class MediaPart:
    kind: str  # 'video' | 'image' | 'audio'
    path: Path
    mime: str


@dataclass
class AIResult:
    data: dict
    raw_text: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    extra: dict = field(default_factory=dict)


class AIProvider(ABC):
    name = "base"
    supports_video = False
    supports_images = False
    supports_transcription = False
    supports_embedding = False

    @abstractmethod
    def generate_json(
        self,
        prompt: str,
        *,
        system: str | None = None,
        media: list[MediaPart] | None = None,
        purpose: str = "text",  # 'video' | 'text'
        max_output_tokens: int = 8192,
        temperature: float = 0.2,
    ) -> AIResult: ...

    def embed(self, texts: list[str]) -> tuple[list[list[float]], str]:
        raise AIError(f"{self.name} không hỗ trợ embedding")

    def transcribe(self, audio: Path) -> str:
        raise AIError(f"{self.name} không hỗ trợ transcription")

    def describe(self) -> dict:
        return {
            "name": self.name,
            "video": self.supports_video,
            "images": self.supports_images,
            "transcription": self.supports_transcription,
            "embedding": self.supports_embedding,
        }


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I | re.M)


def parse_json_loose(text: str) -> dict:
    """Parse JSON từ output model; chịu được ```json fences và text thừa."""
    t = _FENCE.sub("", (text or "").strip()).strip()
    try:
        v = json.loads(t)
        return v if isinstance(v, dict) else {"items": v}
    except json.JSONDecodeError:
        pass
    start, end = t.find("{"), t.rfind("}")
    if start >= 0 and end > start:
        try:
            v = json.loads(t[start : end + 1])
            return v if isinstance(v, dict) else {"items": v}
        except json.JSONDecodeError:
            pass
    raise AIError("Model trả về JSON không hợp lệ", retryable=True)
