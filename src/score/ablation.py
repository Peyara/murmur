"""Closure signal ablation study.

Reads scored pairs from risk_scores, recomputes fusion_raw with modified
weights to isolate the independent contribution of closure signals
(closure_gap, orphaned_priv).

Two ablation modes:
- zero: set closure weights to 0, renormalize remaining to sum=1.0
- redistribute: redistribute closure weight proportionally across remaining signals

Read-only from production DB. All recomputation is in-memory.
"""

import math
import statistics
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

    report = f"""# Closure Signal Ablation Report

**Date:** {__import__('datetime').date.today()}
**DB:** `{db_path}` — {n} scored pairs
**Closure signals:** closure_gap (weight 0.10), orphaned_priv (weight 0.05) — total 0.15

## Method

- **Baseline:** current FUSION_WEIGHTS (closure_gap=0.10, orphaned_priv=0.05)
- **Ablation A (zero):** closure weights set to 0, remaining 8 signals renormalized to sum=1.0
- **Ablation B (redistribute):** closure weight (0.15) redistributed proportionally across remaining signals

Weights after ablation:

| Signal | Baseline | Zero | Redistribute |
|--------|----------|------|--------------|
{chr(10).join(f'| {k} | {FUSION_WEIGHTS[k]:.2f} | {zero_result.weights[k]:.4f} | {redist_result.weights[k]:.4f} |' for k in FUSION_WEIGHTS if FUSION_WEIGHTS[k] > 0 or k in ['closure_gap', 'orphaned_priv'])}

## Closure Signal Activity

Before interpreting ablation, check if closure signals are even active:

- **closure_gap > 0** in {nonzero_cg}/{n} pairs ({100*nonzero_cg/n:.1f}%)
- **orphaned_priv > 0** in {nonzero_op}/{n} pairs ({100*nonzero_op/n:.1f}%)
- **closure_gap mean:** {statistics.mean(closure_gaps):.4f}, max: {max(closure_gaps):.4f}
- **orphaned_priv mean:** {statistics.mean(orphaned_privs):.4f}, max: {max(orphaned_privs):.4f}

## Results

### Fusion score distribution

| Metric | Baseline | Zero | Redistribute |
|--------|----------|------|--------------|
| Mean   | {statistics.mean(baseline_fusions):.6f} | {statistics.mean(zero_fusions):.6f} | {statistics.mean(redist_fusions):.6f} |
| Median | {statistics.median(baseline_fusions):.6f} | {statistics.median(zero_fusions):.6f} | {statistics.median(redist_fusions):.6f} |
| Std    | {_stdev(baseline_fusions):.6f} | {_stdev(zero_fusions):.6f} | {_stdev(redist_fusions):.6f} |
| Max    | {max(baseline_fusions):.6f} | {max(zero_fusions):.6f} | {max(redist_fusions):.6f} |

### Delta statistics (absolute)

| Metric | Zero | Redistribute |
|--------|------|--------------|
| Mean   | {zero_result.stats['mean']:.6f} | {redist_result.stats['mean']:.6f} |
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

If zero and redistribute produce **similar** deltas, the effect is purely from weight redistribution
(other signals absorb the freed weight). If zero produces **larger** deltas or different tier migrations,
closure carries independent signal.

- Zero ablation mean delta: {zero_result.stats['mean']:.6f}
- Redistribute mean delta: {redist_result.stats['mean']:.6f}
- Ratio: {zero_result.stats['mean'] / redist_result.stats['mean']:.2f}x (>1 means closure has independent value)

### Tier stability

- Zero: {zero_changes}/{n} pairs changed tier ({100*zero_changes/n:.1f}%)
- Redistribute: {redist_changes}/{n} pairs changed tier ({100*redist_changes/n:.1f}%)

## Conclusion

{"Closure signals appear to carry independent detection value." if zero_result.stats['mean'] > redist_result.stats['mean'] * 1.1 else "Closure signal impact is primarily from weight redistribution." if abs(zero_result.stats['mean'] - redist_result.stats['mean']) / max(redist_result.stats['mean'], 0.0001) < 0.1 else "Results are inconclusive — the difference between modes is marginal."}

**Signal activity:** closure_gap is active in {100*nonzero_cg/n:.1f}% of pairs, orphaned_priv in {100*nonzero_op/n:.1f}%.
{"Low activity means the signal hasn't had enough data to exercise closure patterns — the ablation may not be representative of steady-state behavior." if nonzero_cg/n < 0.3 else "Sufficient activity to draw conclusions from this ablation."}

**Recommendation:** Review the tier migration tables and top-10 affected pairs to determine if the pairs
that change tier are ones where closure *should* matter (attack scenarios with unclosed privilege grants)
vs. ones where it's noise.
"""
    return report
