import random


class ProvenanceGenerator:
    """Generates trigger_ref patterns for synthetic GCP audit log events.

    Patterns range from valid benign provenance to attack-grade evasion
    techniques (forged, partial, missing references).
    """

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)  # noqa: S311  # nosec B311
        self.trigger_counter = 0

    def benign_trigger_ref(self, actor_email: str) -> str:
        """Generate a valid Cloud Scheduler trigger_ref.

        Represents a real, verifiable scheduled job invocation.

        Args:
            actor_email: Actor email (used to derive role for naming)

        Returns:
            Valid Cloud Scheduler resource path
        """
        parts = actor_email.split("-")
        role = parts[0] if parts else "unknown"
        job_id = f"trigger-{role}-{self.trigger_counter}"
        self.trigger_counter += 1
        return f"projects/synth-project/locations/us-central1/jobs/{job_id}"

    def no_trigger_ref(self) -> None:
        """Return None for events with no provenance.

        Represents interactive/manual actions with no scheduled job backing.
        Useful for attacks that have no provenance trail.

        Returns:
            None
        """
        return None

    def forged_trigger_ref(self, actor_email: str) -> str:
        """Generate a plausible but non-matching Cloud Scheduler trigger_ref.

        Represents an attacker's attempt to blend in by mimicking scheduled job
        provenance. The reference LOOKS valid but the job ID doesn't exist in
        reality.

        Args:
            actor_email: Actor email

        Returns:
            Maliciously crafted Cloud Scheduler path that doesn't resolve
        """
        # Generate a short random hex string to make it look random but consistent
        hash_val = f"{self.rng.randint(0, 0xFFFFFF):06x}"
        return f"projects/synth-project/locations/us-central1/jobs/forged-{hash_val}"

    def partial_trigger_ref(self, actor_email: str) -> str:
        """Generate a malformed/incomplete Cloud Scheduler trigger_ref.

        Represents weak or broken provenance — the reference is present but
        doesn't fully resolve. Could be truncated, missing the job ID, or
        referencing a deleted job.

        Args:
            actor_email: Actor email

        Returns:
            Incomplete or malformed Cloud Scheduler path
        """
        # Randomly choose one of several malformation patterns
        pattern = self.rng.choice(
            [
                # Trailing slash, no job name
                "projects/synth-project/locations/us-central1/jobs/",
                # Missing location
                "projects/synth-project/locations//jobs/deleted-job",
                # Truncated path
                "projects/synth-project/locations/us-central1",
                # Missing project
                "locations/us-central1/jobs/partial-job",
            ]
        )
        return pattern

    def add_trigger_ref(self, event: dict, trigger_ref: str | None) -> dict:
        """Attach a trigger_ref to an event's metadata.

        If trigger_ref is None, no metadata is added.

        Args:
            event: Event dict to modify
            trigger_ref: Trigger reference string or None

        Returns:
            Modified event dict
        """
        if trigger_ref:
            if "metadata" not in event:
                event["metadata"] = {}
            event["metadata"]["trigger_ref"] = trigger_ref
        return event
