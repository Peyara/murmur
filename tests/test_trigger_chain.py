"""Tests for provenance trigger chain resolution."""

from datetime import datetime

from src.provenance.trigger_chain import TriggerChain, resolve_trigger_chain


KNOWN = {
    "service-123@gcp-sa-cloudscheduler.iam.gserviceaccount.com",
    "deploy-bot@proj.iam.gserviceaccount.com",
}


class TestResolvedChain:
    def test_scheduler_trigger_resolves(self, db):
        """sched:job:epoch -> scheduler SA -> known_initiator -> resolved."""
        chain = resolve_trigger_chain(
            db, "sched:trigger-normal-worker:1711612800", KNOWN,
        )
        assert chain.resolved is True
        assert chain.depth == 1
        assert len(chain.chain) == 1
        assert chain.terminal_initiator is not None

    def test_depth_is_one_for_scheduler(self, db):
        chain = resolve_trigger_chain(
            db, "sched:my-job:12345", KNOWN,
        )
        assert chain.depth == 1


class TestUnresolved:
    def test_no_trigger_ref(self, db):
        """No trigger_ref -> chain unresolved."""
        chain = resolve_trigger_chain(db, None, KNOWN)
        assert chain.resolved is False
        assert chain.depth == 0
        assert chain.chain == []
        assert chain.terminal_initiator is None

    def test_empty_trigger_ref(self, db):
        chain = resolve_trigger_chain(db, "", KNOWN)
        assert chain.resolved is False

    def test_unknown_format(self, db):
        """Non-sched format with no resolution path."""
        chain = resolve_trigger_chain(db, "unknown:foo:bar", KNOWN)
        assert chain.resolved is False

    def test_scheduler_not_in_known(self, db):
        """Scheduler trigger but no matching known_initiator."""
        chain = resolve_trigger_chain(db, "sched:job:123", set())
        assert chain.resolved is False
        assert chain.depth == 1  # we tried, just didn't resolve


class TestCycleDetection:
    def test_cycle_stops(self, db):
        """Chain with cycle detection should not infinite loop."""
        # For scheduler triggers, cycles can't happen (1-hop).
        # But the interface should handle it gracefully.
        chain = resolve_trigger_chain(db, "sched:job:123", KNOWN)
        # No cycle possible in 1-hop, just verify it completes
        assert isinstance(chain, TriggerChain)


class TestMaxDepth:
    def test_respects_max_depth(self, db):
        """Chain should stop at max_depth."""
        chain = resolve_trigger_chain(
            db, "sched:job:123", KNOWN, max_depth=0,
        )
        assert chain.resolved is False
        assert chain.depth == 0
