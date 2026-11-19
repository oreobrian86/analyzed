"""Stage 2–6: phân tích phân cấp từ dữ liệu có cấu trúc (không nhồi toàn bộ video vào 1 prompt)."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from statistics import median

from .. import db, services
from ..ai import prompts, registry
from ..analysis import clustering, normalize, performance
from ..analysis.report_md import render_markdown
from ..config import settings
from ..quota import limits_for
from .common import check_cancel, stage

MAX_VIDEOS_PER_TOPIC_PROMPT = 25


def _compact(v: dict, a: dict, perf: dict) -> dict:
    hook = a.get("hook") or {}
    return {
        "ref": v["ref"], "main_topic": a.get("main_topic"), "subtopics": (a.get("subtopics") or [])[:4],
        "format": a.get("content_format"), "hook_type": hook.get("type"), "hook": (hook.get("text") or "")[:160],
        "narrative": (a.get("narrative_structure") or "")[:200], "formula": (a.get("content_formula") or "")[:200],
        "cta": (a.get("cta") or {}).get("type"), "strengths": (a.get("strengths") or [])[:2],
        "weaknesses": (a.get("weaknesses") or [])[:2], "views": perf.get("views"),
        "vs_channel_median": perf.get("relative_to_median"), "engagement_rate": perf.get("engagement_rate"),
        "confidence": a.get("confidence"),
    }


def _distribution(videos: list[dict], analyses: dict, pillars: list[dict]) -> dict:
    an = [analyses[v["id"]] for v in videos if v["id"] in analyses]
    n = len(an) or 1
    fmt = Counter(a.get("content_format") or "other" for a in an)
    hooks = Counter((a.get("hook") or {}).get("type") or "unknown" for a in an)
    cta = sum(1 for a in an if (a.get("cta") or {}).get("present"))
    cpm = [v["media_meta"].get("cuts_per_minute") for v in videos if (v.get("media_meta") or {}).get("cuts_per_minute") is not None]
    durs = [v["duration_sec"] or (v.get("media_meta") or {}).get("original_duration") for v in videos]
    durs = [d for d in durs if d]
    return {
        "by_pillar": [{"pillar": p["name"], "videos": p["stats"]["video_count"], "share": p["stats"]["share"]} for p in pillars],
        "by_format": [{"format": k, "videos": c, "share": round(c / n, 3)} for k, c in fmt.most_common()],
        "by_hook_type": [{"hook_type": k, "videos": c, "share": round(c / n, 3)} for k, c in hooks.most_common()],
        "cta_share": round(cta / n, 3),
        "median_duration_sec": round(median(durs), 1) if durs else None,
        "median_cuts_per_minute": round(median(cpm), 1) if cpm else None,
        "analyzed_videos": len(an),
    }


def handle(job: dict) -> None:
    aid = str(job["analysis_id"])
    a = check_cancel(aid)
    uid = a["user_id"]
    lim = limits_for(uid)["max_ai_requests_per_day"]
    lang = settings.report_language
    sys_prompt = prompts.system(lang)
    db.run("update analyses set status='aggregating' where id=%s and status <> 'cancelled'", (aid,))

    videos = db.all_("select * from videos where analysis_id=%s order by ref", (aid,))
    va_rows = db.all_("select va.* from video_analyses va join videos v on v.id=va.video_id where v.analysis_id=%s", (aid,))
    analyses = {r["video_id"]: (r["analysis"] or {}) | {"transcript": r["transcript"]} for r in va_rows}
    analyzed = [v for v in videos if v["id"] in analyses]
    valid_refs = {v["ref"] for v in videos}
    ref_to_id = {v["ref"]: str(v["id"]) for v in videos}
    an_by_ref = {v["ref"]: analyses[v["id"]] for v in analyzed}

    # ---- Hiệu suất (xác định) ----
    stage(aid, "Phân tích hiệu suất (thống kê, không dùng AI)", 0.81)
    perf = performance.analyze(videos)
    perf_by_ref = {r["ref"]: r for r in perf["videos"]}
    ch_median = perf["channel"].get("median_views")

    # ---- Embedding + clustering ----
    stage(aid, "Embedding + phân nhóm nội dung", 0.83)
    texts = [clustering.embedding_text(analyses[v["id"]], v["caption"]) for v in analyzed]
    vecs, eprov, emodel = registry.embed(uid, lim, texts)
    db.run("delete from video_embeddings where analysis_id=%s", (aid,))
    for v, vec in zip(analyzed, vecs):
        db.run("insert into video_embeddings(video_id, analysis_id, provider, model, dims, embedding) values (%s,%s,%s,%s,%s,%s)",
               (v["id"], aid, eprov, emodel, len(vec), vec))
    cl = clustering.cluster(vecs, max_k=min(8, max(2, len(analyzed) // 3)))
    groups: dict[int, list[dict]] = {}
    for v, lab in zip(analyzed, cl["labels"]):
        groups.setdefault(lab, []).append(v)

    # ---- Stage 2: topic ----
    db.run("delete from clusters where analysis_id=%s", (aid,))
    topics = []
    for i, (lab, members) in enumerate(sorted(groups.items(), key=lambda kv: -len(kv[1])), start=1):
        check_cancel(aid)
        key = f"T{i}"
        stage(aid, f"Stage 2: phân tích nhóm chủ đề {key} ({len(members)} video)", 0.85 + 0.04 * i / max(len(groups), 1))
        refs = {m["ref"] for m in members}
        stats = performance.group_stats(perf["videos"], refs, ch_median, len(videos))
        rep_idx = cl["representatives"].get(lab)
        rep_ref = analyzed[rep_idx]["ref"] if rep_idx is not None else members[0]["ref"]
        compact = [_compact(m, analyses[m["id"]], perf_by_ref.get(m["ref"], {})) for m in members][:MAX_VIDEOS_PER_TOPIC_PROMPT]
        res = registry.call_json(uid, lim, prompts.topic_prompt(key, compact, stats), system=sys_prompt, max_output_tokens=2048)
        d = res.data
        if d.get("representative_ref") in refs:
            rep_ref = d["representative_ref"]
        t = {"key": key, "name": normalize.as_str(d.get("name")) or key, "description": normalize.as_str(d.get("description")),
             "topic": normalize.as_str(d.get("topic")), "dominant_format": normalize.as_str(d.get("dominant_format")),
             "common_hooks": normalize.as_list(d.get("common_hooks")), "pattern": normalize.as_str(d.get("pattern")),
             "content_formula": normalize.as_str(d.get("content_formula")), "coherence": d.get("coherence"),
             "confidence": normalize.conf(d.get("confidence")), "refs": sorted(refs), "representative_ref": rep_ref,
             "stats": stats}
        topics.append(t)
        db.run("insert into clusters(analysis_id, kind, key, name, description, data, video_ids) values (%s,'topic',%s,%s,%s,%s,%s)",
               (aid, key, t["name"], t["description"], db.j(t), [ref_to_id[r] for r in refs]))

    # ---- Stage 3: pillar ----
    check_cancel(aid)
    stage(aid, "Stage 3: xác định Content Pillars", 0.90)
    topic_by_key = {t["key"]: t for t in topics}
    raw_pillars = []
    if len(topics) > 1:
        tcompact = [{k: t[k] for k in ("key", "name", "description", "dominant_format", "pattern", "content_formula", "confidence")}
                    | {"videos": t["stats"]["video_count"], "median_vs_channel": t["stats"]["median_vs_channel"]} for t in topics]
        res = registry.call_json(uid, lim, prompts.pillar_prompt(tcompact, len(analyzed)), system=sys_prompt, max_output_tokens=3000)
        raw_pillars = normalize.as_list(res.data.get("pillars"))
    assigned: set[str] = set()
    pillars = []
    for p in raw_pillars:
        if not isinstance(p, dict):
            continue
        keys = [k for k in normalize.as_list(p.get("topic_keys")) if k in topic_by_key and k not in assigned]
        if not keys:
            continue
        assigned.update(keys)
        pillars.append({"name": normalize.as_str(p.get("name")), "description": normalize.as_str(p.get("description")),
                        "topic": normalize.as_str(p.get("topic")), "content_format": normalize.as_str(p.get("content_format")),
                        "pattern": normalize.as_str(p.get("pattern")), "content_formula": normalize.as_str(p.get("content_formula")),
                        "role_in_channel": normalize.as_str(p.get("role_in_channel")), "confidence": normalize.conf(p.get("confidence")),
                        "topic_keys": keys})
    for t in topics:  # topic không được LLM gán => thành pillar riêng (không đánh rơi dữ liệu)
        if t["key"] not in assigned:
            pillars.append({"name": t["name"], "description": t["description"], "topic": t["topic"],
                            "content_format": t["dominant_format"], "pattern": t["pattern"], "content_formula": t["content_formula"],
                            "role_in_channel": "", "confidence": t["confidence"], "topic_keys": [t["key"]]})
    for i, p in enumerate(pillars, start=1):
        p["key"] = f"P{i}"
        refs = set().union(*(set(topic_by_key[k]["refs"]) for k in p["topic_keys"]))
        p["refs"] = sorted(refs)
        p["stats"] = performance.group_stats(perf["videos"], refs, ch_median, len(videos))
        biggest = max((topic_by_key[k] for k in p["topic_keys"]), key=lambda t: len(t["refs"]))
        p["representative_ref"] = biggest["representative_ref"]
        fmts = Counter(an_by_ref[r].get("content_format") or "other" for r in refs if r in an_by_ref)
        p["format_breakdown"] = dict(fmts.most_common(4))
        db.run("insert into clusters(analysis_id, kind, key, name, description, data, video_ids) values (%s,'pillar',%s,%s,%s,%s,%s)",
               (aid, p["key"], p["name"], p["description"], db.j(p), [ref_to_id[r] for r in refs]))
    pillars.sort(key=lambda p: -p["stats"]["video_count"])

    distribution = _distribution(videos, analyses, pillars)
    perf_summary = {"channel": perf["channel"], "outliers": perf["outliers"], "notes": perf["notes"]}
    pillar_compact = [{k: p[k] for k in ("key", "name", "description", "content_format", "pattern", "content_formula",
                                         "role_in_channel", "representative_ref", "stats", "refs")} for p in pillars]
    pillar_of = {r: p["key"] for p in pillars for r in p["refs"]}
    index = [{"ref": v["ref"], "pillar": pillar_of.get(v["ref"]), "topic": analyses[v["id"]].get("main_topic"),
              "format": analyses[v["id"]].get("content_format"), "hook_type": (analyses[v["id"]].get("hook") or {}).get("type"),
              "views": perf_by_ref.get(v["ref"], {}).get("views"),
              "vs_median": perf_by_ref.get(v["ref"], {}).get("relative_to_median"),
              "er": perf_by_ref.get(v["ref"], {}).get("engagement_rate")} for v in analyzed][:80]
    channel_info = {"handle": (a.get("options") or {}).get("handle"), "title": a.get("title"), "videos_total": len(videos),
                    "videos_analyzed": len(analyzed)}

    # ---- Stage 4: channel ----
    check_cancel(aid)
    stage(aid, "Stage 4: Channel DNA & Content Formula", 0.93)
    r4 = registry.call_json(uid, lim, prompts.channel_prompt(channel_info, pillar_compact, distribution, perf_summary, index),
                            system=sys_prompt, max_output_tokens=6000).data
    channel = {
        "dna": r4.get("channel_dna") if isinstance(r4.get("channel_dna"), dict) else {},
        "content_formula": r4.get("content_formula") if isinstance(r4.get("content_formula"), dict) else {},
        "insights": normalize.insights(r4.get("insights"), valid_refs),
        "weaknesses": normalize.insights(r4.get("weaknesses"), valid_refs),
    }
    for k in ("dna", "content_formula"):
        channel[k]["confidence"] = normalize.conf(channel[k].get("confidence"))

    # ---- Stage 5: strategy ----
    check_cancel(aid)
    stage(aid, "Stage 5: Chiến lược & cơ hội nội dung", 0.96)
    r5 = registry.call_json(uid, lim, prompts.strategy_prompt(
        {"dna": channel["dna"], "formula": channel["content_formula"], "insights": channel["insights"]},
        pillar_compact, perf_summary, channel["weaknesses"]), system=sys_prompt, max_output_tokens=6000).data
    experiments = []
    for e in normalize.as_list(r5.get("experiments")):
        if isinstance(e, dict):
            e["based_on_refs"] = [r for r in normalize.as_list(e.get("based_on_refs")) if r in valid_refs]
            experiments.append(e)
    strategy = {"summary": normalize.as_str(r5.get("summary")),
                "opportunities": normalize.insights(r5.get("opportunities"), valid_refs),
                "strategy": normalize.insights(r5.get("strategy"), valid_refs),
                "content_mix": [m for m in normalize.as_list(r5.get("content_mix")) if isinstance(m, dict)],
                "experiments": experiments}

    # ---- Stage 6: report ----
    stage(aid, "Stage 6: Tạo báo cáo", 0.99)
    data_notes = list(perf["notes"])
    if eprov == "local":
        data_notes.append("Embedding dùng chế độ local (hashing TF-IDF) — phân nhóm kém chính xác hơn embedding AI.")
    failed = [v["ref"] for v in videos if v["status"] in ("failed", "cancelled")]
    skipped = [v["ref"] for v in videos if v["status"] == "skipped"]
    if failed:
        data_notes.append(f"{len(failed)} video lỗi không được phân tích nội dung: {', '.join(failed[:15])}.")
    if skipped:
        data_notes.append(f"{len(skipped)} video bị bỏ qua: {', '.join(skipped[:15])}.")
    modes = Counter(r["input_mode"] for r in va_rows)
    if modes.get("frames+transcript"):
        data_notes.append(f"{modes['frames+transcript']} video được phân tích qua keyframe + transcript (không xem chuyển động).")

    report = {
        "meta": {"analysis_id": aid, "channel": channel_info, "generated_at": datetime.now(timezone.utc).isoformat(),
                 "language": lang, "prompt_version": prompts.PROMPT_VERSION, "ai": registry.describe(),
                 "embedding": {"provider": eprov, "model": emodel}, "clustering": {"k": cl["k"], "silhouette": cl["silhouette"]},
                 "data_notes": data_notes},
        "videos": [{"ref": v["ref"], "id": str(v["id"]), "url": v["url"], "caption": (v["caption"] or "")[:200],
                    "status": v["status"], "pillar": pillar_of.get(v["ref"]),
                    "main_topic": analyses.get(v["id"], {}).get("main_topic"),
                    "format": analyses.get(v["id"], {}).get("content_format"), **{k: perf_by_ref.get(v["ref"], {}).get(k) for k in
                    ("views", "engagement_rate", "relative_to_median", "views_z", "age_days")}} for v in videos],
        "performance": perf_summary,
        "distribution": distribution,
        "topics": topics,
        "pillars": pillars,
        "channel": channel,
        "strategy": strategy,
    }
    md = render_markdown(report)
    db.run("""insert into reports(analysis_id, user_id, report, markdown) values (%s,%s,%s,%s)
              on conflict (analysis_id) do update set report=excluded.report, markdown=excluded.markdown, created_at=now()""",
           (aid, uid, db.j(report), md))
    final = "partial" if failed else "done"
    db.run("""update analyses set status=%s, stage='Hoàn tất', progress=1, finished_at=now(), updated_at=now(), expires_at=%s, error=null
              where id=%s and status <> 'cancelled'""", (final, services.expires_at(), aid))
    db.log(aid, "Báo cáo kênh đã sẵn sàng.")


def on_final_failure(job: dict, error: str) -> None:
    db.run("update analyses set status='failed', error=%s, finished_at=now() where id=%s and status <> 'cancelled'",
           ("Lỗi ở bước tổng hợp kênh: " + error[:800] + " — bấm Retry để chạy lại bước tổng hợp (video đã phân tích được giữ nguyên).",
            job["analysis_id"]))
