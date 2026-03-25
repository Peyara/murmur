"""Agentic interpretation layer for the log inspector.

Sits on top of the deterministic inspector (inspector.py). Takes the structured
InspectionReport and produces human-actionable analysis: field mapping proposals,
correlation strategy recommendations, and provenance chain identification.

Architecture:
  1. Deterministic layer (inspector.py) -> InspectionReport
  2. Agentic layer (this module) -> reads report, reasons about it

The agent config below defines the system prompt, structured input/output, and
the reasoning steps. It is designed to be called with any LLM backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.ingest.inspector import InspectionReport

# --- Agent Configuration ---

AGENT_SYSTEM_PROMPT = """\
You are a log analysis expert. You receive a structured inspection report from
an automated log scanner and must interpret the findings to produce actionable
recommendations for a security monitoring system.

Your goals:
1. FIELD MAPPING: Propose which log fields map to canonical roles (actor, target,
   action, timestamp, correlation_id). Justify each mapping with evidence from
   the report.
2. CORRELATION STRATEGY: Identify how events from different log sources can be
   linked into causal chains (e.g., scheduler triggers service, service accesses
   resource). Specify the linking mechanism (shared field, temporal proximity,
   identity matching).
3. PROVENANCE ASSESSMENT: For each log type, determine what level of provenance
   it can provide (STRONG = cryptographic proof, WEAK = temporal/identity
   correlation, NONE = no linkage).
4. GAP ANALYSIS: Identify what the logs DON'T tell us. What events are missing?
   What correlations are ambiguous? What would improve the signal?

You must be specific: name exact field paths, give evidence (cardinality, presence
rate, sample values), and state confidence levels (HIGH/MEDIUM/LOW).

Output your analysis as structured JSON matching the AgentOutput schema.
"""


@dataclass
class FieldMapping:
    """Proposed mapping from a log field to a canonical role."""

    field_path: str
    canonical_role: str  # actor, target, action, timestamp, correlation_id, source_type
    log_types: list[str]  # which log types this applies to
    confidence: str  # HIGH, MEDIUM, LOW
    evidence: str  # why this mapping is proposed


@dataclass
class CorrelationLink:
    """Proposed mechanism for linking events across log types."""

    source_log: str
    target_log: str
    mechanism: str  # temporal, identity, shared_field, trace_id
    source_field: str | None = None
    target_field: str | None = None
    window_seconds: float | None = None  # for temporal correlation
    confidence: str = "MEDIUM"
    notes: str = ""


@dataclass
class ProvenanceAssessment:
    """Provenance level assessment for a log type."""

    log_type: str
    level: str  # STRONG, WEAK, NONE
    justification: str
    missing_for_upgrade: str  # what would be needed to upgrade the level


@dataclass
class Gap:
    """Identified gap in log coverage or correlation."""

    description: str
    impact: str  # how this affects detection/provenance
    recommendation: str


@dataclass
class AgentOutput:
    """Complete output from the interpretation agent."""

    field_mappings: list[FieldMapping] = field(default_factory=list)
    correlation_links: list[CorrelationLink] = field(default_factory=list)
    provenance_assessments: list[ProvenanceAssessment] = field(default_factory=list)
    gaps: list[Gap] = field(default_factory=list)
    trigger_ref_verdict: str = ""  # the key question: how to implement trigger_ref
    raw_reasoning: str = ""  # the agent's chain of thought


def build_agent_input(report: InspectionReport) -> dict[str, Any]:
    """Build the input payload for the interpretation agent.

    Returns a dict suitable for inclusion in an LLM prompt (as JSON or text).
    """
    # Structured summary (not the full formatted report — too verbose)
    log_type_summary = {}
    for log_name, count in report.log_types.items():
        short = log_name.split("/logs/")[-1] if "/logs/" in log_name else log_name
        log_type_summary[short] = count

    # Top fields per log type
    fields_by_log = {}
    for path, stats in report.field_inventory.items():
        for log_name in report.log_types:
            short = log_name.split("/logs/")[-1] if "/logs/" in log_name else log_name
            if short not in fields_by_log:
                fields_by_log[short] = []

    # Simplified field inventory
    field_summary = []
    for path, stats in sorted(
        report.field_inventory.items(), key=lambda x: -x[1].count
    ):
        if stats.count >= 5:  # Skip very rare fields
            field_summary.append({
                "path": path,
                "count": stats.count,
                "total": stats.total_entries,
                "cardinality": stats.cardinality,
                "cardinality_ratio": round(stats.cardinality_ratio, 3),
                "dominant_type": stats.dominant_type(),
                "samples": stats.sample_values[:3],
            })

    # Correlation candidates
    correlation_summary = [
        {
            "field": c.field_path,
            "type": c.evidence_type,
            "score": c.score,
            "details": c.details,
        }
        for c in report.correlation_candidates[:20]
    ]

    # Temporal cluster summary
    cluster_summary = []
    for i, cluster in enumerate(report.temporal_clusters[:15]):
        interesting_shared = {
            k: v
            for k, v in cluster.shared_values.items()
            if "type.googleapis" not in str(v) and len(str(v)) < 100
        }
        cluster_summary.append({
            "cluster_id": i + 1,
            "entry_count": len(cluster.entries),
            "duration_seconds": round(cluster.duration_seconds, 1),
            "start": cluster.start.isoformat(),
            "end": cluster.end.isoformat(),
            "shared_fields_count": len(interesting_shared),
            "shared_fields_sample": dict(list(interesting_shared.items())[:5]),
        })

    # Cross-log correlations (deduplicated, top)
    cross_log = []
    seen = set()
    for corr in sorted(
        report.cross_log_correlations, key=lambda x: -x["shared_values"]
    ):
        key = (corr["field_1"], corr["field_2"])
        if key not in seen:
            seen.add(key)
            cross_log.append(corr)
        if len(cross_log) >= 15:
            break

    return {
        "total_entries": report.total_entries,
        "log_types": log_type_summary,
        "field_inventory": field_summary[:50],
        "timestamp_fields": report.timestamp_fields,
        "actor_candidates": [
            {"path": p, "cardinality": c, "samples": s[:2]}
            for p, c, s in report.actor_candidates
        ],
        "target_candidates": [
            {"path": p, "cardinality": c, "samples": s[:2]}
            for p, c, s in report.target_candidates[:10]
        ],
        "correlation_candidates": correlation_summary,
        "temporal_clusters": cluster_summary,
        "cross_log_correlations": cross_log,
    }


def build_agent_prompt(report: InspectionReport) -> str:
    """Build the complete prompt for the interpretation agent.

    This can be sent to any LLM API. The system prompt + user message
    together form the full agent invocation.
    """
    import json

    agent_input = build_agent_input(report)

    user_message = f"""\
Here is the log inspection report from an automated scanner. Analyze it and
produce your recommendations.

INSPECTION DATA:
```json
{json.dumps(agent_input, indent=2, default=str)}
```

CRITICAL QUESTION: We are building a security monitoring system (Murmur) that
needs to establish "provenance" — proving that an action was authorized by a
known orchestrator (like Cloud Scheduler) rather than being an ad-hoc human or
attacker action. We call this correlation ID "trigger_ref".

Based on this log data:
1. Is there a native per-execution correlation ID that links the orchestrator
   to the triggered action?
2. If not, what is the best fallback mechanism?
3. What confidence level can we achieve?

Respond with structured JSON matching the AgentOutput schema, plus your
chain-of-thought reasoning in the raw_reasoning field.
"""
    return f"SYSTEM:\n{AGENT_SYSTEM_PROMPT}\n\nUSER:\n{user_message}"
