"""ActorPopulation — generate service account actors with roles and capabilities."""

import random
from dataclasses import dataclass


@dataclass
class Actor:
    """A service account actor with role-based capabilities."""

    email: str
    role: str  # admin, deployer, scheduler, worker, attacker
    home_zone: str  # IDENTITY, CONTROL, DATA, COMPUTE, SECRET
    action_types: list[str]  # Actions this actor typically performs


class ActorPopulation:
    """Generate and manage a population of service account actors."""

    # Role -> typical home zone and action types
    ROLE_TEMPLATES = {
        "admin": {
            "home_zone": "CONTROL",
            "action_types": [
                "IAM_SET_POLICY",
                "IAM_CREATE_SA",
                "SCHEDULER_ADMIN",
                "COMPUTE_CREATE",
            ],
        },
        "deployer": {
            "home_zone": "CONTROL",
            "action_types": [
                "COMPUTE_CREATE",
                "IAM_SET_POLICY",
                "GCS_READ",
                "GCS_WRITE",
            ],
        },
        "scheduler": {
            "home_zone": "CONTROL",
            "action_types": [
                "SCHEDULER_ADMIN",
                "IAM_IMPERSONATE",
                "GCS_READ",
            ],
        },
        "worker": {
            "home_zone": "DATA",
            "action_types": [
                "GCS_READ",
                "GCS_WRITE",
                "GCS_LIST",
                "SECRET_ACCESS",
                "BQ_JOB_SUBMIT",
            ],
        },
        "attacker": {
            "home_zone": "IDENTITY",
            "action_types": [
                "IAM_CREATE_KEY",
                "IAM_DELETE_KEY",
                "IAM_IMPERSONATE",
                "SECRET_ACCESS",
                "GCS_READ",
                "KMS_DECRYPT",
            ],
        },
    }

    def __init__(self, count: int, seed: int = 42):
        """Initialize actor population.

        Args:
            count: Number of actors (5-50)
            seed: Random seed
        """
        self.count = max(5, min(50, count))
        self.rng = random.Random(seed)
        self.actors: list[Actor] = []
        self._generate_actors()

    def _generate_actors(self):
        """Generate a diverse set of actors."""
        # Distribution: admin (1), deployer (1-2), scheduler (1-2), worker (many), attacker (1-3)
        roles = []

        # Always one admin
        roles.append("admin")

        # 1-2 deployers
        roles.extend(["deployer"] * self.rng.randint(1, 2))

        # 1-2 schedulers
        roles.extend(["scheduler"] * self.rng.randint(1, 2))

        # Fill rest with workers
        worker_count = max(1, self.count - len(roles) - self.rng.randint(1, 3))
        roles.extend(["worker"] * worker_count)

        # 1-3 attackers (for attack scenario generation)
        attacker_count = min(3, max(1, self.count - len(roles)))
        roles.extend(["attacker"] * attacker_count)

        # Shuffle
        self.rng.shuffle(roles)

        # Create actors
        for i, role in enumerate(roles[: self.count]):
            template = self.ROLE_TEMPLATES[role]
            email = f"{role}-sa-{i}@synth-project.iam.gserviceaccount.com"
            actor = Actor(
                email=email,
                role=role,
                home_zone=template["home_zone"],
                action_types=template["action_types"],
            )
            self.actors.append(actor)

    def get_all(self) -> list[Actor]:
        """Get all actors."""
        return self.actors

    def get_by_role(self, role: str) -> list[Actor]:
        """Get actors by role."""
        return [a for a in self.actors if a.role == role]

    def get_random(self) -> Actor:
        """Get a random actor."""
        return self.rng.choice(self.actors)

    def get_random_by_role(self, role: str) -> Actor | None:
        """Get a random actor by role."""
        matching = self.get_by_role(role)
        if not matching:
            return None
        return self.rng.choice(matching)
