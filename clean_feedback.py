#!/usr/bin/env python3
"""Clean WorkshopPulse feedback records using the supplied task rules."""

import argparse
import csv
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


FEEDBACK_FIELDS = [
    "row_id",
    "event_id",
    "participant_id",
    "session_id",
    "score",
    "has_issue",
    "submitted_at",
    "comment",
]
SUMMARY_FIELDS = ["session_id", "response_count", "average_score", "issue_rate"]
REJECTED_FIELDS = ["row_id", "reason"]


def parse_timestamp(value):
    """Parse a timezone-aware ISO 8601 timestamp."""
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return timestamp


def validate_row(row, known_session_ids):
    """Return the first stable validation reason, or None for a valid row."""
    if row.get("session_id") not in known_session_ids:
        return "unknown_session"
    if not row.get("participant_id"):
        return "missing_participant"
    try:
        score = int(row.get("score", ""))
    except (TypeError, ValueError):
        return "score_not_integer"
    if not 1 <= score <= 5:
        return "score_out_of_range"
    if row.get("has_issue") not in {"true", "false"}:
        return "has_issue_invalid"
    try:
        parse_timestamp(row.get("submitted_at", ""))
    except (TypeError, ValueError):
        return "submitted_at_invalid"
    return None


def content_signature(row):
    """Return event content excluding row/event identifiers."""
    return tuple(row[field] for field in FEEDBACK_FIELDS if field not in {"row_id", "event_id"})


def _rounded_ratio(numerator, denominator):
    value = (Decimal(numerator) / Decimal(denominator)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return format(value, ".2f")


def process_data(sessions, feedback):
    """Return deterministic summary rows and rejected-row records."""
    known_session_ids = {row["session_id"] for row in sessions}
    rejected = []

    events = defaultdict(list)
    for row in feedback:
        events[row["event_id"]].append(row)

    candidates = []
    for event_id in sorted(events):
        group = sorted(events[event_id], key=lambda row: row["row_id"])
        signatures = {content_signature(row) for row in group}
        if len(signatures) > 1:
            rejected.extend(
                {"row_id": row["row_id"], "reason": "event_conflict"} for row in group
            )
            continue
        candidate = group[0]
        rejected.extend(
            {"row_id": row["row_id"], "reason": "duplicate_retry"} for row in group[1:]
        )
        reason = validate_row(candidate, known_session_ids)
        if reason:
            rejected.append({"row_id": candidate["row_id"], "reason": reason})
        else:
            candidates.append(candidate)

    participant_sessions = defaultdict(list)
    for row in candidates:
        participant_sessions[(row["participant_id"], row["session_id"])].append(row)

    final_rows = []
    for key in sorted(participant_sessions):
        group = participant_sessions[key]
        latest_timestamp = max(parse_timestamp(row["submitted_at"]) for row in group)
        latest = [
            row
            for row in group
            if parse_timestamp(row["submitted_at"]) == latest_timestamp
        ]
        if len(latest) > 1:
            rejected.extend(
                {"row_id": row["row_id"], "reason": "latest_timestamp_tie"}
                for row in latest
            )
            rejected.extend(
                {"row_id": row["row_id"], "reason": "superseded_by_latest"}
                for row in group
                if row not in latest
            )
            continue

        winner = latest[0]
        final_rows.append(winner)
        rejected.extend(
            {"row_id": row["row_id"], "reason": "superseded_by_latest"}
            for row in group
            if row["row_id"] != winner["row_id"]
        )

    final_by_session = defaultdict(list)
    for row in final_rows:
        final_by_session[row["session_id"]].append(row)

    summary = []
    for session_id in sorted(known_session_ids):
        rows = final_by_session[session_id]
        count = len(rows)
        if count < 3:
            average_score = ""
            issue_rate = ""
        else:
            average_score = _rounded_ratio(sum(int(row["score"]) for row in rows), count)
            issue_rate = _rounded_ratio(
                sum(row["has_issue"] == "true" for row in rows), count
            )
        summary.append(
            {
                "session_id": session_id,
                "response_count": str(count),
                "average_score": average_score,
                "issue_rate": issue_rate,
            }
        )

    rejected.sort(key=lambda row: (row["row_id"], row["reason"]))
    return summary, rejected


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, fieldnames, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args(argv)

    sessions = read_csv(args.input_dir / "sessions.csv")
    feedback = read_csv(args.input_dir / "feedback.csv")
    summary, rejected = process_data(sessions, feedback)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "session_summary.csv", SUMMARY_FIELDS, summary)
    write_csv(args.output_dir / "rejected_rows.csv", REJECTED_FIELDS, rejected)


if __name__ == "__main__":
    main()
