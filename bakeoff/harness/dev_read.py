#!/usr/bin/env python3
"""
DEV-ONLY physics read (2026-07-03, autonomous). Generates a BALANCED dev landscape
(equal campaigns per flavor, incl. LivingOffTheLand) and reports:
  1. Campaigns per flavor (sanity: balanced, LOTL present).
  2. P1e (excess EP) + P2 (flux) score distributions: benign housekeeping vs attack, per flavor.
     Tests pre-registered predictions: P1e ignores housekeeping (~0) and elevates on attacks;
     P1e catches LOTL (rate/order departure from own baseline); P2 catches sinks.
  3. Instance-grouped leakage red-team (fairness) on this set.
This is EXPLORATORY (dev seeds only); NOT the frozen Phase-5 held-out verdict. No baselines yet.
"""
import statistics as st
from collections import defaultdict

from bakeoff.worldgen.model import WorldConfig, ArchetypeKind, AttackType
from bakeoff.worldgen.world import generate
from bakeoff.common.trajectory import Trajectory, Transition
from bakeoff.detectors import p1e_excess, p2_flux
from bakeoff.audits import leakage_redteam

HOUSEKEEPING = {ArchetypeKind.ETLPipelineServiceAccount.value,
                ArchetypeKind.BackupLogShippingAccount.value}

def make_config(seed):
    return WorldConfig(
        population_size=80,
        archetype_mixture={  # ensure enough eligible actors per flavor
            ArchetypeKind.Developer.value: 0.22, ArchetypeKind.DataAnalyst.value: 0.18,
            ArchetypeKind.CICDServiceAccount.value: 0.12, ArchetypeKind.ETLPipelineServiceAccount.value: 0.12,
            ArchetypeKind.BackupLogShippingAccount.value: 0.10, ArchetypeKind.OnCallSRE.value: 0.10,
            ArchetypeKind.NewHire.value: 0.06, ArchetypeKind.RoleChange.value: 0.05,
            ArchetypeKind.BreakGlassAdmin.value: 0.05,
        },
        horizon_days=60.0, event_rate_lambda=18.0,
        attack_mix={t.value: 0.2 for t in AttackType},
        attack_compromise_count=5, attack_onset_phase=(1/3, 2/3),
        action_vocab=("auth","read","write","invoke","grant","assume"),
        zone_labels=("IDENTITY","SECRET","DATA","COMPUTE","LOGGING","EXTERNAL","ADMIN"),
        seed=seed, attack_world_ratio=0.5,
    )

def traj_map(world):
    by = defaultdict(list)
    for e in world.anonymized_events:
        by[e.actor].append(e)
    out = {}
    for a, evs in by.items():
        evs.sort(key=lambda e: e.t)
        out[a] = [Transition(e.t, e.actor, e.src, e.dst, e.action) for e in evs]
    return out

def p1e_p2_for_window(trans, t_lo, t_hi):
    win = [t for t in trans if t_lo <= t.t <= t_hi]
    if len(win) < 5:
        up = [t for t in trans if t.t <= t_hi]
        win = up[-80:] if len(up) >= 80 else up
    if len(win) < 2:
        return None, None
    up_to = [t for t in trans if t.t <= win[-1].t]
    if len(up_to) <= len(win):
        return None, None
    try:
        p1e = p1e_excess.score_window(Trajectory(up_to), Trajectory(win))
        p2 = p2_flux.score(Trajectory(win))
    except Exception:
        return None, None
    return p1e, p2

def main():
    flavors = list(AttackType)
    worlds, seed = [], 0
    ATTACK_PER_FLAVOR, CLEAN = 4, 6
    for f in flavors:
        for _ in range(ATTACK_PER_FLAVOR):
            worlds.append(generate(make_config(seed), seed, force_attack_world=True, forced_flavor=f)); seed += 1
    for _ in range(CLEAN):
        worlds.append(generate(make_config(seed), seed, force_attack_world=False)); seed += 1

    # 1. campaigns per flavor
    per_flavor_campaigns = defaultdict(list)
    for w in worlds:
        for c in w.ground_truth.campaigns:
            per_flavor_campaigns[c.flavor].append((w, c))
    print("=== CAMPAIGNS PER FLAVOR ===")
    for f in flavors:
        print(f"  {f.value:26s} {len(per_flavor_campaigns[f.value])}")

    # 2a. attack window scores per flavor
    print("\n=== P1e / P2 ATTACK-WINDOW SCORES (per flavor) ===")
    attack_p1e = defaultdict(list); attack_p2 = defaultdict(list)
    for w in worlds:
        tm = traj_map(w)
        for c in w.ground_truth.campaigns:
            trans = tm.get(c.actor_hash)
            if not trans:
                continue
            p1e, p2 = p1e_p2_for_window(trans, c.t_start, c.t_end)
            if p1e is not None:
                attack_p1e[c.flavor].append(p1e); attack_p2[c.flavor].append(p2)
    for f in flavors:
        n = len(attack_p1e[f.value])
        if n:
            print(f"  {f.value:26s} n={n:3d}  P1e mean={st.mean(attack_p1e[f.value]):.3f}  P2 mean={st.mean(attack_p2[f.value]):.3f}")
        else:
            print(f"  {f.value:26s} n=0")

    # 2b. benign scores (all + housekeeping) from clean worlds
    ben_p1e, ben_p2, hk_p1e, hk_p2 = [], [], [], []
    for w in worlds:
        if w.ground_truth.campaigns:
            continue  # clean worlds only for benign baseline
        raw2arch = {a.id: a.archetype.value for a in w.actors}
        hash2raw = {h: r for r, h in w.anonymized_mapping.actor_hashes.items()}
        tm = traj_map(w)
        for a, trans in tm.items():
            if len(trans) < 160:
                continue
            mid = len(trans) // 2
            win = trans[mid-80:mid]
            up_to = trans[:mid]
            try:
                p1e = p1e_excess.score_window(Trajectory(trans[:mid]), Trajectory(win))
                p2 = p2_flux.score(Trajectory(win))
            except Exception:
                continue
            ben_p1e.append(p1e); ben_p2.append(p2)
            arch = raw2arch.get(hash2raw.get(a))
            if arch in HOUSEKEEPING:
                hk_p1e.append(p1e); hk_p2.append(p2)
    print("\n=== BENIGN BASELINE SCORES ===")
    if ben_p1e:
        print(f"  all-benign     n={len(ben_p1e):3d}  P1e mean={st.mean(ben_p1e):.3f}  P2 mean={st.mean(ben_p2):.3f}")
    if hk_p1e:
        print(f"  HOUSEKEEPING   n={len(hk_p1e):3d}  P1e mean={st.mean(hk_p1e):.3f}  P2 mean={st.mean(hk_p2):.3f}  (ETL/backup one-way; prediction: ~low excess)")

    # separation summary
    if ben_p1e:
        b1 = st.mean(ben_p1e); b2 = st.mean(ben_p2)
        print("\n=== SEPARATION (attack mean / benign mean) ===")
        for f in flavors:
            if attack_p1e[f.value]:
                r1 = st.mean(attack_p1e[f.value]) / b1 if b1 else float('inf')
                r2 = st.mean(attack_p2[f.value]) / b2 if b2 else float('inf')
                print(f"  {f.value:26s} P1e x{r1:.2f}  P2 x{r2:.2f}")

    # 3. fairness
    print("\n=== FAIRNESS (instance-grouped leakage red-team) ===")
    try:
        rt = leakage_redteam.run(worlds)
        print(" ", rt.message)
        for at, r in sorted(rt.stratified_results.items()):
            print(f"    {at:26s} {r}")
    except Exception as e:
        print("  red-team error:", e)

if __name__ == "__main__":
    main()
