"""Benchmark report formatting — plain text comparison tables."""

from src.benchmark.runner import BenchmarkResult


def format_scenario_report(result: BenchmarkResult) -> str:
    """Format a single scenario's results."""
    lines = [f"Scenario: {result.scenario_path}"]
    lines.append(f"  Ingest: {result.ingest_stats.get('inserted', 0)} events")
    lines.append(f"  Windows scored: {len(result.actor_results)}")
    lines.append(f"  Max residual: {result.max_residual:.4f}")
    lines.append(f"  Mean residual: {result.mean_residual:.4f}")
    lines.append(f"  Alert tier: {result.max_alert_tier}")
    lines.append(f"  Invariants fired: {sorted(result.all_fired_invariants) or 'none'}")

    if result.actor_results:
        lines.append("")
        lines.append("  Per (window, actor):")
        for r in result.actor_results:
            lines.append(
                f"    {r.actor_id[:40]:40s}  "
                f"fusion={r.fusion_raw:.4f}  residual={r.residual_risk:.4f}  "
                f"tier={r.alert_tier:6s}  inv={r.fired_invariants or '-'}"
            )

    return "\n".join(lines)


def format_comparison_table(results: dict[str, BenchmarkResult]) -> str:
    """Format a comparison table across multiple scenarios."""
    lines = [
        f"{'Scenario':<30s}  {'Type':>7s}  {'MaxRes':>7s}  {'MeanRes':>7s}  "
        f"{'Tier':>6s}  {'Invariants'}"
    ]
    lines.append("-" * 100)

    for name, result in results.items():
        scenario_type = _infer_type(name)
        invs = ", ".join(sorted(result.all_fired_invariants)) or "none"
        lines.append(
            f"{name:<30s}  {scenario_type:>7s}  {result.max_residual:>7.4f}  "
            f"{result.mean_residual:>7.4f}  {result.max_alert_tier:>6s}  {invs}"
        )

    return "\n".join(lines)


def _infer_type(scenario_name: str) -> str:
    """Infer scenario type from filename convention."""
    name = scenario_name.lower()
    if name.startswith("b"):
        return "BENIGN"
    if name.startswith("s") and name[1:3].isdigit():
        n = int(name[1:3])
        if n >= 10:
            return "HYBRID"
        return "ATTACK"
    return "UNKNOWN"
