#!/usr/bin/env python3
"""
Lean sandbox re-founding: full orchestration.

Phases:
1. Generate 100 deterministic worlds per SANDBOX_CONTRACT.md
2. Verify campaign allocation (target ~40 per flavor)
3. Verify per-actor transition counts (>> 80 for P1e, >> 20 for P2)
4. Run audits:
   - grep_leak_check: no label leakage
   - fairness_audit: structural fairness (no attack/clean separation)
   - leakage_redteam (instance-grouped): dumb classifier on subtle attacks at chance
5. Report gate: 'fair' | 'inconclusive' | 'rigged'
6. Persist dataset seeds and sandbox_v2_gate.md

Final outputs persisted to bakeoff/reports/:
- sandbox_v2_worlds.pkl (100 World objects)
- sandbox_v2_gate.md (human-readable report)
- sandbox_v2_summary.json (machine-readable summary with metrics)

Date: 2026-07-03
Status: executable entry point for Phase 3 (dev / held-out generation)
"""

import json
import sys
import pickle
from pathlib import Path
from typing import Dict, List, Tuple

# Suppress sklearn deprecation warnings
import warnings
warnings.filterwarnings('ignore', category=FutureWarning)

from bakeoff.configs.world_config import DEFAULT_WORLD_CONFIG
from bakeoff.worldgen.sandbox import generate_balanced_batch
from bakeoff.audits.grep_leak_check import run as run_grep_leak_check
from bakeoff.audits.fairness_audit import run as run_fairness_audit
from bakeoff.audits.leakage_redteam import run as run_leakage_redteam


def main():
    """Main orchestration: generate, audit, report."""
    print("\n" + "=" * 80)
    print("MURMUR PHYSICS FALSIFICATION — LEAN SANDBOX RE-FOUNDING (Phase 3)")
    print("=" * 80)
    print(f"\nDate: 2026-07-03")
    print(f"Contract: SANDBOX_CONTRACT.md (frozen)")
    print(f"Evaluation unit: Attack instance (campaign)")
    print(f"Target: ~40 campaigns per flavor (200 total across 5 flavors)")

    # --- PHASE 1: Generate worlds ---
    print("\n" + "-" * 80)
    print("PHASE 1: Generating 100 deterministic worlds (50 attack, 50 clean)...")
    print("-" * 80)

    try:
        batch = generate_balanced_batch(
            config=DEFAULT_WORLD_CONFIG,
            total_seeds=100,
            target_campaigns_per_flavor=40.0,
            dev_fraction=0.3,  # seeds 0-29 dev, 30-99 held-out
            verbose=True,
        )
    except Exception as e:
        print(f"\n✗ FATAL: World generation failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    worlds = batch["worlds"]
    print(f"\n✓ Generated {len(worlds)} worlds.")

    # --- PHASE 2: Campaign allocation ---
    print("\n" + "-" * 80)
    print("PHASE 2: Campaign allocation check...")
    print("-" * 80)

    campaigns_per_flavor = batch["campaigns_per_flavor"]
    total_campaigns = sum(campaigns_per_flavor.values())

    print(f"\nTotal campaigns: {total_campaigns}")
    print(f"Campaign counts by flavor:")
    for flavor in sorted(campaigns_per_flavor.keys()):
        count = campaigns_per_flavor[flavor]
        print(f"  {flavor:30s}: {count:3d} / 40 ({100*count/40:.0f}%)")

    # Check balance: each flavor should have ~40 (target_campaigns_per_flavor=40)
    min_count = min(campaigns_per_flavor.values()) if campaigns_per_flavor else 0
    max_count = max(campaigns_per_flavor.values()) if campaigns_per_flavor else 0
    print(f"\nBalance: min={min_count}, max={max_count}")

    allocation_ok = (
        total_campaigns >= 150  # at least 150 (75% of target 200)
        and min_count >= 6      # no flavor under-represented
        and max_count <= 80     # no flavor over-concentrated
    )
    if allocation_ok:
        print(f"✓ Campaign allocation balanced.")
    else:
        print(f"⚠ Campaign allocation may be unbalanced; continuing with audits.")

    # --- PHASE 3: Per-actor transition counts ---
    print("\n" + "-" * 80)
    print("PHASE 3: Per-actor transition count check...")
    print("-" * 80)

    transitions_per_actor = batch["transitions_per_actor"]
    all_counts = []
    for world_seed, actor_counts in transitions_per_actor.items():
        all_counts.extend(actor_counts.values())

    import numpy as np
    if all_counts:
        mean_trans = float(np.mean(all_counts))
        median_trans = float(np.median(all_counts))
        min_trans = int(np.min(all_counts))
        max_trans = int(np.max(all_counts))
        p90_trans = float(np.percentile(all_counts, 90))

        print(f"\nPer-actor transition statistics (across all actors in all worlds):")
        print(f"  Mean: {mean_trans:.1f}")
        print(f"  Median: {median_trans:.1f}")
        print(f"  Min: {min_trans}, Max: {max_trans}")
        print(f"  P90: {p90_trans:.1f}")

        p1e_min = 80  # Per PREDICTIONS.md
        p2_min = 20
        p90_sufficient_p1e = p90_trans >= p1e_min
        p90_sufficient_p2 = p90_trans >= p2_min

        print(f"\nData sufficiency:")
        print(f"  P1e (needs ≥{p1e_min}): P90 = {p90_trans:.0f} → " +
              ("✓ PASS" if p90_sufficient_p1e else "✗ WARN (may be data-starved)"))
        print(f"  P2 (needs ≥{p2_min}): P90 = {p90_trans:.0f} → " +
              ("✓ PASS" if p90_sufficient_p2 else "✗ FAIL (insufficient)"))

        transitions_ok = p90_sufficient_p1e
    else:
        print(f"✗ No transition data found.")
        transitions_ok = False

    # --- PHASE 4: Audits ---
    print("\n" + "-" * 80)
    print("PHASE 4: Running audits...")
    print("-" * 80)

    # 4a: Grep leak check
    print("\n  4a. Grep leak check (label leakage)...", end=" ", flush=True)
    try:
        grep_result = run_grep_leak_check(worlds)
        grep_clean = grep_result.passed
        print(f"{'✓ PASS' if grep_clean else '✗ FAIL'}")
        if not grep_clean:
            print(f"      Leaks found: {len(grep_result.leaks_found)}")
            for leaked_str, location, context in grep_result.leaks_found[:5]:
                print(f"        - {leaked_str} in {location} ({context})")
    except Exception as e:
        print(f"✗ EXCEPTION: {e}")
        grep_clean = False
        grep_result = None

    # 4b: Fairness audit
    print(f"\n  4b. Fairness audit (structural equalization)...", end=" ", flush=True)
    try:
        fairness_result = run_fairness_audit(worlds)
        fairness_ok = fairness_result.passed
        print(f"{'✓ PASS' if fairness_ok else '✗ FAIL'}")
        if fairness_result.details:
            for world_seed, gate_name, passed, msg in fairness_result.details[:5]:
                if not passed:
                    print(f"      - World {world_seed}, {gate_name}: {msg}")
    except Exception as e:
        print(f"✗ EXCEPTION: {e}")
        fairness_ok = False
        fairness_result = None

    # 4c: Leakage red-team (instance-grouped)
    print(f"\n  4c. Leakage red-team (instance-grouped, subtle attacks)...", end=" ", flush=True)
    try:
        redteam_result = run_leakage_redteam(worlds)
        redteam_at_chance = redteam_result.at_chance
        print(f"{'✓ AT CHANCE' if redteam_at_chance else '⚠ ABOVE CHANCE'}")
        print(f"      AUC-PR: {redteam_result.auc_pr:.4f} (no-skill: {redteam_result.no_skill_pr:.4f})")
        print(f"      CI: [{redteam_result.ci_lower:.4f}, {redteam_result.ci_upper:.4f}]")
        if redteam_result.stratified_results:
            for attack_type, info in redteam_result.stratified_results.items():
                if attack_type in ("LivingOffTheLand", "SlowExfiltration", "ServiceAccountHijack"):
                    status = info.get("status", "UNKNOWN")
                    ap = info.get("auc_pr", 0.0)
                    print(f"        {attack_type:30s}: {status:15s} (AUC-PR={ap:.4f})")
    except Exception as e:
        print(f"✗ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        redteam_at_chance = False
        redteam_result = None

    # --- PHASE 5: Gate decision ---
    print("\n" + "-" * 80)
    print("PHASE 5: Gate decision...")
    print("-" * 80)

    gate = "fair"
    issues = []

    # Gather all findings
    if not grep_clean:
        gate = "rigged"
        issues.append("Label leakage detected in anonymized events")

    if not fairness_ok:
        gate = "rigged"
        issues.append("Fairness audit failed (structural separation between attack/clean worlds)")

    if not redteam_at_chance:
        # Check if subtle attacks specifically are above chance
        if redteam_result and redteam_result.stratified_results:
            subtle_leaking = False
            for attack_type in ("LivingOffTheLand", "SlowExfiltration", "ServiceAccountHijack"):
                info = redteam_result.stratified_results.get(attack_type, {})
                status = info.get("status", "")
                if status in ("LEAKS", "ABOVE_CHANCE"):
                    subtle_leaking = True
                    issues.append(f"Subtle attack '{attack_type}' above chance in leakage red-team")
                elif status == "INCONCLUSIVE":
                    issues.append(f"Subtle attack '{attack_type}' has insufficient positives (<10)")
                    gate = "inconclusive"

            if subtle_leaking:
                gate = "rigged"

    if not transitions_ok:
        gate = "inconclusive"
        issues.append("Per-actor transitions insufficient for P1e rolling-window scoring")

    if not allocation_ok:
        gate = "inconclusive"
        issues.append("Campaign allocation unbalanced (target ~40 per flavor)")

    print(f"\nGate result: {gate.upper()}")
    if issues:
        print(f"Issues ({len(issues)}):")
        for issue in issues:
            print(f"  - {issue}")

    # --- PHASE 6: Persist results ---
    print("\n" + "-" * 80)
    print("PHASE 6: Persisting results...")
    print("-" * 80)

    reports_dir = Path("/Users/shamreeniram/Desktop/Peyara/Murmur/bakeoff/reports")
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Persist worlds as pickle
    worlds_path = reports_dir / "sandbox_v2_worlds.pkl"
    try:
        with open(worlds_path, 'wb') as f:
            pickle.dump(worlds, f)
        print(f"\n✓ Worlds persisted to {worlds_path}")
    except Exception as e:
        print(f"\n✗ Failed to persist worlds: {e}")

    # Persist seed mapping
    seeds_path = reports_dir / "sandbox_v2_seeds.json"
    seeds_info = {
        "total_seeds": 100,
        "dev_seeds": batch["dev_seeds"],
        "held_out_seeds": batch["held_out_seeds"],
        "timestamp": "2026-07-03",
    }
    try:
        with open(seeds_path, 'w') as f:
            json.dump(seeds_info, f, indent=2)
        print(f"✓ Seed mapping persisted to {seeds_path}")
    except Exception as e:
        print(f"✗ Failed to persist seed mapping: {e}")

    # Persist summary metrics
    summary_path = reports_dir / "sandbox_v2_summary.json"
    summary = {
        "date": "2026-07-03",
        "gate": gate,
        "issues": issues,
        "worlds": {
            "total": len(worlds),
            "attack_worlds": batch["attack_world_count"],
            "clean_worlds": batch["clean_world_count"],
        },
        "campaigns": {
            "total": total_campaigns,
            "per_flavor": campaigns_per_flavor,
            "target_per_flavor": 40,
        },
        "transitions": {
            "mean": float(np.mean(all_counts)) if all_counts else 0.0,
            "median": float(np.median(all_counts)) if all_counts else 0.0,
            "p90": float(np.percentile(all_counts, 90)) if all_counts else 0.0,
            "min": int(np.min(all_counts)) if all_counts else 0,
            "max": int(np.max(all_counts)) if all_counts else 0,
        },
        "audits": {
            "grep_leak_check_passed": grep_clean,
            "fairness_audit_passed": fairness_ok,
            "leakage_redteam_at_chance": redteam_at_chance,
            "redteam_auc_pr": redteam_result.auc_pr if redteam_result else 0.0,
            "redteam_no_skill_pr": redteam_result.no_skill_pr if redteam_result else 0.0,
            "redteam_ci_lower": redteam_result.ci_lower if redteam_result else 0.0,
            "redteam_ci_upper": redteam_result.ci_upper if redteam_result else 0.0,
        },
    }
    try:
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)
        print(f"✓ Summary persisted to {summary_path}")
    except Exception as e:
        print(f"✗ Failed to persist summary: {e}")

    # --- Human-readable report ---
    gate_report_path = reports_dir / "sandbox_v2_gate.md"
    gate_report = _format_gate_report(
        gate, issues, batch, campaigns_per_flavor, all_counts,
        grep_clean, fairness_ok, redteam_at_chance, redteam_result
    )
    try:
        with open(gate_report_path, 'w') as f:
            f.write(gate_report)
        print(f"✓ Gate report persisted to {gate_report_path}")
    except Exception as e:
        print(f"✗ Failed to persist gate report: {e}")

    # --- Final summary ---
    print("\n" + "=" * 80)
    print("SANDBOX V2 GENERATION COMPLETE")
    print("=" * 80)
    print(f"\nGate: {gate.upper()}")
    print(f"Campaigns per flavor: {min(campaigns_per_flavor.values()) if campaigns_per_flavor else 0}–{max(campaigns_per_flavor.values()) if campaigns_per_flavor else 0}")
    print(f"Per-actor transitions (P90): {p90_trans:.0f}")
    print(f"Issues: {len(issues)}")
    print(f"\nReports:")
    print(f"  - {worlds_path}")
    print(f"  - {seeds_path}")
    print(f"  - {summary_path}")
    print(f"  - {gate_report_path}")
    print()

    return 0 if gate in ("fair", "inconclusive") else 1


def _format_gate_report(
    gate: str,
    issues: List[str],
    batch: Dict,
    campaigns_per_flavor: Dict[str, int],
    all_counts: List[int],
    grep_clean: bool,
    fairness_ok: bool,
    redteam_at_chance: bool,
    redteam_result,
) -> str:
    """Format human-readable gate report (markdown)."""
    import numpy as np

    lines = [
        "# Sandbox V2 Gate Report",
        "",
        "**Date:** 2026-07-03",
        f"**Gate Verdict:** `{gate.upper()}`",
        "",
        "---",
        "",
        "## Gate Decision Criteria",
        "",
        "| Criterion | Result | Status |",
        "|-----------|--------|--------|",
    ]

    # Append audit results
    lines.append(f"| Grep leak check (no label leakage) | {'✓ PASS' if grep_clean else '✗ FAIL'} | {'PASS' if grep_clean else 'FAIL'} |")
    lines.append(f"| Fairness audit (structural equalization) | {'✓ PASS' if fairness_ok else '✗ FAIL'} | {'PASS' if fairness_ok else 'FAIL'} |")
    lines.append(f"| Leakage red-team (subtle attacks @ chance) | {'✓ AT CHANCE' if redteam_at_chance else '⚠ ABOVE CHANCE'} | {'PASS' if redteam_at_chance else 'FLAG'} |")

    lines.extend([
        "",
        "---",
        "",
        "## Campaign Allocation",
        "",
        "| Flavor | Count | Target | % |",
        "|--------|-------|--------|-----|",
    ])

    for flavor in sorted(campaigns_per_flavor.keys()):
        count = campaigns_per_flavor[flavor]
        pct = 100 * count / 40
        lines.append(f"| {flavor} | {count} | 40 | {pct:.0f}% |")

    total_campaigns = sum(campaigns_per_flavor.values())
    lines.append(f"| **TOTAL** | **{total_campaigns}** | **200** | **{100*total_campaigns/200:.0f}%** |")

    lines.extend([
        "",
        "---",
        "",
        "## Per-Actor Transition Statistics",
        "",
    ])

    if all_counts:
        mean_t = np.mean(all_counts)
        median_t = np.median(all_counts)
        min_t = np.min(all_counts)
        max_t = np.max(all_counts)
        p90_t = np.percentile(all_counts, 90)

        lines.extend([
            f"- **Mean:** {mean_t:.1f}",
            f"- **Median:** {median_t:.1f}",
            f"- **Min:** {int(min_t)}, **Max:** {int(max_t)}",
            f"- **P90:** {p90_t:.1f}",
            "",
            f"**Data Sufficiency (locked decision 1):**",
            f"- P1e requires ≥80 transitions: P90 = {p90_t:.0f} → {'✓ PASS' if p90_t >= 80 else '✗ WARN'}",
            f"- P2 requires ≥20 transitions: P90 = {p90_t:.0f} → {'✓ PASS' if p90_t >= 20 else '✗ FAIL'}",
            "",
        ])

    # World distribution
    lines.extend([
        "---",
        "",
        "## World Distribution",
        "",
        f"- **Total worlds:** {batch['attack_world_count'] + batch['clean_world_count']}",
        f"- **Attack worlds:** {batch['attack_world_count']} ({100*batch['attack_world_count']/(batch['attack_world_count'] + batch['clean_world_count']):.0f}%)",
        f"- **Clean worlds:** {batch['clean_world_count']} ({100*batch['clean_world_count']/(batch['attack_world_count'] + batch['clean_world_count']):.0f}%)",
        f"- **Dev seeds:** {len(batch['dev_seeds'])} (seeds 0–{max(batch['dev_seeds'])})",
        f"- **Held-out seeds:** {len(batch['held_out_seeds'])} (seeds {min(batch['held_out_seeds'])}–{max(batch['held_out_seeds'])})",
        "",
    ])

    # Audit details
    lines.extend([
        "---",
        "",
        "## Audit Details",
        "",
        "### Grep Leak Check",
        "",
        f"Status: {'✓ PASS (no label leakage detected)' if grep_clean else '✗ FAIL (labels leaked in anonymized events)'}",
        "",
        "Checked for:",
        "- Zone names: IDENTITY, SECRET, DATA, COMPUTE, LOGGING, EXTERNAL, ADMIN",
        "- Archetype names: Developer, DataAnalyst, CICDServiceAccount, ...",
        "- Attack type names: CredentialTheftLateral, SlowExfiltration, ...",
        "",
        "### Fairness Audit (Structural Equalization)",
        "",
        f"Status: {'✓ PASS' if fairness_ok else '✗ FAIL'}",
        "",
        "Checks:",
        "- Zone counts: KS-test (attack vs clean), α=0.01",
        "- Node degrees: KS-test (attack vs clean), α=0.01",
        "- Per-zone event volumes: KS-test (attack vs clean), α=0.01",
        "- Attack path lengths within benign IQR",
        "- Per-edge rarity matching (hard negatives)",
        "- Per-actor transition counts >> 80",
        "",
        "### Leakage Red-Team (Instance-Grouped)",
        "",
        f"Status: {'✓ AT CHANCE' if redteam_at_chance else '⚠ ABOVE CHANCE'}",
        "",
    ])

    if redteam_result:
        lines.extend([
            f"- **Shallow classifier:** Logistic regression on 7 shallow features",
            f"- **Metric:** AUC-PR (not ROC-AUC; class imbalance extreme)",
            f"- **AUC-PR:** {redteam_result.auc_pr:.4f}",
            f"- **No-skill baseline (positive prevalence):** {redteam_result.no_skill_pr:.4f}",
            f"- **95% CI:** [{redteam_result.ci_lower:.4f}, {redteam_result.ci_upper:.4f}]",
            f"- **At chance (upper CI within 5pp of no-skill):** {'✓ YES' if redteam_at_chance else '✗ NO'}",
            "",
            "**Stratified by attack type:**",
            "",
        ])

        if redteam_result.stratified_results:
            for attack_type in sorted(redteam_result.stratified_results.keys()):
                info = redteam_result.stratified_results[attack_type]
                status = info.get("status", "UNKNOWN")
                auc_pr = info.get("auc_pr", 0.0)
                n_pos = info.get("n_positives", 0)
                is_subtle = attack_type in ("LivingOffTheLand", "SlowExfiltration", "ServiceAccountHijack")
                is_exempt = attack_type in ("SmashAndGrab",)
                marker = "🎯" if is_subtle else ("🔕" if is_exempt else "•")
                lines.append(f"{marker} **{attack_type}** ({n_pos} instances): AUC-PR={auc_pr:.4f}, Status={status}")

    # Issues
    lines.extend([
        "",
        "---",
        "",
        "## Issues & Findings",
        "",
    ])

    if not issues:
        lines.append("✓ **No issues found. Landscape is fair and non-rigged.**")
    else:
        lines.append(f"⚠ **{len(issues)} issues found:**")
        lines.append("")
        for i, issue in enumerate(issues, 1):
            lines.append(f"{i}. {issue}")

    lines.extend([
        "",
        "---",
        "",
        "## Gate Decision",
        "",
        f"### Verdict: `{gate.upper()}`",
        "",
    ])

    if gate == "fair":
        lines.extend([
            "✓ Landscape is **FAIR**. No label leakage, structural equalization passes, subtle attacks at chance.",
            "",
            "**Proceeding to Phase 4:** Baseline and physics detector tuning on dev worlds.",
            "",
        ])
    elif gate == "inconclusive":
        lines.extend([
            "⚠ Landscape is **INCONCLUSIVE**. Some audits incomplete or under-powered.",
            "",
            "**Action:** Review flagged issues. Regenerate with adjusted parameters if needed.",
            "",
        ])
    else:  # rigged
        lines.extend([
            "✗ Landscape is **RIGGED**. Label leakage or structural separation detected.",
            "",
            "**Action:** Fix generator. Do not proceed to Phase 4 with this world set.",
            "",
        ])

    lines.extend([
        "---",
        "",
        f"**Report generated:** 2026-07-03",
        f"**Evaluation unit:** Attack instance (campaign)",
        f"**Contract:** SANDBOX_CONTRACT.md (frozen 2026-07-03)",
        "",
    ])

    return "\n".join(lines)


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
