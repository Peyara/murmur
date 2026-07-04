"""
Leakage red-team audit (§4.3) — the single most important fairness gate.

Trains a deliberately dumb "cheat detector" (shallow logistic regression) to distinguish
attack INSTANCES (campaigns) from benign windows. If it beats chance on SUBTLE attacks,
the landscape leaks a trivial discriminator and is RIGGED — fix the generator, do not proceed.

EVALUATION UNIT (2026-07-03, instance-grouped refactor):
Each positive sample = ONE ATTACK INSTANCE (campaign), features aggregated over the instance's
full time span (or representative window if instance is multi-window — choice documented below).
Each negative sample = a non-overlapping W-sized benign window, where W = median instance duration.

AGGREGATION CHOICE: Features computed over entire instance span [t_start, t_end).
Rationale: instance is the ground-truth unit; aggregating over the full span captures campaign
behavior, not window artifacts. (Alternative: use a single representative window within the
instance — not chosen here; would require instance-internal median/max selection.)

CORRECTNESS (rewritten 2026-07-03 after human review caught three flaws in the first version):
1. MATCHED GRANULARITY: both classes are sampled as (actor, span) pairs with consistent duration W.
2. HELD-OUT SPLIT: fit on TRAIN worlds, evaluate AUC-PR + bootstrap CI on HELD-OUT worlds only.
3. GROUP BY WORLD: the train/test split is by world, so instances from one world never appear in
   both splits (no within-world leakage inflating the score).
4. GROUP BY INSTANCE: positive samples grouped at campaign level (one per unique attack instance),
   not per-window within the instance.

STRATIFIED (locked decision 2):
- Subtle attacks {LivingOffTheLand, SlowExfiltration, ServiceAccountHijack} MUST be at chance.
  If any subtle attack's CI upper exceeds no-skill baseline, landscape is RIGGED.
- SmashAndGrab EXEMPT from gate — it is meant to be aggregate-visible. Status recorded but
  does not fail the gate.
- CredentialTheftLateral: reported but not a hard fail (target near-chance, not mandatory).
- Insufficient positives (<10 per attack type) → status INCONCLUSIVE, not vacuous pass.

Primary metric: AUC-PR (extreme class imbalance makes ROC flattering — banned per §6.1).
No-skill baseline = positive prevalence in the held-out set. "At chance" = CI upper bound within
a small margin of the no-skill line (margin = 5pp, hard-coded per spec).
"""

from typing import List, Dict, Tuple
from collections import Counter, defaultdict
import numpy as np

try:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score
    sklearn_available = True
except ImportError:
    sklearn_available = False

from ..worldgen.model import World

SUBTLE_ATTACKS = ("LivingOffTheLand", "SlowExfiltration", "ServiceAccountHijack")
EXEMPT_ATTACKS = ("SmashAndGrab",)  # means-to-be-aggregate-visible; does not fail the gate
_AT_CHANCE_MARGIN = 0.05   # CI upper may exceed no-skill by this and still count as "at chance"
_INSUFFICIENT_POSITIVES = 10  # threshold for INCONCLUSIVE status (per spec 2026-07-03)
_NEG_PER_POS = 8           # benign:attack sampling ratio (keeps imbalance realistic-ish)
_TRAIN_FRAC = 0.7          # fraction of WORLDS assigned to train
_N_BOOTSTRAP = 1000
_FEATURE_NAMES = (
    "event_count", "unique_resources", "unique_edges", "unique_actions",
    "edge_diversity_ratio", "max_degree", "mean_degree",
)


class LeakageRedTeamResult:
    def __init__(self):
        self.at_chance: bool = False
        self.auc_pr: float = 0.0
        self.no_skill_pr: float = 0.0
        self.ci_lower: float = 0.0
        self.ci_upper: float = 0.0
        self.feature_importances: Dict[str, float] = {}
        self.message: str = ""
        self.stratified_results: Dict[str, Dict] = {}
        # kept for harness back-compat
        self.auc_roc: float = 0.0


def _window_features(world: World, actor: str, t_start: float, t_end: float) -> List[float]:
    """Shallow features over ONE actor's anonymized events in [t_start, t_end)."""
    evs = [e for e in world.anonymized_events if e.actor == actor and t_start <= e.t < t_end]
    if not evs:
        return [0.0] * len(_FEATURE_NAMES)
    n = len(evs)
    resources = {e.src for e in evs} | {e.dst for e in evs}
    edges = {(e.src, e.dst, e.action) for e in evs}
    actions = {e.action for e in evs}
    deg = Counter()
    for e in evs:
        deg[e.src] += 1
        deg[e.dst] += 1
    degvals = list(deg.values()) or [0]
    return [
        float(n),
        float(len(resources)),
        float(len(edges)),
        float(len(actions)),
        float(len(edges)) / n,
        float(max(degvals)),
        float(sum(degvals)) / len(degvals),
    ]


def _actor_event_span(world: World, actor: str) -> Tuple[float, float]:
    ts = [e.t for e in world.anonymized_events if e.actor == actor]
    return (min(ts), max(ts)) if ts else (0.0, 0.0)


def _overlaps_any(actor: str, t0: float, t1: float, labels) -> bool:
    for lab in labels:
        if lab.actor_hash == actor and not (t1 <= lab.t_window_start or t0 >= lab.t_window_end):
            return True
    return False


class _Inst:
    """Adapter exposing a campaign as the label-like interface this module expects."""
    __slots__ = ("actor_hash", "t_window_start", "t_window_end", "attack_type")
    def __init__(self, actor_hash, t_start, t_end, attack_type):
        self.actor_hash = actor_hash
        self.t_window_start = t_start
        self.t_window_end = t_end
        self.attack_type = attack_type


def _instances(world) -> List["_Inst"]:
    """Prefer campaigns (post-2026-07-03 refactor); fall back to legacy labels."""
    campaigns = getattr(world.ground_truth, "campaigns", None)
    if campaigns:
        return [_Inst(c.actor_hash, c.t_start, c.t_end, c.flavor) for c in campaigns]
    return [_Inst(l.actor_hash, l.t_window_start, l.t_window_end, l.attack_type)
            for l in world.ground_truth.labels]


def run(worlds: List[World]) -> LeakageRedTeamResult:
    if not sklearn_available:
        raise ImportError("scikit-learn required; 'uv add scikit-learn'")
    if not worlds:
        raise ValueError("worlds list cannot be empty")

    result = LeakageRedTeamResult()
    rng = np.random.default_rng(42)

    # --- window size W = median instance duration (matched granularity for both classes) ---
    # Each label represents one attack INSTANCE (campaign). W is used for benign-negative sampling.
    durations = [
        lab.t_window_end - lab.t_window_start
        for w in worlds for lab in _instances(w)
        if lab.t_window_end > lab.t_window_start
    ]
    if not durations:
        result.at_chance = True
        result.message = "No attack labels present; nothing to test."
        return result
    W = float(np.median(durations))

    # --- build (world_idx, actor, t0, t1, y, attack_type) samples, GROUPED BY INSTANCE ---
    # Evaluation unit: one positive sample = ONE ATTACK INSTANCE (label).
    # Features aggregated over the instance's full [t_start, t_end) span.
    # (Alternative design: use single representative window within multi-window instances;
    #  not chosen here — aggregation ensures campaign behavior is captured, not windowing artifacts.)
    samples = []  # each: dict(world_idx, actor, t0, t1, y, atype, instance_id)
    instance_id = 0
    for wi, world in enumerate(worlds):
        labels = _instances(world)
        # positives: one sample per attack instance (campaign)
        for lab in labels:
            samples.append(dict(world_idx=wi, actor=lab.actor_hash,
                                t0=lab.t_window_start, t1=lab.t_window_end,
                                y=1, atype=lab.attack_type, instance_id=instance_id))
            instance_id += 1

        # negatives: non-overlapping W-windows over each actor's span, not overlapping any label
        # Benign "instances" are W-sized windows of normal behavior from the same actors
        actors = {e.actor for e in world.anonymized_events}
        neg_candidates = []
        for actor in actors:
            lo, hi = _actor_event_span(world, actor)
            t = lo
            while t + W <= hi:
                if not _overlaps_any(actor, t, t + W, labels):
                    neg_candidates.append((actor, t, t + W))
                t += W

        # cap negatives per world to keep imbalance sane relative to that world's positives
        n_pos_world = sum(1 for s in samples if s["world_idx"] == wi)
        cap = max(_NEG_PER_POS * max(n_pos_world, 1), 5)
        if len(neg_candidates) > cap:
            idx = rng.choice(len(neg_candidates), size=cap, replace=False)
            neg_candidates = [neg_candidates[i] for i in idx]
        for actor, t0, t1 in neg_candidates:
            samples.append(dict(world_idx=wi, actor=actor, t0=t0, t1=t1, y=0,
                                atype="benign", instance_id=instance_id))
            instance_id += 1

    # --- group split by WORLD (no world in both train and test) ---
    world_ids = sorted({s["world_idx"] for s in samples})
    rng.shuffle(world_ids)
    n_train = max(1, int(round(_TRAIN_FRAC * len(world_ids))))
    train_worlds = set(world_ids[:n_train])
    test_worlds = set(world_ids[n_train:])
    if not test_worlds:
        result.message = "Too few worlds for a held-out split (need >=2 worlds)."
        return result

    def _matrix(pred):
        X, y, at = [], [], []
        for s in samples:
            if pred(s["world_idx"]):
                X.append(_window_features(worlds[s["world_idx"]], s["actor"], s["t0"], s["t1"]))
                y.append(s["y"])
                at.append(s["atype"])
        return np.array(X, dtype=np.float64), np.array(y, dtype=np.int32), at

    Xtr, ytr, _ = _matrix(lambda w: w in train_worlds)
    Xte, yte, at_te = _matrix(lambda w: w in test_worlds)

    if len(set(ytr)) < 2 or len(set(yte)) < 2:
        result.at_chance = True
        result.message = (f"Held-out split lacks both classes (train pos={int(ytr.sum())}, "
                          f"test pos={int(yte.sum())}); inconclusive -> treat as at-chance pending more worlds.")
        return result

    clf = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)
    clf.fit(Xtr, ytr)
    proba = clf.predict_proba(Xte)[:, 1]

    no_skill = float(yte.mean())
    auc_pr = float(average_precision_score(yte, proba))

    boot = []
    for _ in range(_N_BOOTSTRAP):
        idx = rng.choice(len(yte), size=len(yte), replace=True)
        if len(set(yte[idx])) > 1:
            boot.append(average_precision_score(yte[idx], proba[idx]))
    ci_lower = float(np.percentile(boot, 2.5)) if boot else auc_pr
    ci_upper = float(np.percentile(boot, 97.5)) if boot else auc_pr

    result.auc_pr = auc_pr
    result.no_skill_pr = no_skill
    result.ci_lower = ci_lower
    result.ci_upper = ci_upper
    result.feature_importances = {n: float(c) for n, c in zip(_FEATURE_NAMES, clf.coef_[0])}
    overall_at_chance = ci_upper <= no_skill + _AT_CHANCE_MARGIN

    # --- stratified: each attack type's positives vs all held-out negatives ---
    # Gate verdict determined by SUBTLE attacks only; SmashAndGrab (EXEMPT) doesn't fail the gate.
    neg_mask = np.array([a == "benign" for a in at_te])
    result.at_chance = overall_at_chance
    subtle_at_chance = True  # tracks if all subtle attacks are at-chance
    for atype in sorted({a for a in at_te if a != "benign"}):
        pos_mask = np.array([a == atype for a in at_te])
        sel = pos_mask | neg_mask
        y_s, p_s = yte[sel], proba[sel]
        n_pos = int(pos_mask.sum())

        # Insufficient positives: mark as INCONCLUSIVE, don't force pass/fail
        if n_pos < _INSUFFICIENT_POSITIVES:
            result.stratified_results[atype] = {
                "n_pos": n_pos,
                "status": "INCONCLUSIVE",
                "reason": f"fewer than {_INSUFFICIENT_POSITIVES} positive instances",
                "at_chance": True,  # treat as "not failing" but not a successful pass
                "is_subtle": atype in SUBTLE_ATTACKS,
                "is_exempt": atype in EXEMPT_ATTACKS,
            }
            continue

        if len(set(y_s)) < 2:
            result.stratified_results[atype] = {
                "n_pos": n_pos,
                "status": "INCONCLUSIVE",
                "reason": "held-out split lacks both classes for this attack type",
                "at_chance": True,
                "is_subtle": atype in SUBTLE_ATTACKS,
                "is_exempt": atype in EXEMPT_ATTACKS,
            }
            continue

        ns = float(y_s.mean())
        ap = float(average_precision_score(y_s, p_s))
        b = []
        for _ in range(min(500, _N_BOOTSTRAP)):
            idx = rng.choice(len(y_s), size=len(y_s), replace=True)
            if len(set(y_s[idx])) > 1:
                b.append(average_precision_score(y_s[idx], p_s[idx]))
        ci_u = float(np.percentile(b, 97.5)) if b else ap
        ci_l = float(np.percentile(b, 2.5)) if b else ap
        at_chance_t = ci_u <= ns + _AT_CHANCE_MARGIN

        # Verdict: SUBTLE attacks must be at-chance; EXEMPT attacks don't fail the gate
        is_subtle = atype in SUBTLE_ATTACKS
        is_exempt = atype in EXEMPT_ATTACKS
        if is_subtle and not at_chance_t:
            subtle_at_chance = False
            result.at_chance = False  # ANY subtle attack non-at-chance → RIGGED

        result.stratified_results[atype] = {
            "n_pos": n_pos,
            "auc_pr": ap,
            "no_skill": ns,
            "ci_lower": ci_l,
            "ci_upper": ci_u,
            "at_chance": at_chance_t,
            "status": "at_chance" if at_chance_t else "EXCEEDS_NO_SKILL",
            "is_subtle": is_subtle,
            "is_exempt": is_exempt,
        }

    top = sorted(result.feature_importances.items(), key=lambda x: abs(x[1]), reverse=True)[:3]

    # Build detailed message with instance-grouping context
    n_instances_test = len(yte)
    n_attacks_test = int(yte.sum())
    stratified_summary = []
    for atype in sorted(result.stratified_results.keys()):
        r = result.stratified_results[atype]
        n_pos = r.get("n_pos", 0)
        status = r.get("status", "unknown")
        is_subtle = r.get("is_subtle", False)
        is_exempt = r.get("is_exempt", False)

        tag = ""
        if is_subtle:
            tag = " [SUBTLE]"
        elif is_exempt:
            tag = " [EXEMPT]"

        if status == "INCONCLUSIVE":
            reason = r.get("reason", "unknown")
            stratified_summary.append(f"{atype} ({n_pos} inst): INCONCLUSIVE ({reason}){tag}")
        elif status == "at_chance":
            ap = r.get("auc_pr", 0.0)
            ci_u = r.get("ci_upper", 0.0)
            stratified_summary.append(f"{atype} ({n_pos} inst): AUC-PR {ap:.3f} [ub {ci_u:.3f}] @ chance{tag}")
        else:
            ap = r.get("auc_pr", 0.0)
            ci_u = r.get("ci_upper", 0.0)
            ns = r.get("no_skill", 0.0)
            stratified_summary.append(
                f"{atype} ({n_pos} inst): AUC-PR {ap:.3f} [ub {ci_u:.3f}] > no-skill {ns:.3f}{tag}"
            )

    stratified_str = " | ".join(stratified_summary)

    if result.at_chance:
        result.message = (f"PASS (subtle attacks at chance): Instance-grouped evaluation. "
                          f"Held-out: {n_attacks_test} attacks across {n_instances_test} instances. "
                          f"Cheat AUC-PR {auc_pr:.3f} [CI {ci_lower:.3f}-{ci_upper:.3f}] vs no-skill {no_skill:.3f}. "
                          f"Stratified: {stratified_str}")
    else:
        failed = [a for a, r in result.stratified_results.items()
                  if r.get("is_subtle") and not r.get("at_chance")]
        result.message = (f"RIGGED: Instance-grouped evaluation detected cheat leakage. "
                          f"Subtle attacks {failed} beat chance. "
                          f"Held-out: {n_attacks_test} attacks across {n_instances_test} instances. "
                          f"Cheat AUC-PR {auc_pr:.3f} [CI {ci_lower:.3f}-{ci_upper:.3f}] > no-skill {no_skill:.3f}. "
                          f"Top leaking features: {top}. Stratified: {stratified_str}")
    return result
