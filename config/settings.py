"""Centralized configuration for all Murmur parameters."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = Path(__file__).parent


@dataclass
class MurmurSettings:
    # --- Infrastructure ---
    db_path: str = str(PROJECT_ROOT / "murmur.duckdb")
    schema_path: str = str(PROJECT_ROOT / "sql" / "schema.sql")
    fixtures_dir: str = str(PROJECT_ROOT / "data" / "fixtures")
    known_initiators_path: str = str(CONFIG_DIR / "known_initiators.json")

    # --- GCP (read from .env via environment variables) ---
    gcp_project_id: str = field(default_factory=lambda: os.environ.get("GCP_PROJECT_ID", ""))
    gcp_region: str = field(default_factory=lambda: os.environ.get("GCP_REGION", "us-central1"))

    # --- Ingestion ---
    gcs_bucket: str = field(default_factory=lambda: os.environ.get("GCS_AUDIT_BUCKET", ""))
    gcs_prefix: str = "cloudaudit.googleapis.com"  # legacy — kept for backward compat
    gcs_prefixes: list[str] = field(default_factory=lambda: [
        "cloudaudit.googleapis.com",
        "cloudscheduler.googleapis.com",
        "run.googleapis.com",
    ])

    # --- Windowing ---
    window_size_minutes: int = 15

    # --- Parser ---
    # Resource path patterns that indicate EXFIL_RISK zone instead of DATA
    exfil_risk_patterns: list[str] = field(default_factory=lambda: [
        "storage.googleapis.com/public-",
        "storage.googleapis.com/external-",
        "bigquery.googleapis.com/projects/public-",
    ])

    # --- Scoring thresholds (Sprint 1+) ---
    alert_high_threshold: float = 8.0
    alert_med_threshold: float = 5.0
    watch_threshold: float = 3.0

    # --- Provenance (Sprint 1+) ---
    trigger_penalty_weight: float = 0.3
    discount_multipliers: dict[str, float] = field(default_factory=lambda: {
        "STRONG": 1.0,
        "WEAK": 0.6,
        "NONE": 0.0,
    })

    # --- Pattern match component weights (Sprint 1+) ---
    pattern_weight_actor: float = 0.30
    pattern_weight_zone: float = 0.35
    pattern_weight_time: float = 0.20
    pattern_weight_rate: float = 0.15

    # --- Correlation (Sprint 1) ---
    # Maps Cloud Run service_name → expected worker SA email
    service_worker_map: dict[str, str] = field(default_factory=lambda: {
        "normal-worker": "normal-worker-sa@project-1f4f13c5-912e-45ae-b8a.iam.gserviceaccount.com",
    })

    # --- Trigger chain ---
    trigger_chain_max_depth: int = 10

    # --- Closure (Sprint 3) ---
    closure_sensitivity: dict[str, float] = field(default_factory=lambda: {
        "SA_KEY": 5.0,
        "IAM_POLICY": 4.0,
        "IMPERSONATION": 4.0,
        "SECRET": 3.0,
    })

    def load_known_initiators(self) -> set[str]:
        path = Path(self.known_initiators_path)
        if path.exists():
            with open(path) as f:
                return set(json.load(f))
        return set()


# Singleton instance — import this
SETTINGS = MurmurSettings()
