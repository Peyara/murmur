"""TrajectoryComposer — orchestrate actors, workflows, and temporal patterns."""

import json
import random
from datetime import datetime, timedelta

from src.synthetic.actors import ActorPopulation
from src.synthetic.provenance import ProvenanceGenerator
from src.synthetic.temporal import TemporalEngine
from src.synthetic.workflows import WorkflowTemplates


class TrajectoryComposer:
    """Compose synthetic audit log trajectory from actors and workflows."""

    def __init__(
        self,
        actors: int = 10,
        windows: int = 20,
        attack_ratio: float = 0.1,
        seed: int = 42,
    ):
        """Initialize composer.

        Args:
            actors: Number of service account actors (5-50)
            windows: Number of 15-minute windows (5-100)
            attack_ratio: Fraction of windows to inject attacks (0.0-1.0)
            seed: Random seed
        """
        self.actors = ActorPopulation(actors, seed)
        self.temporal = TemporalEngine(seed)
        self.provenance = ProvenanceGenerator(seed)
        self.rng = random.Random(seed)

        self.window_count = max(5, min(100, windows))
        self.attack_ratio = max(0.0, min(1.0, attack_ratio))
        self.seed = seed

        self.event_counter = 0
        self.events: list[dict] = []

    def compose(self) -> list[dict]:
        """Generate full trajectory.

        Returns:
            List of raw GCP audit log dicts, sorted by timestamp
        """
        self.events = []
        self.event_counter = 0

        windows = self.temporal.get_windows(self.window_count)

        # Decide which windows get attacks
        attack_windows = set()
        attack_count = int(self.window_count * self.attack_ratio)
        if attack_count > 0:
            attack_windows = set(
                self.rng.sample(range(self.window_count), attack_count)
            )

        # Generate events for each window
        for window_idx, window_start in enumerate(windows):
            window_end = window_start + timedelta(minutes=15)

            if window_idx in attack_windows:
                # Attack window
                self._generate_attack_window(window_start, window_end)
            else:
                # Benign window
                self._generate_benign_window(window_start, window_end)

            # Add background noise
            self._generate_background_noise(window_start, window_end)

        # Sort by timestamp
        self.events.sort(key=lambda e: e["timestamp"])

        return self.events

    def _generate_benign_window(self, window_start: datetime, window_end: datetime):
        """Generate benign events in a window."""
        # Pick 1-2 benign workflows
        workflow_count = self.rng.randint(1, 2)
        for _ in range(workflow_count):
            workflow_template = self.rng.choice(WorkflowTemplates.get_benign_workflows())
            actor = self.rng.choice(self.actors.get_by_role("worker"))

            # Determine if this is scheduler-delegated
            scheduler_actor = None
            if self.rng.random() < 0.5:
                scheduler_actor = self.rng.choice(
                    self.actors.get_by_role("scheduler")
                )

            # Pick a random start time in the window
            workflow_start = self.temporal.uniform_random_time(
                window_start, window_end
            )

            trigger_ref = self.provenance.benign_trigger_ref(
                scheduler_actor.email if scheduler_actor else actor.email
            )

            # Generate events from workflow
            for step in workflow_template:
                event_time = workflow_start + timedelta(seconds=step.offset_sec)

                # Clamp to window if necessary
                if event_time >= window_end:
                    continue

                event = self._create_raw_event(
                    actor_email=actor.email,
                    service_name=step.service_name,
                    method_name=step.method_name,
                    resource_name=step.resource_pattern,
                    timestamp=event_time,
                    log_name_suffix=step.log_name_suffix,
                    trigger_ref=trigger_ref,
                    delegated_from_email=scheduler_actor.email if scheduler_actor else None,
                )

                self.events.append(event)

    def _generate_attack_window(self, window_start: datetime, window_end: datetime):
        """Generate attack events in a window."""
        # Pick 1-2 attack workflows
        workflow_count = self.rng.randint(1, 2)
        for _ in range(workflow_count):
            workflow_template = self.rng.choice(WorkflowTemplates.get_attack_workflows())

            # Attacker always initiates (no provenance)
            actor = self.rng.choice(self.actors.get_by_role("attacker"))
            if not actor:
                # Fallback: use any actor
                actor = self.rng.choice(self.actors.get_all())

            # Pick a random start time in the window
            workflow_start = self.temporal.uniform_random_time(
                window_start, window_end
            )

            # No trigger_ref for attacks
            for step in workflow_template:
                event_time = workflow_start + timedelta(seconds=step.offset_sec)

                # Clamp to window
                if event_time >= window_end:
                    continue

                event = self._create_raw_event(
                    actor_email=actor.email,
                    service_name=step.service_name,
                    method_name=step.method_name,
                    resource_name=step.resource_pattern,
                    timestamp=event_time,
                    log_name_suffix=step.log_name_suffix,
                    trigger_ref=None,  # Attacks have no provenance
                )

                self.events.append(event)

    def _generate_background_noise(
        self, window_start: datetime, window_end: datetime
    ):
        """Add routine background events (routine reads, etc.)."""
        # 5-10 background events per window
        noise_count = self.rng.randint(5, 10)

        for _ in range(noise_count):
            # Random actor
            actor = self.rng.choice(self.actors.get_all())

            # Random timestamp
            event_time = self.temporal.uniform_random_time(
                window_start, window_end
            )

            # Determine if this should be scheduler-delegated
            scheduler_actor = None
            if self.rng.random() < 0.4:
                scheduler_actor = self.rng.choice(
                    self.actors.get_by_role("scheduler")
                )

            trigger_ref = None
            if self.rng.random() < 0.7:
                trigger_ref = self.provenance.benign_trigger_ref(
                    scheduler_actor.email if scheduler_actor else actor.email
                )

            # Routine actions: GCS_READ, BQ_JOB_SUBMIT, GCS_LIST
            action = self.rng.choice(["gcs_read", "bq_query", "gcs_list"])

            if action == "gcs_read":
                event = self._create_raw_event(
                    actor_email=actor.email,
                    service_name="storage.googleapis.com",
                    method_name="storage.objects.get",
                    resource_name="projects/_/buckets/data-bucket/objects/file.csv",
                    timestamp=event_time,
                    log_name_suffix="data_access",
                    trigger_ref=trigger_ref,
                    delegated_from_email=scheduler_actor.email if scheduler_actor else None,
                )
            elif action == "bq_query":
                event = self._create_raw_event(
                    actor_email=actor.email,
                    service_name="bigquery.googleapis.com",
                    method_name="jobservice.insert",
                    resource_name="projects/synth-project/jobs/query-noise",
                    timestamp=event_time,
                    log_name_suffix="activity",
                    trigger_ref=trigger_ref,
                    delegated_from_email=scheduler_actor.email if scheduler_actor else None,
                )
            else:  # gcs_list
                event = self._create_raw_event(
                    actor_email=actor.email,
                    service_name="storage.googleapis.com",
                    method_name="storage.objects.list",
                    resource_name="projects/_/buckets/data-bucket",
                    timestamp=event_time,
                    log_name_suffix="data_access",
                    trigger_ref=None,
                    delegated_from_email=None,
                )

            self.events.append(event)

    def _create_raw_event(
        self,
        actor_email: str,
        service_name: str,
        method_name: str,
        resource_name: str,
        timestamp: datetime,
        log_name_suffix: str,
        trigger_ref: str | None = None,
        delegated_from_email: str | None = None,
    ) -> dict:
        """Create a raw GCP audit log event dict."""
        insert_id = f"synth-evt-{self.event_counter:06d}"
        self.event_counter += 1

        # ISO 8601 timestamp with Z
        ts_str = timestamp.isoformat(timespec="milliseconds") + "Z"

        auth_info = {
            "principalEmail": actor_email,
        }

        # Add delegation chain if present
        if delegated_from_email:
            auth_info["serviceAccountDelegationInfo"] = [
                {
                    "firstPartyPrincipal": {
                        "principalEmail": delegated_from_email,
                    }
                }
            ]

        event = {
            "protoPayload": {
                "@type": "type.googleapis.com/google.cloud.audit.v1.AuditLog",
                "serviceName": service_name,
                "methodName": method_name,
                "authenticationInfo": auth_info,
                "resourceName": resource_name,
                "status": {},
            },
            "resource": {
                "type": "service_account" if "serviceAccounts" in resource_name
                else "gcs_bucket" if "buckets" in resource_name
                else "bigquery" if "bigquery" in resource_name
                else "compute" if "instances" in resource_name
                else "secretmanager.googleapis.com/Secret" if "secrets" in resource_name
                else "other",
                "labels": {
                    "project_id": "synth-project",
                },
            },
            "timestamp": ts_str,
            "insertId": insert_id,
            "logName": f"projects/synth-project/logs/cloudaudit.googleapis.com%2F{log_name_suffix}",
        }

        # Add provenance if present
        if trigger_ref:
            event["metadata"] = {
                "trigger_ref": trigger_ref,
            }

        return event
