import random
from datetime import datetime, timedelta

from src.synthetic.actors import ActorPopulation
from src.synthetic.provenance import ProvenanceGenerator
from src.synthetic.temporal import TemporalEngine
from src.synthetic.workflows import WorkflowTemplates


class TrajectoryComposer:
    def __init__(
        self,
        actors: int = 10,
        windows: int = 20,
        attack_ratio: float = 0.1,
        seed: int = 42,
    ):
        self.actors = ActorPopulation(actors, seed)
        self.temporal = TemporalEngine(seed)
        self.provenance = ProvenanceGenerator(seed)
        self.rng = random.Random(seed)  # noqa: S311  # nosec B311
        self.window_count = max(5, min(100, windows))
        self.attack_ratio = max(0.0, min(1.0, attack_ratio))
        self.seed = seed
        self.event_counter = 0
        self.events: list[dict] = []

    def compose(self) -> list[dict]:
        self.events = []
        self.event_counter = 0
        windows = self.temporal.get_windows(self.window_count)
        attack_windows = set()
        attack_count = int(self.window_count * self.attack_ratio)
        if attack_count > 0:
            attack_windows = set(self.rng.sample(range(self.window_count), attack_count))

        for window_idx, window_start in enumerate(windows):
            window_end = window_start + timedelta(minutes=15)
            if window_idx in attack_windows:
                self._generate_attack_window(window_start, window_end)
            else:
                self._generate_benign_window(window_start, window_end)
            self._generate_background_noise(window_start, window_end)

        self.events.sort(key=lambda e: e["timestamp"])
        return self.events

    def _generate_benign_window(
        self, window_start: datetime, window_end: datetime
    ):
        workflow_count = self.rng.randint(1, 2)
        for _ in range(workflow_count):
            workflow_template = self.rng.choice(
                WorkflowTemplates.get_benign_workflows()
            )
            actor = self.rng.choice(self.actors.get_by_role("worker"))
            scheduler_actor = None
            if self.rng.random() < 0.5:
                sched = self.rng.choice(self.actors.get_by_role("scheduler"))
                scheduler_actor = sched if sched else None
            workflow_start = self.temporal.uniform_random_time(
                window_start, window_end
            )
            sched_email = (
                scheduler_actor.email if scheduler_actor else actor.email
            )
            trigger_ref = self.provenance.benign_trigger_ref(sched_email)
            for step in workflow_template:
                event_time = workflow_start + timedelta(seconds=step.offset_sec)
                if event_time >= window_end:
                    continue
                delegated_email = (
                    scheduler_actor.email if scheduler_actor else None
                )
                event = self._create_raw_event(
                    actor.email,
                    step.service_name,
                    step.method_name,
                    step.resource_pattern,
                    event_time,
                    step.log_name_suffix,
                    trigger_ref,
                    delegated_email,
                )
                self.events.append(event)

    def _generate_attack_window(
        self, window_start: datetime, window_end: datetime
    ):
        workflow_count = self.rng.randint(1, 2)
        for _ in range(workflow_count):
            workflow_template = self.rng.choice(
                WorkflowTemplates.get_attack_workflows()
            )
            actor = self.rng.choice(self.actors.get_by_role("attacker"))
            if not actor:
                actor = self.rng.choice(self.actors.get_all())
            workflow_start = self.temporal.uniform_random_time(
                window_start, window_end
            )
            for step in workflow_template:
                event_time = workflow_start + timedelta(seconds=step.offset_sec)
                if event_time >= window_end:
                    continue
                event = self._create_raw_event(
                    actor.email,
                    step.service_name,
                    step.method_name,
                    step.resource_pattern,
                    event_time,
                    step.log_name_suffix,
                    None,
                )
                self.events.append(event)

    def _generate_background_noise(
        self, window_start: datetime, window_end: datetime
    ):
        noise_count = self.rng.randint(5, 10)
        for _ in range(noise_count):
            actor = self.rng.choice(self.actors.get_all())
            event_time = self.temporal.uniform_random_time(
                window_start, window_end
            )
            scheduler_actor = None
            if self.rng.random() < 0.4:
                sched = self.rng.choice(self.actors.get_by_role("scheduler"))
                scheduler_actor = sched if sched else None
            trigger_ref = None
            if self.rng.random() < 0.7:
                sched_email = (
                    scheduler_actor.email if scheduler_actor else actor.email
                )
                trigger_ref = self.provenance.benign_trigger_ref(sched_email)
            action = self.rng.choice(["gcs_read", "bq_query", "gcs_list"])
            delegated_email = scheduler_actor.email if scheduler_actor else None
            if action == "gcs_read":
                event = self._create_raw_event(
                    actor.email,
                    "storage.googleapis.com",
                    "storage.objects.get",
                    "projects/_/buckets/data-bucket/objects/file.csv",
                    event_time,
                    "data_access",
                    trigger_ref,
                    delegated_email,
                )
            elif action == "bq_query":
                event = self._create_raw_event(
                    actor.email,
                    "bigquery.googleapis.com",
                    "jobservice.insert",
                    "projects/synth-project/jobs/query-noise",
                    event_time,
                    "activity",
                    trigger_ref,
                    delegated_email,
                )
            else:
                event = self._create_raw_event(
                    actor.email,
                    "storage.googleapis.com",
                    "storage.objects.list",
                    "projects/_/buckets/data-bucket",
                    event_time,
                    "data_access",
                    None,
                    None,
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
        insert_id = f"synth-evt-{self.event_counter:06d}"
        self.event_counter += 1
        ts_str = timestamp.isoformat(timespec="milliseconds") + "Z"
        auth_info = {"principalEmail": actor_email}
        if delegated_from_email:
            delegation_info = {
                "firstPartyPrincipal": {"principalEmail": delegated_from_email}
            }
            auth_info["serviceAccountDelegationInfo"] = [delegation_info]

        # Determine resource type based on resource_name
        if "serviceAccounts" in resource_name:
            resource_type = "service_account"
        elif "buckets" in resource_name:
            resource_type = "gcs_bucket"
        elif "bigquery" in resource_name:
            resource_type = "bigquery"
        elif "instances" in resource_name:
            resource_type = "compute"
        elif "secrets" in resource_name:
            resource_type = "secretmanager.googleapis.com/Secret"
        else:
            resource_type = "other"

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
                "type": resource_type,
                "labels": {"project_id": "synth-project"},
            },
            "timestamp": ts_str,
            "insertId": insert_id,
            "logName": (
                f"projects/synth-project/logs/"
                f"cloudaudit.googleapis.com%2F{log_name_suffix}"
            ),
        }
        if trigger_ref:
            event["metadata"] = {"trigger_ref": trigger_ref}
        return event
