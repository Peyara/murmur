# ruff: noqa: S607, S603
#!/usr/bin/env python3
"""Murmur Phase 3: Live Attack Injection Orchestrator.

Executes 4 attack scenarios against the GCP sandbox, waits for GCS audit log
export, then ingests, scores, and captures results.

Architecture: Execute-then-Observe
  Phase 1: Execute all attacks sequentially (fast — just GCP API calls)
  Phase 2: Wait for GCS hourly export (audit logs batch by hour)
  Phase 3: Ingest + Score + Capture all results at once

Adaptation: SA key creation is blocked by org policy, so Attacks B and C
use --impersonate-service-account instead of direct key auth. This means
INV_011 (delegation chain anomaly) cannot be tested with live injection —
documented as limitation, validated via synthetic benchmarks only.

Reference: docs/phase3_attack_injection_plan.md

Usage:
    python scripts/attack_orchestrator.py                    # full run
    python scripts/attack_orchestrator.py --dry-run          # preview only
    python scripts/attack_orchestrator.py --skip-cleanup     # keep artifacts
    python scripts/attack_orchestrator.py --attack A         # single attack
    python scripts/attack_orchestrator.py --observe-only     # skip attacks, just observe
"""

import argparse
import dataclasses
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import duckdb  # noqa: E402

from config.settings import SETTINGS  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
HUMAN_ACCOUNT = os.environ.get("MURMUR_HUMAN_ACCOUNT", "")  # resolved lazily in main()
GCS_BUCKET = os.environ.get("GCS_AUDIT_BUCKET", "murmur-audit-logs-sandbox")
EXFIL_BUCKET = os.environ.get("MURMUR_EXFIL_BUCKET", "public-export-sandbox")
INPUT_BUCKET = os.environ.get("MURMUR_INPUT_BUCKET", "murmur-input-sandbox")
OUTPUT_BUCKET = os.environ.get("MURMUR_OUTPUT_BUCKET", "murmur-output-sandbox")

# SA emails derived from PROJECT_ID — validated in main()
NW_SA = ""
MAINT_SA = ""
SCHED_SA = ""
ATTACKER_SA = ""

RESULTS_DIR = PROJECT_ROOT / "data" / "attack_results"
DB_BACKUP_PATH = PROJECT_ROOT / "murmur.duckdb.pre-attack-backup"

# GCS audit log sink exports hourly. We poll until events appear.
MAX_OBSERVATION_WAIT_SEC = 75 * 60  # 75 min max (covers full hour + margin)
OBSERVATION_POLL_SEC = 120          # check every 2 min

# Scoring thresholds (from settings, normalized to [0,1])
HIGH_T = SETTINGS.alert_high_threshold / 10.0
MED_T = SETTINGS.alert_med_threshold / 10.0
WATCH_T = SETTINGS.watch_threshold / 10.0

RATCHET_WINDOW_GAP_SEC = 16 * 60  # 16 min between slow ratchet windows

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = RESULTS_DIR / "phase3_execution.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_PATH, mode="w"),
    ],
)
log = logging.getLogger("orchestrator")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ActionRecord:
    command: str
    description: str
    expected_zone: str
    expected_action_type: str
    timestamp_utc: str = ""
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    duration_sec: float = 0.0


@dataclass
class WindowResult:
    window_start: str
    actor_id: str
    fusion_raw: float = 0.0
    residual_risk: float = 0.0
    tier: str = ""
    inv_score: float = 0.0
    sigma_coarse: float = 0.0
    novelty_score: float = 0.0
    bridge_new: int = 0
    delta_f: float = 0.0
    burst_per_min: float = 0.0
    breadth_entropy: float = 0.0
    fired_invariants: list = field(default_factory=list)
    explanation: str = ""


@dataclass
class AttackResult:
    attack_id: str
    name: str
    actor: str
    started_at: str = ""
    completed_at: str = ""
    status: str = "PENDING"
    actions: list = field(default_factory=list)
    windows: list = field(default_factory=list)
    baseline_sigma: float = 0.0
    baseline_event_count: int = 0
    expected_invariants: list = field(default_factory=list)
    expected_tier: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Shell helpers
# ---------------------------------------------------------------------------

def gcloud(*args, dry_run=False) -> subprocess.CompletedProcess:
    cmd = ["gcloud"] + list(args) + [f"--project={PROJECT_ID}"]
    if dry_run:
        log.info("[DRY-RUN] %s", " ".join(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="dry-run", stderr="")
    log.info("Running: %s", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)  # noqa: S603, S607
    if r.returncode != 0:
        log.warning("FAILED (exit %d): %s", r.returncode, r.stderr.strip()[:200])
    return r


def gsutil(*args, stdin_data=None, dry_run=False) -> subprocess.CompletedProcess:
    cmd = ["gsutil"] + list(args)
    if dry_run:
        log.info("[DRY-RUN] %s", " ".join(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="dry-run", stderr="")
    log.info("Running: %s", " ".join(cmd))
    r = subprocess.run(  # noqa: S603, S607
        cmd, input=stdin_data, capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        log.warning("gsutil FAILED (exit %d): %s", r.returncode, r.stderr.strip()[:200])
    return r


def pipeline(*args, dry_run=False) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-m", "src.cli"] + list(args)
    if dry_run:
        log.info("[DRY-RUN] pipeline: %s", " ".join(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="dry-run", stderr="")
    log.info("Pipeline: %s", " ".join(args))
    r = subprocess.run(  # noqa: S603, S607
        cmd, capture_output=True, text=True, timeout=600, cwd=str(PROJECT_ROOT),
    )
    if r.returncode != 0:
        log.warning("Pipeline FAILED: %s", r.stderr.strip()[:200])
    elif r.stdout.strip():
        log.info("Pipeline: %s", r.stdout.strip())
    return r


def get_event_count() -> int:
    db = duckdb.connect(SETTINGS.db_path, read_only=True)
    c = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    db.close()
    return c


def get_current_sigma() -> float:
    db = duckdb.connect(SETTINGS.db_path, read_only=True)
    r = db.execute("SELECT sigma_coarse FROM zone_flux_windows ORDER BY window_start DESC LIMIT 1").fetchone()
    db.close()
    return r[0] if r else 0.0


def get_tier(residual: float) -> str:
    if residual >= HIGH_T:
        return "HIGH"
    elif residual >= MED_T:
        return "MEDIUM"
    elif residual >= WATCH_T:
        return "WATCH"
    return "NORMAL"


def timed_action(desc, zone, action_type, fn) -> ActionRecord:
    """Execute fn(), capture timing and result as ActionRecord."""
    ts = datetime.now(UTC).isoformat()
    t0 = time.time()
    try:
        r = fn()
        return ActionRecord(
            command=desc, description=desc,
            expected_zone=zone, expected_action_type=action_type,
            timestamp_utc=ts, exit_code=r.returncode,
            stdout=r.stdout[:500] if r.stdout else "",
            stderr=r.stderr[:300] if r.stderr else "",
            duration_sec=round(time.time() - t0, 2),
        )
    except Exception as e:
        return ActionRecord(
            command=desc, description=desc,
            expected_zone=zone, expected_action_type=action_type,
            timestamp_utc=ts, exit_code=-1, stderr=str(e),
            duration_sec=round(time.time() - t0, 2),
        )


# ---------------------------------------------------------------------------
# Ringfencing
# ---------------------------------------------------------------------------

def ringfence_preflight(dry_run=False):
    log.info("=" * 60)
    log.info("RINGFENCING PRE-FLIGHT")
    log.info("=" * 60)

    # Auth
    acct = subprocess.run(  # noqa: S603, S607
        ["gcloud", "config", "get-value", "account"],
        capture_output=True, text=True, timeout=30,
    ).stdout.strip()
    assert acct == HUMAN_ACCOUNT, f"Wrong auth: {acct}"
    log.info("Auth: %s", acct)

    # Project
    proj = subprocess.run(  # noqa: S603, S607
        ["gcloud", "config", "get-value", "project"],
        capture_output=True, text=True, timeout=30,
    ).stdout.strip()
    assert proj == PROJECT_ID, f"Wrong project: {proj}"
    log.info("Project: %s", proj)

    # DB backup
    db_path = Path(SETTINGS.db_path)
    if not dry_run:
        shutil.copy2(db_path, DB_BACKUP_PATH)
        bdb = duckdb.connect(str(DB_BACKUP_PATH), read_only=True)
        bc = bdb.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        bdb.close()
        log.info("DB backed up: %s (%d events)", DB_BACKUP_PATH, bc)
    else:
        log.info("[DRY-RUN] Would backup DB")

    # GCP state snapshot
    pre_dir = RESULTS_DIR / "pre_flight"
    pre_dir.mkdir(exist_ok=True)
    if not dry_run:
        for sa_name, sa_email in [("normal_worker", NW_SA), ("scheduler", SCHED_SA), ("maintenance", MAINT_SA)]:
            r = gcloud("iam", "service-accounts", "keys", "list", f"--iam-account={sa_email}", "--format=json")
            (pre_dir / f"keys_{sa_name}.json").write_text(r.stdout)
        r = gcloud("projects", "get-iam-policy", PROJECT_ID, "--format=json")
        (pre_dir / "iam_policy.json").write_text(r.stdout)
        for secret in ["secret_high", "secret_low", "secret_medium", "secret_maintenance"]:
            r = gcloud("secrets", "get-iam-policy", secret, "--format=json")
            (pre_dir / f"iam_{secret}.json").write_text(r.stdout)
        log.info("GCP state snapshot saved to %s", pre_dir)

    # Git branch
    branch = subprocess.run(  # noqa: S603, S607
        ["git", "branch", "--show-current"],
        capture_output=True, text=True, timeout=10,
        cwd=str(PROJECT_ROOT),
    ).stdout.strip()
    assert branch != "main", "Must be on feature branch"
    log.info("Git branch: %s", branch)
    log.info("PRE-FLIGHT COMPLETE")


def ringfence_postflight(dry_run=False):
    log.info("=" * 60)
    log.info("POST-FLIGHT VERIFICATION")
    log.info("=" * 60)
    warnings = []

    acct = subprocess.run(  # noqa: S603, S607
        ["gcloud", "config", "get-value", "account"],
        capture_output=True, text=True, timeout=30,
    ).stdout.strip()
    if acct != HUMAN_ACCOUNT:
        warnings.append(f"Auth: expected {HUMAN_ACCOUNT}, got {acct}")
    else:
        log.info("Auth: OK")

    if not dry_run:
        # attacker-sa deleted?
        r = gcloud("iam", "service-accounts", "describe", ATTACKER_SA)
        if r.returncode == 0:
            warnings.append("attacker-sa still exists!")
        else:
            log.info("attacker-sa: deleted (OK)")

        # DB readable?
        try:
            c = get_event_count()
            log.info("DB OK: %d events", c)
        except Exception as e:
            warnings.append(f"DB error: {e}")

        # Exfil bucket
        r = gsutil("ls", f"gs://{EXFIL_BUCKET}/")
        if r.stdout.strip():
            warnings.append("Exfil bucket not empty")
        else:
            log.info("Exfil bucket: empty (OK)")

    for w in warnings:
        log.warning("POST-FLIGHT: %s", w)
    if not warnings:
        log.info("POST-FLIGHT: ALL CLEAR")
    return warnings


# ---------------------------------------------------------------------------
# Pre-flight setup
# ---------------------------------------------------------------------------

def preflight_setup(dry_run=False):
    log.info("=" * 60)
    log.info("PRE-FLIGHT SETUP")
    log.info("=" * 60)

    # Create attacker-sa (for Attack C impersonation target)
    gcloud("iam", "service-accounts", "create", "attacker-sa",
           "--display-name=Phase 3 attacker SA — temporary", dry_run=dry_run)

    for role in ["roles/secretmanager.secretAccessor",
                 "roles/storage.objectViewer",
                 "roles/storage.objectCreator"]:
        gcloud("projects", "add-iam-policy-binding", PROJECT_ID,
               f"--member=serviceAccount:{ATTACKER_SA}", f"--role={role}",
               dry_run=dry_run)

    # Grant human impersonation rights on attacker-sa
    gcloud("iam", "service-accounts", "add-iam-policy-binding", ATTACKER_SA,
           f"--member=user:{HUMAN_ACCOUNT}",
           "--role=roles/iam.serviceAccountTokenCreator", dry_run=dry_run)

    # Grant human impersonation rights on normal-worker-sa (for Attack B)
    gcloud("iam", "service-accounts", "add-iam-policy-binding", NW_SA,
           f"--member=user:{HUMAN_ACCOUNT}",
           "--role=roles/iam.serviceAccountTokenCreator", dry_run=dry_run)

    log.info("PRE-FLIGHT SETUP COMPLETE")
    log.info("Waiting 180s for IAM propagation...")
    if not dry_run:
        time.sleep(180)

    # Verify impersonation works before proceeding
    log.info("Verifying impersonation permissions...")
    for sa, name in [(NW_SA, "normal-worker-sa"), (ATTACKER_SA, "attacker-sa")]:
        if not dry_run:
            r = gcloud("auth", "print-access-token",
                       f"--impersonate-service-account={sa}")
            if r.returncode == 0:
                log.info("Impersonation OK: %s", name)
            else:
                log.warning("Impersonation FAILED for %s — may need more propagation time", name)
                log.info("Waiting 60s more...")
                time.sleep(60)
                r = gcloud("auth", "print-access-token",
                           f"--impersonate-service-account={sa}")
                if r.returncode == 0:
                    log.info("Impersonation OK (retry): %s", name)
                else:
                    log.error("Impersonation still failing for %s. Attack will likely fail.", name)


# ---------------------------------------------------------------------------
# Attack A: Smash and Grab
# ---------------------------------------------------------------------------

def attack_a(dry_run=False) -> AttackResult:
    result = AttackResult(
        attack_id="A_smash_and_grab", name="Smash and Grab",
        actor=HUMAN_ACCOUNT,
        expected_invariants=["INV_006", "INV_010"],
        expected_tier="WATCH or MEDIUM",
    )
    try:
        result.status = "RUNNING"
        result.baseline_sigma = get_current_sigma()
        result.baseline_event_count = get_event_count()
        result.started_at = datetime.now(UTC).isoformat()
        log.info("=" * 60)
        log.info("ATTACK A: SMASH AND GRAB (human actor)")
        log.info("=" * 60)

        actions = []

        # Action 1: Access secret_high (first time for human on this target)
        actions.append(timed_action(
            "Access secret_high", "SECRET", "SECRET_ACCESS",
            lambda: gcloud("secrets", "versions", "access", "latest",
                           "--secret=secret_high", dry_run=dry_run),
        ))

        # Action 2: Exfiltrate to public bucket (EXFIL_RISK — first ever events)
        obj = f"smash_grab_{int(time.time())}.txt"
        actions.append(timed_action(
            f"Write to gs://{EXFIL_BUCKET}/{obj}", "EXFIL_RISK", "GCS_WRITE",
            lambda: gsutil("cp", "-", f"gs://{EXFIL_BUCKET}/{obj}",
                           stdin_data=f"smash-grab-exfil-{datetime.now(UTC).isoformat()}",
                           dry_run=dry_run),
        ))

        # Action 3: List exfil bucket (additional EXFIL_RISK interaction)
        actions.append(timed_action(
            f"List gs://{EXFIL_BUCKET}/", "EXFIL_RISK", "GCS_LIST",
            lambda: gsutil("ls", f"gs://{EXFIL_BUCKET}/", dry_run=dry_run),
        ))

        result.actions = [dataclasses.asdict(a) for a in actions]
        result.completed_at = datetime.now(UTC).isoformat()
        result.status = "SUCCESS"
        log.info("Attack A executed: %d actions", len(actions))

    except Exception as e:
        result.status = "FAILED"
        result.error = str(e)
        log.error("Attack A failed: %s", e)
    return result


# ---------------------------------------------------------------------------
# Attack B: Credential Theft (via impersonation)
# ---------------------------------------------------------------------------

def attack_b(dry_run=False) -> AttackResult:
    """Impersonate normal-worker-sa — same actions, different auth path.

    Note: With impersonation, delegation chain IS present (human→SA).
    INV_011 won't fire. But INV_004 (impersonation) and INV_006 (if
    accessing new targets via the SA) may fire for the human actor.
    The SA's events will have delegation chain, so they look "normal"
    from the SA's perspective — the anomaly is the impersonation event.
    """
    result = AttackResult(
        attack_id="B_impersonated_worker", name="Impersonated Worker",
        actor=f"{HUMAN_ACCOUNT} impersonating {NW_SA}",
        expected_invariants=["INV_004", "INV_005"],
        expected_tier="WATCH",
    )
    try:
        result.status = "RUNNING"
        result.baseline_sigma = get_current_sigma()
        result.baseline_event_count = get_event_count()
        result.started_at = datetime.now(UTC).isoformat()
        log.info("=" * 60)
        log.info("ATTACK B: IMPERSONATED WORKER")
        log.info("=" * 60)

        actions = []
        imp_flag = f"--impersonate-service-account={NW_SA}"

        # Action 1: Read secret_high as normal-worker-sa
        actions.append(timed_action(
            f"Read secret_high via impersonation of {NW_SA}",
            "SECRET", "SECRET_ACCESS",
            lambda: gcloud("secrets", "versions", "access", "latest",
                           "--secret=secret_high", imp_flag, dry_run=dry_run),
        ))

        # Action 2: Read from input bucket as normal-worker-sa
        actions.append(timed_action(
            f"Read gs://{INPUT_BUCKET}/telemetry_001.json via impersonation",
            "DATA", "GCS_READ",
            lambda: gsutil("cat", f"gs://{INPUT_BUCKET}/telemetry_001.json",
                           dry_run=dry_run),
        ))
        # Note: gsutil doesn't support --impersonate-service-account directly
        # The above reads as the human. For a proper impersonated GCS read,
        # we'd need the Python SDK. The secret access is the primary test.

        result.actions = [dataclasses.asdict(a) for a in actions]
        result.completed_at = datetime.now(UTC).isoformat()
        result.status = "SUCCESS"
        log.info("Attack B executed: %d actions", len(actions))

    except Exception as e:
        result.status = "FAILED"
        result.error = str(e)
        log.error("Attack B failed: %s", e)
    return result


# ---------------------------------------------------------------------------
# Attack C: Slow Ratchet (via impersonation)
# ---------------------------------------------------------------------------

def attack_c(dry_run=False) -> AttackResult:
    """Multi-window zone traversal impersonating attacker-sa."""
    result = AttackResult(
        attack_id="C_slow_ratchet", name="Slow Ratchet",
        actor=f"{HUMAN_ACCOUNT} impersonating {ATTACKER_SA}",
        expected_invariants=["INV_004", "INV_006", "INV_010"],
        expected_tier="WATCH or MEDIUM (W4)",
    )
    try:
        result.status = "RUNNING"
        result.baseline_sigma = get_current_sigma()
        result.baseline_event_count = get_event_count()
        result.started_at = datetime.now(UTC).isoformat()
        log.info("=" * 60)
        log.info("ATTACK C: SLOW RATCHET (impersonating attacker-sa)")
        log.info("=" * 60)

        actions = []
        imp_flag = f"--impersonate-service-account={ATTACKER_SA}"

        # Window 1: Reconnaissance — access unused secret
        log.info("── C Window 1: Reconnaissance ──")
        actions.append(timed_action(
            "W1: Access secret_medium via attacker-sa impersonation",
            "SECRET", "SECRET_ACCESS",
            lambda: gcloud("secrets", "versions", "access", "latest",
                           "--secret=secret_medium", imp_flag, dry_run=dry_run),
        ))

        if not dry_run:
            log.info("Waiting %d min for next scoring window...", RATCHET_WINDOW_GAP_SEC // 60)
            time.sleep(RATCHET_WINDOW_GAP_SEC)

        # Window 2: Expand Access
        log.info("── C Window 2: Expand Access ──")
        actions.append(timed_action(
            "W2: Access secret_high via attacker-sa impersonation",
            "SECRET", "SECRET_ACCESS",
            lambda: gcloud("secrets", "versions", "access", "latest",
                           "--secret=secret_high", imp_flag, dry_run=dry_run),
        ))

        if not dry_run:
            log.info("Waiting %d min for next scoring window...", RATCHET_WINDOW_GAP_SEC // 60)
            time.sleep(RATCHET_WINDOW_GAP_SEC)

        # Window 3: Staging — read data files
        log.info("── C Window 3: Staging ──")
        # gsutil doesn't support --impersonate, so read as human but it still
        # generates GCS_READ audit events
        for fname in ["telemetry_001.json", "config_002.json"]:
            actions.append(timed_action(
                f"W3: Read gs://{INPUT_BUCKET}/{fname}",
                "DATA", "GCS_READ",
                lambda f=fname: gsutil("cat", f"gs://{INPUT_BUCKET}/{f}", dry_run=dry_run),
            ))

        if not dry_run:
            log.info("Waiting %d min for next scoring window...", RATCHET_WINDOW_GAP_SEC // 60)
            time.sleep(RATCHET_WINDOW_GAP_SEC)

        # Window 4: Exfiltration
        log.info("── C Window 4: Exfiltration ──")
        obj = f"slow_ratchet_{int(time.time())}.txt"
        actions.append(timed_action(
            f"W4: Exfil to gs://{EXFIL_BUCKET}/{obj}",
            "EXFIL_RISK", "GCS_WRITE",
            lambda: gsutil("cp", "-", f"gs://{EXFIL_BUCKET}/{obj}",
                           stdin_data=f"ratchet-exfil-{datetime.now(UTC).isoformat()}",
                           dry_run=dry_run),
        ))

        result.actions = [dataclasses.asdict(a) for a in actions]
        result.completed_at = datetime.now(UTC).isoformat()
        result.status = "SUCCESS"
        log.info("Attack C executed: %d actions across 4 windows", len(actions))

    except Exception as e:
        result.status = "FAILED"
        result.error = str(e)
        log.error("Attack C failed: %s", e)
    return result


# ---------------------------------------------------------------------------
# Attack D: Insider Lateral Move
# ---------------------------------------------------------------------------

def attack_d(dry_run=False) -> AttackResult:
    result = AttackResult(
        attack_id="D_insider_lateral", name="Insider Lateral Move",
        actor=HUMAN_ACCOUNT,
        expected_invariants=["INV_001", "INV_004", "INV_007"],
        expected_tier="MEDIUM",
    )
    try:
        result.status = "RUNNING"
        result.baseline_sigma = get_current_sigma()
        result.baseline_event_count = get_event_count()
        result.started_at = datetime.now(UTC).isoformat()
        log.info("=" * 60)
        log.info("ATTACK D: INSIDER LATERAL MOVE")
        log.info("=" * 60)

        actions = []

        # Action 1: Grant maintenance-sa access to secret_high
        actions.append(timed_action(
            "Grant maintenance-sa access to secret_high",
            "CONTROL", "IAM_SET_POLICY",
            lambda: gcloud("secrets", "add-iam-policy-binding", "secret_high",
                           f"--member=serviceAccount:{MAINT_SA}",
                           "--role=roles/secretmanager.secretAccessor", dry_run=dry_run),
        ))

        # Action 2: Impersonate maintenance-sa to access secret
        actions.append(timed_action(
            f"Impersonate {MAINT_SA} to access secret_high",
            "IDENTITY+SECRET", "IAM_IMPERSONATE+SECRET_ACCESS",
            lambda: gcloud("secrets", "versions", "access", "latest",
                           "--secret=secret_high",
                           f"--impersonate-service-account={MAINT_SA}", dry_run=dry_run),
        ))

        result.actions = [dataclasses.asdict(a) for a in actions]
        result.completed_at = datetime.now(UTC).isoformat()
        result.status = "SUCCESS"
        log.info("Attack D executed: %d actions", len(actions))

    except Exception as e:
        result.status = "FAILED"
        result.error = str(e)
        log.error("Attack D failed: %s", e)
    return result


# ---------------------------------------------------------------------------
# Observation: batch ingest + score after GCS export
# ---------------------------------------------------------------------------

def wait_and_observe(pre_event_count: int, dry_run=False) -> int:
    """Wait for GCS hourly export, then ingest + window + score."""
    if dry_run:
        log.info("[DRY-RUN] Would wait for GCS export and observe")
        return 0

    log.info("=" * 60)
    log.info("OBSERVATION: Waiting for GCS audit log export...")
    log.info("GCS sink exports hourly. Polling every %ds, max %d min.",
             OBSERVATION_POLL_SEC, MAX_OBSERVATION_WAIT_SEC // 60)
    log.info("=" * 60)

    start = time.time()
    new_events = 0

    while time.time() - start < MAX_OBSERVATION_WAIT_SEC:
        pipeline("ingest", "--gcs-bucket", GCS_BUCKET)
        current = get_event_count()
        new_events = current - pre_event_count

        if new_events > 0:
            log.info("NEW EVENTS DETECTED: %d (total: %d)", new_events, current)
            # Keep polling a bit more — there might be multiple hourly blobs
            log.info("Polling 2 more times to catch remaining blobs...")
            for _ in range(2):
                time.sleep(OBSERVATION_POLL_SEC)
                pipeline("ingest", "--gcs-bucket", GCS_BUCKET)
            current = get_event_count()
            new_events = current - pre_event_count
            log.info("Final new events: %d (total: %d)", new_events, current)
            break

        elapsed = int(time.time() - start)
        log.info("No new events yet (%d total). Elapsed: %d min. Waiting %ds...",
                 current, elapsed // 60, OBSERVATION_POLL_SEC)
        time.sleep(OBSERVATION_POLL_SEC)

    if new_events == 0:
        log.warning("No new events after %d min. Proceeding with scoring anyway.",
                    MAX_OBSERVATION_WAIT_SEC // 60)

    # Recompute world model + scoring
    log.info("Running window + score pipeline...")
    pipeline("window")
    pipeline("score")

    final_count = get_event_count()
    log.info("Observation complete: %d new events ingested, %d total", final_count - pre_event_count, final_count)
    return final_count - pre_event_count


# ---------------------------------------------------------------------------
# Result capture
# ---------------------------------------------------------------------------

def capture_attack_results(attack: AttackResult):
    """Query DB for scoring results matching the attack's time range and actor."""
    db = duckdb.connect(SETTINGS.db_path, read_only=True)

    # Determine actors to query
    actors = []
    if "impersonating" in attack.actor:
        # For impersonation attacks, check both the human and the impersonated SA
        actors = [HUMAN_ACCOUNT]
        for sa in [NW_SA, MAINT_SA, ATTACKER_SA]:
            if sa.split("@")[0] in attack.actor:
                actors.append(sa)
    else:
        actors = [attack.actor]

    all_windows = []
    for actor_id in actors:
        rows = db.execute("""
            SELECT DISTINCT e.window_start
            FROM events e
            WHERE e.ts >= ? AND e.ts <= ?
              AND e.actor_id = ?
            ORDER BY e.window_start
        """, [attack.started_at, attack.completed_at, actor_id]).fetchall()

        for (ws,) in rows:
            score_row = db.execute("""
                SELECT fusion_raw, residual_risk, inv_score, sigma_coarse,
                       novelty_score, bridge_new, delta_f, burst_per_min,
                       breadth_entropy, fired_invariants, explanation
                FROM risk_scores WHERE window_start = ? AND actor_id = ?
            """, [ws, actor_id]).fetchone()

            if score_row:
                fired = json.loads(score_row[9]) if score_row[9] else []
                inv_list = [f["id"] for f in fired if f.get("fired")]
                all_windows.append(dataclasses.asdict(WindowResult(
                    window_start=str(ws), actor_id=actor_id,
                    fusion_raw=score_row[0], residual_risk=score_row[1],
                    tier=get_tier(score_row[1]),
                    inv_score=score_row[2], sigma_coarse=score_row[3],
                    novelty_score=score_row[4], bridge_new=score_row[5],
                    delta_f=score_row[6], burst_per_min=score_row[7],
                    breadth_entropy=score_row[8],
                    fired_invariants=inv_list,
                    explanation=score_row[10] or "",
                )))

    db.close()
    attack.windows = all_windows
    log.info("Captured %d windows for %s", len(all_windows), attack.attack_id)


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def cleanup(dry_run=False):
    log.info("=" * 60)
    log.info("CLEANUP")
    log.info("=" * 60)

    # Revoke maintenance-sa access to secret_high (Attack D)
    gcloud("secrets", "remove-iam-policy-binding", "secret_high",
           f"--member=serviceAccount:{MAINT_SA}",
           "--role=roles/secretmanager.secretAccessor", "--quiet", dry_run=dry_run)

    # Revoke human impersonation on NW SA (Attack B setup)
    gcloud("iam", "service-accounts", "remove-iam-policy-binding", NW_SA,
           f"--member=user:{HUMAN_ACCOUNT}",
           "--role=roles/iam.serviceAccountTokenCreator", "--quiet", dry_run=dry_run)

    # Revoke attacker-sa project bindings
    for role in ["roles/secretmanager.secretAccessor",
                 "roles/storage.objectViewer",
                 "roles/storage.objectCreator"]:
        gcloud("projects", "remove-iam-policy-binding", PROJECT_ID,
               f"--member=serviceAccount:{ATTACKER_SA}",
               f"--role={role}", "--quiet", dry_run=dry_run)

    # Delete attacker-sa
    gcloud("iam", "service-accounts", "delete", ATTACKER_SA, "--quiet", dry_run=dry_run)

    # Clean exfil artifacts
    gsutil("rm", "-f", f"gs://{EXFIL_BUCKET}/**", dry_run=dry_run)
    gsutil("rm", "-f", f"gs://{OUTPUT_BUCKET}/stolen_result.txt", dry_run=dry_run)

    log.info("CLEANUP COMPLETE")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def generate_report(results: list[AttackResult], baseline: dict, postflight_warnings: list) -> str:
    lines = [
        "# Phase 3: Live Attack Injection Results\n\n",
        f"**Generated:** {datetime.now(UTC).isoformat()}Z\n\n",
        "## Adaptation Note\n\n",
        "SA key creation is blocked by org policy (`iam.disableServiceAccountKeyCreation`).\n",
        "Attacks B and C use `--impersonate-service-account` instead of direct key auth.\n",
        "INV_011 (delegation chain anomaly) cannot be tested with live injection.\n\n",
    ]

    # Baseline
    lines.append("## Pre-Attack Baseline\n\n")
    td = baseline.get("tier_distribution", {})
    lines.append("| Tier | Count |\n|---|---|\n")
    for tier in ["HIGH", "MEDIUM", "WATCH", "NORMAL"]:
        lines.append(f"| {tier} | {td.get(tier, 0)} |\n")
    lines.append(f"\nTotal events: {baseline.get('total_events', '?')}\n")
    lines.append(f"Avg NORMAL residual: {baseline.get('avg_normal_residual', '?')}\n")
    lines.append(f"2x threshold: {baseline.get('validation_2x_threshold', '?')}\n\n")

    nw = baseline.get("nw_delegation", {})
    lines.append(f"NW delegation ratio: {nw.get('ratio', '?')} ({nw.get('chained', '?')}/{nw.get('total', '?')})\n\n")

    # Per-attack
    for ar in results:
        lines.append(f"---\n\n## {ar.attack_id}: {ar.name}\n\n")
        lines.append(f"**Actor:** {ar.actor}\n")
        lines.append(f"**Status:** {ar.status}\n")
        lines.append(f"**Time:** {ar.started_at} → {ar.completed_at}\n")
        lines.append(f"**Baseline sigma:** {ar.baseline_sigma:.4f}\n\n")

        if ar.error:
            lines.append(f"**ERROR:** {ar.error}\n\n")

        lines.append("### Actions\n\n")
        lines.append("| # | Description | Zone | Exit | Duration |\n|---|---|---|---|---|\n")
        for i, a in enumerate(ar.actions):
            desc = a['description']
            zone = a['expected_zone']
            lines.append(f"| {i+1} | {desc} | {zone} | {a['exit_code']} | {a['duration_sec']}s |\n")

        if ar.windows:
            lines.append("\n### Scoring Results\n\n")
            for w in ar.windows:
                actor = w['actor_id']
                tier = w['tier']
                rr = w['residual_risk']
                lines.append(f"**Window {w['window_start']} — {actor}**"
                             f" → **{tier}** (residual={rr:.4f})\n\n")
                lines.append("| Signal | Value |\n|---|---|\n")
                for sig in ["inv_score", "sigma_coarse", "novelty_score", "bridge_new",
                            "delta_f", "burst_per_min", "breadth_entropy"]:
                    lines.append(f"| {sig} | {w.get(sig, 0):.4f} |\n")
                fired = w.get("fired_invariants", [])
                lines.append(f"\nInvariants: {', '.join(fired) if fired else 'none'}\n")
                lines.append(f"Explanation: {w.get('explanation', '')}\n\n")

        lines.append("### Expected vs Observed\n\n")
        lines.append(f"- Expected invariants: {ar.expected_invariants}\n")
        lines.append(f"- Expected tier: {ar.expected_tier}\n")
        if ar.windows:
            max_rr = max(w.get("residual_risk", 0) for w in ar.windows)
            threshold = baseline.get("validation_2x_threshold", 0)
            verdict = "PASS" if max_rr >= threshold else "FAIL"
            lines.append(
                f"- Max residual: {max_rr:.4f}"
                f" (2x threshold: {threshold:.4f}) → {verdict}\n"
            )
            observed_invs = set()
            for w in ar.windows:
                observed_invs.update(w.get("fired_invariants", []))
            lines.append(f"- Observed invariants: {sorted(observed_invs)}\n")
        lines.append("\n")

    # Post-flight
    lines.append("---\n\n## Post-Flight\n\n")
    if postflight_warnings:
        for w in postflight_warnings:
            lines.append(f"- WARNING: {w}\n")
    else:
        lines.append("All checks passed.\n")

    return "".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Murmur Phase 3 Attack Orchestrator")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-cleanup", action="store_true")
    parser.add_argument("--attack", choices=["A", "B", "C", "D"])
    parser.add_argument("--observe-only", action="store_true",
                        help="Skip attacks, just observe + score from last run")
    args = parser.parse_args()
    dry_run = args.dry_run

    # Resolve globals that depend on runtime state
    global PROJECT_ID, HUMAN_ACCOUNT, NW_SA, MAINT_SA, SCHED_SA, ATTACKER_SA  # noqa: PLW0603

    if not PROJECT_ID:
        log.error("GCP_PROJECT_ID env var is required. Set it in .env or export it.")
        sys.exit(1)

    if not HUMAN_ACCOUNT:
        result = subprocess.run(  # noqa: S603, S607
            ["gcloud", "config", "get-value", "account"],
            capture_output=True, text=True, timeout=10,
        )
        HUMAN_ACCOUNT = result.stdout.strip()
        if not HUMAN_ACCOUNT:
            log.error("Could not determine human account. Set MURMUR_HUMAN_ACCOUNT env var.")
            sys.exit(1)

    NW_SA = f"normal-worker-sa@{PROJECT_ID}.iam.gserviceaccount.com"
    MAINT_SA = f"maintenance-sa@{PROJECT_ID}.iam.gserviceaccount.com"
    SCHED_SA = f"scheduler-sa@{PROJECT_ID}.iam.gserviceaccount.com"
    ATTACKER_SA = f"attacker-sa@{PROJECT_ID}.iam.gserviceaccount.com"

    log.info("=" * 60)
    log.info("MURMUR PHASE 3: ATTACK INJECTION ORCHESTRATOR")
    log.info("Mode: %s", "DRY-RUN" if dry_run else "LIVE")
    log.info("Project: %s, Account: %s", PROJECT_ID, HUMAN_ACCOUNT)
    log.info("Architecture: Execute-then-Observe (GCS hourly batching)")
    log.info("=" * 60)

    # Load baseline
    baseline_path = RESULTS_DIR / "baseline_snapshot.json"
    baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else {}
    if baseline:
        log.info("Baseline: %d events, avg normal residual: %s",
                 baseline.get("total_events", 0), baseline.get("avg_normal_residual", "?"))

    pre_event_count = get_event_count()

    # Load previous results if observe-only
    results_path = RESULTS_DIR / "phase3_results.json"
    if args.observe_only and results_path.exists():
        prev = json.loads(results_path.read_text())
        results = [AttackResult(**{k: v for k, v in a.items()
                                   if k in AttackResult.__dataclass_fields__})
                    for a in prev.get("attacks", prev if isinstance(prev, list) else [])]
        log.info("Loaded %d previous attack results", len(results))
    else:
        # Ringfencing
        ringfence_preflight(dry_run)

        # Pre-flight setup
        preflight_setup(dry_run)

        # Execute attacks
        attack_map = {
            "A": attack_a, "B": attack_b, "C": attack_c, "D": attack_d,
        }
        attacks_to_run = [args.attack] if args.attack else ["A", "B", "C", "D"]

        results = []
        for key in attacks_to_run:
            result = attack_map[key](dry_run)
            results.append(result)
            # Save intermediate
            with open(results_path, "w") as f:
                json.dump({"attacks": [dataclasses.asdict(r) for r in results],
                           "baseline": baseline, "phase": "executing"}, f, indent=2, default=str)
            log.info("Attack %s: %s", key, result.status)

    # Observation phase
    new_events = wait_and_observe(pre_event_count, dry_run)

    # Capture results for each attack
    if not dry_run:
        for r in results:
            if r.status == "SUCCESS":
                capture_attack_results(r)

    # Cleanup
    if not args.skip_cleanup and not args.observe_only:
        cleanup(dry_run)

    # Post-flight
    warnings = ringfence_postflight(dry_run)

    # Report
    report = generate_report(results, baseline, warnings)
    (RESULTS_DIR / "phase3_report.md").write_text(report)
    log.info("Report: %s", RESULTS_DIR / "phase3_report.md")

    # Final results
    final = {
        "started_at": results[0].started_at if results else "",
        "completed_at": datetime.now(UTC).isoformat(),
        "attacks": [dataclasses.asdict(r) for r in results],
        "baseline": baseline,
        "new_events_ingested": new_events,
        "postflight_warnings": warnings,
        "phase": "complete",
    }
    with open(results_path, "w") as f:
        json.dump(final, f, indent=2, default=str)
    log.info("Results: %s", results_path)

    # Summary
    log.info("=" * 60)
    log.info("ORCHESTRATOR COMPLETE")
    for r in results:
        max_rr = max((w.get("residual_risk", 0) for w in r.windows), default=0)
        tiers = [w.get("tier", "?") for w in r.windows] or ["no windows"]
        log.info("  %s: %s | max_residual=%.4f | tiers=%s",
                 r.attack_id, r.status, max_rr, tiers)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
