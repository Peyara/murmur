import random


class ProvenanceGenerator:
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)  # noqa: S311  # nosec B311
        self.trigger_counter = 0

    def benign_trigger_ref(self, actor_email: str) -> str:
        parts = actor_email.split("-")
        role = parts[0] if parts else "unknown"
        job_id = f"trigger-{role}-{self.trigger_counter}"
        self.trigger_counter += 1
        return f"projects/synth-project/locations/us-central1/jobs/{job_id}"

    def add_trigger_ref(self, event: dict, trigger_ref: str | None) -> dict:
        if trigger_ref:
            if "metadata" not in event:
                event["metadata"] = {}
            event["metadata"]["trigger_ref"] = trigger_ref
        return event
