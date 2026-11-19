"""Phân nhóm video bằng embedding + KMeans (cosine), chọn k theo silhouette. Không dùng LLM."""
from __future__ import annotations

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score


def cluster(vectors: list[list[float]], max_k: int = 8, min_size_for_split: int = 4, seed: int = 42) -> dict:
    n = len(vectors)
    if n == 0:
        return {"labels": [], "k": 0, "silhouette": None, "representatives": {}}
    x = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    norms[norms == 0] = 1
    x = x / norms  # chuẩn hoá => Euclid trên vector đơn vị tương đương cosine

    best = {"labels": np.zeros(n, dtype=int), "k": 1, "silhouette": None}
    if n >= min_size_for_split:
        upper = min(max_k, n // 2, n - 1)
        for k in range(2, upper + 1):
            km = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(x)
            if len(set(km.labels_)) < 2:
                continue
            s = float(silhouette_score(x, km.labels_, metric="cosine"))
            if best["silhouette"] is None or s > best["silhouette"]:
                best = {"labels": km.labels_, "k": k, "silhouette": s}
        if best["silhouette"] is not None and best["silhouette"] < 0.04:
            # cấu trúc nhóm quá yếu => giữ 1 nhóm, tránh chia nhóm giả tạo
            best = {"labels": np.zeros(n, dtype=int), "k": 1, "silhouette": best["silhouette"]}

    labels = [int(l) for l in best["labels"]]
    reps: dict[int, int] = {}
    for c in sorted(set(labels)):
        idx = [i for i, l in enumerate(labels) if l == c]
        centroid = x[idx].mean(axis=0)
        reps[c] = idx[int(np.argmax(x[idx] @ centroid))]
    return {"labels": labels, "k": best["k"],
            "silhouette": round(best["silhouette"], 3) if best["silhouette"] is not None else None,
            "representatives": reps}


def embedding_text(a: dict, caption: str | None) -> str:
    """Văn bản đại diện nội dung để embed (từ phân tích thực tế, không chỉ caption)."""
    hook = a.get("hook") or {}
    parts = [
        a.get("main_topic") or "",
        ", ".join(a.get("subtopics") or []),
        a.get("content_format") or "",
        f"hook: {hook.get('type', '')} {hook.get('text', '')}",
        a.get("content_formula") or "",
        a.get("narrative_structure") or "",
        (a.get("transcript") or "")[:800],
        (caption or "")[:300],
    ]
    return "\n".join(p for p in parts if p)
