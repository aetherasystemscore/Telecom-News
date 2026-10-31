"""
AI Processing, 3-Bullet Executive Takeaway, SW Monetization & HW Scarcity Tagging Pipeline (`ai_pipeline.py`)
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

import requests

MNO_PATTERNS: Dict[str, List[str]] = {
    "AT&T": [r"\bat&t\b", r"\batt\b"],
    "Verizon": [r"\bverizon\b"],
    "T-Mobile": [r"\bt-mobile\b", r"\btmobile\b"],
    "Vodafone": [r"\bvodafone\b"],
    "Deutsche Telekom": [r"\bdeutsche telekom\b", r"\bt-systems\b"],
    "Orange": [r"\borange\b"],
    "Telefonica": [r"\btelefonica\b", r"\btelefónica\b"],
    "BT Group": [r"\bbt group\b", r"\bbritish telecom\b", r"\bopenreach\b"],
    "Reliance Jio": [r"\breliance jio\b", r"\bjio\b"],
    "Bharti Airtel": [r"\bbharti airtel\b", r"\bairtel\b"],
    "Singtel": [r"\bsingtel\b"],
    "NTT Docomo": [r"\bdocomo\b", r"\bntt\b"],
    "SoftBank": [r"\bsoftbank\b"],
    "China Mobile": [r"\bchina mobile\b"],
    "e& (Etisalat)": [r"\betisalat\b", r"\be&\b"],
    "STC": [r"\bstc\b", r"\bsaudi telecom\b"],
    "Telstra": [r"\btelstra\b"],
    "Swisscom": [r"\bswisscom\b"],
    "Elisa": [r"\belisa\b"],
}

VENDOR_PATTERNS: Dict[str, List[str]] = {
    "Ericsson": [r"\bericsson\b", r"\beiap\b", r"\bvonage\b"],
    "Nokia": [r"\bnokia\b", r"\bbell labs\b", r"\banyran\b", r"\binfinera\b"],
    "Huawei": [r"\bhuawei\b", r"\b5\.5g\b", r"\bsingleran\b", r"\blampsite\b"],
    "Samsung": [r"\bsamsung\b"],
    "ZTE": [r"\bzte\b"],
    "Mavenir": [r"\bmavenir\b"],
    "Cisco": [r"\bcisco\b", r"\bsplunk\b"],
    "Ciena": [r"\bciena\b"],
    "Amdocs": [r"\bamdocs\b"],
    "Netcracker": [r"\bnetcracker\b"],
    "Rakuten Symphony": [r"\brakuten\b"],
    "NVIDIA": [r"\bnvidia\b", r"\baerial\b"],
    "Qualcomm": [r"\bqualcomm\b"],
}

SATELLITE_PATTERNS: Dict[str, List[str]] = {
    "AST SpaceMobile": [r"\bast spacemobile\b", r"\bbluebird\b", r"\bluewalker\b"],
    "Starlink": [r"\bstarlink\b", r"\bspacex\b", r"\bdirect-to-cell\b"],
    "Kuiper": [r"\bkuiper\b", r"\bproject kuiper\b"],
    "Eutelsat OneWeb": [r"\boneweb\b", r"\beutelsat\b"],
    "Viasat": [r"\bviasat\b", r"\binmarsat\b"],
    "Skylo": [r"\bskylo\b"],
    "Globalstar": [r"\bglobalstar\b"],
    "Iridium": [r"\biridium\b"],
    "Lynk Global": [r"\blynk\b"],
}

TECH_TAXONOMY_RULES: Dict[str, List[str]] = {
    "5G-Advanced": [
        r"5g-advanced",
        r"5g advanced",
        r"5\.5g",
        r"release 18",
        r"rel-18",
        r"release 19",
        r"rel-19",
        r"5g sa",
        r"network slicing",
        r"redcap",
    ],
    "6G": [
        r"\b6g\b",
        r"release 20",
        r"rel-20",
        r"release 21",
        r"imt-2030",
        r"isac",
        r"integrated sensing",
        r"fr3",
        r"sub-thz",
    ],
    "D2D": [
        r"\bd2d\b",
        r"direct-to-device",
        r"direct-to-cell",
        r"direct to cell",
        r"\bntn\b",
        r"non-terrestrial",
        r"satellite",
        r"leo constellation",
        r"supplemental coverage from space",
    ],
    "Open RAN": [
        r"open ran",
        r"o-ran",
        r"vran",
        r"cloud ran",
        r"cloud-ran",
        r"anyran",
        r"\bsmo\b",
        r"\brapp\b",
        r"\bxapp\b",
        r"ric\b",
    ],
    "Telco AI/LTM": [
        r"\bai\b",
        r"artificial intelligence",
        r"\bllm\b",
        r"\bltm\b",
        r"large telecom model",
        r"autonomous network",
        r"ai-ran",
        r"agentic",
        r"machine learning",
        r"copilot",
    ],
    "Edge Compute": [
        r"\bedge\b",
        r"mec\b",
        r"gpuaas",
        r"gpu-as-a-service",
        r"cloudification",
        r"central office",
        r"cloudflare",
        r"hyperscaler",
        r"wavelength",
    ],
    "Subsea": [
        r"subsea",
        r"submarine cable",
        r"undersea",
        r"optical transport",
        r"coherent optical",
        r"\bbgp\b",
        r"route leak",
        r"outage",
        r"rpki",
        r"post-quantum",
    ],
    "BSS/OSS": [
        r"\bbss\b",
        r"\boss\b",
        r"billing",
        r"monetization",
        r"pricing",
        r"camara",
        r"open gateway",
        r"\boda\b",
        r"arpu",
        r"charging",
        r"crm",
    ],
}


def strip_html_tags(raw_html: str) -> str:
    if not raw_html:
        return ""
    cleaned = re.sub(r"<script[^>]*>.*?</script>", " ", raw_html, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<style[^>]*>.*?</style>", " ", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _match_dictionary(text_lower: str, pattern_dict: Dict[str, List[str]]) -> List[str]:
    found: List[str] = []
    for canonical_name, regex_list in pattern_dict.items():
        for pat in regex_list:
            if re.search(pat, text_lower, flags=re.IGNORECASE):
                found.append(canonical_name)
                break
    return found


def extract_entities_and_tags(title: str, clean_body: str, category_tab: str) -> Dict[str, Any]:
    combined = f"{title} {clean_body}".lower()
    mnos = _match_dictionary(combined, MNO_PATTERNS)
    vendors = _match_dictionary(combined, VENDOR_PATTERNS)
    satellites = _match_dictionary(combined, SATELLITE_PATTERNS)
    tech_tags = _match_dictionary(combined, TECH_TAXONOMY_RULES)

    if not tech_tags:
        fallback_map = {
            "Market": ["BSS/OSS", "5G-Advanced"],
            "Standards": ["5G-Advanced", "Open RAN"],
            "Convergence": ["D2D", "Edge Compute"],
            "Whitepapers": ["6G", "Telco AI/LTM"],
        }
        tech_tags = fallback_map.get(category_tab, ["5G-Advanced"])

    return {
        "entities": {
            "mnos": mnos,
            "vendors": vendors,
            "satellites": satellites,
        },
        "tech_tags": tech_tags,
    }


def analyze_hw_scarcity_impact(title: str, clean_body: str, vendors: List[str], tech_tags: List[str]) -> Dict[str, Any]:
    combined = f"{title} {clean_body}".lower()

    scarcity_Rules = [
        (
            [r"cowos", r"hbm3", r"gpu", r"blackwell", r"hopper", r"ai chip", r"accelerator"],
            "CoWoS/HBM3e AI-RAN Accelerators & Edge GPU Servers",
            "Extended GPU/accelerator lead times force operators to multi-tenant pool edge servers between vRAN and enterprise AI inference rather than over-provisioning dedicated hardware.",
        ),
        (
            [r"800g", r"1\.6t", r"optical", r"transceiver", r"coherent", r"fiber", r"laser", r"subsea", r"repeater"],
            "800G/1.6T Coherent Optical Pluggables & Subsea Cable Vessel Capacity",
            "Optical component and cable-ship backlogs push operators to deploy AI traffic engineering, multi-orbit satellite failover, and spectral compression software on existing fiber pairs.",
        ),
        (
            [r"transformer", r"power grid", r"energy", r"electricity", r"cooling", r"substation"],
            "Electrical Grid Transformers & Central Office Power Capacity (kW Ceiling)",
            "24-36 month electrical transformer lead times cap physical edge buildouts, making autonomous RAN sleep-mode and energy-saving rApp software mandatory before adding radios.",
        ),
        (
            [r"asic", r"fpga", r"chip shortage", r"semiconductor", r"supply chain", r"export control", r"scarcity", r"lead time", r"5\.5g"],
            "Custom 5G-Advanced/6G RF Front-End ASICs & Advanced Node Silicon",
            "Silicon supply friction accelerates adoption of hardware-agnostic Cloud RAN (AnyRAN/Open vRAN) and software-defined capacity upgrades that extend deployed radio lifespans by 2-3 years.",
        ),
    ]

    for patterns, component, impact in scarcity_Rules:
        for pat in patterns:
            if re.search(pat, combined, flags=re.IGNORECASE):
                return {
                    "is_hw_scarcity_related": True,
                    "bottleneck_component": component,
                    "expansion_strategy_impact": impact,
                }

    if any(v in vendors for v in ("Ericsson", "Nokia", "Huawei", "Samsung", "Mavenir")):
        return {
            "is_hw_scarcity_related": False,
            "bottleneck_component": "Managed via Software-Defined Radio / Cloud RAN Pooling",
            "expansion_strategy_impact": (
                f"{', '.join(vendors[:2])} emphasize decoupling software features from physical baseband refresh cycles "
                "so operators can expand capacity via license keys despite tight hardware capex."
            ),
        }

    return {
        "is_hw_scarcity_related": False,
        "bottleneck_component": "None (Software / Commercial Layer)",
        "expansion_strategy_impact": "Expansion relies primarily on software orchestration, cloud APIs, and commercial partnerships rather than constrained physical hardware.",
    }


def analyze_pricing_and_monetization(
    title: str,
    clean_body: str,
    category_tab: str,
    vendors: List[str],
    tech_tags: List[str],
) -> Dict[str, Any]:
    combined = f"{title} {clean_body}".lower()

    if any(k in combined for k in ("camara", "open gateway", "api", "stripe", "twilio", "number verification", "sim swap")):
        return {
            "is_pricing_focus": True,
            "pricing_model": "Developer-First API Micro-Toll ($/Call) + B2B2X Revenue Share (Stripe/Twilio Pattern)",
            "flat_market_play": "Monetizes silent 5G core intelligence (fraud, KYC, QoD) to banks and enterprises per API call instead of fighting consumer tariff price wars.",
            "sw_sales_adoption_idea": "Adopt a 'Zero-Friction Developer Sandbox + Per-1,000 API Calls / Revenue-Share' pricing model for our software services.",
        }

    if any(k in combined for k in ("slice", "slicing", "sla", "tier", "fwa", "differentiated", "programmable", "arpu", "pricing")):
        return {
            "is_pricing_focus": True,
            "pricing_model": "Guaranteed SLA Network Slicing + Speed/Latency Experience Tiers",
            "flat_market_play": "Replaces flat 'all-you-can-eat' gigabyte plans with application-aware uplink, latency, and VIP event slices priced as high-margin upsells.",
            "sw_sales_adoption_idea": "Pitch our SW as a 'Self-Funding SLA Upsell Enabler' with a low base platform fee plus a % share of incremental premium-tier revenue.",
        }

    if any(k in combined for k in ("autonomous", "level 4", "oda", "ai", "ltm", "llm", "energy", "rapps", "agent")):
        return {
            "is_pricing_focus": True,
            "pricing_model": "Outcome-Based Agentic Resolution Pricing (Sierra / Intercom Fin Startup Pattern)",
            "flat_market_play": "Bypasses frozen telco CAPEX budgets by tying software fees directly to verified OPEX reductions (% kWh saved or $ per zero-touch ticket resolved).",
            "sw_sales_adoption_idea": "Offer an 'Outcome-Guaranteed Pilot' where the customer pays a percentage of verified NOC labor or energy OPEX savings rather than per-seat licenses.",
        }

    if "D2D" in tech_tags or any(k in combined for k in ("satellite", "starlink", "ast spacemobile", "kuiper")):
        return {
            "is_pricing_focus": True,
            "pricing_model": "Wholesale MNO-Satellite Revenue Share + Flagship Plan Bundling / Day-Pass Add-On",
            "flat_market_play": "Uses satellite Direct-to-Device coverage as a churn-killing differentiator on premium plans and a $5-$10/mo off-grid pass for mid-tier users.",
            "sw_sales_adoption_idea": "Sell our orchestration/entitlement software as a 'Per-Active-Add-On-User' micro-subscription that scales automatically with subscriber adoption.",
        }

    return {
        "is_pricing_focus": "Market" in category_tab or "BSS/OSS" in tech_tags,
        "pricing_model": "Universal Flex Consumption Credit Pool (Snowflake / Databricks Pattern)",
        "flat_market_play": "Shifts rigid multi-year hardware/per-node capex into flexible annual software capacity credits usable across analytics, automation, and security.",
        "sw_sales_adoption_idea": "Contract our SW portfolio using 'Annual Drawdown Flex Credits' so enterprise/telco buyers can activate new modules without repeat procurement delays.",
    }


def compute_strategic_impact_score(
    title: str,
    clean_body: str,
    entities: Dict[str, List[str]],
    tech_tags: List[str],
    is_hw_scarcity: bool,
    is_pricing_focus: bool,
) -> int:
    combined = f"{title} {clean_body}".lower()
    score = 3

    high_finality_terms = [
        r"\bbillion\b",
        r"\$\d+",
        r"merger",
        r"acquisition",
        r"carve-out",
        r"freeze",
        r"release 19",
        r"release 18",
        r"wrc-27",
        r"fcc",
        r"outage",
        r"bgp",
        r"5\.5g",
        r"open gateway",
        r"direct-to-cell",
        r"mobility report",
    ]
    matches = sum(1 for pat in high_finality_terms if re.search(pat, combined))
    if matches >= 2:
        score += 1
    if len(entities.get("vendors", [])) + len(entities.get("mnos", [])) + len(entities.get("satellites", [])) >= 2:
        score += 1
    if is_hw_scarcity or is_pricing_focus:
        score = max(score, 4)
    return max(1, min(5, score))


def generate_three_bullet_takeaway(
    title: str,
    clean_body: str,
    source_name: str,
    category_tab: str,
    entities: Dict[str, List[str]],
    tech_tags: List[str],
    pricing_info: Dict[str, Any],
    hw_info: Dict[str, Any],
) -> Dict[str, str]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_body) if len(s.strip()) > 35]
    what_happened = sentences[0] if sentences else f"{source_name} reported a strategic development: {title}."
    if len(what_happened) > 240:
        what_happened = what_happened[:237].rstrip() + "..."

    mnos_str = ", ".join(entities.get("mnos", [])[:3]) or "Global MNOs and Tier-1 carriers"
    vendors_str = ", ".join(entities.get("vendors", [])[:3]) or "Telecom equipment and software vendors"
    tags_str = ", ".join(tech_tags[:3]) or category_tab

    if len(sentences) >= 2:
        operator_impact = sentences[1]
        if len(operator_impact) > 240:
            operator_impact = operator_impact[:237].rstrip() + "..."
    else:
        operator_impact = (
            f"Directly impacts {mnos_str} across {tags_str}, shifting capital allocation toward "
            f"{pricing_info.get('pricing_model', 'software-driven monetization')}."
        )

    ecosystem_impact = (
        f"Ecosystem & SW Impact ({vendors_str}): {pricing_info.get('sw_sales_adoption_idea', '')} "
        f"{hw_info.get('expansion_strategy_impact', '')}"
    ).strip()
    if len(ecosystem_impact) > 260:
        ecosystem_impact = ecosystem_impact[:257].rstrip() + "..."

    return {
        "what_happened": what_happened,
        "operator_impact": operator_impact,
        "ecosystem_impact": ecosystem_impact,
    }


def enrich_article_with_ai(article: Dict[str, Any], use_llm_if_available: bool = False) -> Dict[str, Any]:
    enriched = dict(article)
    title = enriched.get("title", "").strip()
    raw_html = enriched.get("raw_html", "") or enriched.get("summary", "") or title
    clean_body = strip_html_tags(raw_html)
    category_tab = enriched.get("category_tab", "Market")
    source_name = enriched.get("source_name", "Telecom Portal")

    extracted = extract_entities_and_tags(title, clean_body, category_tab)
    if not enriched.get("entities"):
        enriched["entities"] = extracted["entities"]
    else:
        for k in ("mnos", "vendors", "satellites"):
            merged = list(dict.fromkeys((enriched["entities"].get(k) or []) + extracted["entities"].get(k, [])))
            enriched["entities"][k] = merged

    if not enriched.get("tech_tags"):
        enriched["tech_tags"] = extracted["tech_tags"]

    if not enriched.get("hw_scarcity"):
        enriched["hw_scarcity"] = analyze_hw_scarcity_impact(
            title,
            clean_body,
            enriched["entities"].get("vendors", []),
            enriched["tech_tags"],
        )

    if not enriched.get("pricing_monetization"):
        enriched["pricing_monetization"] = analyze_pricing_and_monetization(
            title,
            clean_body,
            category_tab,
            enriched["entities"].get("vendors", []),
            enriched["tech_tags"],
        )

    if not enriched.get("impact_score"):
        enriched["impact_score"] = compute_strategic_impact_score(
            title,
            clean_body,
            enriched["entities"],
            enriched["tech_tags"],
            bool(enriched["hw_scarcity"].get("is_hw_scarcity_related")),
            bool(enriched["pricing_monetization"].get("is_pricing_focus")),
        )

    if not enriched.get("executive_takeaway"):
        enriched["executive_takeaway"] = generate_three_bullet_takeaway(
            title=title,
            clean_body=clean_body,
            source_name=source_name,
            category_tab=category_tab,
            entities=enriched["entities"],
            tech_tags=enriched["tech_tags"],
            pricing_info=enriched["pricing_monetization"],
            hw_info=enriched["hw_scarcity"],
        )

    return enriched
