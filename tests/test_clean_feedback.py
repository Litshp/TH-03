import csv
import unittest
from pathlib import Path

from clean_feedback import process_data


ROOT = Path(__file__).resolve().parents[1]


def read_csv(path: Path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class CleanFeedbackTests(unittest.TestCase):
    def test_event_conflict_rejects_all_rows_before_field_validation(self):
        sessions = [{"session_id": "S01", "title": "Example"}]
        feedback = [
            {
                "row_id": "R1",
                "event_id": "E1",
                "participant_id": "U1",
                "session_id": "S01",
                "score": "5",
                "has_issue": "false",
                "submitted_at": "2026-01-01T00:00:00Z",
                "comment": "Original",
            },
            {
                "row_id": "R2",
                "event_id": "E1",
                "participant_id": "U1",
                "session_id": "S01",
                "score": "6",
                "has_issue": "false",
                "submitted_at": "2026-01-01T00:00:00Z",
                "comment": "Conflicting upload",
            },
        ]

        summary, rejected = process_data(sessions, feedback)

        self.assertEqual(summary[0]["response_count"], "0")
        self.assertEqual(
            rejected,
            [
                {"row_id": "R1", "reason": "event_conflict"},
                {"row_id": "R2", "reason": "event_conflict"},
            ],
        )

    def test_real_inputs_apply_validation_deduplication_and_privacy_rule(self):
        sessions = read_csv(ROOT / "sessions.csv")
        feedback = read_csv(ROOT / "feedback.csv")

        summary, rejected = process_data(sessions, feedback)

        self.assertEqual(
            summary,
            [
                {
                    "session_id": "S01",
                    "response_count": "4",
                    "average_score": "3.75",
                    "issue_rate": "0.50",
                },
                {
                    "session_id": "S02",
                    "response_count": "3",
                    "average_score": "4.33",
                    "issue_rate": "0.00",
                },
                {
                    "session_id": "S03",
                    "response_count": "11",
                    "average_score": "4.00",
                    "issue_rate": "0.27",
                },
                {
                    "session_id": "S04",
                    "response_count": "2",
                    "average_score": "",
                    "issue_rate": "",
                },
            ],
        )

        rejected_by_id = {row["row_id"]: row["reason"] for row in rejected}
        self.assertEqual(rejected_by_id["R026"], "event_conflict")
        self.assertEqual(rejected_by_id["R027"], "event_conflict")
        self.assertEqual(rejected_by_id["R028"], "latest_timestamp_tie")
        self.assertEqual(rejected_by_id["R029"], "latest_timestamp_tie")
        self.assertEqual(rejected_by_id["R004"], "duplicate_retry")
        self.assertEqual(rejected_by_id["R001"], "superseded_by_latest")


    def test_invalid_rows_are_rejected_with_stable_reasons(self):
        sessions = read_csv(ROOT / "sessions.csv")
        feedback = read_csv(ROOT / "feedback.csv")

        _, rejected = process_data(sessions, feedback)

        rejected_by_id = {row["row_id"]: row["reason"] for row in rejected}
        self.assertEqual(
            rejected_by_id,
            {
                "R001": "superseded_by_latest",
                "R004": "duplicate_retry",
                "R006": "score_out_of_range",
                "R007": "missing_participant",
                "R008": "unknown_session",
                "R009": "superseded_by_latest",
                "R013": "score_not_integer",
                "R016": "superseded_by_latest",
                "R026": "event_conflict",
                "R027": "event_conflict",
                "R028": "latest_timestamp_tie",
                "R029": "latest_timestamp_tie",
                "R031": "superseded_by_latest",
                "R034": "score_not_integer",
                "R035": "has_issue_invalid",
                "R036": "submitted_at_invalid",
                "R037": "duplicate_retry",
            },
        )
