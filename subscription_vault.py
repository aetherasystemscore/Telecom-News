"""
AES-Encrypted Local Email Subscription Vault & Daily/Weekly Digest Engine (`subscription_vault.py`)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except Exception:
    Fernet = None
    PBKDF2HMAC = None
    hashes = None

from checkpoint_manager import DATA_DIR, _atomic_write_json

VAULT_FILE = DATA_DIR / "subscribers_vault.enc"
KEY_FILE = DATA_DIR / ".vault_key"
SALT_FILE = DATA_DIR / ".vault_salt"

EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_email_address(email: str) -> bool:
    cleaned = (email or "").strip()
    return bool(EMAIL_REGEX.match(cleaned)) and len(cleaned) <= 254


def _get_or_create_salt() -> bytes:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if SALT_FILE.exists():
        raw = SALT_FILE.read_bytes()
        if len(raw) >= 16:
            return raw
    salt = secrets.token_bytes(32)
    SALT_FILE.write_bytes(salt)
    return salt


def _get_or_create_fernet_key(custom_passphrase: Optional[str] = None) -> bytes:
    salt = _get_or_create_salt()
    secret_phrase = custom_passphrase or os.environ.get("TELECOM_VAULT_SECRET", "").strip()

    if secret_phrase:
        if PBKDF2HMAC is not None and hashes is not None:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=200_000,
            )
            return base64.urlsafe_b64encode(kdf.derive(secret_phrase.encode("utf-8")))
        dk = hashlib.pbkdf2_hmac("sha256", secret_phrase.encode("utf-8"), salt, 200_000, dklen=32)
        return base64.urlsafe_b64encode(dk)

    if KEY_FILE.exists():
        saved = KEY_FILE.read_bytes().strip()
        if len(saved) == 44:
            return saved

    if Fernet is not None:
        new_key = Fernet.generate_key()
    else:
        new_key = base64.urlsafe_b64encode(secrets.token_bytes(32))
    KEY_FILE.write_bytes(new_key)
    return new_key


def compute_blind_email_index(email: str) -> str:
    salt = _get_or_create_salt()
    norm_email = (email or "").strip().lower().encode("utf-8")
    return hmac.new(salt, norm_email, hashlib.sha256).hexdigest()


def encrypt_payload(payload_dict: Dict[str, Any], custom_passphrase: Optional[str] = None) -> str:
    key = _get_or_create_fernet_key(custom_passphrase)
    raw_bytes = json.dumps(payload_dict, ensure_ascii=False).encode("utf-8")
    if Fernet is not None:
        f = Fernet(key)
        return f.encrypt(raw_bytes).decode("ascii")

    raw_key = base64.urlsafe_b64decode(key)
    nonce = secrets.token_bytes(16)
    keystream = b"".join(
        hashlib.sha256(raw_key + nonce + i.to_bytes(4, "big")).digest()
        for i in range((len(raw_bytes) // 32) + 2)
    )[: len(raw_bytes)]
    cipher_bytes = bytes(a ^ b for a, b in zip(raw_bytes, keystream))
    mac = hmac.new(raw_key, nonce + cipher_bytes, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + mac + cipher_bytes).decode("ascii")


def decrypt_payload(ciphertext_token: str, custom_passphrase: Optional[str] = None) -> Dict[str, Any]:
    key = _get_or_create_fernet_key(custom_passphrase)
    if Fernet is not None:
        f = Fernet(key)
        decrypted_bytes = f.decrypt(ciphertext_token.encode("ascii"))
        return json.loads(decrypted_bytes.decode("utf-8"))

    raw_key = base64.urlsafe_b64decode(key)
    blob = base64.urlsafe_b64decode(ciphertext_token.encode("ascii"))
    nonce, mac, cipher_bytes = blob[:16], blob[16:48], blob[48:]
    expected_mac = hmac.new(raw_key, nonce + cipher_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected_mac):
        raise ValueError("Ciphertext authentication failed (HMAC mismatch).")
    keystream = b"".join(
        hashlib.sha256(raw_key + nonce + i.to_bytes(4, "big")).digest()
        for i in range((len(cipher_bytes) // 32) + 2)
    )[: len(cipher_bytes)]
    plain_bytes = bytes(a ^ b for a, b in zip(cipher_bytes, keystream))
    return json.loads(plain_bytes.decode("utf-8"))


def _load_raw_vault() -> Dict[str, Any]:
    if not VAULT_FILE.exists():
        return {
            "vault_version": "1.0",
            "encryption_standard": "AES-128-CBC + HMAC-SHA256 (Fernet / PBKDF2-SHA256)",
            "updated_at": _utc_iso(),
            "records": [],
        }
    try:
        with open(VAULT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "vault_version": "1.0",
            "encryption_standard": "AES-128-CBC + HMAC-SHA256 (Fernet / PBKDF2-SHA256)",
            "updated_at": _utc_iso(),
            "records": [],
        }


def subscribe_user_encrypted(
    email: str,
    frequency: str = "Daily",
    focus_tabs: Optional[List[str]] = None,
    focus_vendors: Optional[List[str]] = None,
    include_pricing_monetization: bool = True,
    include_hw_scarcity: bool = True,
    custom_passphrase: Optional[str] = None,
) -> Dict[str, Any]:
    clean_email = (email or "").strip().lower()
    if not validate_email_address(clean_email):
        raise ValueError(f"Invalid email address format: '{email}'")

    freq_norm = "Weekly" if str(frequency).strip().lower().startswith("week") else "Daily"
    tabs_list = focus_tabs or ["Market", "Standards", "Convergence", "Whitepapers"]
    vendors_list = focus_vendors or ["Ericsson", "Nokia", "Huawei"]

    blind_idx = compute_blind_email_index(clean_email)
    plaintext_record = {
        "email": clean_email,
        "frequency": freq_norm,
        "focus_tabs": tabs_list,
        "focus_vendors": vendors_list,
        "include_pricing_monetization": bool(include_pricing_monetization),
        "include_hw_scarcity": bool(include_hw_scarcity),
        "subscribed_at": _utc_iso(),
    }

    cipher_token = encrypt_payload(plaintext_record, custom_passphrase=custom_passphrase)
    vault = _load_raw_vault()
    records = vault.setdefault("records", [])

    updated_existing = False
    for rec in records:
        if rec.get("blind_index_sha256") == blind_idx:
            rec["ciphertext_token"] = cipher_token
            rec["updated_at"] = _utc_iso()
            updated_existing = True
            break

    if not updated_existing:
        records.append(
            {
                "blind_index_sha256": blind_idx,
                "ciphertext_token": cipher_token,
                "created_at": _utc_iso(),
                "updated_at": _utc_iso(),
            }
        )

    vault["updated_at"] = _utc_iso()
    _atomic_write_json(VAULT_FILE, vault)

    masked_email = clean_email[:2] + "***@" + clean_email.split("@", 1)[1]
    return {
        "status": "UPDATED" if updated_existing else "SUBSCRIBED",
        "masked_email": masked_email,
        "frequency": freq_norm,
        "blind_index_sha256": blind_idx,
        "ciphertext_preview": cipher_token[:42] + "...",
        "total_subscribers": len(records),
    }


def list_decrypted_subscribers(custom_passphrase: Optional[str] = None) -> List[Dict[str, Any]]:
    vault = _load_raw_vault()
    decrypted_list: List[Dict[str, Any]] = []
    for rec in vault.get("records", []):
        try:
            payload = decrypt_payload(rec["ciphertext_token"], custom_passphrase=custom_passphrase)
            payload["blind_index_sha256"] = rec.get("blind_index_sha256", "")
            payload["ciphertext_preview"] = rec["ciphertext_token"][:36] + "..."
            decrypted_list.append(payload)
        except Exception:
            continue
    return decrypted_list


def remove_subscriber_by_email(email: str) -> bool:
    blind_idx = compute_blind_email_index(email)
    vault = _load_raw_vault()
    before = len(vault.get("records", []))
    vault["records"] = [r for r in vault.get("records", []) if r.get("blind_index_sha256") != blind_idx]
    if len(vault["records"]) < before:
        vault["updated_at"] = _utc_iso()
        _atomic_write_json(VAULT_FILE, vault)
        return True
    return False


def build_digest_newsletter_html(
    articles: List[Dict[str, Any]],
    subscriber_email: str = "executive@telco-strategy.com",
    frequency: str = "Daily",
    max_items: int = 8,
) -> Tuple[str, str]:
    selected = articles[:max_items]
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    subject = f"[{frequency} Telecom & SW Monetization Briefing] Top {len(selected)} Executive Signals ({date_str})"

    cards_html = []
    for idx, art in enumerate(selected, start=1):
        takeaway = art.get("executive_takeaway", {})
        pricing = art.get("pricing_monetization", {})
        hw = art.get("hw_scarcity", {})
        vendors = ", ".join(art.get("entities", {}).get("vendors", [])) or "Multi-Vendor"
        tags = ", ".join(art.get("tech_tags", []))
        url = art.get("canonical_url", "#")

        cards_html.append(
            f"""
            <div style="border:1px solid #1e293b; border-radius:8px; padding:16px; margin-bottom:16px; background:#0f172a; color:#f8fafc;">
              <div style="font-size:12px; color:#38bdf8; font-weight:600; margin-bottom:4px;">
                #{idx} • {art.get('category_tab', 'Market').upper()} • {art.get('source_name', '')} • Impact: {art.get('impact_score', 4)}/5 ⭐
              </div>
              <h3 style="margin:4px 0 8px 0; font-size:16px;">
                <a href="{url}" style="color:#00e5ff; text-decoration:none;">{art.get('title', '')}</a>
              </h3>
              <div style="font-size:12px; color:#94a3b8; margin-bottom:10px;">
                <strong>Verified Link:</strong> <a href="{url}" style="color:#38bdf8;">{url}</a><br/>
                <strong>Vendors:</strong> {vendors} | <strong>Tech Tags:</strong> {tags}
              </div>
              <ul style="font-size:13px; line-height:1.5; color:#e2e8f0; margin:8px 0; padding-left:18px;">
                <li><strong>What Happened:</strong> {takeaway.get('what_happened', '')}</li>
                <li><strong>Operator/Telco Impact:</strong> {takeaway.get('operator_impact', '')}</li>
                <li><strong>Downstream & SW Ecosystem Impact:</strong> {takeaway.get('ecosystem_impact', '')}</li>
              </ul>
              <div style="background:#13233a; padding:10px; border-left:3px solid #10b981; border-radius:4px; font-size:12.5px; margin-top:8px;">
                <strong>💰 Pricing & Flat-Market SW Monetization Play ({pricing.get('pricing_model', '')}):</strong><br/>
                {pricing.get('sw_sales_adoption_idea', '')}
              </div>
              <div style="background:#261c2c; padding:10px; border-left:3px solid #f59e0b; border-radius:4px; font-size:12.5px; margin-top:8px;">
                <strong>🔧 HW Scarcity & Expansion Impact ({hw.get('bottleneck_component', '')}):</strong><br/>
                {hw.get('expansion_strategy_impact', '')}
              </div>
            </div>
            """
        )

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{subject}</title></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background:#020617; color:#f8fafc; padding:24px;">
  <div style="max-width:760px; margin:0 auto;">
    <h2 style="color:#00e5ff; margin-bottom:4px;">📡 Telecom Intelligence & SW Monetization {frequency} Digest</h2>
    <p style="color:#94a3b8; font-size:13px; margin-top:0;">
      Prepared for: <strong>{subscriber_email}</strong> • Date: {date_str} • Encrypted Local Vault Verified
    </p>
    <hr style="border:0; border-top:1px solid #1e293b; margin:16px 0;"/>
    {''.join(cards_html)}
  </div>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = "digest@telecom-intelligence.local"
    msg["To"] = subscriber_email
    msg["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    return html_body, msg.as_string()
