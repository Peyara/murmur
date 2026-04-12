"""ProvenanceGenerator — attach trigger refs to orchestrated workflows."""

import random


class ProvenanceGenerator:
    """Generate provenance metadata for workflows."""

    def __init__(self, seed: int = 42):
        """Initialize provenance generator.

        Args:
            seed: Random seed
        """
        self.rng = random.Random(seed)
        self.trigger_counter = 0

    def benign_trigger_ref(self, actor_email: str) -> str:
        """Generate a trigger ref for benign orchestrated workflows.

        Format: projects/synth-project/locations/us-central1/jobs/trigger-{role}-{N}
        This matches Cloud Scheduler job naming convention.

        Args:
            actor_email: Actor email (used to extract role)

        Returns:
            Trigger ref string
        """
        # Extract role from email: "deployer-sa-0@..." -> "deployer"
        parts = actor_email.split("-")
        role = parts[0] if parts else "unknown"

        # Generate job ID
        job_id = f"trigger-{role}-{self.trigger_counter}"
        self.trigger_counter += 1

        return f"projects/synth-project/locations/us-central1/jobs/{job_id}"

    def add_trigger_ref(self, event: dict, trigger_ref: str | None) -> dict:
        """Add trigger_ref to event metadata.

        Args:
            event: Raw GCP audit log event dict
            trigger_ref: Trigger ref string or None

        Returns:
            Modified event dict
        """
        if trigger_ref:
            if "metadata" not in event:
                event["metadata"] = {}
            event["metadata"]["trigger_ref"] = trigger_ref
        return event
