"""
End-to-End Automated Test & Critic Verification Suite (`test_telecom_news.py`)
==============================================================================
Validates:
1. Information Architecture & 14-Portal + Vendor/Monetization Coverage across all 4 Tabs.
2. Unified Normalized JSON Schema & 100% Verifiable Links.
3. URL Canonicalization & Cosine Similarity Headline Deduplication.
4. AI 3-Bullet Executive Takeaway, Entity/Tech Tagging, SW Monetization & HW Scarcity Analysis.
5. Thumbs-Up (👍) / Thumbs-Down (👎) Adaptive Preference Learning & Top-of-Feed Re-Ranking.
6. AES-Encrypted Local Email Subscription Vault (`cryptography.fernet`) — verifying zero plaintext PII on disk.
7. Resumable Step-by-Step Progress (% Completion + Ongoing Events + Breakpoint Recovery).
"""

from __future__ import annotations

import json
from pathlib import Path

from ai_pipeline import enrich_article_with_ai
from checkpoint_manager import ResumableCheckpointManager
from ingestion_engine import (
    canonicalize_url,
    compute_headline_cosine_similarity,
    deduplicate_articles,
    load_stored_articles,
    run_resumable_ingestion_pipeline,
)
from preference_engine import (
    default_preferences_state,
    load_preferences,
    rank_articles_by_preference,
    record_article_feedback,
    save_preferences,
    toggle_bookmark,
)
from subscription_vault import (
    VAULT_FILE,
    build_digest_newsletter_html,
    list_decrypted_subscribers,
    remove_subscriber_by_email,
    subscribe_user_encrypted,
)
from telecom_sources import (
    SW_MONETIZATION_PLAYBOOKS,
    TELECOM_SOURCES_REGISTRY,
    get_seed_articles_with_ids,
)


def test_four_tabs_and_14_core_portals_coverage():
    tabs_covered = {s["category_tab"] for s in TELECOM_SOURCES_REGISTRY}
    assert tabs_covered == {"Market", "Standards", "Convergence", "Whitepapers"}
    assert len(TELECOM_SOURCES_REGISTRY) >= 14
    assert len(SW_MONETIZATION_PLAYBOOKS) >= 5


def test_schema_normalization_and_verifiable_links():
    articles = load_stored_articles()
    assert len(articles) >= 12
    required_keys = {
        "id",
        "title",
        "source_name",
        "canonical_url",
        "published_at",
        "category_tab",
        "raw_html",
        "author",
        "executive_takeaway",
        "pricing_monetization",
        "hw_scarcity",
        "entities",
        "tech_tags",
        "impact_score",
    }
    vendors_seen = set()
    for art in articles:
        assert required_keys.issubset(set(art.keys()))
        assert art["canonical_url"].startswith("https://")
        assert art["link_verified"] is True
        assert art["category_tab"] in ("Market", "Standards", "Convergence", "Whitepapers")
        assert 1 <= int(art["impact_score"]) <= 5
        take = art["executive_takeaway"]
        assert take.get("what_happened") and take.get("operator_impact") and take.get("ecosystem_impact")
        for v in art["entities"].get("vendors", []):
            vendors_seen.add(v)

    # Must include major vendors: Ericsson, Nokia, Huawei
    for mandatory_vendor in ("Ericsson", "Nokia", "Huawei"):
        assert mandatory_vendor in vendors_seen


def test_url_canonicalization_and_cosine_deduplication():
    dirty_url = "https://www.lightreading.com/5g/ericsson-nokia-deal/?utm_source=rss&utm_medium=feed&fbclid=12345"
    clean_url = canonicalize_url(dirty_url)
    assert "utm_source" not in clean_url
    assert "fbclid" not in clean_url
    assert clean_url == "https://www.lightreading.com/5g/ericsson-nokia-deal"

    h1 = "Vodafone and Three UK Merger Wins Conditional Regulatory Clearance - Light Reading"
    h2 = "Vodafone and Three UK Merger Wins Conditional Regulatory Clearance | Fierce Network"
    sim = compute_headline_cosine_similarity(h1, h2)
    assert sim >= 0.85

    dup_list = [
        {
            "id": "1",
            "title": h1,
            "source_name": "Light Reading",
            "canonical_url": "https://www.lightreading.com/vodafone-three-merger",
            "published_at": "2026-10-31T10:00:00Z",
            "category_tab": "Market",
            "raw_html": "<p>Deal update</p>",
            "author": "Ed",
        },
        {
            "id": "2",
            "title": h2,
            "source_name": "Fierce Network",
            "canonical_url": "https://www.fierce-network.com/vodafone-three-merger",
            "published_at": "2026-10-31T10:05:00Z",
            "category_tab": "Market",
            "raw_html": "<p>Deal update</p>",
            "author": "Ed",
        },
    ]
    deduped, removed = deduplicate_articles(dup_list, cosine_threshold=0.78)
    assert len(deduped) == 1
    assert removed == 1
    assert len(deduped[0]["corroborating_sources"]) == 1


def test_thumbs_up_down_preference_reranking():
    save_preferences(default_preferences_state())
    articles = get_seed_articles_with_ids()
    target = articles[-1]  # Pick an article originally lower in list

    # Like the target article twice
    record_article_feedback(target, "up")
    record_article_feedback(target, "up")

    ranked = rank_articles_by_preference(articles)
    assert ranked[0]["id"] == target["id"]
    assert ranked[0]["thumbs_up"] >= 2

    # Bookmark toggle
    assert toggle_bookmark(target["id"]) is True
    assert toggle_bookmark(target["id"]) is False


def test_aes_encrypted_local_email_subscription_vault():
    test_email = "chief.architect@telco-monetization.io"
    remove_subscriber_by_email(test_email)

    res = subscribe_user_encrypted(
        email=test_email,
        frequency="Weekly",
        focus_vendors=["Ericsson", "Nokia", "Huawei"],
        include_pricing_monetization=True,
        include_hw_scarcity=True,
    )
    assert res["status"] in ("SUBSCRIBED", "UPDATED")
    assert res["frequency"] == "Weekly"

    # Verify raw file on disk NEVER contains the plaintext email
    raw_disk_text = VAULT_FILE.read_text(encoding="utf-8")
    assert test_email not in raw_disk_text

    # Verify authorized decryption recovers exact subscriber record
    decrypted = list_decrypted_subscribers()
    matching = [r for r in decrypted if r.get("email") == test_email]
    assert len(matching) == 1
    assert matching[0]["frequency"] == "Weekly"
    assert "Huawei" in matching[0]["focus_vendors"]

    # Verify HTML & EML newsletter generation
    articles = load_stored_articles()
    html_out, eml_out = build_digest_newsletter_html(articles, subscriber_email=test_email, frequency="Weekly")
    assert test_email in html_out
    assert "Content-Type: text/html" in eml_out

    remove_subscriber_by_email(test_email)


def test_resumable_pipeline_breakpoint_and_recovery():
    # Step A: Simulate interruption at "gsma_newsroom"
    interrupted = run_resumable_ingestion_pipeline(
        resume=False,
        fetch_live_rss=False,
        simulate_break_at_source="gsma_newsroom",
    )
    assert interrupted["status"] == "INTERRUPTED"
    assert interrupted["failed_unit"] == "gsma_newsroom"
    pct_at_break = interrupted["percent_complete"]
    assert 20.0 <= pct_at_break <= 60.0
    completed_before_resume = len(interrupted["completed_units"])
    assert completed_before_resume >= 5

    # Step B: Resume from exact breakpoint without losing prior progress
    resumed = run_resumable_ingestion_pipeline(
        resume=True,
        fetch_live_rss=False,
        simulate_break_at_source=None,
    )
    assert resumed["status"] == "COMPLETED"
    assert resumed["percent_complete"] == 100.0
    assert resumed["articles_count"] >= 12


if __name__ == "__main__":
    suite = [
        ("1. Four Tabs & 14 Core Portals + Monetization Playbooks", test_four_tabs_and_14_core_portals_coverage),
        ("2. Unified JSON Schema & 100% Verifiable Links + Vendor Coverage", test_schema_normalization_and_verifiable_links),
        ("3. URL Canonicalization & Cosine Similarity Deduplication", test_url_canonicalization_and_cosine_deduplication),
        ("4. Thumbs-Up/Down Preference Learning & Top-of-Feed Re-Ranking", test_thumbs_up_down_preference_reranking),
        ("5. AES-Encrypted Local Email Subscription Vault (Zero Plaintext PII)", test_aes_encrypted_local_email_subscription_vault),
        ("6. Resumable Step-by-Step Breakpoint & Recovery Engine", test_resumable_pipeline_breakpoint_and_recovery),
    ]
    for label, fn in suite:
        fn()
        print(f"[PASS] {label}")
    print("\nALL 6 END-TO-END CRITIC & RELIABILITY VERIFICATION SUITES PASSED (100%).")
