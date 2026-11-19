"""Gemini qua REST (không phụ thuộc SDK để dễ thay đổi). Hỗ trợ video, ảnh, audio, embedding."""
from __future__ import annotations

import base64
import re
import time
from pathlib import Path

import httpx

from ..config import settings
from .base import AIError, AIProvider, AIResult, MediaPart, parse_json_loose

API = "https://generativelanguage.googleapis.com/v1beta"
UPLOAD = "https://generativelanguage.googleapis.com/upload/v1beta/files"


def _err(r: httpx.Response) -> AIError:
    retry_after = None
    try:
        body = r.json()
        msg = body.get("error", {}).get("message", r.text[:300])
        for d in body.get("error", {}).get("details", []) or []:
            m = re.match(r"(\d+(?:\.\d+)?)s", str(d.get("retryDelay", "")))
            if m:
                retry_after = float(m.group(1))
    except Exception:
        msg = r.text[:300]
    retryable = r.status_code in (408, 429, 500, 502, 503, 504)
    if r.status_code == 429:
        msg = "Gemini báo vượt rate limit / quota free tier (429). " + msg
    return AIError(f"Gemini HTTP {r.status_code}: {msg}", retryable=retryable, retry_after=retry_after)


class GeminiProvider(AIProvider):
    name = "gemini"
    supports_video = True
    supports_images = True
    supports_transcription = True
    supports_embedding = True

    def __init__(self) -> None:
        if not settings.gemini_api_key:
            raise AIError("Thiếu GEMINI_API_KEY")
        self.key = settings.gemini_api_key
        self.http = httpx.Client(timeout=httpx.Timeout(300, connect=20))

    def _headers(self) -> dict:
        return {"x-goog-api-key": self.key}

    # ---------- Files API (cho video lớn) ----------
    def _upload_file(self, part: MediaPart) -> dict:
        size = part.path.stat().st_size
        r = self.http.post(
            UPLOAD,
            headers={
                **self._headers(),
                "X-Goog-Upload-Protocol": "resumable",
                "X-Goog-Upload-Command": "start",
                "X-Goog-Upload-Header-Content-Length": str(size),
                "X-Goog-Upload-Header-Content-Type": part.mime,
                "Content-Type": "application/json",
            },
            json={"file": {"display_name": part.path.name}},
        )
        if r.status_code != 200:
            raise _err(r)
        url = r.headers.get("x-goog-upload-url")
        if not url:
            raise AIError("Gemini Files API không trả upload URL")
        with open(part.path, "rb") as f:
            r = self.http.post(
                url,
                headers={"Content-Length": str(size), "X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize"},
                content=f.read(),
            )
        if r.status_code != 200:
            raise _err(r)
        info = r.json()["file"]
        deadline = time.time() + 180
        while info.get("state") == "PROCESSING" and time.time() < deadline:
            time.sleep(3)
            g = self.http.get(f"{API}/{info['name']}", headers=self._headers())
            if g.status_code != 200:
                raise _err(g)
            info = g.json()
        if info.get("state") != "ACTIVE":
            raise AIError(f"Gemini không xử lý được file (state={info.get('state')})", retryable=True)
        return info

    def _delete_file(self, name: str) -> None:
        try:
            self.http.delete(f"{API}/{name}", headers=self._headers())
        except httpx.HTTPError:
            pass  # Gemini tự xoá file sau 48h

    def _parts(self, media: list[MediaPart], uploaded: list[str]) -> list[dict]:
        parts = []
        inline_limit = settings.inline_video_max_mb * 1024 * 1024
        for m in media:
            size = m.path.stat().st_size
            if size <= inline_limit:
                parts.append({"inline_data": {"mime_type": m.mime, "data": base64.b64encode(m.path.read_bytes()).decode()}})
            else:
                info = self._upload_file(m)
                uploaded.append(info["name"])
                parts.append({"file_data": {"mime_type": m.mime, "file_uri": info["uri"]}})
        return parts

    def generate_json(self, prompt, *, system=None, media=None, purpose="text", max_output_tokens=8192, temperature=0.2) -> AIResult:
        model = settings.gemini_video_model if purpose == "video" else settings.gemini_text_model
        uploaded: list[str] = []
        try:
            parts = self._parts(media or [], uploaded) + [{"text": prompt}]
            body: dict = {
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "temperature": temperature,
                    "maxOutputTokens": max_output_tokens,
                },
            }
            if media and settings.gemini_media_resolution:
                body["generationConfig"]["mediaResolution"] = settings.gemini_media_resolution
            if settings.gemini_thinking_level:
                body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": settings.gemini_thinking_level}
            if system:
                body["systemInstruction"] = {"parts": [{"text": system}]}
            try:
                r = self.http.post(f"{API}/models/{model}:generateContent", headers=self._headers(), json=body)
            except httpx.TimeoutException:
                raise AIError("Gemini timeout", retryable=True)
            if r.status_code == 400 and any(k in r.text for k in ("mediaResolution", "thinking", "media_resolution")):
                # model không hỗ trợ tham số tối ưu => gửi lại bản tối giản
                body["generationConfig"].pop("mediaResolution", None)
                body["generationConfig"].pop("thinkingConfig", None)
                r = self.http.post(f"{API}/models/{model}:generateContent", headers=self._headers(), json=body)
            if r.status_code != 200:
                raise _err(r)
            data = r.json()
            cands = data.get("candidates") or []
            if not cands:
                reason = (data.get("promptFeedback") or {}).get("blockReason", "không rõ")
                raise AIError(f"Gemini không trả kết quả (blockReason={reason})")
            cand = cands[0]
            text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []) if not p.get("thought"))
            if cand.get("finishReason") == "MAX_TOKENS" and not text.rstrip().endswith("}"):
                raise AIError("Output bị cắt do MAX_TOKENS", retryable=False)
            usage = data.get("usageMetadata") or {}
            return AIResult(
                data=parse_json_loose(text),
                raw_text=text,
                model=model,
                provider=self.name,
                input_tokens=int(usage.get("promptTokenCount") or 0),
                output_tokens=int(usage.get("candidatesTokenCount") or 0) + int(usage.get("thoughtsTokenCount") or 0),
            )
        finally:
            for name in uploaded:
                self._delete_file(name)

    def embed(self, texts: list[str]) -> tuple[list[list[float]], str]:
        model = settings.gemini_embed_model
        out: list[list[float]] = []
        for i in range(0, len(texts), 50):
            batch = texts[i : i + 50]
            body = {
                "requests": [
                    {
                        "model": f"models/{model}",
                        "content": {"parts": [{"text": t[:6000]}]},
                        "taskType": "CLUSTERING",
                        "outputDimensionality": 768,
                    }
                    for t in batch
                ]
            }
            r = self.http.post(f"{API}/models/{model}:batchEmbedContents", headers=self._headers(), json=body)
            if r.status_code != 200:
                raise _err(r)
            out.extend(e["values"] for e in r.json()["embeddings"])
        return out, model

    def transcribe(self, audio: Path) -> str:
        res = self.generate_json(
            'Transcribe this audio verbatim in its original language. Return JSON {"transcript": "..."}',
            media=[MediaPart("audio", audio, "audio/mpeg")],
        )
        return str(res.data.get("transcript", ""))
