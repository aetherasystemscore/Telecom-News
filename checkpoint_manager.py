"""
Atomic Checkpoint & Resumable Progress Engine (`checkpoint_manager.py`)
=======================================================================
Tracks step-by-step progress in percentage (0% -> 100%), logs ongoing timestamped
events, and persists atomic state to disk so both the multi-step build workflow
and runtime feed ingestion / AI tagging pipelines can resume seamlessly from
the exact sub-step where execution was interrupted.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

PIPELINE_CHECKPOINT_FILE = DATA_DIR / "pipeline_checkpoint.json"
BUILD_CHECKPOINT_FILE = DATA_DIR / "build_checkpoint.json"

BUILD_STEPS_DEFINITION: List[Dict[str, Any]] = [
    {
        "step_no": 1,
        "step_id": "step_1_checkpoint_engine",
        "title": "Repository Initialization & Resumable Checkpoint Engine",
        "start_pct": 0.0,
        "end_pct": 12.0,
        "module": "checkpoint_manager.py",
    },
    {
        "step_no": 2,
        "step_id": "step_2_sources_and_corpus",
        "title": "14-Portal + Vendor/Startup Catalog & Verifiable Seed Corpus",
        "start_pct": 12.0,
        "end_pct": 28.0,
        "module": "telecom_sources.py",
    },
    {
        "step_no": 3,
        "step_id": "step_3_ingestion_dedup",
        "title": "Hybrid Ingestion, URL Verification & Cosine Similarity Deduplicator",
        "start_pct": 28.0,
        "end_pct": 45.0,
        "module": "ingestion_engine.py",
    },
    {
        "step_no": 4,
        "step_id": "step_4_ai_pipeline",
        "title": "AI 3-Bullet Takeaway, SW Monetization & HW Scarcity Tagging Pipeline",
        "start_pct": 45.0,
        "end_pct": 62.0,
        "module": "ai_pipeline.py",
    },
    {
        "step_no": 5,
        "step_id": "step_5_preference_engine",
        "title": "Thumbs-Up/Down Adaptive Preference Learning & Top-of-Feed Re-Ranker",
        "start_pct": 62.0,
        "end_pct": 75.0,
        "module": "preference_engine.py",
    },
    {
        "step_no": 6,
        "step_id": "step_6_encrypted_vault",
        "title": "AES-Encrypted Local Email Subscription Vault & Digest Engine",
        "start_pct": 75.0,
        "end_pct": 86.0,
        "module": "subscription_vault.py",
    },
    {
        "step_no": 7,
        "step_id": "step_7_streamlit_ui",
        "title": "4-Tab Executive Streamlit UI, SW Pricing Lab, PDF Viewer & Push Alerts",
        "start_pct": 86.0,
        "end_pct": 95.0,
        "module": "app.py",
    },
    {
        "step_no": 8,
        "step_id": "step_8_verification_git",
        "title": "End-to-End Automated Pytest Suite, Critic Audit & Git Setup",
        "start_pct": 95.0,
        "end_pct": 100.0,
        "module": "test_telecom_news.py",
    },
]


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write_json(target_path: Path, payload: Dict[str, Any]) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, ensure_ascii=False)
    tmp_path = target_path.with_suffix(f".tmp.{os.getpid()}")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(serialized)
        os.replace(tmp_path, target_path)
    except PermissionError:
        try:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(serialized)


class ResumableCheckpointManager:
    def __init__(self, checkpoint_path: Path = PIPELINE_CHECKPOINT_FILE, max_events: int = 80):
        self.checkpoint_path = Path(checkpoint_path)
        self.max_events = max_events

    def _default_state(self) -> Dict[str, Any]:
        return {
            "pipeline_name": "Telecom Intelligence Ingestion & AI Tagging Pipeline",
            "status": "IDLE",
            "percent_complete": 0.0,
            "current_step_no": 0,
            "total_steps": 5,
            "current_stage_label": "Ready",
            "current_unit_id": None,
            "total_units": 0,
            "completed_units": [],
            "failed_unit": None,
            "failure_reason": None,
            "can_resume": False,
            "started_at": None,
            "updated_at": _utc_iso(),
            "completed_at": None,
            "ongoing_events": [],
            "partial_results_count": 0,
        }

    def load_state(self) -> Dict[str, Any]:
        if not self.checkpoint_path.exists():
            return self._default_state()
        try:
            with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            base = self._default_state()
            base.update(data)
            return base
        except Exception:
            return self._default_state()

    def save_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        state["updated_at"] = _utc_iso()
        if len(state.get("ongoing_events", [])) > self.max_events:
            state["ongoing_events"] = state["ongoing_events"][-self.max_events :]
        _atomic_write_json(self.checkpoint_path, state)
        return state

    def log_event(
        self,
        message: str,
        percent_complete: Optional[float] = None,
        stage_label: Optional[str] = None,
        step_no: Optional[int] = None,
        level: str = "INFO",
    ) -> Dict[str, Any]:
        state = self.load_state()
        if percent_complete is not None:
            state["percent_complete"] = round(max(0.0, min(100.0, float(percent_complete))), 1)
        if stage_label is not None:
            state["current_stage_label"] = stage_label
        if step_no is not None:
            state["current_step_no"] = int(step_no)

        event_entry = {
            "timestamp": _utc_iso(),
            "percent": state["percent_complete"],
            "stage": state["current_stage_label"],
            "level": level,
            "message": message,
        }
        state.setdefault("ongoing_events", []).append(event_entry)
        return self.save_state(state)

    def start_or_resume_run(
        self,
        total_units: int,
        resume: bool = True,
        pipeline_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        state = self.load_state()
        if resume and state.get("status") == "INTERRUPTED" and state.get("completed_units"):
            state["status"] = "RUNNING"
            state["failed_unit"] = None
            state["failure_reason"] = None
            state["can_resume"] = False
            state["total_units"] = max(total_units, len(state["completed_units"]))
            done = len(state["completed_units"])
            resumed_pct = round((done / max(1, state["total_units"])) * 100.0, 1)
            state["percent_complete"] = max(state.get("percent_complete", 0.0), resumed_pct)
            state.setdefault("ongoing_events", []).append(
                {
                    "timestamp": _utc_iso(),
                    "percent": state["percent_complete"],
                    "stage": "Resuming from Checkpoint",
                    "level": "RESUMED",
                    "message": (
                        f"Resumed execution from checkpoint at {state['percent_complete']:.1f}% "
                        f"({done}/{state['total_units']} units already verified; skipping completed work)."
                    ),
                }
            )
            return self.save_state(state)

        fresh = self._default_state()
        if pipeline_name:
            fresh["pipeline_name"] = pipeline_name
        fresh["status"] = "RUNNING"
        fresh["started_at"] = _utc_iso()
        fresh["total_units"] = total_units
        fresh["ongoing_events"].append(
            {
                "timestamp": _utc_iso(),
                "percent": 0.0,
                "stage": "Pipeline Initialized",
                "level": "INFO",
                "message": f"Started fresh pipeline run across {total_units} work units (0.0%).",
            }
        )
        return self.save_state(fresh)

    def mark_unit_started(
        self,
        unit_id: str,
        unit_label: str,
        step_no: int = 1,
        stage_label: str = "Processing",
    ) -> Dict[str, Any]:
        state = self.load_state()
        state["status"] = "RUNNING"
        state["current_unit_id"] = unit_id
        state["current_step_no"] = step_no
        state["current_stage_label"] = stage_label
        done = len(state.get("completed_units", []))
        total = max(1, state.get("total_units", 1))
        pct = round((done / total) * 100.0, 1)
        state["percent_complete"] = max(state.get("percent_complete", 0.0), pct)
        state.setdefault("ongoing_events", []).append(
            {
                "timestamp": _utc_iso(),
                "percent": state["percent_complete"],
                "stage": stage_label,
                "level": "ONGOING",
                "message": f"[{state['percent_complete']:.1f}%] Starting unit '{unit_label}' ({done + 1}/{total})...",
            }
        )
        return self.save_state(state)

    def mark_unit_completed(
        self,
        unit_id: str,
        unit_label: str,
        articles_added: int = 0,
        stage_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        state = self.load_state()
        completed = state.setdefault("completed_units", [])
        if unit_id not in completed:
            completed.append(unit_id)
        state["current_unit_id"] = None
        state["partial_results_count"] = int(state.get("partial_results_count", 0)) + int(articles_added)
        total = max(1, state.get("total_units", len(completed)))
        pct = round(min(99.0, (len(completed) / total) * 100.0), 1)
        state["percent_complete"] = pct
        if stage_label:
            state["current_stage_label"] = stage_label

        state.setdefault("ongoing_events", []).append(
            {
                "timestamp": _utc_iso(),
                "percent": pct,
                "stage": state["current_stage_label"],
                "level": "SUCCESS",
                "message": (
                    f"[{pct:.1f}%] Completed '{unit_label}' ({len(completed)}/{total} units done; "
                    f"+{articles_added} verified items)."
                ),
            }
        )
        return self.save_state(state)

    def mark_interrupted(
        self,
        unit_id: str,
        reason: str,
        stage_label: str = "Interrupted / Paused at Breakpoint",
    ) -> Dict[str, Any]:
        state = self.load_state()
        state["status"] = "INTERRUPTED"
        state["failed_unit"] = unit_id
        state["failure_reason"] = reason
        state["can_resume"] = True
        state["current_stage_label"] = stage_label
        pct = state.get("percent_complete", 0.0)
        state.setdefault("ongoing_events", []).append(
            {
                "timestamp": _utc_iso(),
                "percent": pct,
                "stage": stage_label,
                "level": "ERROR",
                "message": (
                    f"[{pct:.1f}%] BREAKPOINT at '{unit_id}': {reason}. "
                    f"State saved atomically ({len(state.get('completed_units', []))} units preserved). "
                    f"Ready to resume from exact breakpoint."
                ),
            }
        )
        return self.save_state(state)

    def mark_completed(self, summary_message: str) -> Dict[str, Any]:
        state = self.load_state()
        state["status"] = "COMPLETED"
        state["percent_complete"] = 100.0
        state["current_unit_id"] = None
        state["failed_unit"] = None
        state["failure_reason"] = None
        state["can_resume"] = False
        state["current_stage_label"] = "Completed (100%)"
        state["completed_at"] = _utc_iso()
        state.setdefault("ongoing_events", []).append(
            {
                "timestamp": _utc_iso(),
                "percent": 100.0,
                "stage": "Completed (100%)",
                "level": "SUCCESS",
                "message": f"[100.0%] {summary_message}",
            }
        )
        return self.save_state(state)

    def reset_checkpoint(self) -> Dict[str, Any]:
        fresh = self._default_state()
        return self.save_state(fresh)

    def get_pending_units(self, all_unit_ids: List[str], resume: bool = True) -> List[str]:
        if not resume:
            return list(all_unit_ids)
        state = self.load_state()
        if state.get("status") in ("INTERRUPTED", "RUNNING"):
            done_set = set(state.get("completed_units", []))
            return [u for u in all_unit_ids if u not in done_set]
        return list(all_unit_ids)
