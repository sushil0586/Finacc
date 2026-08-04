from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG = ROOT / "logs" / "payables_perf.log"

LINE_RE = re.compile(r"\b([A-Za-z0-9_.]+)\b(?:\s+(.*))?$")
FIELD_RE = re.compile(r"([a-zA-Z0-9_]+)=([^=]+?)(?=\s+[a-zA-Z0-9_]+=|$)")


def _coerce_value(raw: str):
    value = raw.strip()
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def parse_line(line: str):
    if not line.strip():
        return None
    parts = line.split()
    if len(parts) < 4:
        return None
    event = parts[3]
    field_text = line.split(event, 1)[1].strip()
    fields = {key: _coerce_value(value) for key, value in FIELD_RE.findall(field_text)}
    return event, fields


def summarize(log_path: Path) -> str:
    events: dict[str, list[dict]] = defaultdict(list)
    for line in log_path.read_text().splitlines():
        parsed = parse_line(line)
        if parsed is None:
            continue
        event, fields = parsed
        events[event].append(fields)

    if not events:
        return f"No parseable payables perf events found in {log_path}"

    lines: list[str] = []
    lines.append(f"Log: {log_path}")
    lines.append(f"Total events: {sum(len(rows) for rows in events.values())}")
    lines.append("")

    for event in sorted(events):
        rows = events[event]
        durations = [row.get("duration_ms") for row in rows if isinstance(row.get("duration_ms"), (int, float))]
        queries = [row.get("query_count") for row in rows if isinstance(row.get("query_count"), (int, float))]
        slowest = [row.get("slowest_query_ms") for row in rows if isinstance(row.get("slowest_query_ms"), (int, float))]
        avg_duration = round(sum(durations) / len(durations), 2) if durations else "n/a"
        max_duration = round(max(durations), 2) if durations else "n/a"
        avg_queries = round(sum(queries) / len(queries), 2) if queries else "n/a"
        max_slowest = round(max(slowest), 2) if slowest else "n/a"
        lines.append(
            f"{event}: calls={len(rows)} avg_duration_ms={avg_duration} max_duration_ms={max_duration} "
            f"avg_query_count={avg_queries} max_slowest_query_ms={max_slowest}"
        )
        sample = rows[0]
        interesting = []
        for key in (
            "view",
            "page_size",
            "row_count",
            "vendor_row_count",
            "result_count",
            "report_count",
            "permission_code_count",
            "cache_key_present",
        ):
            if key in sample:
                interesting.append(f"{key}={sample[key]}")
        if interesting:
            lines.append("  sample: " + " ".join(interesting))
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    log_path = Path(argv[1]).resolve() if len(argv) > 1 else DEFAULT_LOG
    if not log_path.exists():
        print(f"Log file not found: {log_path}", file=sys.stderr)
        return 1
    print(summarize(log_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
