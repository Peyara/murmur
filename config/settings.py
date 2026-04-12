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
        "cloudaudit.googleapis.com/activity",
        "cloudaudit.googleapis.com/data_access",
        "cloudaudit.googleapis.com/system_event",
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
    # Maps Cloud Run service_name → expected worker SA email (requires GCP_PROJECT_ID)
    service_worker_map: dict[str, str] = field(default_factory=lambda: (
        {
            "normal-worker": f"normal-worker-sa@{pid}.iam.gserviceaccount.com",
            "maintainer": f"maintenance-sa@{pid}.iam.gserviceaccount.com",
        }
        if (pid := os.environ.get("GCP_PROJECT_ID"))
        else {}
    ))

    # --- Trigger chain ---
    trigger_chain_max_depth: int = 10

    # --- Closure (Sprint 3) ---
    # Platform-specific closure config. GCP defaults below.
    # To support a new platform, replace this with that platform's ClosureConfig.
    closure: "ClosureConfig" = field(default_factory=lambda: _gcp_closure_config())

    def load_known_initiators(self) -> set[str]:
        """Load known initiator SA emails. Resolves PROJECT_NUMBER placeholder from env."""
        path = Path(self.known_initiators_path)
        if not path.exists():
            return set()
        with open(path) as f:
            raw = set(json.load(f))
        # Resolve placeholders from env vars
        project_number = os.environ.get("GCP_PROJECT_NUMBER", "")
        project_id = os.environ.get("GCP_PROJECT_ID", "")
        resolved = set()
        for sa in raw:
            entry = sa
            if "PROJECT_NUMBER" in entry and project_number:
                entry = entry.replace("PROJECT_NUMBER", project_number)
            if "PROJECT_ID" in entry and project_id:
                entry = entry.replace("PROJECT_ID", project_id)
            resolved.add(entry)
        return resolved


def _gcp_closure_config() -> "ClosureConfig":
    """GCP-specific closure configuration. The only platform-specific code."""
    from src.score.closure import ClosureConfig

    return ClosureConfig(
        seeded_pairs=[
            {
                "pair_id": "seed-iam-create-key",
                "opening_action_type": "IAM_CREATE_KEY",
                "closing_action_type": "IAM_DELETE_KEY",
                "window_hours": 720,
                "tier": 1,
            },
            {
                "pair_id": "seed-iam-create-sa",
                "opening_action_type": "IAM_CREATE_SA",
                "closing_action_type": "IAM_DELETE_SA",
                "window_hours": 720,
                "tier": 1,
            },
        ],
        temporal_ttl={
            "IAM_IMPERSONATE": 1,  # GCP access token default: 1 hour
        },
        opening_types={
            "IAM_CREATE_KEY", "IAM_CREATE_SA", "IAM_IMPERSONATE",
            "IAM_SET_POLICY", "COMPUTE_METADATA_CHANGE",
        },
        action_to_resource_type={
            "IAM_CREATE_KEY": "SA_KEY",
            "IAM_CREATE_SA": "SERVICE_ACCOUNT",
            "IAM_IMPERSONATE": "IMPERSONATION",
            "IAM_SET_POLICY": "IAM_POLICY",
            "SECRET_ADMIN": "SECRET",
            "COMPUTE_METADATA_CHANGE": "COMPUTE",
        },
        sensitivity={
            "SA_KEY": 5.0,
            "SERVICE_ACCOUNT": 4.0,
            "IMPERSONATION": 4.0,
            "IAM_POLICY": 4.0,
            "SECRET": 3.0,
            "COMPUTE": 2.0,
            "UNKNOWN": 3.0,
        },
        settlement_hours={
            "IMPERSONATION": 1,
            "IAM_POLICY": 4,
            "COMPUTE": 2,
            "SECRET": 4,
            "UNKNOWN": 4,
        },
        never_settle_types={"SA_KEY", "SERVICE_ACCOUNT"},
        failsafe_zones={"IDENTITY", "CONTROL"},
    )


# Singleton instance — import this
SETTINGS = MurmurSettings()
