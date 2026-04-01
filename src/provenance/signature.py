"""Provenance signature verification stub.

Always returns unverified. Sprint 3 fills in cryptographic verification.
"""

from dataclasses import dataclass


@dataclass
class SignatureResult:
    verified: bool = False
    signer: str | None = None
    method: str | None = None


def verify_signature(event_id: str) -> SignatureResult:
    """Stub — always returns unverified."""
    return SignatureResult()
