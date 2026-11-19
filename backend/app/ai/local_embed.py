"""Embedding chạy ngay trong backend, không gọi AI (fallback khi hết quota / không cấu hình embedding).

Char n-gram + word hashing + TF-IDF: chịu được tiếng Việt có dấu/không dấu ở mức chấp nhận được.
Chất lượng thấp hơn embedding neural, nên báo cáo ghi rõ khi dùng chế độ này.
"""
from __future__ import annotations

import unicodedata

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer, TfidfTransformer
from sklearn.pipeline import FeatureUnion

MODEL_NAME = "local-hashing-tfidf-v1"


def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower()).replace("đ", "d")
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def local_embed(texts: list[str], dims: int = 2048) -> list[list[float]]:
    if not texts:
        return []
    docs = [_strip_accents(t or "") for t in texts]
    union = FeatureUnion([
        ("w", HashingVectorizer(n_features=dims, analyzer="word", ngram_range=(1, 2), alternate_sign=False, norm=None)),
        ("c", HashingVectorizer(n_features=dims, analyzer="char_wb", ngram_range=(3, 5), alternate_sign=False, norm=None)),
    ])
    x = union.transform(docs)
    x = TfidfTransformer(sublinear_tf=True).fit_transform(x)
    arr = x.toarray().astype(np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return (arr / norms).tolist()
