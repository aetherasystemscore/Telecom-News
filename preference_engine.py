"""
Thumbs-Up / Thumbs-Down Adaptive Preference Learning, Bookmarking & Re-Ranking Engine (`preference_engine.py`)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from checkpoint_manager import DATA_DIR, _atomic_write_json

PREFERENCES_FILE = DATA_DIR / "user_preferences.json"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_preferences_state() -> Dict[str, Any]:
    return {
        "updated_at": _utc_iso(),
        "article_votes": {},
        "tag_weights": {
            "5G-Advanced": 2.0,
            "Telco AI/LTM": 2.5,
            "BSS/OSS": 2.5,
            "Open RAN": 2.0,
            "D2D": 2.0,
            "6G": 1.5,
            "Edge Compute": 2.0,
            "Subsea": 1.5,
        },
        "vendor_weights": {
            "Ericsson": 3.0,
            "Nokia": 3.0,
            "Huawei": 3.0,
            "Samsung": 1.5,
            "Mavenir": 1.5,
            "Amdocs": 2.0,
            "Cisco": 1.5,
            "Ciena": 1.5,
        },
        "theme_weights": {
            "pricing_monetization": 5.0,
            "hw_scarcity": 4.5,
        },
        "source_weights": {},
        "bookmarks": [],
        "vote_history": [],
    }


def load_preferences() -> Dict[str, Any]:
    if not PREFERENCES_FILE.exists():
        state = default_preferences_state()
        _atomic_write_json(PREFERENCES_FILE, state)
        return state
    try:
        with open(PREFERENCES_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        base = default_preferences_state()
        base.update(loaded)
        return base
    except Exception:
        return default_preferences_state()


def save_preferences(state: Dict[str, Any]) -> Dict[str, Any]:
    state["updated_at"] = _utc_iso()
    _atomic_write_json(PREFERENCES_FILE, state)
    return state


def record_article_feedback(
    article: Dict[str, Any],
    vote_type: str,
) -> Dict[str, Any]:
    prefs = load_preferences()
    art_id = article["id"]
    votes_map = prefs.setdefault("article_votes", {})
    curr = votes_map.get(art_id, {"thumbs_up": int(article.get("thumbs_up", 0)), "thumbs_down": int(article.get("thumbs_down", 0))})

    delta = 3.0 if vote_type == "up" else -2.0
    if vote_type == "up":
        curr["thumbs_up"] = int(curr.get("thumbs_up", 0)) + 1
        curr["last_action"] = "up"
    else:
        curr["thumbs_down"] = int(curr.get("thumbs_down", 0)) + 1
        curr["last_action"] = "down"
    votes_map[art_id] = curr

    tag_w = prefs.setdefault("tag_weights", {})
    for t in article.get("tech_tags", []):
        tag_w[t] = round(max(-15.0, min(40.0, float(tag_w.get(t, 0.0)) + delta)), 2)

    vendor_w = prefs.setdefault("vendor_weights", {})
    for v in article.get("entities", {}).get("vendors", []):
        vendor_w[v] = round(max(-15.0, min(40.0, float(vendor_w.get(v, 0.0)) + delta * 1.2)), 2)

    theme_w = prefs.setdefault("theme_weights", {})
    if article.get("pricing_monetization", {}).get("is_pricing_focus"):
        theme_w["pricing_monetization"] = round(
            max(-15.0, min(50.0, float(theme_w.get("pricing_monetization", 5.0)) + delta * 1.3)),
            2,
        )
    if article.get("hw_scarcity", {}).get("is_hw_scarcity_related"):
        theme_w["hw_scarcity"] = round(
            max(-15.0, min(50.0, float(theme_w.get("hw_scarcity", 4.5)) + delta * 1.3)),
            2,
        )

    source_w = prefs.setdefault("source_weights", {})
    src = article.get("source_name", "")
    if src:
        source_w[src] = round(max(-15.0, min(30.0, float(source_w.get(src, 0.0)) + delta * 0.8)), 2)

    prefs.setdefault("vote_history", []).append(
        {
            "timestamp": _utc_iso(),
            "article_id": art_id,
            "title": article.get("title", "")[:90],
            "vote": vote_type,
        }
    )
    if len(prefs["vote_history"]) > 100:
        prefs["vote_history"] = prefs["vote_history"][-100:]

    return save_preferences(prefs)


def compute_article_rank_score(article: Dict[str, Any], prefs: Dict[str, Any]) -> Tuple[float, float, List[str]]:
    art_id = article.get("id", "")
    vote_entry = prefs.get("article_votes", {}).get(art_id, {})
    up = int(vote_entry.get("thumbs_up", article.get("thumbs_up", 0)))
    down = int(vote_entry.get("thumbs_down", article.get("thumbs_down", 0)))

    base_impact = float(article.get("impact_score", 3)) * 16.0
    direct_vote_boost = (up * 32.0) - (down * 38.0)

    feature_boost = 0.0
    reasons: List[str] = []

    if up > down:
        reasons.append(f"👍 Liked (+{up - down})")
    elif down > up:
        reasons.append(f"👎 Demoted (-{down - up})")

    theme_w = prefs.get("theme_weights", {})
    if article.get("pricing_monetization", {}).get("is_pricing_focus"):
        w = float(theme_w.get("pricing_monetization", 5.0))
        feature_boost += w
        if w > 0:
            reasons.append("💰 Pricing & SW Monetization Focus")

    if article.get("hw_scarcity", {}).get("is_hw_scarcity_related"):
        w = float(theme_w.get("hw_scarcity", 4.5))
        feature_boost += w
        if w > 0:
            reasons.append("🔧 HW Scarcity & Expansion Impact")

    vendor_w = prefs.get("vendor_weights", {})
    matched_vendors: List[str] = []
    for v in article.get("entities", {}).get("vendors", []):
        vw = float(vendor_w.get(v, 0.0))
        feature_boost += vw
        if vw >= 2.0:
            matched_vendors.append(v)
    if matched_vendors:
        reasons.append(f"🏢 Vendor Focus ({', '.join(matched_vendors[:2])})")

    tag_w = prefs.get("tag_weights", {})
    for t in article.get("tech_tags", []):
        feature_boost += float(tag_w.get(t, 0.0)) * 0.7

    src = article.get("source_name", "")
    feature_boost += float(prefs.get("source_weights", {}).get(src, 0.0))

    total_boost = round(direct_vote_boost + feature_boost, 1)
    total_score = round(base_impact + total_boost, 1)
    return total_score, total_boost, reasons


def rank_articles_by_preference(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    prefs = load_preferences()
    votes_map = prefs.get("article_votes", {})
    bookmarks_set = set(prefs.get("bookmarks", []))

    ranked: List[Dict[str, Any]] = []
    for art in articles:
        item = dict(art)
        art_id = item.get("id", "")
        if art_id in votes_map:
            item["thumbs_up"] = int(votes_map[art_id].get("thumbs_up", 0))
            item["thumbs_down"] = int(votes_map[art_id].get("thumbs_down", 0))
        total_score, boost_delta, boost_reasons = compute_article_rank_score(item, prefs)
        item["personalized_rank_score"] = total_score
        item["preference_boost_delta"] = boost_delta
        item["boost_reasons"] = boost_reasons
        item["is_bookmarked"] = art_id in bookmarks_set
        ranked.append(item)

    ranked.sort(
        key=lambda x: (
            x.get("personalized_rank_score", 0.0),
            x.get("published_at", ""),
        ),
        reverse=True,
    )
    return ranked


def toggle_bookmark(article_id: str) -> bool:
    prefs = load_preferences()
    bmarks = prefs.setdefault("bookmarks", [])
    if article_id in bmarks:
        bmarks.remove(article_id)
        save_preferences(prefs)
        return False
    bmarks.append(article_id)
    save_preferences(prefs)
    return True
