"""Cloud-agnostic log inspector — discovers structure, patterns, and correlation
candidates from raw log files with zero prior knowledge of the source system.

Designed to work on GCP Cloud Audit Logs, Cloud Scheduler execution logs, Cloud
Run request logs, AWS CloudTrail, Azure Activity Logs, or any JSONL-formatted
log data. All analysis is statistical, not rule-based.
"""

import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# --- Value pattern detectors (heuristic, not exhaustive) ---

_PATTERNS = {
    "email": re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"),
    "ipv4": re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"),
    "ipv6": re.compile(r"^[0-9a-fA-F:]{3,}$"),
    "uri": re.compile(r"^(https?://|gs://|s3://|projects/|arn:)"),
    "iso_timestamp": re.compile(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    ),
    "uuid": re.compile(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    ),
    "hex_hash": re.compile(r"^[0-9a-fA-F]{16,}$"),
}

_TIMESTAMP_FORMATS = [
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S",
]


def _detect_value_type(value: str) -> str | None:
    """Return the detected semantic type of a string value, or None."""
    for name, pattern in _PATTERNS.items():
        if pattern.match(value):
            return name
    return None


def _try_parse_timestamp(value: str) -> datetime | None:
    """Attempt to parse a string as a timestamp."""
    for fmt in _TIMESTAMP_FORMATS:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except ValueError:
            continue
    # Handle nanosecond precision (truncate to microseconds)
    if "T" in value and len(value) > 26:
        truncated = value[:26] + "Z"
        return _try_parse_timestamp(truncated)
    return None


# --- Data structures ---


@dataclass
class FieldStats:
    """Statistics for a single field path across all entries."""

    path: str
    count: int = 0
    total_entries: int = 0
    distinct_values: set = field(default_factory=set)
    value_types: Counter = field(default_factory=Counter)
    sample_values: list = field(default_factory=list)
    cardinality_capped: bool = False

    @property
    def presence_rate(self) -> float:
        return self.count / self.total_entries if self.total_entries else 0

    @property
    def cardinality(self) -> int:
        return len(self.distinct_values)

    @property
    def cardinality_ratio(self) -> float:
        """1.0 = unique per entry, 0.0 = same value everywhere.
        Approximate when cardinality_capped is True."""
        return self.cardinality / self.count if self.count else 0

    def dominant_type(self) -> str | None:
        if not self.value_types:
            return None
        return self.value_types.most_common(1)[0][0]


@dataclass
class TemporalCluster:
    """A group of events within a time window."""

    start: datetime
    end: datetime
    entries: list = field(default_factory=list)
    shared_values: dict = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        return (self.end - self.start).total_seconds()


@dataclass
class CorrelationCandidate:
    """A field that may serve as a correlation/grouping key."""

    field_path: str
    evidence_type: str  # "shared_in_cluster", "cross_log_type", "moderate_cardinality"
    score: float  # 0-1, higher = stronger evidence
    details: str


@dataclass
class InspectionReport:
    """Complete output of a log inspection run."""

    total_entries: int = 0
    files_processed: int = 0
    log_types: dict = field(default_factory=dict)  # logName -> count
    field_inventory: dict = field(default_factory=dict)  # path -> FieldStats
    timestamp_fields: list = field(default_factory=list)
    actor_candidates: list = field(default_factory=list)
    target_candidates: list = field(default_factory=list)
    correlation_candidates: list = field(default_factory=list)
    temporal_clusters: list = field(default_factory=list)
    cross_log_correlations: list = field(default_factory=list)


# --- Core inspection logic ---


def _collect_fields(obj: object, prefix: str = "") -> list[tuple[str, object]]:
    """Recursively collect all leaf field paths and their values."""
    results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, (dict, list)):
                results.extend(_collect_fields(v, path))
            else:
                results.append((path, v))
    elif isinstance(obj, list):
        for i, item in enumerate(obj[:3]):  # Sample first 3 array items
            results.extend(_collect_fields(item, f"{prefix}[]"))
    else:
        results.append((prefix, obj))
    return results


def _load_entries(directory: Path) -> list[dict]:
    """Load all JSON/JSONL entries from a directory recursively."""
    entries = []
    json_files = sorted(directory.rglob("*.json")) + sorted(directory.rglob("*.jsonl"))
    seen_paths = set()

    for filepath in json_files:
        if filepath in seen_paths:
            continue
        seen_paths.add(filepath)

        with open(filepath) as f:
            content = f.read().strip()
            if not content:
                continue

            # Try as JSON array first
            if content.startswith("["):
                try:
                    items = json.loads(content)
                    if isinstance(items, list):
                        entries.extend(items)
                        continue
                except json.JSONDecodeError:
                    pass

            # Try as JSONL (one object per line)
            for line_num, line in enumerate(content.split("\n"), 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.debug("Skipped malformed line %d in %s", line_num, filepath)

    return entries


def inspect_logs(directory: str | Path, cluster_window_seconds: float = 30.0) -> InspectionReport:
    """Run a complete log inspection on all files in a directory.

    Args:
        directory: Path to directory containing JSON/JSONL log files.
        cluster_window_seconds: Time window for temporal clustering.

    Returns:
        InspectionReport with all findings.
    """
    directory = Path(directory)
    entries = _load_entries(directory)
    report = InspectionReport(
        total_entries=len(entries),
        files_processed=len(list(directory.rglob("*.json"))) + len(list(directory.rglob("*.jsonl"))),
    )

    if not entries:
        return report

    # --- Phase 1: Structure Discovery ---
    field_stats: dict[str, FieldStats] = {}

    for entry in entries:
        # Categorize by log type
        log_name = entry.get("logName", "UNKNOWN")
        report.log_types[log_name] = report.log_types.get(log_name, 0) + 1

        # Collect all leaf fields
        fields = _collect_fields(entry)
        for path, value in fields:
            if path not in field_stats:
                field_stats[path] = FieldStats(path=path, total_entries=len(entries))
            stats = field_stats[path]
            stats.count += 1

            str_val = str(value) if value is not None else ""
            if len(stats.distinct_values) < 1000:
                stats.distinct_values.add(str_val)
            else:
                stats.cardinality_capped = True
            if len(stats.sample_values) < 5:
                stats.sample_values.append(str_val)

            # Detect value type
            if isinstance(value, str):
                vtype = _detect_value_type(value)
                if vtype:
                    stats.value_types[vtype] += 1

    report.field_inventory = field_stats

    # --- Phase 2: Pattern Detection ---

    # Find timestamp fields
    for path, stats in field_stats.items():
        if stats.dominant_type() == "iso_timestamp" or "timestamp" in path.lower() or "time" in path.lower():
            # Verify by trying to parse sample values
            parsed_count = sum(1 for v in stats.sample_values if _try_parse_timestamp(v))
            if parsed_count > 0:
                report.timestamp_fields.append(path)

    # Find actor candidates (email fields with moderate cardinality)
    for path, stats in field_stats.items():
        if stats.dominant_type() == "email" and stats.cardinality >= 1:
            report.actor_candidates.append(
                (path, stats.cardinality, stats.sample_values[:3])
            )

    # Find target candidates (URI fields)
    for path, stats in field_stats.items():
        if stats.dominant_type() == "uri" and stats.cardinality >= 1:
            report.target_candidates.append(
                (path, stats.cardinality, stats.sample_values[:3])
            )

    # Find correlation candidates (moderate cardinality fields that repeat)
    for path, stats in field_stats.items():
        ratio = stats.cardinality_ratio
        # Interesting: not unique per entry (< 0.8) and not constant (> 0.01)
        # These are fields that group entries together
        if 0.01 < ratio < 0.8 and stats.cardinality >= 2 and stats.count >= 5:
            score = 1.0 - abs(ratio - 0.3)  # Peak score at ~30% cardinality ratio
            report.correlation_candidates.append(
                CorrelationCandidate(
                    field_path=path,
                    evidence_type="moderate_cardinality",
                    score=round(score, 3),
                    details=f"cardinality={stats.cardinality}, ratio={ratio:.2f}, "
                    f"count={stats.count}/{stats.total_entries}",
                )
            )

    # --- Phase 3: Temporal Clustering ---
    # Use the most common timestamp field
    ts_field = None
    if report.timestamp_fields:
        # Prefer top-level "timestamp" if present
        for tf in report.timestamp_fields:
            if tf == "timestamp":
                ts_field = tf
                break
        if ts_field is None:
            ts_field = report.timestamp_fields[0]

    if ts_field:
        # Parse timestamps for all entries
        timed_entries = []
        for entry in entries:
            # Navigate dotted path
            val = entry
            for key in ts_field.split("."):
                if isinstance(val, dict):
                    val = val.get(key)
                else:
                    val = None
                    break
            if isinstance(val, str):
                dt = _try_parse_timestamp(val)
                if dt:
                    timed_entries.append((dt, entry))

        timed_entries.sort(key=lambda x: x[0])

        # Cluster by time window
        clusters: list[TemporalCluster] = []
        current_cluster = None

        for dt, entry in timed_entries:
            if current_cluster is None:
                current_cluster = TemporalCluster(start=dt, end=dt, entries=[(dt, entry)])
            elif (dt - current_cluster.end).total_seconds() <= cluster_window_seconds:
                current_cluster.end = dt
                current_cluster.entries.append((dt, entry))
            else:
                if len(current_cluster.entries) >= 2:
                    clusters.append(current_cluster)
                current_cluster = TemporalCluster(start=dt, end=dt, entries=[(dt, entry)])

        if current_cluster and len(current_cluster.entries) >= 2:
            clusters.append(current_cluster)

        # Analyze shared values within clusters
        for cluster in clusters:
            # Collect all field values for each entry in the cluster
            value_sets: dict[str, set] = defaultdict(set)
            for _, entry in cluster.entries:
                for path, value in _collect_fields(entry):
                    if value is not None:
                        value_sets[path].add(str(value))

            # Find fields where all entries share the same value
            shared = {}
            for path, values in value_sets.items():
                if len(values) == 1 and len(cluster.entries) >= 2:
                    shared[path] = next(iter(values))
            cluster.shared_values = shared

        report.temporal_clusters = clusters

        # Find fields that are shared within clusters but vary across clusters
        if len(clusters) >= 2:
            cluster_varying_fields = defaultdict(set)
            for cluster in clusters:
                for path, value in cluster.shared_values.items():
                    cluster_varying_fields[path].add(value)

            for path, values_across_clusters in cluster_varying_fields.items():
                if len(values_across_clusters) >= 2:
                    # This field has different values in different clusters
                    # but same value within each cluster — strong correlation signal
                    report.correlation_candidates.append(
                        CorrelationCandidate(
                            field_path=path,
                            evidence_type="shared_in_cluster",
                            score=0.9,
                            details=f"same within {len(clusters)} clusters, "
                            f"{len(values_across_clusters)} distinct values across clusters",
                        )
                    )

    # --- Phase 4: Cross-Log-Type Correlation ---
    # Group entries by log type, then find fields whose values appear across types
    entries_by_log = defaultdict(list)
    for entry in entries:
        log_name = entry.get("logName", "UNKNOWN")
        # Normalize to short name
        short = log_name.split("/logs/")[-1] if "/logs/" in log_name else log_name
        entries_by_log[short].append(entry)

    if len(entries_by_log) >= 2:
        # For each log type, collect all values per field
        values_by_log_field: dict[str, dict[str, set]] = {}  # log_type -> {field -> {values}}
        for log_type, log_entries in entries_by_log.items():
            values_by_log_field[log_type] = defaultdict(set)
            for entry in log_entries:
                for path, value in _collect_fields(entry):
                    if value is not None and isinstance(value, str) and len(str(value)) > 3:
                        values_by_log_field[log_type][path].add(str(value))

        # Find value overlaps across log types
        log_types = list(values_by_log_field.keys())
        for i, lt1 in enumerate(log_types):
            for lt2 in log_types[i + 1 :]:
                for field1, values1 in values_by_log_field[lt1].items():
                    for field2, values2 in values_by_log_field[lt2].items():
                        overlap = values1 & values2
                        if overlap and len(overlap) >= 1:
                            report.cross_log_correlations.append({
                                "log_type_1": lt1,
                                "field_1": field1,
                                "log_type_2": lt2,
                                "field_2": field2,
                                "shared_values": len(overlap),
                                "sample": list(overlap)[:3],
                            })

    # Sort correlation candidates by score
    report.correlation_candidates.sort(key=lambda c: c.score, reverse=True)

    return report


def format_report(report: InspectionReport) -> str:
    """Format an InspectionReport as a human-readable string."""
    lines = []
    lines.append("=" * 70)
    lines.append("LOG INSPECTION REPORT")
    lines.append("=" * 70)
    lines.append(f"\nTotal entries: {report.total_entries}")
    lines.append(f"Files processed: {report.files_processed}")

    # Log types
    lines.append(f"\n--- Log Types ({len(report.log_types)}) ---")
    for log_name, count in sorted(report.log_types.items(), key=lambda x: -x[1]):
        short = log_name.split("/logs/")[-1] if "/logs/" in log_name else log_name
        lines.append(f"  {count:4d}  {short}")

    # Field inventory (top fields by presence)
    lines.append("\n--- Field Inventory (top 40 by presence) ---")
    sorted_fields = sorted(
        report.field_inventory.values(), key=lambda s: s.count, reverse=True
    )
    for stats in sorted_fields[:40]:
        dtype = stats.dominant_type() or "-"
        sample = stats.sample_values[0][:50] if stats.sample_values else "-"
        lines.append(
            f"  {stats.count:4d}/{stats.total_entries}  "
            f"card={stats.cardinality:<4d}  "
            f"type={dtype:<14s}  "
            f"{stats.path}"
        )
        lines.append(f"         sample: {sample}")

    # Timestamp fields
    if report.timestamp_fields:
        lines.append("\n--- Timestamp Fields ---")
        for tf in report.timestamp_fields:
            lines.append(f"  {tf}")

    # Actor candidates
    if report.actor_candidates:
        lines.append("\n--- Actor Candidates ---")
        for path, card, samples in report.actor_candidates:
            lines.append(f"  {path}  (cardinality={card})")
            for s in samples:
                lines.append(f"    - {s}")

    # Target candidates
    if report.target_candidates:
        lines.append("\n--- Target Candidates ---")
        for path, card, samples in report.target_candidates:
            lines.append(f"  {path}  (cardinality={card})")
            for s in samples[:3]:
                lines.append(f"    - {s[:80]}")

    # Correlation candidates
    if report.correlation_candidates:
        lines.append("\n--- Correlation Candidates (top 15) ---")
        for c in report.correlation_candidates[:15]:
            lines.append(f"  [{c.score:.2f}] {c.field_path}")
            lines.append(f"         type={c.evidence_type}  {c.details}")

    # Temporal clusters
    if report.temporal_clusters:
        lines.append(f"\n--- Temporal Clusters ({len(report.temporal_clusters)} found) ---")
        for i, cluster in enumerate(report.temporal_clusters[:10]):
            lines.append(
                f"  Cluster {i + 1}: {len(cluster.entries)} entries, "
                f"{cluster.duration_seconds:.1f}s span "
                f"({cluster.start.isoformat()} to {cluster.end.isoformat()})"
            )
            if cluster.shared_values:
                interesting = {
                    k: v
                    for k, v in cluster.shared_values.items()
                    if not k.startswith("protoPayload.@type")
                    and "type.googleapis" not in str(v)
                    and len(str(v)) < 100
                }
                if interesting:
                    lines.append(f"    Shared fields ({len(interesting)}):")
                    for k, v in sorted(interesting.items())[:8]:
                        lines.append(f"      {k} = {v}")

    # Cross-log correlations
    if report.cross_log_correlations:
        lines.append(f"\n--- Cross-Log Correlations ({len(report.cross_log_correlations)} found) ---")
        # Deduplicate and sort by shared value count
        seen = set()
        sorted_corrs = sorted(
            report.cross_log_correlations, key=lambda x: -x["shared_values"]
        )
        for corr in sorted_corrs[:20]:
            key = (corr["field_1"], corr["field_2"])
            if key in seen:
                continue
            seen.add(key)
            lines.append(
                f"  {corr['log_type_1'][:40]}::{corr['field_1']}"
                f"\n    <-> {corr['log_type_2'][:40]}::{corr['field_2']}"
                f"\n    shared_values={corr['shared_values']}, sample={corr['sample'][:2]}"
            )

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)
