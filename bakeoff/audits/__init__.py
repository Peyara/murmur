"""
Anti-cheat controls: fairness audit, leakage red-team, structural equalization checks.

Exports:
- fairness_audit: verify structural equalization, attack path lengths, determinism (§4.1, §4.4)
- leakage_redteam: train shallow cheat detector to verify it's at chance (§4.3)
- grep_leak_check: mechanical grep for label leakage (§4.2)
"""

from . import fairness_audit, leakage_redteam, grep_leak_check

__all__ = ["fairness_audit", "leakage_redteam", "grep_leak_check"]
