"""Supabase Storage qua REST API (service role key chỉ nằm ở backend)."""
from __future__ import annotations

from pathlib import Path

import httpx

from .config import settings


def _h(extra: dict | None = None) -> dict:
    h = {"apikey": settings.supabase_service_key, "Authorization": f"Bearer {settings.supabase_service_key}"}
    if extra:
        h.update(extra)
    return h


def _base() -> str:
    return f"{settings.supabase_url}/storage/v1"


def upload_file(bucket: str, path: str, file_path: Path, content_type: str) -> None:
    r = httpx.post(
        f"{_base()}/object/{bucket}/{path}",
        headers=_h({"Content-Type": content_type, "x-upsert": "true"}),
        content=Path(file_path).read_bytes(),
        timeout=300,
    )
    r.raise_for_status()


def upload_bytes(bucket: str, path: str, data: bytes, content_type: str) -> None:
    r = httpx.post(
        f"{_base()}/object/{bucket}/{path}",
        headers=_h({"Content-Type": content_type, "x-upsert": "true"}),
        content=data,
        timeout=120,
    )
    r.raise_for_status()


def download_to(bucket: str, path: str, dest: Path, max_bytes: int) -> None:
    with httpx.stream("GET", f"{_base()}/object/authenticated/{bucket}/{path}", headers=_h(), timeout=300) as r:
        r.raise_for_status()
        total = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(1024 * 256):
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("File vượt giới hạn dung lượng.")
                f.write(chunk)


def signed_urls(bucket: str, paths: list[str], expires_in: int = 3600) -> dict[str, str]:
    if not paths:
        return {}
    try:
        r = httpx.post(
            f"{_base()}/object/sign/{bucket}",
            headers=_h({"Content-Type": "application/json"}),
            json={"expiresIn": expires_in, "paths": paths},
            timeout=20,
        )
        r.raise_for_status()
    except httpx.HTTPError:
        return {}
    out = {}
    for item in r.json():
        url = item.get("signedURL") or item.get("signedUrl")
        if url and not item.get("error"):
            out[item["path"]] = f"{settings.supabase_url}/storage/v1{url}"
    return out


def delete(bucket: str, paths: list[str]) -> None:
    paths = [p for p in paths if p]
    for i in range(0, len(paths), 100):
        try:
            httpx.request(
                "DELETE",
                f"{_base()}/object/{bucket}",
                headers=_h({"Content-Type": "application/json"}),
                json={"prefixes": paths[i : i + 100]},
                timeout=30,
            )
        except httpx.HTTPError:
            pass
