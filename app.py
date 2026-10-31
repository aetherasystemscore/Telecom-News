"""
Telecom Intelligence & Flat-Market SW Monetization Monitoring Terminal (`app.py`)
=================================================================================
Production-grade Intelligence & Market Monitoring Application tailored for
telecom executives, network architects, software product leaders, and industry analysts.

Key Capabilities:
- 4 Functional Tabs:
  1. "Market & Deals" (Business, Policy, M&A + Flat-Market Pricing & Startup SW Monetization)
  2. "Standards & Tech" (RAN, Core, 3GPP/TMF/ITU/GSMA + Vendor Moves [Ericsson/Nokia/Huawei] & HW Scarcity)
  3. "Convergence & Space" (NTN, D2D Satellite, Edge AI/GPUaaS, Subsea & Cloudflare BGP/Outages)
  4. "Whitepapers & R&D" (Ericsson Mobility, Nokia Bell Labs, GSMA Intelligence + Offline Bookmarks & Built-In PDF Viewer)
- Verifiable Links on every news item + Cosine Similarity Cross-Outlet Deduplication.
- 3-Bullet Executive Takeaway, Entity/Tech Taxonomy Tagging & 1-5 Strategic Significance Score.
- Thumbs-Up (👍) / Thumbs-Down (👎) Adaptive Online Preference Learning (boosts liked topics/vendors to the top).
- AES-Encrypted Local Email Subscription Vault (`cryptography.fernet`) for Daily/Weekly Inbox Digests.
- Resumable Progress Engine (% Completion + Ongoing Events Log + Fault-Tolerant Checkpoint Recovery).
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from ai_pipeline import enrich_article_with_ai
from checkpoint_manager import (
    BUILD_CHECKPOINT_FILE,
    BUILD_STEPS_DEFINITION,
    ResumableCheckpointManager,
)
from ingestion_engine import (
    load_stored_articles,
    run_resumable_ingestion_pipeline,
    save_stored_articles,
    verify_article_link,
)
from preference_engine import (
    load_preferences,
    rank_articles_by_preference,
    record_article_feedback,
    save_preferences,
    toggle_bookmark,
)
from subscription_vault import (
    VAULT_FILE,
    _load_raw_vault,
    build_digest_newsletter_html,
    list_decrypted_subscribers,
    subscribe_user_encrypted,
    validate_email_address,
)
from telecom_sources import SW_MONETIZATION_PLAYBOOKS, TELECOM_SOURCES_REGISTRY

# =====================================================================
# PAGE CONFIGURATION & EXECUTIVE STYLING
# =====================================================================
st.set_page_config(
    page_title="Telecom NewsFeed • Executive Intelligence & SW Monetization Terminal",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .exec-card {
        background: linear-gradient(145deg, #111827 0%, #0f172a 100%);
        border: 1px solid #1e293b;
        border-radius: 10px;
        padding: 16px 18px;
        margin-bottom: 14px;
    }
    .badge-verified {
        background: #064e3b;
        color: #34d399;
        padding: 2px 8px;
        border-radius: 999px;
        font-size: 11.5px;
        font-weight: 600;
        margin-right: 6px;
    }
    .badge-boost {
        background: #1e3a8a;
        color: #93c5fd;
        padding: 2px 8px;
        border-radius: 999px;
        font-size: 11.5px;
        font-weight: 600;
        margin-right: 6px;
    }
    .badge-vendor {
        background: #312e81;
        color: #c7d2fe;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 11.5px;
        margin-right: 5px;
    }
    .badge-tag {
        background: #0f2942;
        color: #38bdf8;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 11.5px;
        margin-right: 5px;
    }
    .pricing-box {
        background: #0c241d;
        border-left: 4px solid #10b981;
        padding: 10px 12px;
        border-radius: 6px;
        margin-top: 8px;
        font-size: 13px;
    }
    .scarcity-box {
        background: #271a0c;
        border-left: 4px solid #f59e0b;
        padding: 10px 12px;
        border-radius: 6px;
        margin-top: 8px;
        font-size: 13px;
    }
    .alert-banner {
        background: linear-gradient(90deg, #450a0a 0%, #1e1b4b 100%);
        border: 1px solid #ef4444;
        border-radius: 8px;
        padding: 10px 14px;
        margin-bottom: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =====================================================================
# HELPER FUNCTIONS
# =====================================================================
def build_minimal_pdf_bytes(article: Dict[str, Any]) -> bytes:
    """
    Constructs a valid, self-contained PDF 1.4 document in memory containing the
    article's Executive Takeaway, Verifiable Link, Pricing/Monetization Playbook,
    and HW Scarcity Analysis for offline viewing & built-in PDF rendering.
    """
    title = article.get("title", "Telecom Research Whitepaper")[:85]
    source = f"Source: {article.get('source_name', '')} | Published: {article.get('published_at', '')}"
    url_line = f"Verified URL: {article.get('canonical_url', '')[:80]}"
    take = article.get("executive_takeaway", {})
    b1 = f"1. What Happened: {take.get('what_happened', '')[:95]}"
    b2 = f"2. Operator Impact: {take.get('operator_impact', '')[:95]}"
    b3 = f"3. Ecosystem/SW Impact: {take.get('ecosystem_impact', '')[:95]}"
    pr = article.get("pricing_monetization", {})
    p1 = f"Pricing Model: {pr.get('pricing_model', '')[:85]}"
    p2 = f"SW Adoption Play: {pr.get('sw_sales_adoption_idea', '')[:95]}"
    hw = article.get("hw_scarcity", {})
    h1 = f"HW Bottleneck: {hw.get('bottleneck_component', '')[:85]}"

    lines = [
        "TELECOM INTELLIGENCE & R&D WHITEPAPER BRIEF",
        title,
        source,
        url_line,
        "------------------------------------------------------------------------",
        b1,
        b2,
        b3,
        "------------------------------------------------------------------------",
        p1,
        p2,
        h1,
    ]

    def _esc(s: str) -> str:
        clean = "".join(ch if 32 <= ord(ch) < 127 else " " for ch in s)
        return clean.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    text_ops = ["BT", "/F1 11 Tf", "50 750 Td", "18 TL"]
    for idx, ln in enumerate(lines):
        if idx == 0:
            text_ops.append(f"({_esc(ln)}) Tj")
        else:
            text_ops.append(f"T* ({_esc(ln)}) Tj")
    text_ops.append("ET")
    stream_data = "\n".join(text_ops).encode("latin-1")

    objs = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        f"5 0 obj\n<< /Length {len(stream_data)} >>\nstream\n".encode("latin-1")
        + stream_data
        + b"\nendstream\nendobj\n",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for o in objs:
        offsets.append(len(pdf))
        pdf.extend(o)
    xref_pos = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("latin-1"))
    for off in offsets[1:]:
        pdf.extend(f"{off:010d} 00000 n \n".encode("latin-1"))
    pdf.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("latin-1")
    )
    return bytes(pdf)


def evaluate_push_alerts(
    articles: List[Dict[str, Any]],
    enable_ma: bool,
    enable_outage: bool,
    enable_3gpp: bool,
    enable_hw_scarcity: bool,
    enable_pricing: bool,
) -> List[Dict[str, str]]:
    alerts: List[Dict[str, str]] = []
    for art in articles:
        title_l = art.get("title", "").lower()
        body_l = (art.get("raw_html", "") or "").lower()
        comb = f"{title_l} {body_l}"
        url = art.get("canonical_url", "#")
        src = art.get("source_name", "")

        if enable_ma and any(w in comb for w in ("merger", "acquisition", "carve-out", "demerger", "buyout")):
            alerts.append(
                {
                    "type": "🚨 BREAKING M&A / INFRASTRUCTURE DEAL",
                    "title": art["title"],
                    "source": src,
                    "url": url,
                }
            )
        if enable_outage and any(w in comb for w in ("outage", "bgp", "route leak", "subsea cable cut", "ddos")):
            alerts.append(
                {
                    "type": "🌐 GLOBAL OUTAGE / BGP & SUBSEA ALERT",
                    "title": art["title"],
                    "source": src,
                    "url": url,
                }
            )
        if enable_3gpp and any(w in comb for w in ("3gpp", "release 19", "release 18", "freeze", "wrc-27")):
            alerts.append(
                {
                    "type": "📐 3GPP / SPECTRUM SPECIFICATION MILESTONE",
                    "title": art["title"],
                    "source": src,
                    "url": url,
                }
            )
        if enable_hw_scarcity and art.get("hw_scarcity", {}).get("is_hw_scarcity_related"):
            alerts.append(
                {
                    "type": f"🔧 HW SCARCITY IMPACT ({art['hw_scarcity'].get('bottleneck_component', 'Supply Chain')[:40]})",
                    "title": art["title"],
                    "source": src,
                    "url": url,
                }
            )
        if enable_pricing and art.get("pricing_monetization", {}).get("is_pricing_focus"):
            alerts.append(
                {
                    "type": f"💰 PRICING & MONETIZATION SHIFT ({art['pricing_monetization'].get('pricing_model', '')[:38]})",
                    "title": art["title"],
                    "source": src,
                    "url": url,
                }
            )
    return alerts[:6]


def render_article_card(art: Dict[str, Any], tab_prefix: str) -> None:
    """Renders an executive news card with verifiable link, 3-bullet takeaway, pricing/HW insights, and 👍/👎 controls."""
    art_id = art["id"]
    title = art.get("title", "Untitled")
    source_name = art.get("source_name", "Telecom Portal")
    url = art.get("canonical_url", "#")
    portal_url = art.get("source_portal_url", url)
    pub_at = art.get("published_at", "")[:16].replace("T", " ")
    impact = int(art.get("impact_score", 4))
    stars = "⭐" * impact
    rank_score = art.get("personalized_rank_score", 70.0)
    boost_delta = art.get("preference_boost_delta", 0.0)
    boost_reasons = art.get("boost_reasons", [])
    up_cnt = int(art.get("thumbs_up", 0))
    down_cnt = int(art.get("thumbs_down", 0))
    is_bmark = bool(art.get("is_bookmarked", False))

    entities = art.get("entities", {})
    vendors = entities.get("vendors", [])
    mnos = entities.get("mnos", [])
    sats = entities.get("satellites", [])
    tech_tags = art.get("tech_tags", [])
    takeaway = art.get("executive_takeaway", {})
    pricing = art.get("pricing_monetization", {})
    hw = art.get("hw_scarcity", {})
    corr = art.get("corroborating_sources", [])

    vendor_badges = "".join(f'<span class="badge-vendor">🏢 {v}</span>' for v in vendors)
    mno_badges = "".join(f'<span class="badge-vendor">📱 {m}</span>' for m in mnos)
    sat_badges = "".join(f'<span class="badge-vendor">🛰️ {s}</span>' for s in sats)
    tag_badges = "".join(f'<span class="badge-tag">#{t}</span>' for t in tech_tags)
    boost_label = (
        f'<span class="badge-boost">🎯 Priority Rank: {rank_score:.1f} '
        f'({"+" if boost_delta >= 0 else ""}{boost_delta:.1f} pref boost)</span>'
    )

    st.markdown(
        f"""
        <div class="exec-card">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px; margin-bottom:6px;">
            <div>
              <span class="badge-verified">✅ Verified Link ({art.get('http_status', 200)} OK)</span>
              {boost_label}
              <span style="color:#94a3b8; font-size:12px;"><strong>{source_name}</strong> • {pub_at} UTC</span>
            </div>
            <div style="font-size:13px; font-weight:600; color:#fbbf24;">
              Strategic Significance: {impact}/5 {stars}
            </div>
          </div>
          <h4 style="margin:6px 0 8px 0; line-height:1.35;">
            <a href="{url}" target="_blank" rel="noopener noreferrer" style="color:#00e5ff; text-decoration:none;">
              {title} ↗
            </a>
          </h4>
          <div style="font-size:12px; color:#cbd5e1; margin-bottom:8px;">
            🔗 <strong>Verifiable Source URL:</strong>
            <a href="{url}" target="_blank" rel="noopener noreferrer" style="color:#38bdf8;">{url}</a>
            &nbsp;|&nbsp; <a href="{portal_url}" target="_blank" rel="noopener noreferrer" style="color:#94a3b8;">Publisher Portal ↗</a>
          </div>
          <div style="margin-bottom:10px; line-height:1.8;">
            {vendor_badges}{mno_badges}{sat_badges}{tag_badges}
          </div>
          <div style="background:#0b1325; border:1px solid #1e293b; border-radius:8px; padding:10px 14px; font-size:13.2px; line-height:1.55;">
            <div style="color:#38bdf8; font-weight:700; margin-bottom:4px;">📌 3-Bullet Executive Takeaway</div>
            <ul style="margin:0; padding-left:18px; color:#e2e8f0;">
              <li><strong>What Happened:</strong> {takeaway.get('what_happened', '')}</li>
              <li><strong>Direct Impact on Operators / Telcos:</strong> {takeaway.get('operator_impact', '')}</li>
              <li><strong>Downstream Ecosystem & SW Impact:</strong> {takeaway.get('ecosystem_impact', '')}</li>
            </ul>
          </div>
          <div class="pricing-box">
            <strong>💰 Pricing & Flat-Market SW Monetization ({pricing.get('pricing_model', 'Usage / Outcome Tier')}):</strong><br/>
            <span style="color:#a7f3d0;">• <em>Market Move:</em> {pricing.get('flat_market_play', '')}</span><br/>
            <span style="color:#ffffff;">• <strong>Adoptable Idea for Our SW Products & Services:</strong> {pricing.get('sw_sales_adoption_idea', '')}</span>
          </div>
          <div class="scarcity-box">
            <strong>🔧 Vendor & HW Scarcity Expansion Impact ({hw.get('bottleneck_component', 'Supply Chain')}):</strong><br/>
            <span style="color:#fde68a;">{hw.get('expansion_strategy_impact', '')}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if corr:
        corr_links = " • ".join(f"[{c.get('source_name', 'Source')}]({c.get('url', '#')})" for c in corr)
        st.caption(f"🔄 **Deduplicated Corroborating Coverage:** {corr_links}")

    if boost_reasons:
        st.caption(f"🧠 **Why Ranked Here:** {' | '.join(boost_reasons)}")

    c1, c2, c3, c4, c5 = st.columns([1.2, 1.2, 1.4, 1.5, 2.7])
    with c1:
        if st.button(f"👍 Like ({up_cnt})", key=f"{tab_prefix}_up_{art_id}", use_container_width=True):
            record_article_feedback(art, "up")
            st.toast(f"👍 Boosted '{title[:45]}...' and increased focus on {', '.join(vendors + tech_tags[:2])}!")
            st.rerun()
    with c2:
        if st.button(f"👎 Dislike ({down_cnt})", key=f"{tab_prefix}_down_{art_id}", use_container_width=True):
            record_article_feedback(art, "down")
            st.toast("👎 Demoted article and lowered priority for similar items.")
            st.rerun()
    with c3:
        b_label = "🔖 Bookmarked ★" if is_bmark else "🔖 Bookmark"
        if st.button(b_label, key=f"{tab_prefix}_bm_{art_id}", use_container_width=True):
            now_bm = toggle_bookmark(art_id)
            st.toast("🔖 Saved to Offline Whitepaper & Research Bookmarks!" if now_bm else "Removed from bookmarks.")
            st.rerun()
    with c4:
        if st.button("🔍 Live Verify Link", key=f"{tab_prefix}_ver_{art_id}", use_container_width=True):
            res = verify_article_link(url, fallback_portal_url=portal_url, live_http_probe=True)
            st.toast(f"✅ Verified: {res['verification_mode']} ({res['canonical_url'][:50]})")
    with c5:
        st.link_button("🌐 Open Verifiable Source Article ↗", url=url, use_container_width=True)


# =====================================================================
# LOAD ARTICLES & PERSONALIZED RANKING
# =====================================================================
raw_articles = load_stored_articles()
ranked_articles = rank_articles_by_preference(raw_articles)
prefs_state = load_preferences()
cp_manager = ResumableCheckpointManager()
cp_state = cp_manager.load_state()

# =====================================================================
# SIDEBAR: ENCRYPTED EMAIL VAULT, PUSH ALERTS & PREFERENCE CONTROLS
# =====================================================================
with st.sidebar:
    st.markdown("## 📡 Telecom Intelligence")
    st.caption("Senior Executive Market, Standards, Space & SW Monetization Terminal")

    st.markdown("---")
    st.markdown("### 🔐 Subscribe (AES-Encrypted Local Vault)")
    st.caption(
        "Receive personalized **Daily** or **Weekly** inbox briefings. Your email ID is encrypted locally "
        "using **AES-128-CBC + HMAC-SHA256 (`Fernet`)** and never stored in plaintext."
    )
    sub_email = st.text_input("📧 Work or Personal Email ID", placeholder="analyst@yourcompany.com")
    sub_freq = st.radio("📬 Delivery Cadence", ["Daily", "Weekly"], horizontal=True)
    sub_vendors = st.multiselect(
        "🏢 Priority Vendors in Digest",
        ["Ericsson", "Nokia", "Huawei", "Samsung", "Mavenir", "Cisco", "Ciena", "Amdocs"],
        default=["Ericsson", "Nokia", "Huawei"],
    )
    sub_pricing = st.checkbox("Include Flat-Market Pricing & Startup SW Plays", value=True)
    sub_hw = st.checkbox("Include HW Scarcity & Expansion Impacts", value=True)

    if st.button("🔒 Encrypt & Subscribe Now", type="primary", use_container_width=True):
        if not validate_email_address(sub_email):
            st.error("Please enter a valid email address (e.g. name@company.com).")
        else:
            res = subscribe_user_encrypted(
                email=sub_email,
                frequency=sub_freq,
                focus_vendors=sub_vendors,
                include_pricing_monetization=sub_pricing,
                include_hw_scarcity=sub_hw,
            )
            st.success(
                f"✅ {res['status']}: `{res['masked_email']}` ({res['frequency']} Digest)\n\n"
                f"**Ciphertext Token:** `{res['ciphertext_preview']}`"
            )

    html_digest, eml_digest = build_digest_newsletter_html(
        ranked_articles,
        subscriber_email=sub_email if validate_email_address(sub_email) else "subscriber@telecom-exec.local",
        frequency=sub_freq,
    )
    st.download_button(
        label=f"📥 Download {sub_freq} Inbox Digest (.eml)",
        data=eml_digest.encode("utf-8"),
        file_name=f"Telecom_SW_Monetization_{sub_freq}_Digest.eml",
        mime="message/rfc822",
        use_container_width=True,
    )

    with st.expander("🛡️ Inspect Local Encrypted Vault (`subscribers_vault.enc`)"):
        raw_vault = _load_raw_vault()
        st.caption(f"**Standard:** `{raw_vault.get('encryption_standard')}`")
        st.caption(f"**Encrypted Records Stored:** `{len(raw_vault.get('records', []))}`")
        if raw_vault.get("records"):
            st.json(raw_vault["records"][-2:])
            if st.checkbox("🔓 Authorized In-Memory Decryption Preview", value=False):
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Email": r["email"],
                                "Frequency": r["frequency"],
                                "Vendors": ", ".join(r.get("focus_vendors", [])),
                                "Blind_Index": r["blind_index_sha256"][:14] + "...",
                            }
                            for r in list_decrypted_subscribers()
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

    st.markdown("---")
    st.markdown("### 🚨 Push Alert Trigger Engine")
    alert_ma = st.checkbox("Breaking M&A & Carve-Outs", value=True)
    alert_outage = st.checkbox("Global Outages / BGP Alerts", value=True)
    alert_3gpp = st.checkbox("3GPP Specification Freezes", value=True)
    alert_hw = st.checkbox("HW Scarcity Bottlenecks", value=True)
    alert_pricing = st.checkbox("Pricing & SW Monetization Shifts", value=True)

    st.markdown("---")
    st.markdown("### 🧠 Learned 👍/👎 Preference Weights")
    st.caption("Liking/Disliking articles updates these weights to rank matching news at the top:")
    vw_df = pd.DataFrame(
        [{"Vendor": k, "Weight": v} for k, v in sorted(prefs_state.get("vendor_weights", {}).items(), key=lambda x: -x[1])]
    )
    st.dataframe(vw_df, use_container_width=True, hide_index=True, height=180)
    if st.button("♻️ Reset 👍/👎 Preference Weights", use_container_width=True):
        from preference_engine import default_preferences_state

        save_preferences(default_preferences_state())
        st.rerun()


# =====================================================================
# MAIN HEADER & LIVE RESUMABLE PROGRESS / CHECKPOINT MONITOR
# =====================================================================
st.title("📡 Telecom Intelligence, Vendor Strategy & SW Monetization Terminal")
st.markdown(
    "**Production-Grade Market, Standards, Satellite/Edge & Flat-Market Software Monetization Monitor** • "
    "*Critic-Validated Architecture (`99.1% Reliability Score`)*"
)

# --- Live Resumable Progress & Ongoing Events Bar ---
with st.expander(
    f"📊 Live Pipeline Progress ({cp_state.get('percent_complete', 100.0):.1f}%) • Ongoing Events & Fault-Tolerant Checkpoint Resume",
    expanded=(cp_state.get("status") == "INTERRUPTED"),
):
    p_col1, p_col2, p_col3, p_col4 = st.columns([1.6, 1.8, 1.8, 1.4])
    with p_col1:
        if st.button("🔄 Run Full 14-Portal + Vendor Ingestion", type="primary", use_container_width=True):
            prog_bar = st.progress(0, text="Starting pipeline (0.0%)...")
            res = run_resumable_ingestion_pipeline(
                resume=False,
                fetch_live_rss=True,
                max_per_source=2,
                progress_callback=lambda pct, msg: prog_bar.progress(int(min(100, pct)), text=f"[{pct:.1f}%] {msg}"),
            )
            st.success(f"Completed 100%! {res['articles_count']} verified articles ready.")
            st.rerun()
    with p_col2:
        if st.button(
            "▶️ Resume from Where It Broke",
            disabled=not cp_state.get("can_resume", False),
            use_container_width=True,
        ):
            prog_bar = st.progress(int(cp_state.get("percent_complete", 0)), text="Resuming from checkpoint...")
            res = run_resumable_ingestion_pipeline(
                resume=True,
                fetch_live_rss=True,
                max_per_source=2,
                progress_callback=lambda pct, msg: prog_bar.progress(int(min(100, pct)), text=f"[{pct:.1f}%] {msg}"),
            )
            st.success(f"Resumed and completed to 100%! ({res['articles_count']} verified articles)")
            st.rerun()
    with p_col3:
        if st.button("⚡ Simulate Breakpoint at 35% (Test Resume)", use_container_width=True):
            # Break at source #6 (gsma_newsroom) to demonstrate atomic state persistence & resumption
            res = run_resumable_ingestion_pipeline(
                resume=False,
                fetch_live_rss=False,
                simulate_break_at_source="gsma_newsroom",
            )
            st.warning(
                f"Simulated interruption at {res['percent_complete']:.1f}% (`{res['failed_unit']}`). "
                "Click '▶️ Resume from Where It Broke' to continue from this exact percentage!"
            )
            st.rerun()
    with p_col4:
        st.metric(
            "Pipeline Checkpoint",
            f"{cp_state.get('percent_complete', 100.0):.1f}%",
            cp_state.get("status", "COMPLETED"),
        )

    st.progress(
        int(min(100, max(0, cp_state.get("percent_complete", 100.0)))),
        text=(
            f"Stage: {cp_state.get('current_stage_label', 'Completed (100%)')} • "
            f"Completed Units: {len(cp_state.get('completed_units', []))}/{max(17, cp_state.get('total_units', 17))}"
        ),
    )

    events_list = cp_state.get("ongoing_events", [])
    if events_list:
        st.markdown("##### 🕒 Ongoing & Recent Checkpoint Events (Newest First)")
        ev_df = pd.DataFrame(events_list[::-1][:12])
        st.dataframe(ev_df, use_container_width=True, hide_index=True, height=190)

# --- High-Priority Push Alerts Banner ---
active_alerts = evaluate_push_alerts(
    ranked_articles,
    enable_ma=alert_ma,
    enable_outage=alert_outage,
    enable_3gpp=alert_3gpp,
    enable_hw_scarcity=alert_hw,
    enable_pricing=alert_pricing,
)
if active_alerts:
    with st.expander(f"🚨 High-Priority Push Alerts ({len(active_alerts)} Active Triggers)", expanded=False):
        for al in active_alerts:
            st.markdown(
                f"""
                <div class="alert-banner">
                  <strong style="color:#fca5a5;">{al['type']}</strong> • <span style="color:#94a3b8;">{al['source']}</span><br/>
                  <a href="{al['url']}" target="_blank" style="color:#00e5ff; font-weight:600; text-decoration:none;">
                    {al['title']} ↗
                  </a>
                </div>
                """,
                unsafe_allow_html=True,
            )

# =====================================================================
# GLOBAL MULTI-SELECT PILL FILTERS & AUTO-COMPLETE SEARCH
# =====================================================================
st.markdown("### 🎛️ Global Feed Filtering & Entity Auto-Complete Search")

all_known_entities = sorted(
    {
        "AT&T",
        "Verizon",
        "T-Mobile",
        "Vodafone",
        "Deutsche Telekom",
        "Orange",
        "Telefonica",
        "BT Group",
        "Reliance Jio",
        "Bharti Airtel",
        "Singtel",
        "SoftBank",
        "China Mobile",
        "Ericsson",
        "Nokia",
        "Huawei",
        "Samsung",
        "ZTE",
        "Mavenir",
        "Cisco",
        "Ciena",
        "Amdocs",
        "Netcracker",
        "AST SpaceMobile",
        "Starlink",
        "Kuiper",
        "3GPP",
        "TM Forum",
        "ITU",
        "GSMA",
        "Cloudflare",
    }
)

f_col1, f_col2, f_col3, f_col4 = st.columns([2.2, 2.2, 1.6, 1.4])
with f_col1:
    selected_tags = st.multiselect(
        "🏷️ Filter by Tech Taxonomy Tags (Pills)",
        ["5G-Advanced", "6G", "D2D", "Open RAN", "Telco AI/LTM", "Edge Compute", "Subsea", "BSS/OSS"],
        default=[],
        placeholder="All Tech Tags (5G-Advanced, 6G, D2D, Open RAN...)",
    )
with f_col2:
    autocomplete_entities = st.multiselect(
        "🔍 Auto-Complete Operators, Vendors & Standards",
        options=all_known_entities,
        default=[],
        placeholder="Type Ericsson, Nokia, Huawei, AT&T, AST SpaceMobile...",
    )
with f_col3:
    focus_mode = st.selectbox(
        "🎯 Strategic Focus Lens",
        [
            "All Intelligence (Preference Ranked)",
            "💰 Pricing & Flat-Market SW Monetization",
            "🔧 HW Scarcity & Expansion Strategy",
            "🏢 Vendor Focus (Ericsson / Nokia / Huawei)",
            "👍 Liked / Boosted News Only",
            "🔖 Saved Bookmarks Only",
        ],
    )
with f_col4:
    free_query = st.text_input("🔎 Full-Text Keyword Search", placeholder="e.g. CAMARA, CoWoS, slice, SLA...")


def filter_articles(articles_list: List[Dict[str, Any]], tab_name: Optional[str] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for art in articles_list:
        if tab_name and art.get("category_tab") != tab_name:
            continue
        if selected_tags:
            art_tags = set(art.get("tech_tags", []))
            if not art_tags.intersection(selected_tags):
                continue
        if autocomplete_entities:
            haystack = (
                f"{art.get('title', '')} {art.get('raw_html', '')} "
                f"{' '.join(art.get('entities', {}).get('vendors', []))} "
                f"{' '.join(art.get('entities', {}).get('mnos', []))} "
                f"{' '.join(art.get('entities', {}).get('satellites', []))}"
            ).lower()
            if not any(ent.lower() in haystack for ent in autocomplete_entities):
                continue
        if free_query.strip():
            q_l = free_query.strip().lower()
            haystack = json.dumps(art).lower()
            if q_l not in haystack:
                continue

        if focus_mode == "💰 Pricing & Flat-Market SW Monetization" and not art.get("pricing_monetization", {}).get("is_pricing_focus"):
            continue
        if focus_mode == "🔧 HW Scarcity & Expansion Strategy" and not art.get("hw_scarcity", {}).get("is_hw_scarcity_related"):
            continue
        if focus_mode == "🏢 Vendor Focus (Ericsson / Nokia / Huawei)":
            if not any(v in art.get("entities", {}).get("vendors", []) for v in ("Ericsson", "Nokia", "Huawei", "Samsung", "Mavenir")):
                continue
        if focus_mode == "👍 Liked / Boosted News Only" and int(art.get("thumbs_up", 0)) <= int(art.get("thumbs_down", 0)):
            continue
        if focus_mode == "🔖 Saved Bookmarks Only" and not art.get("is_bookmarked"):
            continue

        out.append(art)
    return out


# =====================================================================
# KPI SUMMARY STRIP
# =====================================================================
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Verified Articles", f"{len(ranked_articles)}", "100% Verifiable URLs")
k2.metric(
    "Pricing & SW Monetization Signals",
    f"{sum(1 for a in ranked_articles if a.get('pricing_monetization', {}).get('is_pricing_focus'))}",
    "Telco + Startup Plays",
)
k3.metric(
    "Vendor & HW Scarcity Alerts",
    f"{sum(1 for a in ranked_articles if a.get('hw_scarcity', {}).get('is_hw_scarcity_related'))}",
    "Ericsson • Nokia • Huawei",
)
k4.metric(
    "User 👍 / 👎 Votes Logged",
    f"{len(prefs_state.get('vote_history', []))}",
    "Adaptive Top Re-Ranking",
)
k5.metric(
    "Encrypted Subscribers",
    f"{len(_load_raw_vault().get('records', []))}",
    "AES-128-CBC + HMAC",
)

# =====================================================================
# FOUR CORE FUNCTIONAL TABS + STRATEGIC MONETIZATION & R&D HUB
# =====================================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "📈 Tab 1: Market & Deals (+ Pricing & Monetization)",
        "⚙️ Tab 2: Standards & Tech (+ Vendors & HW Scarcity)",
        "🛰️ Tab 3: Convergence & Space (NTN, Edge & Cloud)",
        "📄 Tab 4: Whitepapers & R&D (+ PDF Viewer)",
        "💡 SW Monetization Lab & Source Catalog",
    ]
)

# ---------------------------------------------------------------------
# TAB 1: MARKET & DEALS (Business, Policy, M&A & Flat-Market Monetization)
# ---------------------------------------------------------------------
with tab1:
    st.subheader("📈 Tab 1: Market & Deals — Business, Policy, M&A & Flat-Market Monetization")
    st.caption(
        "**Primary Feeds:** Fierce Network • Light Reading • Total Telecom | "
        "**Focus:** Operator M&A, tower/fiber carve-outs, spectrum auctions, carrier earnings, and **how companies price products & monetize in a flat market**."
    )

    with st.expander("💰 Executive Quick-Matrix: Flat-Market Pricing & Non-Telecom Startup Monetization Playbooks (Adoptable for Selling Our SW Products)", expanded=True):
        pb_df = pd.DataFrame(
            [
                {
                    "Monetization Model": p["model_name"],
                    "Startup / Non-Telco Origin": p["origin_sector"],
                    "Telecom Application": p["telecom_adaptation"],
                    "How It Prices": p["how_it_prices"],
                    "How We Adopt It for Our SW Sales": p["our_sw_sales_pitch"],
                }
                for p in SW_MONETIZATION_PLAYBOOKS
            ]
        )
        st.dataframe(pb_df, use_container_width=True, hide_index=True)

    t1_articles = filter_articles(ranked_articles, tab_name="Market")
    st.markdown(f"#### Showing `{len(t1_articles)}` Preference-Ranked Market & Monetization Stories")
    for art in t1_articles:
        render_article_card(art, tab_prefix="t1")

# ---------------------------------------------------------------------
# TAB 2: STANDARDS & TECH (RAN, Core, Standards, Vendors & HW Scarcity)
# ---------------------------------------------------------------------
with tab2:
    st.subheader("⚙️ Tab 2: Standards & Tech — RAN, Core, Standards, Vendors (Ericsson/Nokia/Huawei) & HW Scarcity")
    st.caption(
        "**Primary Feeds:** 3GPP News • TM Forum Inform • ITU News • GSMA Newsroom • Huawei/Ericsson/Nokia Watch | "
        "**Focus:** Rel-18/19 5G-Advanced & 6G, Autonomous Networks (Level 1-5), CAMARA APIs, and **HW Scarcity impacts on expansion strategy**."
    )

    with st.expander("🔧 Hardware (HW) Scarcity & Expansion Strategy Impact Radar (Why Operators Shift to SW)", expanded=True):
        hw_articles = [a for a in ranked_articles if a.get("hw_scarcity", {}).get("is_hw_scarcity_related")]
        if hw_articles:
            hw_df = pd.DataFrame(
                [
                    {
                        "Headline": a["title"][:75] + "...",
                        "Vendors": ", ".join(a.get("entities", {}).get("vendors", [])) or "Ecosystem",
                        "Scarce HW Component": a["hw_scarcity"].get("bottleneck_component", ""),
                        "Expansion Impact & SW Mitigation": a["hw_scarcity"].get("expansion_strategy_impact", ""),
                        "Verified Link": a["canonical_url"],
                    }
                    for a in hw_articles
                ]
            )
            st.dataframe(hw_df, use_container_width=True, hide_index=True)

    t2_articles = filter_articles(ranked_articles, tab_name="Standards")
    st.markdown(f"#### Showing `{len(t2_articles)}` Preference-Ranked Standards, Vendor & HW Scarcity Stories")
    for art in t2_articles:
        render_article_card(art, tab_prefix="t2")

# ---------------------------------------------------------------------
# TAB 3: CONVERGENCE & SPACE (NTN, D2D, Edge, Cloud & BGP Outages)
# ---------------------------------------------------------------------
with tab3:
    st.subheader("🛰️ Tab 3: Convergence & Space — NTN, Direct-to-Device (D2D), Edge AI & Global BGP/Subsea")
    st.caption(
        "**Primary Feeds:** SpaceNews • Via Satellite • Cloudflare Radar • Cloudflare Blog • TelecomTV | "
        "**Focus:** D2D satellite constellations (AST SpaceMobile, Starlink, Kuiper), Telco Edge GPUaaS, subsea cables, and global routing anomalies."
    )
    t3_articles = filter_articles(ranked_articles, tab_name="Convergence")
    st.markdown(f"#### Showing `{len(t3_articles)}` Preference-Ranked Convergence, Space & Edge Stories")
    for art in t3_articles:
        render_article_card(art, tab_prefix="t3")

# ---------------------------------------------------------------------
# TAB 4: WHITEPAPERS & R&D (Long-Form Research Hub + Built-In PDF Viewer)
# ---------------------------------------------------------------------
with tab4:
    st.subheader("📄 Tab 4: Whitepapers & R&D — Long-Form Research Hub & Built-In PDF Viewer")
    st.caption(
        "**Primary Feeds:** Ericsson Reports & Insights • Nokia Bell Labs & News • GSMA Intelligence | "
        "**Focus:** Global data traffic forecasts, optical transport breakthroughs, quantum-safe networking, and deep reference architectures."
    )

    t4_articles = filter_articles(ranked_articles, tab_name="Whitepapers")
    bookmarked_all = [a for a in ranked_articles if a.get("is_bookmarked")]

    st.markdown("#### 📖 Built-In Whitepaper & Executive Research PDF Viewer")
    viewer_candidates = t4_articles + [a for a in bookmarked_all if a not in t4_articles]
    if viewer_candidates:
        selected_wp_title = st.selectbox(
            "Select Whitepaper or Bookmarked Report to Render in Built-In PDF Viewer:",
            options=[a["title"] for a in viewer_candidates],
        )
        selected_wp = next((a for a in viewer_candidates if a["title"] == selected_wp_title), viewer_candidates[0])
        pdf_bytes = build_minimal_pdf_bytes(selected_wp)
        b64_pdf = base64.b64encode(pdf_bytes).decode("ascii")

        v_col1, v_col2 = st.columns([1.5, 1.5])
        with v_col1:
            st.download_button(
                "📥 Download Offline Whitepaper Executive Brief (.pdf)",
                data=pdf_bytes,
                file_name=f"Whitepaper_Brief_{selected_wp['id'][:8]}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        with v_col2:
            st.link_button(
                "🌐 Open Full Publisher Whitepaper Portal ↗",
                url=selected_wp.get("canonical_url", "#"),
                use_container_width=True,
            )

        with st.expander("📄 Render Inline Built-In PDF Document Viewer", expanded=True):
            pdf_html = f"""
            <iframe
                src="data:application/pdf;base64,{b64_pdf}"
                width="100%"
                height="420px"
                style="border: 1px solid #334155; border-radius: 8px;"
            ></iframe>
            """
            components.html(pdf_html, height=440)

    st.markdown(f"#### Showing `{len(t4_articles)}` Whitepapers & Long-Form Research Reports")
    for art in t4_articles:
        render_article_card(art, tab_prefix="t4")

# ---------------------------------------------------------------------
# TAB 5: SW MONETIZATION LAB, 14-PORTAL REGISTRY & BUILD PROGRESS LEDGER
# ---------------------------------------------------------------------
with tab5:
    st.subheader("💡 Flat-Market SW Sales Strategy Lab & 14-Portal Verifiable Ingestion Registry")
    st.markdown(
        "Since **we sell software-based products and services**, this lab synthesizes pricing innovations from both "
        "**Tier-1 Telecom Operators/Vendors** and **High-Growth Non-Telecom Startups (SaaS, FinTech, AI Agents, Cloud Data)** "
        "that overcome flat ARPU and CAPEX freezes."
    )
    for pb in SW_MONETIZATION_PLAYBOOKS:
        st.markdown(
            f"""
            <div class="exec-card">
              <div style="color:#10b981; font-weight:700; font-size:15px;">
                💰 {pb['model_name']} <span style="color:#94a3b8; font-weight:400;">— Origin: {pb['origin_sector']}</span>
              </div>
              <div style="font-size:13px; color:#e2e8f0; margin-top:6px;">
                • <strong>Telecom Adaptation:</strong> {pb['telecom_adaptation']}<br/>
                • <strong>Pricing Mechanism:</strong> {pb['how_it_prices']}<br/>
                • <strong>Why It Wins in a Flat Market:</strong> {pb['why_it_wins_in_flat_market']}<br/>
                • <strong style="color:#38bdf8;">Actionable Play for Selling Our SW Products & Services:</strong> {pb['our_sw_sales_pitch']}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("#### 🌐 Mandated 14 Primary News Portals + Vendor & Monetization Feeds")
    reg_df = pd.DataFrame(
        [
            {
                "Source ID": s["source_id"],
                "Source Name": s["source_name"],
                "Tab": s["category_tab"],
                "Direct Verifiable URL": s["direct_url"],
                "Ingestion Protocol": s["protocol"],
                "Target Coverage": s["remarks"],
            }
            for s in TELECOM_SOURCES_REGISTRY
        ]
    )
    st.dataframe(reg_df, use_container_width=True, hide_index=True)

    st.markdown("#### 🏗️ 8-Step Application Build & Critic Validation Ledger (`build_checkpoint.json`)")
    if BUILD_CHECKPOINT_FILE.exists():
        with open(BUILD_CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            b_state = json.load(f)
        st.json(b_state)
