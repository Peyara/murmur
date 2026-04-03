"""Tests for scoring invariants layer."""

from datetime import datetime, timedelta

from src.ingest.dedup import insert_event
from src.schema import ActionType, TargetZone
from src.score.invariants import InvariantResult, check_invariants, compute_inv_score
from tests.conftest import make_event

W1 = datetime(2026, 3, 28, 10, 0, 0)
KNOWN = {"known-sa@proj.iam.gserviceaccount.com"}


def _make_events(db, specs):
    """Create and insert events from simplified specs. Returns list of CanonicalEvents."""
    events = []
    for i, spec in enumerate(specs):
        e = make_event(
            event_id=f"e{i}",
            ts=W1 + timedelta(minutes=i + 1),
            window_start=W1,
            actor_id=spec.get("actor_id", "attacker@proj"),
            action_type=spec["action_type"],
            target_zone=spec.get("target_zone", TargetZone.DATA),
            target_id=spec.get("target_id", f"target-{i}"),
            is_deploy=spec.get("is_deploy", False),
        )
        insert_event(db, e)
        events.append(e)
    return events


def _check(db, events, actor_id="attacker@proj", known=KNOWN):
    return check_invariants(db, W1, actor_id, events, known)


def _find(results, inv_id):
    return next((r for r in results if r.id == inv_id), None)


# --- INV_001: IAM policy change outside deploy ---


class TestINV001:
    def test_fires_outside_deploy(self, db):
        events = _make_events(db, [
            {"action_type": ActionType.IAM_SET_POLICY, "target_zone": TargetZone.CONTROL},
        ])
        r = _find(_check(db, events), "INV_001")
        assert r.fired is True
        assert r.severity == 5

    def test_silent_during_deploy(self, db):
        events = _make_events(db, [
            {"action_type": ActionType.IAM_SET_POLICY, "target_zone": TargetZone.CONTROL, "is_deploy": True},
        ])
        r = _find(_check(db, events), "INV_001")
        assert r.fired is False


# --- INV_002: SA key created ---


class TestINV002:
    def test_fires(self, db):
        events = _make_events(db, [
            {"action_type": ActionType.IAM_CREATE_KEY, "target_zone": TargetZone.IDENTITY},
        ])
        r = _find(_check(db, events), "INV_002")
        assert r.fired is True
        assert r.severity == 5

    def test_silent_no_key(self, db):
        events = _make_events(db, [
            {"action_type": ActionType.GCS_READ},
        ])
        r = _find(_check(db, events), "INV_002")
        assert r.fired is False


# --- INV_003: Key created by novel actor ---


class TestINV003:
    def test_fires_novel_actor(self, db):
        events = _make_events(db, [
            {"action_type": ActionType.IAM_CREATE_KEY, "actor_id": "unknown@proj",
             "target_zone": TargetZone.IDENTITY},
        ])
        r = _find(_check(db, events, actor_id="unknown@proj"), "INV_003")
        assert r.fired is True
        assert r.severity == 5

    def test_silent_known_actor(self, db):
        events = _make_events(db, [
            {"action_type": ActionType.IAM_CREATE_KEY,
             "actor_id": "known-sa@proj.iam.gserviceaccount.com",
             "target_zone": TargetZone.IDENTITY},
        ])
        r = _find(
            _check(db, events, actor_id="known-sa@proj.iam.gserviceaccount.com"),
            "INV_003",
        )
        assert r.fired is False


# --- INV_004: Impersonation ---


class TestINV004:
    def test_fires(self, db):
        events = _make_events(db, [
            {"action_type": ActionType.IAM_IMPERSONATE, "target_zone": TargetZone.IDENTITY},
        ])
        r = _find(_check(db, events), "INV_004")
        assert r.fired is True
        assert r.severity == 4

    def test_silent(self, db):
        events = _make_events(db, [
            {"action_type": ActionType.GCS_READ},
        ])
        r = _find(_check(db, events), "INV_004")
        assert r.fired is False


# --- INV_005: Impersonation rate spike ---


class TestINV005:
    def test_fires_spike(self, db):
        """5 impersonations when baseline is 2 -> fires."""
        # Insert historical: 2 impersonations in each of 3 past windows
        for d in range(1, 4):
            old_w = W1 - timedelta(days=d)
            for j in range(2):
                insert_event(db, make_event(
                    event_id=f"hist-{d}-{j}", ts=old_w + timedelta(minutes=j),
                    window_start=old_w, actor_id="attacker@proj",
                    action_type=ActionType.IAM_IMPERSONATE,
                    target_zone=TargetZone.IDENTITY,
                ))
        # Current window: 5 impersonations
        events = _make_events(db, [
            {"action_type": ActionType.IAM_IMPERSONATE, "target_zone": TargetZone.IDENTITY},
            {"action_type": ActionType.IAM_IMPERSONATE, "target_zone": TargetZone.IDENTITY},
            {"action_type": ActionType.IAM_IMPERSONATE, "target_zone": TargetZone.IDENTITY},
            {"action_type": ActionType.IAM_IMPERSONATE, "target_zone": TargetZone.IDENTITY},
            {"action_type": ActionType.IAM_IMPERSONATE, "target_zone": TargetZone.IDENTITY},
        ])
        r = _find(_check(db, events), "INV_005")
        assert r.fired is True
        assert r.severity == 5

    def test_silent_normal_rate(self, db):
        """2 impersonations when baseline is 2 -> does not fire."""
        for d in range(1, 4):
            old_w = W1 - timedelta(days=d)
            for j in range(2):
                insert_event(db, make_event(
                    event_id=f"hist-{d}-{j}", ts=old_w + timedelta(minutes=j),
                    window_start=old_w, actor_id="attacker@proj",
                    action_type=ActionType.IAM_IMPERSONATE,
                    target_zone=TargetZone.IDENTITY,
                ))
        events = _make_events(db, [
            {"action_type": ActionType.IAM_IMPERSONATE, "target_zone": TargetZone.IDENTITY},
            {"action_type": ActionType.IAM_IMPERSONATE, "target_zone": TargetZone.IDENTITY},
        ])
        r = _find(_check(db, events), "INV_005")
        assert r.fired is False

    def test_fires_zero_baseline(self, db):
        """Any impersonation with zero history -> fires."""
        events = _make_events(db, [
            {"action_type": ActionType.IAM_IMPERSONATE, "target_zone": TargetZone.IDENTITY},
        ])
        r = _find(_check(db, events), "INV_005")
        assert r.fired is True


# --- INV_006: Secret access by new actor ---


class TestINV006:
    def test_fires_new_actor(self, db):
        events = _make_events(db, [
            {"action_type": ActionType.SECRET_ACCESS, "target_zone": TargetZone.SECRET,
             "target_id": "secret/high"},
        ])
        r = _find(_check(db, events), "INV_006")
        assert r.fired is True
        assert r.severity == 5

    def test_silent_known_accessor(self, db):
        """Actor accessed this secret last week -> does not fire."""
        old_w = W1 - timedelta(days=3)
        insert_event(db, make_event(
            event_id="hist-1", ts=old_w, window_start=old_w,
            actor_id="attacker@proj", action_type=ActionType.SECRET_ACCESS,
            target_zone=TargetZone.SECRET, target_id="secret/high",
        ))
        events = _make_events(db, [
            {"action_type": ActionType.SECRET_ACCESS, "target_zone": TargetZone.SECRET,
             "target_id": "secret/high"},
        ])
        r = _find(_check(db, events), "INV_006")
        assert r.fired is False


# --- INV_007: Secret access within same window as IAM policy change ---


class TestINV007:
    def test_fires(self, db):
        events = _make_events(db, [
            {"action_type": ActionType.IAM_SET_POLICY, "target_zone": TargetZone.CONTROL},
            {"action_type": ActionType.SECRET_ACCESS, "target_zone": TargetZone.SECRET},
        ])
        r = _find(_check(db, events), "INV_007")
        assert r.fired is True
        assert r.severity == 5

    def test_silent_no_policy(self, db):
        events = _make_events(db, [
            {"action_type": ActionType.SECRET_ACCESS, "target_zone": TargetZone.SECRET},
        ])
        r = _find(_check(db, events), "INV_007")
        assert r.fired is False


# --- INV_008: KMS decrypt by new actor ---


class TestINV008:
    def test_fires_new_actor(self, db):
        events = _make_events(db, [
            {"action_type": ActionType.KMS_DECRYPT, "target_zone": TargetZone.SECRET,
             "target_id": "kms/key1"},
        ])
        r = _find(_check(db, events), "INV_008")
        assert r.fired is True
        assert r.severity == 4

    def test_silent_known_decryptor(self, db):
        old_w = W1 - timedelta(days=3)
        insert_event(db, make_event(
            event_id="hist-1", ts=old_w, window_start=old_w,
            actor_id="attacker@proj", action_type=ActionType.KMS_DECRYPT,
            target_zone=TargetZone.SECRET, target_id="kms/key1",
        ))
        events = _make_events(db, [
            {"action_type": ActionType.KMS_DECRYPT, "target_zone": TargetZone.SECRET,
             "target_id": "kms/key1"},
        ])
        r = _find(_check(db, events), "INV_008")
        assert r.fired is False


# --- INV_009: Compute metadata change ---


class TestINV009:
    def test_fires(self, db):
        events = _make_events(db, [
            {"action_type": ActionType.COMPUTE_METADATA_CHANGE,
             "target_zone": TargetZone.COMPUTE},
        ])
        r = _find(_check(db, events), "INV_009")
        assert r.fired is True
        assert r.severity == 5


# --- INV_010: New edge to SECRET/EXFIL_RISK ---


class TestINV010:
    def test_fires_new_secret_edge(self, db):
        db.execute(
            "INSERT INTO edges_window VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [W1, "attacker@proj", "DATA", "SECRET", "s1", 1, W1, True],
        )
        events = _make_events(db, [{"action_type": ActionType.GCS_READ}])
        r = _find(_check(db, events), "INV_010")
        assert r.fired is True
        assert r.severity == 5

    def test_fires_new_exfil_edge(self, db):
        db.execute(
            "INSERT INTO edges_window VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [W1, "attacker@proj", "DATA", "EXFIL_RISK", "x1", 1, W1, True],
        )
        events = _make_events(db, [{"action_type": ActionType.GCS_READ}])
        r = _find(_check(db, events), "INV_010")
        assert r.fired is True

    def test_silent_old_edge(self, db):
        db.execute(
            "INSERT INTO edges_window VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [W1, "attacker@proj", "DATA", "SECRET", "s1", 1, W1, False],
        )
        events = _make_events(db, [{"action_type": ActionType.GCS_READ}])
        r = _find(_check(db, events), "INV_010")
        assert r.fired is False


# --- INV_011: SA acting without delegation chain ---


class TestINV011:
    def _seed_history(self, db, actor_id, chained_count, unchained_count):
        """Insert historical events with/without delegation chains."""
        base = W1 - timedelta(days=7)
        for i in range(chained_count):
            e = make_event(
                event_id=f"hist-chain-{i}",
                ts=base + timedelta(hours=i),
                window_start=base + timedelta(hours=i),
                actor_id=actor_id,
                action_type=ActionType.SECRET_ACCESS,
                delegation_chain='["robot-prod@proj.iam.gserviceaccount.com"]',
            )
            insert_event(db, e)
        for i in range(unchained_count):
            e = make_event(
                event_id=f"hist-nochain-{i}",
                ts=base + timedelta(hours=chained_count + i),
                window_start=base + timedelta(hours=chained_count + i),
                actor_id=actor_id,
                delegation_chain="[]",
                action_type=ActionType.SECRET_ACCESS,
            )
            insert_event(db, e)

    def test_fires_sa_without_chain_when_historical(self, db):
        """SA with 90% historical delegation acts without chain → fire."""
        actor = "worker-sa@proj.iam.gserviceaccount.com"
        self._seed_history(db, actor, chained_count=18, unchained_count=2)
        events = _make_events(db, [
            {"actor_id": actor, "action_type": ActionType.SECRET_ACCESS,
             "target_zone": TargetZone.SECRET},
        ])
        # Current events have no delegation_chain (default is "[]")
        r = _find(_check(db, events, actor_id=actor), "INV_011")
        assert r.fired is True
        assert r.severity == 5
        assert "delegation chain" in r.explanation

    def test_silent_when_chain_present(self, db):
        """SA with delegation chain in current window → silent."""
        actor = "worker-sa@proj.iam.gserviceaccount.com"
        self._seed_history(db, actor, chained_count=18, unchained_count=2)
        e = make_event(
            event_id="current-chained",
            ts=W1 + timedelta(minutes=1),
            window_start=W1,
            actor_id=actor,
            action_type=ActionType.SECRET_ACCESS,
            delegation_chain='["robot-prod@proj.iam.gserviceaccount.com"]',
        )
        insert_event(db, e)
        r = _find(_check(db, [e], actor_id=actor), "INV_011")
        assert r.fired is False

    def test_silent_for_human_actor(self, db):
        """Human actors (not .iam.gserviceaccount.com) → always silent."""
        events = _make_events(db, [
            {"actor_id": "admin@company.com", "action_type": ActionType.IAM_SET_POLICY},
        ])
        r = _find(_check(db, events, actor_id="admin@company.com"), "INV_011")
        assert r.fired is False

    def test_silent_insufficient_history(self, db):
        """SA with <10 historical events → silent (not enough to baseline)."""
        actor = "new-sa@proj.iam.gserviceaccount.com"
        self._seed_history(db, actor, chained_count=5, unchained_count=0)
        events = _make_events(db, [
            {"actor_id": actor, "action_type": ActionType.SECRET_ACCESS},
        ])
        r = _find(_check(db, events, actor_id=actor), "INV_011")
        assert r.fired is False

    def test_silent_low_chain_ratio(self, db):
        """SA with <80% historical chains → not expected to have chains."""
        actor = "mixed-sa@proj.iam.gserviceaccount.com"
        self._seed_history(db, actor, chained_count=5, unchained_count=10)
        events = _make_events(db, [
            {"actor_id": actor, "action_type": ActionType.SECRET_ACCESS},
        ])
        r = _find(_check(db, events, actor_id=actor), "INV_011")
        assert r.fired is False


# --- inv_score computation ---


class TestInvScore:
    def test_no_fires(self):
        results = [
            InvariantResult("INV_001", False, 0, ""),
            InvariantResult("INV_002", False, 0, ""),
        ]
        score, count, json_str = compute_inv_score(results)
        assert score == 0
        assert count == 0
        assert json_str == "[]"

    def test_single_fire(self):
        results = [
            InvariantResult("INV_001", True, 5, "policy change"),
            InvariantResult("INV_002", False, 0, ""),
        ]
        score, count, json_str = compute_inv_score(results)
        assert score == 5
        assert count == 1
        assert "INV_001" in json_str

    def test_max_severity(self):
        results = [
            InvariantResult("INV_004", True, 4, "impersonation"),
            InvariantResult("INV_001", True, 5, "policy change"),
        ]
        score, count, _ = compute_inv_score(results)
        assert score == 5
        assert count == 2

    def test_fired_json_contains_all(self):
        results = [
            InvariantResult("INV_001", True, 5, "a"),
            InvariantResult("INV_004", True, 4, "b"),
            InvariantResult("INV_009", True, 5, "c"),
        ]
        _, count, json_str = compute_inv_score(results)
        assert count == 3
        import json
        fired = json.loads(json_str)
        assert sorted(fired) == ["INV_001", "INV_004", "INV_009"]
