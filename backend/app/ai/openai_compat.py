"""Provider cho mọi API tương thích OpenAI (Groq, OpenRouter, Mistral, OpenAI, Together...).

Không gửi được video => pipeline dùng chế độ 'frames+transcript': keyframe (ảnh) + transcript từ audio.
"""
from __future__ import annotations

import base64

import httpx

from ..config import settings
from .base import AIError, AIProvider, AIResult, parse_json_loose


class OpenAICompatProvider(AIProvider):
    name = "openai_compat"
    supports_video = False

    def __init__(self) -> None:
        if not (settings.openai_base_url and settings.openai_api_key and settings.openai_text_model):
            raise AIError("Thiếu OPENAI_COMPAT_BASE_URL / OPENAI_COMPAT_API_KEY / OPENAI_COMPAT_TEXT_MODEL")
        self.base = settings.openai_base_url
        self.http = httpx.Client(timeout=httpx.Timeout(240, connect=20), headers={"Authorization": f"Bearer {settings.openai_api_key}"})
        self.supports_images = bool(settings.openai_vision_model)
        self.supports_transcription = bool(settings.openai_transcribe_model)
        self.supports_embedding = bool(settings.openai_embed_model)

    def _check(self, r: httpx.Response) -> dict:
        if r.status_code != 200:
            retry_after = None
            try:
                retry_after = float(r.headers.get("retry-after", ""))
            except ValueError:
                pass
            raise AIError(f"{self.name} HTTP {r.status_code}: {r.text[:300]}",
                          retryable=r.status_code in (408, 429, 500, 502, 503, 504), retry_after=retry_after)
        return r.json()

    def generate_json(self, prompt, *, system=None, media=None, purpose="text", max_output_tokens=8192, temperature=0.2) -> AIResult:
        images = [m for m in (media or []) if m.kind == "image"]
        if any(m.kind == "video" for m in (media or [])):
            raise AIError("Provider này không nhận video trực tiếp")
        model = settings.openai_vision_model if images else settings.openai_text_model
        if images and not model:
            raise AIError("Chưa cấu hình OPENAI_COMPAT_VISION_MODEL")
        content: list | str = prompt
        if images:
            content = [{"type": "text", "text": prompt}] + [
                {"type": "image_url", "image_url": {"url": f"data:{m.mime};base64,{base64.b64encode(m.path.read_bytes()).decode()}"}}
                for m in images
            ]
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": content}]
        body = {"model": model, "messages": msgs, "temperature": temperature, "max_tokens": max_output_tokens,
                "response_format": {"type": "json_object"}}
        try:
            r = self.http.post(f"{self.base}/chat/completions", json=body)
            if r.status_code == 400 and "response_format" in r.text:
                body.pop("response_format")
                r = self.http.post(f"{self.base}/chat/completions", json=body)
        except httpx.TimeoutException:
            raise AIError("Timeout", retryable=True)
        data = self._check(r)
        text = data["choices"][0]["message"].get("content") or ""
        usage = data.get("usage") or {}
        return AIResult(parse_json_loose(text), text, model, self.name,
                        int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0))

    def transcribe(self, audio) -> str:
        if not self.supports_transcription:
            raise AIError("Chưa cấu hình OPENAI_COMPAT_TRANSCRIBE_MODEL")
        with open(audio, "rb") as f:
            r = self.http.post(f"{self.base}/audio/transcriptions",
                               data={"model": settings.openai_transcribe_model, "response_format": "json"},
                               files={"file": (audio.name, f, "audio/mpeg")})
        return str(self._check(r).get("text", ""))

    def embed(self, texts):
        if not self.supports_embedding:
            raise AIError("Chưa cấu hình OPENAI_COMPAT_EMBED_MODEL")
        out = []
        for i in range(0, len(texts), 64):
            r = self.http.post(f"{self.base}/embeddings", json={"model": settings.openai_embed_model, "input": [t[:6000] for t in texts[i:i + 64]]})
            out.extend(d["embedding"] for d in sorted(self._check(r)["data"], key=lambda d: d["index"]))
        return out, settings.openai_embed_model
