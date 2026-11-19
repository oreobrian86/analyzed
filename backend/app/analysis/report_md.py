"""Xuất báo cáo ra Markdown (hàm thuần)."""
from __future__ import annotations


def _n(x) -> str:
    if x is None:
        return "—"
    if isinstance(x, float) and x < 1:
        return f"{x:.2%}"
    try:
        return f"{int(x):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(x)


def _insight(i: dict) -> list[str]:
    out = [f"**{i.get('conclusion', '')}** _(độ tin cậy {i.get('confidence', 0):.0%})_"]
    if i.get("evidence"):
        out.append("- Bằng chứng: " + "; ".join(i["evidence"]))
    if i.get("video_refs"):
        out.append("- Video: " + ", ".join(i["video_refs"]))
    for label, key in (("Dữ liệu quan sát", "observed_data"), ("Pattern", "pattern"), ("Giả thuyết", "hypothesis"),
                       ("Khuyến nghị", "recommendation")):
        if i.get(key):
            out.append(f"- {label}: {i[key]}")
    for f in i.get("quality_flags") or []:
        out.append(f"- ⚠ {f}")
    return out + [""]


def render_markdown(r: dict) -> str:
    m, ch = r["meta"], r["channel"]
    L = [f"# Báo cáo kênh {('@' + m['channel']['handle']) if m['channel'].get('handle') else (m['channel'].get('title') or '')}",
         "", f"Tạo lúc {m['generated_at'][:16]} UTC · {m['channel']['videos_analyzed']}/{m['channel']['videos_total']} video được phân tích nội dung", ""]
    if m.get("data_notes"):
        L += ["## Giới hạn dữ liệu"] + [f"- {n}" for n in m["data_notes"]] + [""]
    dna = ch.get("dna") or {}
    L += ["## Channel DNA", dna.get("summary", ""), ""]
    for k, label in (("positioning", "Định vị"), ("target_audience", "Khán giả"), ("tone_and_persona", "Giọng điệu")):
        if dna.get(k):
            L.append(f"- **{label}:** {dna[k]}")
    if dna.get("signature_elements"):
        L.append("- **Dấu hiệu nhận diện:** " + "; ".join(map(str, dna["signature_elements"])))
    f = ch.get("content_formula") or {}
    L += ["", "## Content Formula", f"`{f.get('formula', '')}`", ""] + [f"{i}. {s}" for i, s in enumerate(f.get("steps") or [], 1)] + [""]
    L += ["## Content Pillars", "", "| Pillar | Video | Tỷ trọng | Median views | So với kênh | ER median |", "|---|---|---|---|---|---|"]
    for p in r["pillars"]:
        s = p["stats"]
        L.append(f"| {p['name']} | {s['video_count']} | {s['share']:.0%} | {_n(s['median_views'])} | "
                 f"{(str(s['median_vs_channel']) + '×') if s['median_vs_channel'] is not None else '—'} | {_n(s['median_engagement_rate'])} |")
    L.append("")
    for p in r["pillars"]:
        L += [f"### {p['key']}. {p['name']}", p.get("description", ""), f"- Format: {p.get('content_format', '')}",
              f"- Pattern: {p.get('pattern', '')}", f"- Công thức: {p.get('content_formula', '')}",
              f"- Video đại diện: {p.get('representative_ref')} · Video: {', '.join(p['refs'])}",
              f"- Độ tin cậy: {p.get('confidence', 0):.0%}" + (" · ⚠ mẫu nhỏ" if p["stats"]["small_sample"] else ""), ""]
    pc = r["performance"]["channel"]
    L += ["## Hiệu suất", f"- Median views: {_n(pc.get('median_views'))} · ER median: {_n(pc.get('median_engagement_rate'))} · "
          f"Tần suất: {pc.get('posts_per_week') or '—'} video/tuần",
          f"- Vượt trội so với kênh: {', '.join(r['performance']['outliers']['over']) or 'không có'}",
          f"- Thấp bất thường: {', '.join(r['performance']['outliers']['under']) or 'không có'}"]
    L += [f"- _{n}_" for n in r["performance"].get("notes", [])] + [""]
    if ch.get("insights"):
        L += ["## Insight chính", ""] + [x for i in ch["insights"] for x in _insight(i)]
    if ch.get("weaknesses"):
        L += ["## Điểm yếu nội dung", ""] + [x for i in ch["weaknesses"] for x in _insight(i)]
    st = r["strategy"]
    L += ["## Chiến lược", st.get("summary", ""), ""] + [x for i in st.get("strategy", []) for x in _insight(i)]
    if st.get("opportunities"):
        L += ["## Cơ hội nội dung", ""] + [x for i in st["opportunities"] for x in _insight(i)]
    if st.get("experiments"):
        L += ["## Thử nghiệm đề xuất", ""] + [f"- {e.get('idea')} — đo bằng: {e.get('success_metric')} ({e.get('sample_size', '')})"
                                               for e in st["experiments"]]
    return "\n".join(str(x) for x in L) + "\n"
