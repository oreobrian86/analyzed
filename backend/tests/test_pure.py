"""Unit test cho các module thuần (không cần DB, không cần API key)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.ai.base import AIError, parse_json_loose
from app.ai.local_embed import local_embed
from app.analysis import clustering, normalize, performance
from app.analysis.report_md import render_markdown
from app.collectors import importer
from app.collectors.base import CollectorError, parse_handle, to_int, ts, video_id_from_url
from app.limits import merge_limits
from app.media.scenes import cuts_per_minute, parse_showinfo, pick_keyframe_times

NOW = datetime(2026, 11, 19, tzinfo=timezone.utc)


def _v(ref, views, likes=None, age=10, comments=None, shares=None):
    return {"id": ref, "ref": ref, "views": views, "likes": likes, "comments": comments, "shares": shares,
            "posted_at": NOW - timedelta(days=age)}


def test_parse_handle():
    assert parse_handle("https://www.tiktok.com/@abc.xyz?lang=vi") == "abc.xyz"
    assert parse_handle("@Some_User") == "some_user"
    assert parse_handle("not a url!!") is None
    assert video_id_from_url("https://www.tiktok.com/@a/video/7417328428443110663?x=1") == "7417328428443110663"


def test_to_int_and_ts():
    assert to_int("1.2K") == 1200
    assert to_int("3,456") == 3456
    assert to_int("2M") == 2_000_000
    assert to_int("") is None and to_int(None) is None
    assert ts("20260101").year == 2026
    assert ts(1700000000).tzinfo is not None
    assert ts("garbage") is None


def test_importer_csv_and_json():
    csv_text = "link;views;likes;date\nhttps://www.tiktok.com/@a/video/111111111;1.5K;100;2026-10-01\n"
    rows = importer.parse_import(csv_text, 10)
    assert rows[0].views == 1500 and rows[0].metrics_source == "user_import" and rows[0].platform_video_id == "111111111"
    js = '[{"url": "https://www.tiktok.com/@a/video/222222222", "playCount": 50}]'
    assert importer.parse_import(js, 10)[0].views == 50
    with pytest.raises(CollectorError):
        importer.parse_import("a,b\n1,2", 10)
    urls = importer.parse_urls("xem https://www.tiktok.com/@a/video/123456789 và https://vm.tiktok.com/ZMabc/ nhé", 5)
    assert len(urls) == 2


def test_performance_outliers_and_notes():
    vids = [_v(f"V{i:02d}", 1000 + i * 50, likes=50, comments=5, shares=2) for i in range(10)]
    vids.append(_v("V11", 500_000, likes=20000))        # vượt trội
    vids.append(_v("V12", 3_000_000, age=1))           # quá mới => không xét
    vids.append(_v("V13", None))                       # thiếu metrics
    r = performance.analyze(vids, now=NOW)
    assert "V11" in r["outliers"]["over"]
    assert "V12" not in r["outliers"]["over"]
    assert r["channel"]["videos_with_metrics"] == 12
    assert any("không có dữ liệu lượt xem" in n for n in r["notes"])
    assert any("viral" in n for n in r["notes"])
    er = next(x for x in r["videos"] if x["ref"] == "V00")["engagement_rate"]
    assert er == round(57 / 1000, 4)


def test_performance_small_sample_no_outliers():
    r = performance.analyze([_v("V01", 10), _v("V02", 1_000_000)], now=NOW)
    assert r["outliers"] == {"over": [], "under": []}
    assert any("cần ≥5" in n for n in r["notes"])


def test_group_stats():
    rows = performance.analyze([_v(f"V{i}", 100 * (i + 1)) for i in range(6)], now=NOW)["videos"]
    s = performance.group_stats(rows, {"V4", "V5"}, 350.0, 6)
    assert s["video_count"] == 2 and s["share"] == 0.333 and s["median_views"] == 550 and s["small_sample"]


def test_local_embed_and_clustering_separates_topics():
    texts = ["công thức nấu phở bò tại nhà nước dùng hầm xương", "nấu phở gà nước dùng trong ngọt",
             "nau pho bo ngon nuoc dung xuong", "bí quyết nấu phở bò nước dùng thơm", "phở bò tái nước dùng hầm",
             "review điện thoại camera pin chơi game", "đánh giá điện thoại pin trâu camera đẹp",
             "review smartphone camera pin game", "so sánh điện thoại camera pin", "review điện thoại chơi game pin"]
    vecs = local_embed(texts)
    out = clustering.cluster(vecs, max_k=4)
    labels = out["labels"]
    assert out["k"] >= 2
    assert not (set(labels[:5]) & set(labels[5:]))  # không nhóm nào trộn 2 chủ đề
    assert set(out["representatives"]) == set(labels)


def test_clustering_tiny_input():
    assert clustering.cluster([[1.0, 0.0]])["k"] == 1
    assert clustering.cluster([])["k"] == 0


def test_normalize_insight_drops_fake_refs():
    i = normalize.insight({"conclusion": "Hook câu hỏi hiệu quả", "evidence": ["V01 có 3x median"],
                           "video_refs": ["V01", "V99"], "confidence": 85}, {"V01", "V02"})
    assert i["video_refs"] == ["V01"] and i["confidence"] == 0.85 and i["quality_flags"]
    j = normalize.insight({"conclusion": "x", "video_refs": ["V77"], "confidence": 0.9}, {"V01"})
    assert j["confidence"] <= 0.3
    assert normalize.insight({"conclusion": ""}, set()) is None


def test_normalize_video_analysis_defaults():
    a = normalize.video_analysis({"hook": "Bạn có biết?", "content_format": "Talking Head", "confidence": "0.7"})
    assert a["hook"]["text"] == "Bạn có biết?" and a["content_format"] == "talking_head" and a["confidence"] == 0.7
    assert a["subtopics"] == [] and isinstance(a["cta"], dict)


def test_parse_json_loose():
    assert parse_json_loose('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_loose('Here: {"a": {"b": 2}} done') == {"a": {"b": 2}}
    with pytest.raises(AIError):
        parse_json_loose("no json")


def test_scenes():
    stderr = "[Parsed_showinfo_1] n:0 pts:1 pts_time:1.5 ...\n[Parsed_showinfo_1] n:1 pts_time:4.25\n"
    assert parse_showinfo(stderr) == [1.5, 4.25]
    assert cuts_per_minute([1, 2, 3], 30) == 6.0
    t = pick_keyframe_times([1.5, 4.0, 8.0, 12.0], 20, 4)
    assert len(t) == 4 and t[0] == 0.5 and t == sorted(t)
    assert len(pick_keyframe_times([], 20, 4)) == 4


def test_merge_limits():
    d = {"max_analyses_per_day": 3, "max_videos_per_day": 40, "max_ai_requests_per_day": 150, "max_active_analyses": 1, "x": 1}
    assert merge_limits(d, {"max_videos_per_day": "99", "unknown": 5})["max_videos_per_day"] == 99
    adm = merge_limits(d, {}, is_admin=True)
    assert adm["max_analyses_per_day"] == 15 and adm["max_active_analyses"] == 3


def test_report_markdown_renders():
    report = {
        "meta": {"generated_at": "2026-11-19T10:00:00", "channel": {"handle": "abc", "videos_analyzed": 2, "videos_total": 3},
                 "data_notes": ["1 video lỗi"]},
        "channel": {"dna": {"summary": "Kênh nấu ăn"}, "content_formula": {"formula": "A+B", "steps": ["A", "B"]},
                    "insights": [{"conclusion": "c", "evidence": ["e"], "video_refs": ["V01"], "confidence": 0.6}], "weaknesses": []},
        "pillars": [{"key": "P1", "name": "Nấu ăn", "refs": ["V01", "V02"], "representative_ref": "V01", "confidence": 0.7,
                     "stats": {"video_count": 2, "share": 0.67, "median_views": 1000, "median_vs_channel": 1.2,
                               "median_engagement_rate": 0.05, "small_sample": True}}],
        "performance": {"channel": {"median_views": 900}, "outliers": {"over": [], "under": []}, "notes": []},
        "strategy": {"summary": "s", "strategy": [], "opportunities": [], "experiments": []},
    }
    md = render_markdown(report)
    assert "# Báo cáo kênh @abc" in md and "Nấu ăn" in md and "mẫu nhỏ" in md
