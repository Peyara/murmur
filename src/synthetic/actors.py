import random
from dataclasses import dataclass

@dataclass
class Actor:
    email: str
    role: str
    home_zone: str
    action_types: list[str]

class ActorPopulation:
    ROLE_TEMPLATES = {
        "admin": {"home_zone": "CONTROL", "action_types": ["IAM_SET_POLICY", "IAM_CREATE_SA", "SCHEDULER_ADMIN", "COMPUTE_CREATE"]},
        "deployer": {"home_zone": "CONTROL", "action_types": ["COMPUTE_CREATE", "IAM_SET_POLICY", "GCS_READ", "GCS_WRITE"]},
        "scheduler": {"home_zone": "CONTROL", "action_types": ["SCHEDULER_ADMIN", "IAM_IMPERSONATE", "GCS_READ"]},
        "worker": {"home_zone": "DATA", "action_types": ["GCS_READ", "GCS_WRITE", "GCS_LIST", "SECRET_ACCESS", "BQ_JOB_SUBMIT"]},
        "attacker": {"home_zone": "IDENTITY", "action_types": ["IAM_CREATE_KEY", "IAM_DELETE_KEY", "IAM_IMPERSONATE", "SECRET_ACCESS", "GCS_READ", "KMS_DECRYPT"]},
    }

    def __init__(self, count: int, seed: int = 42):
        self.count = max(5, min(50, count))
        self.rng = random.Random(seed)
        self.actors = []
        self._generate_actors()

    def _generate_actors(self):
        roles = ["admin"] + ["deployer"] * self.rng.randint(1, 2) + ["scheduler"] * self.rng.randint(1, 2)
        worker_count = max(1, self.count - len(roles) - self.rng.randint(1, 3))
        roles.extend(["worker"] * worker_count)
        attacker_count = min(3, max(1, self.count - len(roles)))
        roles.extend(["attacker"] * attacker_count)
        self.rng.shuffle(roles)
        
        for i, role in enumerate(roles[:self.count]):
            template = self.ROLE_TEMPLATES[role]
            email = f"{role}-sa-{i}@synth-project.iam.gserviceaccount.com"
            self.actors.append(Actor(email, role, template["home_zone"], template["action_types"]))

    def get_all(self): return self.actors
    def get_by_role(self, role): return [a for a in self.actors if a.role == role]
    def get_random(self): return self.rng.choice(self.actors)
    def get_random_by_role(self, role): matching = self.get_by_role(role); return self.rng.choice(matching) if matching else None
