"""Closure signal ablation study.

Reads scored pairs from risk_scores, recomputes fusion_raw with modified
weights to isolate the independent contribution of closure signals
(closure_gap, orphaned_priv).

Two ablation modes:
- zero: set closure weights to 0, renormalize remaining to sum=1.0
- redistribute: redistribute closure weight proportionally across remaining signals

Note: for proportional weight distributions, zero and redistribute are
algebraically equivalent (both produce the same final weights). They would
differ only if the non-zeroed weights were non-proportional to each other.

Read-only from production DB. All recomputation is in-memory.
"""

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass

import duckdb

from src.score.fusion import (
    FUSION_WEIGHTS,
    NORM_BOUNDS,
    SIGMA_SIGMOID_K,
    SIGMA_SIGMOID_X0,
    normalize,
    sigmoid_normalize,
)

# Tier thresholds (from config/settings.py defaults, on [0,1] scale)
TIER_THRESHOLDS = {"HIGH": 0.8, "MEDIUM": 0.5}
# WATCH threshold: anything > 0 that isn't MEDIUM or HIGH
WATCH_FLOOR = 0.005


def extract_role(actor_id: str) -> str:
    """Extract role from synthetic actor_id (e.g., 'worker-sa-3@...' → 'worker')."""
    try:
        prefix = actor_id.split("-sa-")[0]
        if prefix and prefix != actor_id:
            return prefix
    except (IndexError, AttributeError):
        pass
    return "unknown"


@dataclass
class RoleBasedStats:
    """Per-role aggregated ablation metrics."""
    role: str
    count: int
    baseline_mean: float
    baseline_stdev: float
    zero_mean: float
    zero_stdev: float
    redist_mean: float
    redist_stdev: float
    gap_baseline: float
    gap_zero: float
    gap_redist: float
    closure_gap_active_pct: float
    orphaned_priv_active_pct: float
    tier_changes_zero: int
    tier_changes_redist: int


def assign_tier(fusion_raw: float) -> str:
    """Assign tier from fusion_raw score."""
    if fusion_raw >= TIER_THRESHOLDS["HIGH"]:
        return "HIGH"
    if fusion_raw >= TIER_THRESHOLDS["MEDIUM"]:
        return "MEDIUM"
    if fusion_raw >= WATCH_FLOOR:
        return "WATCH"
    return "NORMAL"


@dataclass
class ScoredRow:
    """One scored (window, actor) pair with raw signal values."""
    window_start: str
    actor_id: str
    inv_score: float
    inv_count: float
    sigma_coarse: float
    novelty_score: float
    bridge_new: float
    delta_f: float
    burst_per_min: float
    breadth_entropy: float
    closure_ratio: float
    orphaned_privilege: float
    fusion_raw: float
    residual_risk: float
    explanation: str

    def normalize_signals(self) -> dict[str, float]:
        """Normalize raw signals to [0,1] using the same logic as fusion.py."""
        return {
            "inv_score": normalize(self.inv_score, NORM_BOUNDS["inv_score"]),
            "inv_count": normalize(self.inv_count, NORM_BOUNDS["inv_count"]),
            "sigma_coarse": sigmoid_normalize(self.sigma_coarse, SIGMA_SIGMOID_K, SIGMA_SIGMOID_X0),
            "novelty_score": normalize(self.novelty_score, NORM_BOUNDS["novelty_score"]),
            "bridge_new": normalize(self.bridge_new, NORM_BOUNDS["bridge_new"]),
            "delta_f": normalize(self.delta_f, NORM_BOUNDS["delta_f"]),
            "closure_gap": 1.0 - self.closure_ratio,  # invert: high ratio = low risk
            "orphaned_priv": normalize(self.orphaned_privilege, NORM_BOUNDS["orphaned_priv"]),
            "burst_per_min": normalize(self.burst_per_min, NORM_BOUNDS["burst_per_min"]),
            "breadth_entropy": normalize(self.breadth_entropy, NORM_BOUNDS["breadth_entropy"]),
        }


def capture_baseline(db_path: str) -> list[ScoredRow]:
    """Read all scored pairs from risk_scores. Read-only."""
    conn = duckdb.connect(db_path, read_only=True)
    try:
        rows = conn.execute(
            """SELECT window_start, actor_id, inv_score, inv_count,
                      sigma_coarse, novelty_score, bridge_new, delta_f,
                      burst_per_min, breadth_entropy, closure_ratio,
                      orphaned_privilege, fusion_raw, residual_risk, explanation
               FROM risk_scores
               ORDER BY fusion_raw DESC"""
        ).fetchall()
        return [ScoredRow(*r) for r in rows]
    finally:
        conn.close()


def reweight(weights: dict[str, float], zeroed: list[str], mode: str) -> dict[str, float]:
    """Compute new weights with specified signals zeroed.

    mode="zero": zero the signals, renormalize remaining to sum=1.0
    mode="redistribute": redistribute zeroed weight proportionally
    """
    new_w = dict(weights)
    removed_weight = sum(new_w[k] for k in zeroed)

    for k in zeroed:
        new_w[k] = 0.0

    remaining_sum = sum(new_w[k] for k in new_w if k not in zeroed)

    if remaining_sum == 0:
        return new_w

    if mode == "zero":
        # Renormalize remaining to sum=1.0
        scale = 1.0 / remaining_sum
        for k in new_w:
            if k not in zeroed:
                new_w[k] *= scale
    elif mode == "redistribute":
        # Distribute removed weight proportionally
        for k in new_w:
            if k not in zeroed:
                new_w[k] += removed_weight * (new_w[k] / remaining_sum)

    return new_w


def compute_fusion_with_weights(signals: dict[str, float], weights: dict[str, float]) -> float:
    """Weighted sum of normalized signals."""
    return sum(weights[k] * signals[k] for k in weights)


@dataclass
class AblationResult:
    """Result of one ablation comparison."""
    mode: str
    weights: dict[str, float]
    rows: list[tuple[ScoredRow, float, str, str]]  # (row, new_fusion, old_tier, new_tier)
    deltas: list[float]

    @property
    def tier_migrations(self) -> dict[tuple[str, str], int]:
        """Count tier transitions: {(old_tier, new_tier): count}."""
        migrations: dict[tuple[str, str], int] = {}
        for _, _, old_t, new_t in self.rows:
            key = (old_t, new_t)
            migrations[key] = migrations.get(key, 0) + 1
        return migrations

    @property
    def stats(self) -> dict[str, float]:
        """Statistical summary of absolute fusion deltas."""
        abs_deltas = [abs(d) for d in self.deltas]
        return {
            "mean": statistics.mean(abs_deltas),
            "median": statistics.median(abs_deltas),
            "stdev": statistics.stdev(abs_deltas) if len(abs_deltas) > 1 else 0.0,
            "max": max(abs_deltas),
        }


def run_ablation(
    baseline: list[ScoredRow],
    zeroed_signals: list[str],
    mode: str,
) -> AblationResult:
    """Recompute fusion for all rows with modified weights."""
    new_weights = reweight(FUSION_WEIGHTS, zeroed_signals, mode)

    rows = []
    deltas = []
    for row in baseline:
        signals = row.normalize_signals()
        new_fusion = compute_fusion_with_weights(signals, new_weights)
        old_tier = assign_tier(row.fusion_raw)
        new_tier = assign_tier(new_fusion)
        delta = new_fusion - row.fusion_raw
        rows.append((row, new_fusion, old_tier, new_tier))
        deltas.append(delta)

    return AblationResult(mode=mode, weights=new_weights, rows=rows, deltas=deltas)


def compute_role_stats(
    baseline: list[ScoredRow],
    zero_result: AblationResult,
    redist_result: AblationResult,
) -> dict[str, RoleBasedStats]:
    """Group ablation results by role and compute per-role metrics."""
    # Index ablation rows by (window_start, actor_id) for lookup
    zero_by_key: dict[tuple[str, str], tuple] = {}
    for row, new_f, old_t, new_t in zero_result.rows:
        zero_by_key[(row.window_start, row.actor_id)] = (new_f, old_t, new_t)

    redist_by_key: dict[tuple[str, str], tuple] = {}
    for row, new_f, old_t, new_t in redist_result.rows:
        redist_by_key[(row.window_start, row.actor_id)] = (new_f, old_t, new_t)

    # Group baseline rows by role
    groups: dict[str, list[int]] = defaultdict(list)
    for i, row in enumerate(baseline):
        role = extract_role(row.actor_id)
        groups[role].append(i)

    def _safe_stdev(vals: list[float]) -> float:
        return statistics.stdev(vals) if len(vals) > 1 else 0.0

    # Compute worker mean for gap metric
    worker_indices = groups.get("worker", [])
    worker_baseline_mean = (
        statistics.mean([baseline[i].fusion_raw for i in worker_indices])
        if worker_indices else 0.0
    )
    worker_zero_mean = (
        statistics.mean([zero_by_key[(baseline[i].window_start, baseline[i].actor_id)][0] for i in worker_indices])
        if worker_indices else 0.0
    )
    worker_redist_mean = (
        statistics.mean([redist_by_key[(baseline[i].window_start, baseline[i].actor_id)][0] for i in worker_indices])
        if worker_indices else 0.0
    )

    result = {}
    for role, indices in groups.items():
        rows = [baseline[i] for i in indices]
        b_fusions = [r.fusion_raw for r in rows]
        z_fusions = [zero_by_key[(r.window_start, r.actor_id)][0] for r in rows]
        r_fusions = [redist_by_key[(r.window_start, r.actor_id)][0] for r in rows]

        b_mean = statistics.mean(b_fusions)
        z_mean = statistics.mean(z_fusions)
        rd_mean = statistics.mean(r_fusions)

        # Gap = this_role_mean / worker_mean
        has_workers = bool(worker_indices) and worker_baseline_mean > 0
        gap_b = b_mean / worker_baseline_mean if has_workers else math.nan
        gap_z = z_mean / worker_zero_mean if has_workers and worker_zero_mean > 0 else math.nan
        gap_r = rd_mean / worker_redist_mean if has_workers and worker_redist_mean > 0 else math.nan

        # Closure activation
        cg_active = sum(1 for r in rows if (1.0 - r.closure_ratio) > 0.001)
        op_active = sum(1 for r in rows if r.orphaned_privilege > 0.001)
        n = len(rows)

        # Tier changes
        tc_zero = sum(
            1 for r in rows
            if zero_by_key[(r.window_start, r.actor_id)][1] != zero_by_key[(r.window_start, r.actor_id)][2]
        )
        tc_redist = sum(
            1 for r in rows
            if redist_by_key[(r.window_start, r.actor_id)][1] != redist_by_key[(r.window_start, r.actor_id)][2]
        )

        result[role] = RoleBasedStats(
            role=role,
            count=n,
            baseline_mean=b_mean,
            baseline_stdev=_safe_stdev(b_fusions),
            zero_mean=z_mean,
            zero_stdev=_safe_stdev(z_fusions),
            redist_mean=rd_mean,
            redist_stdev=_safe_stdev(r_fusions),
            gap_baseline=gap_b,
            gap_zero=gap_z,
            gap_redist=gap_r,
            closure_gap_active_pct=100.0 * cg_active / n,
            orphaned_priv_active_pct=100.0 * op_active / n,
            tier_changes_zero=tc_zero,
            tier_changes_redist=tc_redist,
        )

    return result


def format_tier_matrix(migrations: dict[tuple[str, str], int]) -> str:
    """Format tier migration as a markdown table."""
    tiers = ["NORMAL", "WATCH", "MEDIUM", "HIGH"]
    lines = ["| From \\ To | " + " | ".join(tiers) + " |"]
    lines.append("|" + "---|" * (len(tiers) + 1))
    for from_t in tiers:
        cells = []
        for to_t in tiers:
            count = migrations.get((from_t, to_t), 0)
            cells.append(str(count) if count > 0 else ".")
        lines.append(f"| {from_t} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def generate_report(
    baseline: list[ScoredRow],
    zero_result: AblationResult,
    redist_result: AblationResult,
    db_path: str,
    include_role_analysis: bool = True,
) -> str:
    """Generate markdown ablation report."""
    n = len(baseline)
    baseline_fusions = [r.fusion_raw for r in baseline]
    zero_fusions = [row[1] for row in zero_result.rows]
    redist_fusions = [row[1] for row in redist_result.rows]

    def _stdev(vals: list[float]) -> float:
        return statistics.stdev(vals) if len(vals) > 1 else 0.0

    # Top 10 most-affected pairs (by absolute delta, zero mode)
    affected = sorted(zero_result.rows, key=lambda x: abs(x[1] - x[0].fusion_raw), reverse=True)[:10]
    top10_lines = []
    for row, new_f, old_t, new_t in affected:
        delta = new_f - row.fusion_raw
        signals = row.normalize_signals()
        dominant = sorted(
            ((k, FUSION_WEIGHTS[k] * signals[k]) for k in FUSION_WEIGHTS if FUSION_WEIGHTS[k] > 0),
            key=lambda x: x[1], reverse=True,
        )[:3]
        dom_str = ", ".join(f"{k}={v:.3f}" for k, v in dominant)
        tier_change = f"{old_t}→{new_t}" if old_t != new_t else old_t
        top10_lines.append(
            f"| {str(row.window_start)[:16]} | {row.actor_id[:30]} | "
            f"{row.fusion_raw:.4f} | {new_f:.4f} | {delta:+.4f} | {tier_change} | {dom_str} |"
        )

    # Count actual tier changes
    zero_changes = sum(1 for _, _, o, n in zero_result.rows if o != n)
    redist_changes = sum(1 for _, _, o, n in redist_result.rows if o != n)

    # Closure signal stats
    closure_gaps = [1.0 - r.closure_ratio for r in baseline]
    orphaned_privs = [normalize(r.orphaned_privilege, NORM_BOUNDS["orphaned_priv"]) for r in baseline]
    nonzero_cg = sum(1 for v in closure_gaps if v > 0.001)
    nonzero_op = sum(1 for v in orphaned_privs if v > 0.001)

    # Build weight table rows
    weight_rows = []
    for k in FUSION_WEIGHTS:
        if FUSION_WEIGHTS[k] > 0 or k in ["closure_gap", "orphaned_priv"]:
            zw = zero_result.weights[k]
            rw = redist_result.weights[k]
            weight_rows.append(
                f"| {k} | {FUSION_WEIGHTS[k]:.2f} | {zw:.4f} | {rw:.4f} |"
            )
    weight_table = chr(10).join(weight_rows)

    # Build stats rows
    b_mean = statistics.mean(baseline_fusions)
    z_mean = statistics.mean(zero_fusions)
    r_mean = statistics.mean(redist_fusions)
    b_med = statistics.median(baseline_fusions)
    z_med = statistics.median(zero_fusions)
    r_med = statistics.median(redist_fusions)
    b_std = _stdev(baseline_fusions)
    z_std = _stdev(zero_fusions)
    r_std = _stdev(redist_fusions)
    b_max = max(baseline_fusions)
    z_max = max(zero_fusions)
    r_max = max(redist_fusions)

    # Derive conclusion
    z_delta = zero_result.stats["mean"]
    r_delta = redist_result.stats["mean"]
    ratio_denom = max(r_delta, 0.0001)
    if z_delta > r_delta * 1.1:
        conclusion = (
            "Closure signals appear to carry independent detection value."
        )
    elif abs(z_delta - r_delta) / ratio_denom < 0.1:
        conclusion = (
            "Closure signal impact is primarily from weight redistribution."
        )
    else:
        conclusion = (
            "Results are inconclusive "
            "— the difference between modes is marginal."
        )

    cg_pct = 100 * nonzero_cg / n
    op_pct = 100 * nonzero_op / n
    if nonzero_cg / n < 0.3:
        activity_note = (
            "Low activity means the signal hasn't had enough data to "
            "exercise closure patterns — the ablation may not be "
            "representative of steady-state behavior."
        )
    else:
        activity_note = (
            "Sufficient activity to draw conclusions from this ablation."
        )

    report = f"""# Closure Signal Ablation Report

**Date:** {__import__('datetime').date.today()}
**DB:** `{db_path}` — {n} scored pairs
**Closure signals:** closure_gap (weight 0.10), orphaned_priv (weight 0.05) — total 0.15

## Method

- **Baseline:** current FUSION_WEIGHTS (closure_gap=0.10, orphaned_priv=0.05)
- **Ablation A (zero):** closure weights set to 0, renormalized to sum=1.0
- **Ablation B (redistribute):** closure weight redistributed proportionally

Weights after ablation:

| Signal | Baseline | Zero | Redistribute |
|--------|----------|------|--------------|
{weight_table}

## Closure Signal Activity

Before interpreting ablation, check if closure signals are even active:

- **closure_gap > 0** in {nonzero_cg}/{n} pairs ({cg_pct:.1f}%)
- **orphaned_priv > 0** in {nonzero_op}/{n} pairs ({op_pct:.1f}%)
- **closure_gap mean:** {statistics.mean(closure_gaps):.4f}, \
max: {max(closure_gaps):.4f}
- **orphaned_priv mean:** {statistics.mean(orphaned_privs):.4f}, \
max: {max(orphaned_privs):.4f}

## Results

### Fusion score distribution

| Metric | Baseline | Zero | Redistribute |
|--------|----------|------|--------------|
| Mean   | {b_mean:.6f} | {z_mean:.6f} | {r_mean:.6f} |
| Median | {b_med:.6f} | {z_med:.6f} | {r_med:.6f} |
| Std    | {b_std:.6f} | {z_std:.6f} | {r_std:.6f} |
| Max    | {b_max:.6f} | {z_max:.6f} | {r_max:.6f} |

### Delta statistics (absolute)

| Metric | Zero | Redistribute |
|--------|------|--------------|
| Mean   | {z_delta:.6f} | {r_delta:.6f} |
| Median | {zero_result.stats['median']:.6f} | {redist_result.stats['median']:.6f} |
| Std    | {zero_result.stats['stdev']:.6f} | {redist_result.stats['stdev']:.6f} |
| Max    | {zero_result.stats['max']:.6f} | {redist_result.stats['max']:.6f} |

### Tier migrations

**Zero ablation** ({zero_changes} pairs changed tier):

{format_tier_matrix(zero_result.tier_migrations)}

**Redistribute ablation** ({redist_changes} pairs changed tier):

{format_tier_matrix(redist_result.tier_migrations)}

### Top 10 most-affected pairs (zero ablation)

| Window | Actor | Baseline | Ablated | Delta | Tier | Top 3 signals |
|--------|-------|----------|---------|-------|------|---------------|
{chr(10).join(top10_lines)}

## Interpretation

### Does closure add independent detection value?

If zero and redistribute produce **similar** deltas, the effect is purely
from weight redistribution. If zero produces **larger** deltas or different
tier migrations, closure carries independent signal.

- Zero ablation mean delta: {z_delta:.6f}
- Redistribute mean delta: {r_delta:.6f}
- Ratio: {z_delta / ratio_denom:.2f}x (>1 means closure has independent value)

### Tier stability

- Zero: {zero_changes}/{n} pairs changed tier ({100*zero_changes/n:.1f}%)
- Redistribute: {redist_changes}/{n} changed ({100*redist_changes/n:.1f}%)

## Conclusion

{conclusion}

**Signal activity:** closure_gap active in {cg_pct:.1f}% of pairs, \
orphaned_priv in {op_pct:.1f}%.
{activity_note}

**Recommendation:** Review the tier migration tables and top-10 affected
pairs to determine if the pairs that change tier are ones where closure
*should* matter (attack scenarios with unclosed privilege grants)
vs. ones where it's noise.
"""

    if include_role_analysis and n > 0:
        role_stats = compute_role_stats(baseline, zero_result, redist_result)
        sorted_roles = sorted(role_stats.keys(), key=lambda r: role_stats[r].baseline_mean, reverse=True)

        # Per-role fusion table
        role_rows = []
        for role in sorted_roles:
            s = role_stats[role]
            role_rows.append(
                f"| {role} | {s.count} | {s.baseline_mean:.4f} | "
                f"{s.zero_mean:.4f} | {s.redist_mean:.4f} | "
                f"{s.baseline_stdev:.4f} |"
            )

        # Gap table (attacker vs worker)
        atk = role_stats.get("attacker")
        gap_rows = ""
        if atk and not math.isnan(atk.gap_baseline):
            gap_b_pct = (atk.gap_baseline - 1.0) * 100
            gap_z_pct = (atk.gap_zero - 1.0) * 100
            gap_r_pct = (atk.gap_redist - 1.0) * 100
            delta_z = gap_z_pct - gap_b_pct
            delta_r = gap_r_pct - gap_b_pct
            gap_rows = f"""| Baseline | {atk.gap_baseline:.3f} ({gap_b_pct:+.1f}%) | — | — |
| Zero ablation | {atk.gap_zero:.3f} ({gap_z_pct:+.1f}%) | {delta_z:+.1f}pp | {100*delta_z/gap_b_pct:.1f}% |
| Redistribute | {atk.gap_redist:.3f} ({gap_r_pct:+.1f}%) | {delta_r:+.1f}pp | {100*delta_r/gap_b_pct:.1f}% |"""
        else:
            gap_rows = "No attacker+worker roles found — gap metric unavailable."

        # Activation by role table
        act_rows = []
        for role in sorted_roles:
            s = role_stats[role]
            act_rows.append(
                f"| {role} | {s.count} | {s.closure_gap_active_pct:.1f}% | "
                f"{s.orphaned_priv_active_pct:.1f}% |"
            )

        # Tier stability by role
        tier_rows = []
        for role in sorted_roles:
            s = role_stats[role]
            pct = 100.0 * s.tier_changes_zero / s.count if s.count > 0 else 0.0
            tier_rows.append(
                f"| {role} | {s.count} | {s.tier_changes_zero} | {pct:.1f}% |"
            )

        report += f"""
## Role-Based Analysis

### Fusion score by role

| Role | Count | Baseline Mean | Zero Mean | Redist Mean | Baseline Std |
|------|-------|---------------|-----------|-------------|--------------|
{chr(10).join(role_rows)}

### Attacker vs Worker Gap

Gap = attacker_mean / worker_mean. A gap of 1.70 means attackers average 70% higher fusion scores.

| Scenario | Gap (ratio) | Change from Baseline | % of Gap |
|----------|-------------|----------------------|----------|
{gap_rows}

### Closure Signal Activation by Role

| Role | Count | Closure Gap Active | Orphaned Priv Active |
|------|-------|--------------------|----------------------|
{chr(10).join(act_rows)}

### Tier Stability by Role (Zero Ablation)

| Role | Count | Tier Changes | % Changed |
|------|-------|--------------|-----------|
{chr(10).join(tier_rows)}
"""

    return report
