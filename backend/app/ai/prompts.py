"""Prompt cho 6 stage. Đổi nội dung prompt => tăng PROMPT_VERSION để cache không dùng kết quả cũ."""
from __future__ import annotations

import json

PROMPT_VERSION = "v1.2"

RULES = """Rules you MUST follow:
- Only state what is observable in the provided media/data. Never invent numbers, quotes, scenes or metrics.
- If something cannot be determined, use null or "unknown" and explain in data_limitations.
- Distinguish observation (what is seen/heard) from hypothesis (why it may work). Correlation is not causation.
- Do not call a video "viral" based on views alone.
- confidence is a number 0..1 reflecting how well the evidence supports the claim.
- Output ONLY valid JSON matching the schema. Field names in English; all human-readable text values in {lang}.
"""

VIDEO_SCHEMA = {
    "language": "detected spoken/written language code",
    "transcript": "verbatim transcript of speech (empty string if no speech)",
    "ocr_text": "all on-screen text in order, separated by ' | '",
    "main_topic": "string",
    "subtopics": ["string"],
    "content_format": "one of: talking_head, tutorial, listicle, storytelling, vlog, skit_comedy, review, reaction, news_commentary, behind_the_scenes, montage_broll, interview, challenge_trend, slideshow, other",
    "target_audience": "string",
    "hook": {"text": "exact words/visual in first ~3s", "type": "one of: question, bold_claim, curiosity_gap, pain_point, result_first, pattern_interrupt, story_open, list_promise, visual_shock, trend_sound, direct_address, none", "first_seconds_description": "string"},
    "storytelling": "string",
    "narrative_structure": "e.g. hook > problem > steps > result > CTA",
    "retention_mechanisms": ["string"],
    "visual_style": "string",
    "scene_structure": [{"start_sec": 0, "end_sec": 0, "description": "string"}],
    "audio": {"voice": "string", "music": "string", "sound_effects": "string"},
    "editing_rhythm": "string, use the measured cut data given",
    "cta": {"present": True, "text": "string or null", "type": "follow/comment/share/link/buy/none"},
    "ending": "string",
    "content_formula": "short reusable template, e.g. [Pain point question] + [3 quick tips with on-screen text] + [result] + [comment CTA]",
    "strengths": ["string"],
    "weaknesses": ["string"],
    "evidence": [{"claim": "string", "source": "visual|audio|ocr|caption|metrics", "timestamp_sec": 0}],
    "confidence": 0.0,
    "data_limitations": ["string"],
}

INSIGHT_SCHEMA = {
    "conclusion": "string",
    "evidence": ["string - concrete observations"],
    "video_refs": ["V01"],
    "observed_data": "numbers copied ONLY from the provided stats",
    "pattern": "string",
    "hypothesis": "string, clearly marked as hypothesis",
    "recommendation": "string",
    "confidence": 0.0,
}


def system(lang: str) -> str:
    return ("You are a senior short-form video strategist and data analyst. You analyze TikTok content rigorously "
            "and evidence-first.\n" + RULES.format(lang=lang))


def video_prompt(meta: dict, media_meta: dict, mode: str, transcript_hint: str | None = None) -> str:
    m = {k: meta.get(k) for k in ("caption", "posted_at", "duration_sec", "views", "likes", "comments", "shares", "saves")}
    cut = {k: media_meta.get(k) for k in ("analyzed_seconds", "original_duration", "scene_cuts", "cuts_per_minute", "width", "height", "has_audio")}
    src = ("You are given the VIDEO itself (frames + audio). Analyze the actual video content, not just the caption."
           if mode == "video" else
           "You are given KEYFRAMES (images, in time order with timestamps listed below) and an automatic TRANSCRIPT. "
           "You cannot see motion; say so in data_limitations where relevant.")
    parts = [
        "Task: Stage 1 — video-level analysis of one TikTok video.", src,
        f"Video metadata (from collector; may be incomplete): {json.dumps(m, ensure_ascii=False, default=str)}",
        f"Measured media data (computed by ffmpeg, reliable): {json.dumps(cut, ensure_ascii=False)}",
    ]
    if media_meta.get("keyframe_times"):
        parts.append(f"Keyframe timestamps (sec): {media_meta['keyframe_times']}")
    if transcript_hint:
        parts.append(f"Automatic transcript:\n{transcript_hint[:6000]}")
    parts.append("Return JSON with exactly this schema:\n" + json.dumps(VIDEO_SCHEMA, ensure_ascii=False))
    return "\n\n".join(parts)


def topic_prompt(key: str, videos: list[dict], stats: dict) -> str:
    return "\n\n".join([
        f"Task: Stage 2 — topic-level analysis for cluster {key}. The videos below were grouped automatically by "
        "embedding similarity. Describe what actually unites them. If they are not coherent, say so and lower confidence.",
        "Videos (structured summaries from Stage 1):\n" + json.dumps(videos, ensure_ascii=False),
        "Deterministic performance stats for this cluster (do not recompute, do not invent others):\n" + json.dumps(stats, ensure_ascii=False),
        "Return JSON: " + json.dumps({
            "name": "short topic name", "description": "string", "topic": "string",
            "dominant_format": "string", "common_hooks": ["string"], "pattern": "string",
            "content_formula": "string", "representative_ref": "V01", "coherence": "high|medium|low",
            "confidence": 0.0}, ensure_ascii=False),
    ])


def pillar_prompt(topics: list[dict], n_videos: int) -> str:
    return "\n\n".join([
        f"Task: Stage 3 — content pillar analysis. The channel has {n_videos} analyzed videos grouped into the topic "
        "clusters below. Merge related topics into 2–6 CONTENT PILLARS (strategic content categories). Every topic key "
        "must be assigned to exactly one pillar. Use only the provided data.",
        "Topics:\n" + json.dumps(topics, ensure_ascii=False),
        "Return JSON: " + json.dumps({"pillars": [{
            "name": "string", "description": "string", "topic_keys": ["T1"], "topic": "string",
            "content_format": "string", "pattern": "string", "content_formula": "string",
            "role_in_channel": "e.g. reach / trust / conversion / community", "confidence": 0.0}]}, ensure_ascii=False),
    ])


def channel_prompt(channel: dict, pillars: list[dict], distribution: dict, performance: dict, video_index: list[dict]) -> str:
    return "\n\n".join([
        "Task: Stage 4 — channel-level analysis (Channel DNA, overall Content Formula, weaknesses). "
        "Base every claim on the pillars, distribution, performance stats and video index below. Cite video refs.",
        "Channel: " + json.dumps(channel, ensure_ascii=False, default=str),
        "Pillars (with deterministic stats): " + json.dumps(pillars, ensure_ascii=False),
        "Distribution (deterministic): " + json.dumps(distribution, ensure_ascii=False),
        "Performance (deterministic, relative to this channel's own median): " + json.dumps(performance, ensure_ascii=False),
        "Video index: " + json.dumps(video_index, ensure_ascii=False),
        "Return JSON: " + json.dumps({
            "channel_dna": {"summary": "string", "positioning": "string", "target_audience": "string",
                            "tone_and_persona": "string", "signature_elements": ["string"], "confidence": 0.0},
            "content_formula": {"formula": "string", "steps": ["string"], "variations": ["string"], "confidence": 0.0},
            "insights": [INSIGHT_SCHEMA], "weaknesses": [INSIGHT_SCHEMA]}, ensure_ascii=False),
    ])


def strategy_prompt(channel_summary: dict, pillars: list[dict], performance: dict, weaknesses: list) -> str:
    return "\n\n".join([
        "Task: Stage 5 — strategy. Propose content opportunities and a content strategy grounded ONLY in the analysis "
        "below. Each item must cite evidence and video refs; recommendations are hypotheses to test, not guarantees. "
        "Include a simple test plan (what to post, how many, what metric to compare against the channel median).",
        "Channel analysis: " + json.dumps(channel_summary, ensure_ascii=False),
        "Pillars: " + json.dumps(pillars, ensure_ascii=False),
        "Performance: " + json.dumps(performance, ensure_ascii=False),
        "Weaknesses: " + json.dumps(weaknesses, ensure_ascii=False),
        "Return JSON: " + json.dumps({
            "summary": "string", "opportunities": [INSIGHT_SCHEMA], "strategy": [INSIGHT_SCHEMA],
            "content_mix": [{"pillar": "string", "suggested_share": 0.0, "reason": "string"}],
            "experiments": [{"idea": "string", "based_on_refs": ["V01"], "success_metric": "string", "sample_size": "string"}]},
            ensure_ascii=False),
    ])
