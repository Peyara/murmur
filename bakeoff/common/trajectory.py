"""
Shared trajectory representation for P1/P2 estimators and mechanism tests.

A trajectory is the time-ordered sequence of an actor's state transitions
over a resource graph. Used as input to all physics estimators and
constructed-input builders for mechanism tests.

All classes are immutable. Determinism is enforced by using
frozenlist-like containers (tuple-based) and explicit seed threading.
"""

from dataclasses import dataclass
from typing import Sequence, FrozenSet, Tuple
from itertools import islice


@dataclass(frozen=True)
class Transition:
    """
    A single state transition in an actor's trajectory.

    Immutable; hashable for use in sets/dicts.

    Attributes:
        t: float — timestamp (seconds since epoch, or any monotonic real-valued time).
        actor: str — actor identifier (user, service account, etc.).
        src: str — source resource/state identifier.
        dst: str — destination resource/state identifier.
        action: str — action type (e.g., 'auth', 'read', 'write', 'invoke', 'grant', 'assume').
    """
    t: float
    actor: str
    src: str
    dst: str
    action: str

    def __hash__(self):
        return hash((self.t, self.actor, self.src, self.dst, self.action))


class Trajectory:
    """
    Time-ordered sequence of transitions for a single actor.

    Immutable; backed by a tuple to guarantee no post-construction mutation.
    Provides constructors and helper methods for both estimators and test harnesses.

    Usage:
        # From a sequence of (src, dst, action) tuples with uniform timestamps:
        traj = Trajectory.from_state_visits(
            actor='user@example.com',
            states=['IDENTITY', 'COMPUTE', 'DATA', 'COMPUTE'],
            actions=['auth', 'read', 'write', 'read'],
            start_time=0.0,
            dt=1.0
        )

        # From explicit Transition objects:
        traj = Trajectory(transitions=[t1, t2, t3])

        # From edge multiset (for mechanism tests):
        traj = Trajectory.from_edge_multiset(
            actor='test_actor',
            edges=[('A', 'B', 'move'), ('B', 'C', 'move'), ('B', 'A', 'move')],
            start_time=0.0,
            dt=1.0
        )

        # Access and iteration:
        for transition in traj:
            print(transition)
        print(len(traj))
        print(traj[0])
    """

    def __init__(self, transitions: Sequence[Transition]) -> None:
        """
        Initialize a trajectory from a sequence of Transition objects.

        Args:
            transitions: sequence of Transition objects, in time order.
                        Will be converted to tuple for immutability.

        Raises:
            ValueError: if transitions is empty or not time-ordered.
        """
        if not transitions:
            raise ValueError("Trajectory must contain at least one transition.")

        # Verify time-ordered.
        times = [t.t for t in transitions]
        if times != sorted(times):
            raise ValueError("Transitions must be time-ordered (ascending t).")

        # Verify all transitions belong to same actor.
        actors = set(t.actor for t in transitions)
        if len(actors) > 1:
            raise ValueError(
                f"All transitions must belong to same actor; got {actors}."
            )

        self._transitions: Tuple[Transition, ...] = tuple(transitions)
        self._actor = self._transitions[0].actor

    @property
    def actor(self) -> str:
        """Actor ID for this trajectory."""
        return self._actor

    @property
    def transitions(self) -> Tuple[Transition, ...]:
        """Immutable tuple of transitions."""
        return self._transitions

    def __len__(self) -> int:
        """Number of transitions in this trajectory."""
        return len(self._transitions)

    def __iter__(self):
        """Iterate over transitions in order."""
        return iter(self._transitions)

    def __getitem__(self, index: int) -> Transition:
        """Index into transitions."""
        return self._transitions[index]

    def __repr__(self) -> str:
        return (
            f"Trajectory(actor={self._actor!r}, "
            f"length={len(self._transitions)}, "
            f"t_start={self._transitions[0].t}, "
            f"t_end={self._transitions[-1].t})"
        )

    @classmethod
    def from_state_visits(
        cls,
        actor: str,
        states: Sequence[str],
        actions: Sequence[str],
        start_time: float = 0.0,
        dt: float = 1.0,
    ) -> "Trajectory":
        """
        Construct a trajectory from a sequence of state visits with uniform time spacing.

        Creates transitions (state[i] -> state[i+1]) with evenly-spaced timestamps.

        Args:
            actor: actor identifier.
            states: sequence of state/resource identifiers, length n.
            actions: sequence of action types, length n-1 (one per edge).
            start_time: initial timestamp.
            dt: time delta between consecutive transitions.

        Returns:
            Trajectory object.

        Raises:
            ValueError: if len(actions) != len(states) - 1.
        """
        if len(actions) != len(states) - 1:
            raise ValueError(
                f"Expected {len(states) - 1} actions for {len(states)} states; "
                f"got {len(actions)}."
            )

        transitions = []
        for i, (src, dst, action) in enumerate(zip(states[:-1], states[1:], actions)):
            t = start_time + i * dt
            transitions.append(Transition(t=t, actor=actor, src=src, dst=dst, action=action))

        return cls(transitions)

    @classmethod
    def from_edge_multiset(
        cls,
        actor: str,
        edges: Sequence[Tuple[str, str, str]],
        start_time: float = 0.0,
        dt: float = 1.0,
    ) -> "Trajectory":
        """
        Construct a trajectory from an unordered multiset of (src, dst, action) edges.

        Useful for mechanism tests where the order matters but edges are specified as a set.
        Edges are consumed in the order given; timestamps are assigned sequentially.

        Args:
            actor: actor identifier.
            edges: sequence of (src, dst, action) tuples.
            start_time: initial timestamp.
            dt: time delta between consecutive transitions.

        Returns:
            Trajectory object.

        Raises:
            ValueError: if edges is empty.
        """
        if not edges:
            raise ValueError("Edge multiset must be non-empty.")

        transitions = []
        for i, (src, dst, action) in enumerate(edges):
            t = start_time + i * dt
            transitions.append(Transition(t=t, actor=actor, src=src, dst=dst, action=action))

        return cls(transitions)

    def state_space(self) -> FrozenSet[str]:
        """
        Return the set of all states visited in this trajectory.

        Returns:
            frozenset of state identifiers.
        """
        states = set()
        for trans in self._transitions:
            states.add(trans.src)
            states.add(trans.dst)
        return frozenset(states)

    def edges(self) -> Tuple[Tuple[str, str, str], ...]:
        """
        Return all (src, dst, action) edges in this trajectory, in order.

        Returns:
            tuple of (src, dst, action) tuples.
        """
        return tuple((t.src, t.dst, t.action) for t in self._transitions)

    def window(self, t_start: float, t_end: float) -> "Trajectory":
        """
        Extract a sub-trajectory within a time window [t_start, t_end).

        Transitions with t_start <= t < t_end are included.

        Args:
            t_start: window start time (inclusive).
            t_end: window end time (exclusive).

        Returns:
            New Trajectory object containing only transitions in the window.

        Raises:
            ValueError: if the result window is empty.
        """
        windowed = [
            t for t in self._transitions if t_start <= t.t < t_end
        ]
        if not windowed:
            raise ValueError(
                f"Window [{t_start}, {t_end}) contains no transitions."
            )
        return Trajectory(windowed)

    def time_reversed(self) -> "Trajectory":
        """
        Return a time-reversed copy of this trajectory.

        Transitions are reordered in reverse, and src/dst are swapped
        (so the reversed trajectory visits states in reverse order).
        Timestamps are negated and reordered; the returned trajectory will
        have t_start < t_end as usual.

        Used for mechanism test 3 (reversal sanity).

        Returns:
            New Trajectory with edges reversed and src/dst swapped.
        """
        reversed_transitions = []
        max_t = self._transitions[-1].t
        for trans in reversed(self._transitions):
            # Reverse the edge direction and negate time for sorting.
            new_t = max_t - trans.t
            reversed_transitions.append(
                Transition(
                    t=new_t,
                    actor=trans.actor,
                    src=trans.dst,
                    dst=trans.src,
                    action=trans.action,
                )
            )

        # Re-sort by time to maintain time-ordered property.
        reversed_transitions.sort(key=lambda t: t.t)
        return Trajectory(reversed_transitions)

    def truncate(self, length: int) -> "Trajectory":
        """
        Return a truncated copy containing the first `length` transitions.

        Used for mechanism test 4 (convergence via subsampling).

        Args:
            length: number of transitions to keep.

        Raises:
            ValueError: if length > trajectory length or length < 1.
        """
        if length < 1 or length > len(self):
            raise ValueError(
                f"Cannot truncate to length {length} (trajectory has {len(self)})."
            )
        return Trajectory(list(islice(self._transitions, length)))
