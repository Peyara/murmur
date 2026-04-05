# Phase 3: Live Attack Injection — Operational Plan

> This document is the single source of truth for the attack injection session.
> Every command, every safeguard, every expected outcome is specified here.
> The orchestrator script (`scripts/attack_orchestrator.py`) implements this plan exactly.

**Date planned:** 2026-04-03
**Author:** Shamreen + Claude (R&D collaboration)
**Status:** DRAFT — pending sign-off before execution

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [What We're Validating](#2-what-were-validating)
3. [Ringfencing Protocol](#3-ringfencing-protocol)
4. [Pre-Flight Setup](#4-pre-flight-setup)
5. [Attack A: Smash and Grab](#5-attack-a-smash-and-grab)
6. [Attack B: Credential Theft](#6-attack-b-credential-theft)
7. [Attack C: Slow Ratchet](#7-attack-c-slow-ratchet)
8. [Attack D: Insider Lateral Move](#8-attack-d-insider-lateral-move)
9. [Observation Methodology](#9-observation-methodology)
10. [Cleanup Protocol](#10-cleanup-protocol)
11. [Timeline](#11-timeline)
12. [Risk Matrix](#12-risk-matrix)
13. [Success Criteria](#13-success-criteria)
14. [Post-MVP: Parked Findings](#14-post-mvp-parked-findings)

---

## 1. Purpose

Murmur has been validated on **synthetic benchmarks** (6 scenarios, 395 tests) and **10 days of real benign data** (14,560 events, attack/benign ratio 2.7x). But synthetic benchmarks exercise different code paths than production — we discovered this the hard way in Session H when a column mapping bug was invisible to 388 tests but broke 77% of real-data scoring.

**This session closes the loop:** real adversarial GCP API calls → real Cloud Audit Logs → real GCS sink → real ingestion pipeline → real scoring. If the signals hold, we have MVP validation. If they don't, we learn exactly where the model breaks under adversarial conditions.

This is also about **detection latency** — how fast does an attack become visible? The live observation thread measures per-action propagation time from GCP API call to scored event in DuckDB.

---

## 2. What We're Validating

### Signals that can ONLY be validated with live attacks

| Signal | Why synthetic benchmarks can't test it | What live injection proves |
|--------|---------------------------------------|--------------------------|
| **sigma_coarse** | Needs real zone flux matrix with competing benign traffic | Attack zone flux is distinguishable from baseline |
| **delta_f** | Needs EMA built from 10 days of real windows | Sigma spike registers against real baseline |
| **INV_011** (delegation chain) | Needs 10+ days of real delegation history per SA | Stolen credential without delegation chain is detectable |
| **EXFIL_RISK zone** | Zero events in this zone — completely dark | First-ever events score correctly |
| **novelty_score** (30-day edges) | Synthetic benchmarks seed fake history | New edges register against real edge history |
| **Propagation latency** | Not applicable to in-memory benchmarks | Measures real GCS sink → detection time |

### The four attack archetypes

| Attack | Archetype | What it tests | Why this matters |
|--------|-----------|--------------|-----------------|
| **A: Smash and Grab** | Loud, fast, novel actor | Multi-signal activation (invariants + novelty + bridge + sigma) | Can Murmur detect an obvious, aggressive attacker? (Baseline capability) |
| **B: Credential Theft** | Subtle, mimics normal | INV_011 delegation chain anomaly | Can Murmur detect a stolen credential doing "normal" things? (Unique capability) |
| **C: Slow Ratchet** | Stealthy, multi-window | Score escalation across windows, sigma accumulation | Can Murmur detect slow, deliberate zone traversal toward exfiltration? |
| **D: Insider Lateral** | Cross-actor, impersonation | IAM + impersonation invariants, cross-actor correlation | Can Murmur detect privilege escalation via insider access grant? |

---

## 3. Ringfencing Protocol

### 3.1 Why ringfencing matters

The Murmur database (`murmur.duckdb`) contains 10 days of carefully accumulated data — 14,560 events, scored baselines, edge histories, EMA values. This is irreplaceable in the short term. The GCP sandbox has service accounts, IAM bindings, secrets, and scheduled jobs that took multiple sessions to configure.

**The goal:** make every action taken during this session reversible. If anything goes wrong at any point, we can restore to pre-session state within minutes.

### 3.2 Pre-attack ringfence (execute BEFORE any GCP action)

#### 3.2.1 Database backup

```bash
# THE most important step. Do not proceed without this.
cp murmur.duckdb murmur.duckdb.pre-attack-backup

# Verify backup is valid
python -c "
import duckdb
db = duckdb.connect('murmur.duckdb.pre-attack-backup', read_only=True)
count = db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
print(f'Backup valid: {count} events')
db.close()
"
```

**Restore command (if needed at any point):**
```bash
cp murmur.duckdb.pre-attack-backup murmur.duckdb
```

#### 3.2.2 GCP state snapshot

```bash
PROJECT="${PROJECT}"

# Snapshot all existing SA keys (so we know what's ours vs pre-existing)
mkdir -p data/attack_results/pre_flight

gcloud iam service-accounts keys list \
  --iam-account=normal-worker-sa@${PROJECT}.iam.gserviceaccount.com \
  --format=json > data/attack_results/pre_flight/keys_normal_worker.json

gcloud iam service-accounts keys list \
  --iam-account=scheduler-sa@${PROJECT}.iam.gserviceaccount.com \
  --format=json > data/attack_results/pre_flight/keys_scheduler.json

gcloud iam service-accounts keys list \
  --iam-account=maintenance-sa@${PROJECT}.iam.gserviceaccount.com \
  --format=json > data/attack_results/pre_flight/keys_maintenance.json

# Snapshot project-level IAM policy
gcloud projects get-iam-policy ${PROJECT} \
  --format=json > data/attack_results/pre_flight/iam_policy.json

# Snapshot secret-level IAM policies
for secret in secret_high secret_low secret_medium secret_maintenance; do
  gcloud secrets get-iam-policy ${secret} \
    --format=json > data/attack_results/pre_flight/iam_${secret}.json 2>/dev/null || true
done

# Record current service accounts
gcloud iam service-accounts list --format=json \
  > data/attack_results/pre_flight/service_accounts.json

# Record auth state
gcloud config get-value account > data/attack_results/pre_flight/auth_account.txt
```

#### 3.2.3 Verify auth and project

```bash
# Must be human identity, not a service account
ACCOUNT=$(gcloud config get-value account 2>/dev/null)
if [ "$ACCOUNT" != "${HUMAN_ACCOUNT}" ]; then
  echo "ABORT: Expected ${HUMAN_ACCOUNT}, got $ACCOUNT"
  exit 1
fi

# Must be the sandbox project
PROJ=$(gcloud config get-value project 2>/dev/null)
if [ "$PROJ" != "${PROJECT}" ]; then
  echo "ABORT: Expected sandbox project, got $PROJ"
  exit 1
fi
```

#### 3.2.4 Git state

```bash
# Must be on a feature branch, not main
BRANCH=$(git branch --show-current)
if [ "$BRANCH" = "main" ]; then
  echo "ABORT: Must be on feature branch, not main"
  exit 1
fi

# Working tree should be clean (or only have the orchestrator script)
git status --short
```

### 3.3 Per-attack ringfence

Every attack function wraps service account auth switches in **try/finally**:

```python
def attack_b_credential_theft(ctx):
    """Attack B: uses normal-worker-sa key directly."""
    try:
        # Switch to stolen credential
        run_gcloud("auth", "activate-service-account",
                   f"normal-worker-sa@{ctx.project}.iam.gserviceaccount.com",
                   f"--key-file={ctx.nw_key_path}")

        # ... attack actions ...

    finally:
        # ALWAYS restore human auth, even if attack fails
        run_gcloud("config", "set", "account", "${HUMAN_ACCOUNT}")
        # Verify restoration
        account = run_gcloud("config", "get-value", "account", capture=True)
        assert account.strip() == "${HUMAN_ACCOUNT}", \
            f"Auth restore failed! Got: {account}"
```

### 3.4 Post-attack ringfence (automated, after cleanup)

```bash
# 1. Auth restored?
ACCOUNT=$(gcloud config get-value account 2>/dev/null)
echo "Auth account: $ACCOUNT"  # Must be ${HUMAN_ACCOUNT}

# 2. No orphaned keys? Compare to pre-flight snapshot
for sa in normal-worker-sa scheduler-sa maintenance-sa; do
  gcloud iam service-accounts keys list \
    --iam-account=${sa}@${PROJECT}.iam.gserviceaccount.com \
    --format="value(name)" > /tmp/post_keys_${sa}.txt
  diff data/attack_results/pre_flight/keys_${sa}.json /tmp/post_keys_${sa}.txt || \
    echo "WARNING: Key diff detected for $sa"
done

# 3. attacker-sa deleted?
gcloud iam service-accounts describe \
  attacker-sa@${PROJECT}.iam.gserviceaccount.com 2>&1 | \
  grep -q "NOT_FOUND" && echo "attacker-sa: deleted (OK)" || \
  echo "WARNING: attacker-sa still exists"

# 4. No orphaned IAM bindings?
gcloud projects get-iam-policy ${PROJECT} --format=json \
  > /tmp/post_iam_policy.json
diff data/attack_results/pre_flight/iam_policy.json /tmp/post_iam_policy.json || \
  echo "WARNING: IAM policy diff detected"

# 5. Secret IAM restored?
gcloud secrets get-iam-policy secret_high --format=json \
  > /tmp/post_iam_secret_high.json
diff data/attack_results/pre_flight/iam_secret_high.json /tmp/post_iam_secret_high.json || \
  echo "WARNING: secret_high IAM diff detected"

# 6. Temp files cleaned?
ls /tmp/murmur-*.json 2>/dev/null && \
  echo "WARNING: temp key files still on disk" || \
  echo "Temp files: cleaned (OK)"

# 7. DB readable and larger than backup? (attack events added)
python -c "
import duckdb
db = duckdb.connect('murmur.duckdb', read_only=True)
count = db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
print(f'DB OK: {count} events')
db.close()
"

# 8. Exfil bucket cleaned?
gsutil ls gs://public-export-sandbox/ 2>&1 | grep -q "CommandException" || \
  gsutil ls gs://public-export-sandbox/ | wc -l
```

### 3.5 Emergency procedures

| Scenario | Action |
|----------|--------|
| Script crashes mid-attack | Check `gcloud config get-value account`. If SA, run `gcloud config set account ${HUMAN_ACCOUNT}`. Then run cleanup manually. |
| DB corrupted mid-ingest | `cp murmur.duckdb.pre-attack-backup murmur.duckdb` |
| Orphaned SA key can't be deleted via CLI | Go to GCP Console → IAM → Service Accounts → select SA → Keys tab → delete |
| Orphaned IAM binding | `gcloud projects remove-iam-policy-binding` or `gcloud secrets remove-iam-policy-binding` with exact member+role |
| attacker-sa not deleted | `gcloud iam service-accounts delete attacker-sa@${PROJECT}.iam.gserviceaccount.com` |
| Auth stuck on SA | `gcloud auth login` to re-authenticate as human |
| Need full sandbox rebuild | `bash scripts/setup-sandbox.sh` (idempotent) |

---

## 4. Pre-Flight Setup

**Actor:** ${HUMAN_ACCOUNT} (human identity)
**Purpose:** Create the attack instruments (SA keys, temp SA) before any attack window. These setup actions generate their own audit events, which we capture in the baseline observation — they are NOT part of any attack scenario.

### 4.1 Create key for normal-worker-sa (Attack B instrument)

```bash
gcloud iam service-accounts keys create /tmp/murmur-nw-key.json \
  --iam-account=normal-worker-sa@${PROJECT}.iam.gserviceaccount.com

# Record the key ID for cleanup
NW_KEY_ID=$(cat /tmp/murmur-nw-key.json | python -c "import json,sys; print(json.load(sys.stdin)['private_key_id'])")
echo "normal-worker-sa key: $NW_KEY_ID"
```

**Audit trail:** This generates an `iam.googleapis.com/CreateServiceAccountKey` event with actor=${HUMAN_ACCOUNT}. It will fire INV_002 for ${HUMAN_ACCOUNT}'s window. This is expected and documented.

### 4.2 Create attacker-sa (Attack C instrument)

```bash
# Create the SA
gcloud iam service-accounts create attacker-sa \
  --display-name="Phase 3 attacker SA — temporary, delete after session"

# Grant minimal permissions for the ratchet scenario
gcloud projects add-iam-policy-binding ${PROJECT} \
  --member=serviceAccount:attacker-sa@${PROJECT}.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor \
  --condition=None

gcloud projects add-iam-policy-binding ${PROJECT} \
  --member=serviceAccount:attacker-sa@${PROJECT}.iam.gserviceaccount.com \
  --role=roles/storage.objectViewer \
  --condition=None

gcloud projects add-iam-policy-binding ${PROJECT} \
  --member=serviceAccount:attacker-sa@${PROJECT}.iam.gserviceaccount.com \
  --role=roles/storage.objectCreator \
  --condition=None

# Create key
gcloud iam service-accounts keys create /tmp/murmur-attacker-key.json \
  --iam-account=attacker-sa@${PROJECT}.iam.gserviceaccount.com

ATTACKER_KEY_ID=$(cat /tmp/murmur-attacker-key.json | python -c "import json,sys; print(json.load(sys.stdin)['private_key_id'])")
echo "attacker-sa key: $ATTACKER_KEY_ID"
```

**Audit trail:** Creates `CreateServiceAccount`, `SetIamPolicy` (x3), `CreateServiceAccountKey` events. All attributed to ${HUMAN_ACCOUNT}. Captured in baseline, not attack.

### 4.3 Baseline data pull

```bash
# Pull latest GCS audit logs (covers ~24h since last sync)
python -m src.cli ingest --gcs-bucket murmur-audit-logs-sandbox

# Recompute world model + scoring
python -m src.cli window
python -m src.cli score
```

### 4.4 Baseline snapshot

Query DuckDB for the "before" state:

```sql
-- Tier distribution
SELECT
  CASE
    WHEN residual_risk >= 0.8 THEN 'HIGH'
    WHEN residual_risk >= 0.5 THEN 'MEDIUM'
    WHEN residual_risk >= 0.3 THEN 'WATCH'    -- Note: threshold is watch_threshold/10
    ELSE 'NORMAL'
  END as tier,
  COUNT(*) as count
FROM risk_scores
GROUP BY tier ORDER BY tier;

-- sigma_coarse recent values (EMA input)
SELECT window_start, sigma_coarse
FROM zone_flux_windows
ORDER BY window_start DESC LIMIT 20;

-- Per-actor window counts (for INV_011 baseline check)
SELECT actor_id, COUNT(*) as windows,
       AVG(burst_per_min) as avg_burst
FROM actor_windows
GROUP BY actor_id ORDER BY windows DESC;

-- Total event count
SELECT COUNT(*) as total_events FROM events;

-- Edge history for key actors
SELECT actor_id, COUNT(DISTINCT source_zone || '->' || target_zone) as edge_types
FROM edges_window
WHERE is_new_30d = FALSE
GROUP BY actor_id;

-- normal-worker-sa delegation chain ratio (INV_011 prerequisite)
SELECT
  COUNT(*) FILTER (WHERE delegation_chain IS NOT NULL
    AND delegation_chain != '[]' AND LENGTH(delegation_chain) > 2) as chained,
  COUNT(*) as total,
  ROUND(COUNT(*) FILTER (WHERE delegation_chain IS NOT NULL
    AND delegation_chain != '[]' AND LENGTH(delegation_chain) > 2)
    * 100.0 / COUNT(*), 1) as chain_pct
FROM events
WHERE actor_id LIKE '%normal-worker-sa%';
```

**This snapshot is saved to `data/attack_results/baseline_snapshot.json`.**

---

## 5. Attack A: Smash and Grab

### 5.1 Concept

A novel human actor (${HUMAN_ACCOUNT}) performs a rapid, aggressive multi-zone attack: creates a service account key, reads a secret, and exfiltrates data to a public bucket — all within a single 15-minute scoring window.

This is the **baseline detection test**. If Murmur can't detect this obvious, loud attack, nothing else matters. Every signal should activate: invariants fire, novelty is high (new edges to heavy zones), bridge_new spikes, sigma_coarse increases.

### 5.2 Why this attack is realistic

This mimics a compromised admin account performing rapid privilege escalation and data exfiltration. The attacker doesn't know how long they'll have access, so they move fast — grabbing credentials, reading secrets, and pulling data before detection. The speed is the signature: all zones hit in one burst.

### 5.3 Actor and identity

**Actor:** ${HUMAN_ACCOUNT} (human identity, already authenticated)
**Actor type:** HUMAN
**Novelty:** ${HUMAN_ACCOUNT} has ~22 historical windows, mostly setup activity. Creating SA keys and accessing secrets in a burst pattern is novel for this actor.

### 5.4 Commands

```bash
# Action 1: Create key for scheduler-sa (should never happen in normal ops)
# Zone: IDENTITY | Action: IAM_CREATE_KEY
gcloud iam service-accounts keys create /tmp/murmur-sched-key.json \
  --iam-account=scheduler-sa@${PROJECT}.iam.gserviceaccount.com

# Record key ID for cleanup
SCHED_KEY_ID=$(cat /tmp/murmur-sched-key.json | python -c \
  "import json,sys; print(json.load(sys.stdin)['private_key_id'])")

# Action 2: Access secret_high (first time for this actor on this target)
# Zone: SECRET | Action: SECRET_ACCESS
gcloud secrets versions access latest --secret=secret_high \
  --project=${PROJECT}

# Action 3: Exfiltrate to public bucket (EXFIL_RISK — first ever event in this zone)
# Zone: EXFIL_RISK | Action: GCS_WRITE
echo "smash-grab-exfil-$(date -u +%Y%m%dT%H%M%SZ)" | \
  gsutil cp - gs://public-export-sandbox/smash_grab_$(date +%s).txt
```

### 5.5 Expected detection

| Signal | Expected behavior | Why |
|--------|------------------|-----|
| **INV_002** | FIRES (severity 5) | SA key created |
| **INV_003** | FIRES (severity 5) | Novel actor creating key (${HUMAN_ACCOUNT} not in known_initiators as key creator) |
| **INV_006** | FIRES (severity 5) | ${HUMAN_ACCOUNT} hasn't accessed secret_high in 30 days |
| **INV_010** | FIRES (severity 5) | New edge to SECRET and EXFIL_RISK zones |
| **inv_score** | ~20 (4 invariants x severity 5) | Normalized to 1.0 (max bound = 5.0, clipped) → contribution: 0.35 |
| **novelty_score** | ~5.5+ (IDENTITY 1.5 + SECRET 2.0 + EXFIL_RISK 2.0) | All edges are new for this actor. Zone weights: heavy zones amplified. |
| **bridge_new** | 2-3 new zone pairs | IDENTITY→SECRET, SECRET→EXFIL_RISK are new zone transitions |
| **sigma_coarse** | Spike above baseline | Attack zone flux mixed with benign traffic in the same window |
| **delta_f** | Positive (current sigma > EMA) | Spike relative to 10-day baseline |
| **burst_per_min** | ~1.5 (3 actions in ~2 min) | Low normalized value (0.075). Note: this signal is inverted — see Parked Findings. |
| **breadth_entropy** | Moderate (~1.5) | 3 distinct targets across 3 zones |

**Expected tier:** HIGH or MEDIUM
**Expected residual_risk:** >= 2x normal window average (validation criterion)

### 5.6 What success looks like

Murmur flags this window as HIGH or MEDIUM with 4+ invariants fired, high novelty, and a clear sigma spike. This is the "can we detect an elephant in the room?" test.

### 5.7 What failure would mean

If this attack doesn't produce at least WATCH tier, something is fundamentally broken in the scoring pipeline on real data — either the parser isn't mapping the actions correctly, or the fusion weights are too conservative, or the invariant lookback queries aren't returning expected results.

---

## 6. Attack B: Credential Theft

### 6.1 Concept

Use normal-worker-sa's downloaded key to authenticate directly (bypassing the Cloud Scheduler → Cloud Run delegation chain) and perform the same actions the real worker does. The actions are benign. The provenance is wrong.

This is the **crown jewel test**. INV_011 was designed specifically for this scenario: an SA that historically operates through a delegation chain (Cloud Scheduler → Cloud Run → SA) suddenly acts without one. The actions look normal. The authentication path is anomalous.

### 6.2 Why this attack is realistic

Credential theft is the most common cloud attack vector. An attacker compromises a service account key (leaked in a repo, extracted from a compromised VM, etc.) and uses it directly. They know what the SA normally does (from reconnaissance) and mimic its behavior. The actions are identical to normal operations — the only tell is the missing delegation chain.

### 6.3 Why this is hard to detect

- Same actor (normal-worker-sa) doing the same things (read secret, read GCS)
- Same zones visited (SECRET, DATA)
- Same targets accessed
- No new edges (edges already exist in 30-day history)
- No invariants fire for the actions themselves

The ONLY signal is INV_011: the delegation chain is missing. If Murmur doesn't have INV_011, this attack is invisible.

### 6.4 INV_011 prerequisite check

INV_011 fires when:
1. Actor is a service account (contains `.iam.gserviceaccount.com`) ✓
2. Actor has >= 10 historical events ✓ (normal-worker-sa has ~577 windows)
3. Historical delegation chain ratio > 80% — **must verify from baseline snapshot**
4. Current window events have empty/missing delegation chain

The key question: does `gcloud auth activate-service-account --key-file` produce audit logs WITHOUT the `serviceAccountDelegationInfo` field? It should — there's no delegation happening, the SA is acting directly. But we should verify this from a real log entry.

### 6.5 Actor and identity

**Actor:** normal-worker-sa@${PROJECT}.iam.gserviceaccount.com
**Authentication:** Direct key-file auth (no delegation chain)
**Actor type:** SERVICE_ACCOUNT
**Novelty:** Low — this actor has extensive history. Same edges, same zones.

### 6.6 Commands

```bash
# Switch to stolen credential
gcloud auth activate-service-account \
  normal-worker-sa@${PROJECT}.iam.gserviceaccount.com \
  --key-file=/tmp/murmur-nw-key.json

# Mimic normal worker behavior:

# Action 1: Read secret (same as every 5-min worker cycle)
# Zone: SECRET | Action: SECRET_ACCESS
gcloud secrets versions access latest --secret=secret_high \
  --project=${PROJECT}

# Action 2: Read from input bucket (same as normal worker)
# Zone: DATA | Action: GCS_READ
gsutil cat gs://murmur-input-sandbox/telemetry_001.json > /dev/null

# Action 3: Write to output bucket (same as normal worker)
# Zone: DATA | Action: GCS_WRITE
echo "stolen-credential-output-$(date -u +%Y%m%dT%H%M%SZ)" | \
  gsutil cp - gs://murmur-output-sandbox/stolen_result.txt

# CRITICAL: restore human auth immediately
gcloud config set account ${HUMAN_ACCOUNT}
```

### 6.7 Expected detection

| Signal | Expected behavior | Why |
|--------|------------------|-----|
| **INV_011** | FIRES (severity 5) | SA acts without expected delegation chain |
| **INV_006** | Maybe NOT fire | normal-worker-sa accesses secret_high regularly — it's in 30-day history |
| **All other INVs** | Do NOT fire | Actions are completely normal for this actor |
| **inv_score** | 5 (INV_011 only) | Normalized to 1.0 → contribution: 0.35 |
| **novelty_score** | ~0 | No new edges — same actor, same zones, same targets |
| **bridge_new** | 0 | No new zone transitions |
| **sigma_coarse** | Minimal change | Same zone flux pattern as normal window |
| **delta_f** | ~0 | No sigma deviation from baseline |

**Expected tier:** WATCH (inv_score carries almost all the weight; novelty and physics are near-zero)
**Expected residual_risk:** Lower than Attack A, but should still exceed 2x normal average if INV_011 fires.

### 6.8 What success looks like

INV_011 fires. The window scores WATCH or higher. Murmur detects the credential theft despite the attacker perfectly mimicking normal behavior. The explanation specifically mentions "SA acts without expected delegation chain."

### 6.9 What failure would mean

If INV_011 doesn't fire, possible causes:
- **Delegation chain ratio < 80%:** normal-worker-sa's historical events don't have enough delegation chains (check baseline snapshot)
- **Delegation chain field not populated:** the parser might not be extracting `serviceAccountDelegationInfo` correctly for Cloud Scheduler-triggered events
- **gcloud CLI produces delegation info:** maybe direct gcloud use still populates some delegation field (would need to inspect the raw audit log)
- **< 10 historical events:** shouldn't be the case (577 windows), but verify

Each failure mode tells us something important about the system.

---

## 7. Attack C: Slow Ratchet

### 7.1 Concept

A novel service account (attacker-sa, created in pre-flight) performs a slow, deliberate zone traversal across 4 scoring windows over ~48 minutes: reconnaissance → expand access → staging → exfiltration. Each window alone looks mild. The trajectory is the threat.

### 7.2 Why this attack is realistic

Sophisticated attackers don't smash and grab. They move slowly through the kill chain: enumerate what's available, expand access gradually, stage data, then exfiltrate. Each step is individually innocuous — it's the progression that reveals intent. This is the attack pattern that evades per-event alerting systems.

### 7.3 Why this tests what benchmarks can't

The synthetic S04 scenario had 7 events manually spread across windows. But:
- It didn't compete with real benign traffic in the same windows
- It didn't have a real EMA baseline to deviate from
- sigma_coarse was computed on an isolated in-memory DB

Live injection puts these events alongside normal-worker-sa's every-5-minute cycle, maintenance-sa's hourly jobs, and all the system noise. The question is: does the signal survive the noise?

### 7.4 Actor and identity

**Actor:** attacker-sa@${PROJECT}.iam.gserviceaccount.com
**Authentication:** Direct key-file auth
**Actor type:** SERVICE_ACCOUNT
**Novelty:** Maximum — this actor has zero history. Every edge is new.

### 7.5 Commands

```bash
# Activate attacker credential
gcloud auth activate-service-account \
  attacker-sa@${PROJECT}.iam.gserviceaccount.com \
  --key-file=/tmp/murmur-attacker-key.json

# ─── WINDOW 1: Reconnaissance ───
# Action: Access unused secret (secret_medium has no access history)
# Zone: SECRET | Action: SECRET_ACCESS
gcloud secrets versions access latest --secret=secret_medium \
  --project=${PROJECT}

# ─── WAIT ~16 MINUTES (cross into next scoring window) ───

# ─── WINDOW 2: Expand Access ───
# Action: Access a different, more valuable secret + list bucket
# Zone: SECRET + DATA | Action: SECRET_ACCESS + GCS_LIST
gcloud secrets versions access latest --secret=secret_high \
  --project=${PROJECT}
gsutil ls gs://murmur-input-sandbox/

# ─── WAIT ~16 MINUTES ───

# ─── WINDOW 3: Staging ───
# Action: Read actual data files (preparing for exfil)
# Zone: DATA | Action: GCS_READ
gsutil cat gs://murmur-input-sandbox/telemetry_001.json > /dev/null
gsutil cat gs://murmur-input-sandbox/config_002.json > /dev/null

# ─── WAIT ~16 MINUTES ───

# ─── WINDOW 4: Exfiltration ───
# Action: Write to public bucket (EXFIL_RISK)
# Zone: EXFIL_RISK | Action: GCS_WRITE
echo "ratchet-exfil-$(date -u +%Y%m%dT%H%M%SZ)" | \
  gsutil cp - gs://public-export-sandbox/slow_ratchet_$(date +%s).txt

# Restore human auth
gcloud config set account ${HUMAN_ACCOUNT}
```

### 7.6 Expected detection (per window)

| Window | Actions | Expected INVs | Expected novelty | Expected tier |
|--------|---------|---------------|-----------------|---------------|
| **W1** | secret_medium access | INV_006 (new actor, new secret) | 2.0 (SECRET zone weight) | WATCH |
| **W2** | secret_high access + GCS list | INV_006 (new secret target) | 3.0 (SECRET + DATA) | WATCH |
| **W3** | GCS reads | None (just data reads) | 1.0-2.0 (DATA edges, may be new) | NORMAL or WATCH |
| **W4** | GCS write to public bucket | INV_010 (new EXFIL_RISK edge) | 2.0 (EXFIL_RISK weight) | WATCH or MEDIUM |

**sigma_coarse:** Should progressively increase as attacker-sa's activity diversifies the zone flux matrix across windows. Maximum spike expected in W4 when EXFIL_RISK activates.

**delta_f:** Should spike in W4 — sigma deviation from 10-day EMA baseline.

### 7.7 What success looks like

The score **escalates** across windows: W1 < W2 < W3 < W4 (or at least W4 is highest). Window 4 should be WATCH or MEDIUM. The live observation thread captures this progression in real-time, showing how the ratchet builds.

### 7.8 What failure would mean

If Window 4 scores NORMAL despite EXFIL_RISK, either:
- The EXFIL_RISK zone isn't being mapped correctly for `public-export-sandbox`
- The novelty weight isn't applied (check `_is_exfil_risk()` in parser.py)
- The fusion weights are too conservative for physics-only signals (no invariant in W3)

If scores don't escalate across windows, the system may be treating each window too independently — the cross-window accumulation hypothesis needs revision.

---

## 8. Attack D: Insider Lateral Move

### 8.1 Concept

A human admin (${HUMAN_ACCOUNT}) grants a service account (maintenance-sa) access to a resource it shouldn't touch (secret_high), then impersonates that SA to access it. This is a two-step lateral movement: privilege grant → exploitation.

### 8.2 Why this attack is realistic

Insider threats and compromised admin accounts often follow this pattern: use legitimate admin privileges to quietly expand a service account's access, then use that SA (which has less monitoring attention than human accounts) to access sensitive data. The SA becomes a proxy for the attacker.

### 8.3 Actor and identity

**Actor 1:** ${HUMAN_ACCOUNT} (human — performs the IAM grant and impersonation)
**Actor 2:** maintenance-sa (appears as impersonated identity in the access)
**Key interaction:** Both actors appear in the same scoring window, connected by impersonation.

### 8.4 Commands

```bash
# Action 1: Grant maintenance-sa access to secret_high
# (maintenance-sa normally only touches secret_maintenance)
# Zone: CONTROL | Action: IAM_SET_POLICY (on the secret resource)
gcloud secrets add-iam-policy-binding secret_high \
  --member=serviceAccount:maintenance-sa@${PROJECT}.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor \
  --project=${PROJECT}

# Action 2: Impersonate maintenance-sa to access the secret
# Zone: IDENTITY (impersonation) + SECRET (access)
# Action: IAM_IMPERSONATE + SECRET_ACCESS
gcloud secrets versions access latest --secret=secret_high \
  --impersonate-service-account=maintenance-sa@${PROJECT}.iam.gserviceaccount.com \
  --project=${PROJECT}
```

### 8.5 Expected detection

For **${HUMAN_ACCOUNT}'s window:**

| Signal | Expected behavior | Why |
|--------|------------------|-----|
| **INV_001** | FIRES (severity 5) | IAM policy change outside deploy window |
| **INV_004** | FIRES (severity 4) | Impersonation token generated |
| **INV_005** | May FIRE (severity 5) | Impersonation spike (if ${HUMAN_ACCOUNT} hasn't impersonated recently, baseline is 0 → any count fires) |
| **INV_007** | FIRES (severity 5) | Secret access + IAM change in same window |
| **inv_score** | 14-19 | 3-4 invariants × severity 4-5 |

For **maintenance-sa's window** (if the impersonated access creates events attributed to maintenance-sa):

| Signal | Expected behavior | Why |
|--------|------------------|-----|
| **INV_006** | FIRES (severity 5) | maintenance-sa hasn't accessed secret_high in 30 days (only accesses secret_maintenance) |
| **novelty_score** | 2.0+ | New edge to secret_high (SECRET zone, weight 2.0) |

**Expected tier:** MEDIUM (for ${HUMAN_ACCOUNT}), WATCH (for maintenance-sa)

### 8.6 Uncertainty: how does impersonation appear in audit logs?

When ${HUMAN_ACCOUNT} runs `--impersonate-service-account=maintenance-sa`, GCP generates:
1. A `GenerateAccessToken` event (actor=${HUMAN_ACCOUNT}, target=maintenance-sa) → IDENTITY zone
2. A `AccessSecretVersion` event (actor=maintenance-sa with delegation chain containing ${HUMAN_ACCOUNT}) → SECRET zone

The question is: does the second event get attributed to maintenance-sa or ${HUMAN_ACCOUNT}? This depends on how the audit log structures the `authenticationInfo` field. If maintenance-sa is the principal, INV_006 fires for maintenance-sa. If ${HUMAN_ACCOUNT} is the principal, INV_007 fires for ${HUMAN_ACCOUNT} (IAM + secret in same window).

**Either way, we get detection.** We just need to verify which actor gets credited.

### 8.7 What success looks like

The human actor's window scores MEDIUM with 3+ invariants. The IAM-secret co-occurrence (INV_007) is the strongest single signal — it directly captures the "grant then exploit" pattern.

### 8.8 What failure would mean

If INV_001 doesn't fire, check whether the secret-level IAM policy change (not project-level) maps to `IAM_SET_POLICY` in the parser. The parser matches `SetIamPolicy` from `secretmanager.googleapis.com` — this might not exist as a separate method, it might use `SetIamPolicy` on the resource manager path.

---

## 9. Observation Methodology

### 9.1 Three-layer observation

Each attack captures data at three layers:

**Layer 1 — Action Execution Log (main thread)**
Every gcloud command recorded with:
- Exact command string
- UTC timestamp (before execution)
- Exit code
- stdout (truncated to 500 chars)
- stderr
- Duration in seconds

**Layer 2 — Live Propagation Timeline (observer thread)**
Runs in parallel with attack execution:
- Polls GCS + ingests every 60 seconds during the attack
- After each poll: counts new events since attack start
- Matches new events to attack actions by: timestamp (within 5s), actor_id, action_type
- Records per-action propagation latency: `event_appeared_ts - action_executed_ts`
- For Attack C: captures intermediate window scores as each window's events land

**Layer 3 — Full Scoring Snapshot (after attack completes)**
After final propagation poll confirms all events landed:
- Run full `window` + `score` pipeline
- Query all affected (window_start, actor_id) pairs
- For each: capture all 7 signal values (raw + normalized + weighted contribution), fired invariants, explanation, tier
- Compare to baseline snapshot: tier distribution change, sigma delta

### 9.2 Per-action event matching

The observer matches GCP events to orchestrated actions using:

```sql
SELECT event_id, ts, action_type, target_id, actor_id, delegation_chain
FROM events
WHERE ts >= ? AND ts <= ?          -- within 30s of action timestamp
  AND actor_id = ?                  -- matches attack actor
  AND action_type = ?               -- matches expected action type
ORDER BY ts
```

This allows us to compute exact propagation latency per action and verify the parser mapped the event correctly.

### 9.3 What the observation data enables

After the session, we can answer:
- **Detection latency:** How fast can Murmur detect each attack type? (propagation + scoring time)
- **Signal decomposition:** Which signals drove the score for each attack? Were there surprises?
- **Noise floor:** How much did benign activity in the same window affect scoring?
- **Cross-window dynamics:** For Attack C, how does the score build across windows?
- **False positive check:** Did any previously-NORMAL benign windows flip to WATCH or higher?

---

## 10. Cleanup Protocol

Cleanup runs automatically after all attacks complete. Each step has a verification check.

### 10.1 Delete SA keys created during session

```bash
# normal-worker-sa key (Attack B instrument)
gcloud iam service-accounts keys delete ${NW_KEY_ID} \
  --iam-account=normal-worker-sa@${PROJECT}.iam.gserviceaccount.com \
  --quiet

# scheduler-sa key (Attack A artifact)
gcloud iam service-accounts keys delete ${SCHED_KEY_ID} \
  --iam-account=scheduler-sa@${PROJECT}.iam.gserviceaccount.com \
  --quiet

# attacker-sa key (Attack C instrument — delete before deleting SA)
gcloud iam service-accounts keys delete ${ATTACKER_KEY_ID} \
  --iam-account=attacker-sa@${PROJECT}.iam.gserviceaccount.com \
  --quiet
```

### 10.2 Revoke IAM bindings

```bash
# Attack D: maintenance-sa access to secret_high
gcloud secrets remove-iam-policy-binding secret_high \
  --member=serviceAccount:maintenance-sa@${PROJECT}.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor \
  --project=${PROJECT} \
  --quiet

# Pre-flight: attacker-sa project-level bindings
gcloud projects remove-iam-policy-binding ${PROJECT} \
  --member=serviceAccount:attacker-sa@${PROJECT}.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor \
  --quiet

gcloud projects remove-iam-policy-binding ${PROJECT} \
  --member=serviceAccount:attacker-sa@${PROJECT}.iam.gserviceaccount.com \
  --role=roles/storage.objectViewer \
  --quiet

gcloud projects remove-iam-policy-binding ${PROJECT} \
  --member=serviceAccount:attacker-sa@${PROJECT}.iam.gserviceaccount.com \
  --role=roles/storage.objectCreator \
  --quiet
```

### 10.3 Delete attacker-sa

```bash
gcloud iam service-accounts delete \
  attacker-sa@${PROJECT}.iam.gserviceaccount.com \
  --quiet
```

### 10.4 Clean up artifacts

```bash
# Exfil artifacts in public bucket
gsutil rm -f gs://public-export-sandbox/** 2>/dev/null || true

# Stolen credential output
gsutil rm -f gs://murmur-output-sandbox/stolen_result.txt 2>/dev/null || true

# Local key files
rm -f /tmp/murmur-nw-key.json
rm -f /tmp/murmur-attacker-key.json
rm -f /tmp/murmur-sched-key.json
```

### 10.5 Restore auth

```bash
gcloud config set account ${HUMAN_ACCOUNT}
```

### 10.6 Post-cleanup verification

Run the full post-attack ringfence check (Section 3.4). Any discrepancies are logged in the report as warnings.

---

## 11. Timeline

Total estimated duration: **~4 hours**

```
T+0:00   ┌─ RINGFENCING PRE-FLIGHT ─────────────────────────────────┐
         │ DB backup, GCP state snapshot, verify auth/project/branch │
         └──────────────────────────────────────────────────────────┘

T+0:10   ┌─ PRE-FLIGHT SETUP ──────────────────────────────────────┐
         │ Create NW key, create attacker-sa + permissions + key   ��
         └──────────────────────────────────────────────────────────┘

T+0:20   ┌─ BASELINE CAPTURE ──────────────────────────────────────┐
         │ GCS ingest → window → score → snapshot to JSON          │
         └──────────────────────────────────────────────────────────┘

T+0:30   ┌─ ATTACK A: SMASH AND GRAB ─────────────────────────────┐
         │ gcloud: create key → access secret → write to exfil     │
         │ Observer: polling GCS every 60s, matching events         │
         └──────────────────────────────────────────────────────────┘
T+0:35   Observe A: final ingest → window → score → capture results

T+0:50   ┌─ SETTLING (55 min) ────────────────────────────────────┐
         │ sigma_coarse EMA decay: ~4 windows → ~66% residual     │
         │ (~34% of Attack A's sigma spike has decayed)            │
         └──────────────────────────────────────────────────────────┘

T+1:45   ┌─ ATTACK B: CREDENTIAL THEFT ───────────────────────────┐
         │ Activate NW key → read secret → read GCS → write GCS   │
         │ Observer: polling, tracking delegation chain presence    │
         └──────────────────────────────────────────────────────────┘
T+1:50   Observe B: final ingest → window → score → capture results

T+2:05   ┌─ SETTLING (15 min) ────────────────────────────────────┐
         │ Brief settling before multi-window attack               │
         └──────────────────────────────────────────────────────────┘

T+2:20   ┌─ ATTACK C: SLOW RATCHET ───────────────────────────────┐
         │ Window 1: secret_medium access (reconnaissance)         │
         │ Observer: poll + ingest + score W1 when events land     │
T+2:36   │ Window 2: secret_high + list bucket (expand access)    │
         │ Observer: poll + ingest + score W2                      │
T+2:52   │ Window 3: read data files (staging)                    │
         │ Observer: poll + ingest + score W3                      │
T+3:08   │ Window 4: write to public bucket (exfiltration)        │
         │ Observer: poll + ingest + score W4                      │
         └──────────────────────────────────────────────────────────┘
T+3:20   Observe C: final full scoring pass → capture all 4 windows

T+3:30   ┌─ SETTLING (15 min) ────────────────────────────────────┐
         └──────────────────────────────────────────────────────────┘

T+3:45   ┌─ ATTACK D: INSIDER LATERAL MOVE ───────────────────────┐
         │ Grant maintenance-sa → impersonate → access secret      │
         │ Observer: polling, tracking both actors' events         │
         └──────────────────────────────────────────────────────────┘
T+3:50   Observe D: final ingest → window → score → capture results

T+4:00   ┌─ CLEANUP ──────────────────────────────────────────────┐
         │ Delete keys → revoke bindings → delete attacker-sa     │
         │ Clean exfil artifacts → restore auth → verify state    │
         └──────────────────────────────────────────────────────────┘

T+4:10   ┌─ POST-FLIGHT VERIFICATION ─────────────────────────────┐
         │ Diff GCP state vs pre-flight snapshot                   │
         │ Verify DB integrity                                     │
         └──────────────────────────────────────────────────────────┘

T+4:15   ┌─ REPORT GENERATION ─────────────────────────────────────┐
         │ JSON results → markdown report → execution log          │
         └──────────────────────────────────────────────────────────┘
```

### Sigma contamination between attacks

| Transition | Gap | EMA windows | Residual from previous |
|-----------|-----|-------------|----------------------|
| A → B | 55 min | ~4 windows | ~66% decayed (~34% of A's spike remains) |
| B → C | 15 min + C spans 48 min internally | ~1 window before C starts | ~90% remains, but B's sigma impact is small (same zones as benign) |
| C → D | 15 min | ~1 window | ~90% remains, but we capture pre-D baseline |

Each attack captures its own pre-attack sigma_coarse baseline, so the residual is measured, not hidden.

---

## 12. Risk Matrix

| Risk | Likelihood | Impact | Mitigation | Recovery |
|------|-----------|--------|------------|----------|
| DB corruption mid-ingest | Low | **Critical** | `murmur.duckdb.pre-attack-backup` exists | `cp backup original` — 2 second recovery |
| Orphaned SA key | Medium | High (security) | Script logs all key IDs; post-flight diff | Delete via GCP Console |
| Orphaned IAM binding | Medium | High (security) | Script logs all bindings; post-flight diff | `gcloud remove-iam-policy-binding` |
| Auth stuck on SA | Medium | Medium | try/finally on every auth switch | `gcloud config set account ${HUMAN_ACCOUNT}` |
| attacker-sa not deleted | Low | Medium | Post-flight verification check | `gcloud iam service-accounts delete` |
| Audit logs delayed >15 min | Medium | Low (delays run) | Polling with 15 min timeout; script continues | Wait and re-poll manually |
| gcloud auth token expires | Low | Low | gcloud auto-refreshes; SA keys don't expire | `gcloud auth login` |
| Attack doesn't generate expected events | Medium | Low (learning) | Pre-flight test call; document as finding | Investigate parser mapping |
| Pipeline scoring fails | Low | Medium | All 395 tests green pre-run | Debug; DB backup is intact |
| Script crashes mid-run | Low | Medium | All state logged; cleanup is idempotent | Run cleanup manually; restore DB if needed |

---

## 13. Success Criteria

From Sprint 1B Signal Validation Gate spec:

- [ ] **Attack A:** residual_risk >= 2x normal window average
- [ ] **Attack B:** INV_011 fires on credential theft
- [ ] **Attack C:** scores escalate across windows (W4 > W1)
- [ ] **Attack D:** 3+ invariants fire on lateral move
- [ ] **sigma_coarse:** measurable variance between attack and quiet windows
- [ ] **EXFIL_RISK:** zone activates correctly (first real events)
- [ ] **Zero false positives:** no previously-NORMAL benign windows flip to WATCH+
- [ ] **Propagation latency:** measured per action (informational, no threshold)

### Grading

| Grade | Criteria |
|-------|---------|
| **PASS** | All 4 attacks detected at WATCH+ tier, INV_011 fires, no false positives |
| **PARTIAL** | 3/4 attacks detected, or INV_011 doesn't fire but other signals compensate |
| **FAIL** | <3 attacks detected, or false positive regression on benign data |

**PASS = MVP signal validation complete. Proceed to Sprint 2 (UI + API).**
**PARTIAL = Investigate failures, fix, re-run affected attacks.**
**FAIL = Fundamental scoring issue. Debug before any further work.**

---

## 14. Post-MVP: Parked Findings

### 14.1 burst_per_min signal inversion

**Problem:** burst_per_min treats high burst rate as monotonically risky, but benign automated workers burst faster (2.67/min) than stealth attacks (0.30/min). Discrimination power: 1.1x (weakest signal).

**Proposed fix:** Replace raw burst with `burst_deviation` — a per-actor z-score measuring deviation from the actor's own historical baseline, with per-actor-type sensitivity:
- Agentic SA (scheduler-triggered): high sensitivity — tight baseline, any wobble matters
- Service SA (non-scheduled): medium sensitivity
- Human: low sensitivity — inherently noisy

**Why parked:** At 8% weight, fixing burst won't materially change attack detection results. The fix requires new per-actor state (EMA + std) and cold-start policy. Better to validate the core signals first, then refine.

**What to include in final report:** This finding, the proposed B+C approach, empirical data from Session H showing the inversion. Frame as "what Murmur will do next" — temporal activity profiling is a rich signal source for v2.

### 14.2 breadth_entropy anti-correlation

breadth_entropy has negative correlation with risk in some scenarios. May need inversion or removal. Investigate alongside burst_per_min.

### 14.3 Cross-window accumulation

Current scoring is per-window. The slow ratchet (Attack C) tests whether the per-window model is sufficient or whether we need explicit cross-window trajectory tracking. Results from this session will inform whether Sprint 2 needs a trajectory layer.

---

*Document version: 1.0 — 2026-04-03*
*To be updated with results after execution.*
