-- Murmur DuckDB Schema
-- All tables defined upfront; populated incrementally across sprints.

-- ============================================================
-- INGESTION LAYER (Sprint 0)
-- ============================================================

CREATE TABLE IF NOT EXISTS events (
    event_id            VARCHAR PRIMARY KEY,
    ts                  TIMESTAMP NOT NULL,
    window_start        TIMESTAMP NOT NULL,
    actor_id            VARCHAR NOT NULL,
    actor_type          VARCHAR NOT NULL,      -- HUMAN | SERVICE_ACCOUNT | UNKNOWN
    actor_subtype       VARCHAR,               -- AGENT | HUMAN | SERVICE | PIPELINE (untrusted)
    orchestrator_id     VARCHAR,
    trigger_ref         VARCHAR,
    provenance_level    VARCHAR NOT NULL DEFAULT 'NONE',  -- NONE | WEAK | STRONG
    provenance_source   VARCHAR NOT NULL DEFAULT 'UNKNOWN',
    action_type         VARCHAR NOT NULL,      -- 13 action types
    action_subtype      VARCHAR,               -- normalized methodName
    tool_name           VARCHAR,
    tool_parameters_hash VARCHAR,
    model_id            VARCHAR,
    target_id           VARCHAR NOT NULL,
    target_type         VARCHAR NOT NULL,
    target_zone         VARCHAR NOT NULL,      -- CONTROL | IDENTITY | SECRET | DATA | COMPUTE | EXFIL_RISK
    correlation_confidence FLOAT DEFAULT 0.0,    -- 0.0-1.0 composite confidence for derived trigger_ref
    delegation_chain    VARCHAR DEFAULT '[]',   -- JSON array of delegation SA emails (from serviceAccountDelegationInfo)
    result              VARCHAR NOT NULL DEFAULT 'SUCCESS',
    project_id          VARCHAR,
    env                 VARCHAR DEFAULT 'sandbox',
    is_deploy           BOOLEAN DEFAULT FALSE,
    is_incident         BOOLEAN DEFAULT FALSE,
    is_infrastructure   BOOLEAN DEFAULT FALSE,  -- True for infra meta-logs (e.g. logging SA)
    risk_tags           VARCHAR DEFAULT '[]',   -- JSON array
    raw_ref             VARCHAR,
    coverage_flag       BOOLEAN DEFAULT TRUE
);

-- Tracks last-processed blob per source for incremental ingestion
CREATE TABLE IF NOT EXISTS ingest_checkpoints (
    source_id       VARCHAR PRIMARY KEY,
    last_blob_name  VARCHAR NOT NULL,
    last_fetched_ts TIMESTAMP NOT NULL
);

-- ============================================================
-- PROVENANCE LAYER (Sprint 1 scaffold, Sprint 3 full)
-- ============================================================

CREATE TABLE IF NOT EXISTS sanctioned_patterns (
    pattern_id          VARCHAR PRIMARY KEY,
    name                VARCHAR,
    description         VARCHAR,
    initiator_type      VARCHAR,               -- SCHEDULED | HUMAN_TRIGGERED | API_TRIGGERED
    expected_actors     VARCHAR,               -- JSON: SA prefixes or exact IDs
    expected_zones      VARCHAR,               -- JSON: ordered zone sequence
    expected_window     VARCHAR,               -- JSON: {days_of_week, hour_start, hour_end}
    expected_rate_min   FLOAT,
    expected_rate_max   FLOAT,
    expected_duration   INTEGER,               -- typical duration in minutes
    registered_by       VARCHAR,               -- 'operator' | 'auto_observed'
    confidence          FLOAT DEFAULT 1.0,
    registered_ts       TIMESTAMP,
    last_matched_ts     TIMESTAMP,
    match_count         INTEGER DEFAULT 0,
    active              BOOLEAN DEFAULT TRUE
);

-- ============================================================
-- WORLD MODEL LAYER (Sprint 1)
-- ============================================================

CREATE TABLE IF NOT EXISTS actor_windows (
    window_start        TIMESTAMP NOT NULL,
    actor_id            VARCHAR NOT NULL,
    event_count         INTEGER DEFAULT 0,
    action_types        VARCHAR,               -- JSON array of action types seen
    zone_sequence       VARCHAR,               -- JSON array of zones visited in order
    target_ids          VARCHAR,               -- JSON array of unique targets
    burst_per_min       FLOAT,
    breadth_entropy     FLOAT,
    provenance_level    VARCHAR DEFAULT 'NONE',
    pattern_match_score FLOAT DEFAULT 0.0,
    matched_pattern_id  VARCHAR,
    trigger_chain_resolved BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (window_start, actor_id)
);

CREATE TABLE IF NOT EXISTS zone_flux_windows (
    window_start        TIMESTAMP PRIMARY KEY,
    flux_matrix         VARCHAR,               -- JSON: 6x6 matrix as nested list
    net_currents        VARCHAR,               -- JSON: per-pair net currents
    sigma_coarse        FLOAT,
    bridge_count        INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS edges_window (
    window_start        TIMESTAMP NOT NULL,
    actor_id            VARCHAR NOT NULL,
    source_zone         VARCHAR NOT NULL,
    target_zone         VARCHAR NOT NULL,
    target_id           VARCHAR NOT NULL,
    edge_count          INTEGER DEFAULT 1,
    first_seen          TIMESTAMP,
    is_new_30d          BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (window_start, actor_id, source_zone, target_zone, target_id)
);

-- ============================================================
-- SCORING LAYER (Sprint 1 basic, Sprint 3 full)
-- ============================================================

CREATE TABLE IF NOT EXISTS risk_scores (
    window_start        TIMESTAMP NOT NULL,
    actor_id            VARCHAR NOT NULL,
    inv_score           FLOAT DEFAULT 0.0,
    sigma_coarse        FLOAT DEFAULT 0.0,
    novelty_score       FLOAT DEFAULT 0.0,
    bridge_new          FLOAT DEFAULT 0.0,
    delta_f             FLOAT DEFAULT 0.0,
    burst_per_min       FLOAT DEFAULT 0.0,
    breadth_entropy     FLOAT DEFAULT 0.0,
    closure_ratio       FLOAT DEFAULT 1.0,
    orphaned_privilege  FLOAT DEFAULT 0.0,
    fusion_raw          FLOAT DEFAULT 0.0,
    residual_risk       FLOAT DEFAULT 0.0,
    fired_invariants    VARCHAR DEFAULT '[]',  -- JSON array of invariant IDs
    explanation         VARCHAR,               -- human-readable scoring explanation
    PRIMARY KEY (window_start, actor_id)
);

-- ============================================================
-- CLOSURE LAYER (Sprint 3)
-- ============================================================

CREATE TABLE IF NOT EXISTS closure_state (
    resource_id         VARCHAR PRIMARY KEY,
    resource_type       VARCHAR NOT NULL,      -- SA_KEY | IAM_POLICY | IMPERSONATION | SECRET
    opening_event_id    VARCHAR NOT NULL,
    opening_ts          TIMESTAMP NOT NULL,
    opening_actor_id    VARCHAR NOT NULL,
    expected_close_type VARCHAR NOT NULL,
    window_hours        INTEGER NOT NULL,
    closing_event_id    VARCHAR,
    closing_ts          TIMESTAMP,
    is_closed           BOOLEAN DEFAULT FALSE,
    sensitivity         FLOAT NOT NULL
);

CREATE TABLE IF NOT EXISTS opening_closing_pairs (
    pair_id             VARCHAR PRIMARY KEY,
    opening_action_type VARCHAR NOT NULL,
    closing_action_type VARCHAR NOT NULL,
    window_hours        INTEGER NOT NULL,
    tier                INTEGER NOT NULL DEFAULT 1  -- 1 = short-window, 2 = long-window
);

-- ============================================================
-- POLICY LAYER (Sprint 3)
-- ============================================================

CREATE TABLE IF NOT EXISTS policy_suggestions (
    suggestion_id       VARCHAR PRIMARY KEY,
    window_start        TIMESTAMP NOT NULL,
    actor_id            VARCHAR NOT NULL,
    risk_energy         FLOAT NOT NULL,
    alert_level         VARCHAR NOT NULL,      -- ALERT_HIGH | ALERT_MED | WATCH | NORMAL
    suggested_action    VARCHAR NOT NULL,
    explanation         VARCHAR,
    created_ts          TIMESTAMP NOT NULL,
    acknowledged        BOOLEAN DEFAULT FALSE
);

-- ============================================================
-- AUTO-OBSERVED PATTERNS (Post-MVP, table defined now)
-- ============================================================

CREATE TABLE IF NOT EXISTS candidate_patterns (
    candidate_id        VARCHAR PRIMARY KEY,
    cluster_signature   VARCHAR,               -- JSON: cluster characteristics
    structural_regularity FLOAT,
    causal_drift        FLOAT,
    peer_corroboration  FLOAT,
    deployment_anchored BOOLEAN DEFAULT FALSE,
    composite_score     FLOAT,
    tier                VARCHAR,               -- OBSERVED_HIGH | OBSERVED_MEDIUM | OBSERVED_LOW
    run_count           INTEGER DEFAULT 0,
    first_seen          TIMESTAMP,
    last_seen           TIMESTAMP,
    promoted_to         VARCHAR,               -- pattern_id if promoted, NULL otherwise
    rejected            BOOLEAN DEFAULT FALSE
);
