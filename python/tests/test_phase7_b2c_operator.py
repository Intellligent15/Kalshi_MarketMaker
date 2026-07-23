from __future__ import annotations

import copy
from pathlib import Path
import sys
import tempfile
import unittest

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

import pmm_b2c_operator as operator
import pmm_phase7 as phase7


class B2cOperatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.page = self.root / "page-1.json"
        phase7.write_json(self.page, {"markets": self.candidates(), "cursor": None})

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def candidates() -> list[dict]:
        rows = [
            ("KX-A", "SERIES-1", "10.5"),
            ("KX-B", "SERIES-1", "10.5"),
            ("KX-C", "SERIES-2", "9"),
            ("KX-D", "SERIES-3", "8"),
        ]
        return [
            {
                "ticker": ticker,
                "event_ticker": f"EVENT-{ticker}",
                "series_ticker": series,
                "contract_kind": "binary",
                "status": "open",
                "close_time_utc": "2026-08-03T00:00:00Z",
                "volume_24h_fp": volume,
            }
            for ticker, series, volume in rows
        ]

    def snapshot(self) -> dict:
        payload = {
            "environment": "production",
            "activity_field": "volume_24h_fp",
            "retrieval_started_at_utc": "2026-08-01T00:00:00Z",
            "retrieval_completed_at_utc": "2026-08-01T00:01:00Z",
            "query": {"endpoint": "/trade-api/v2/markets", "parameters": {"status": "open"}},
            "pagination_complete": True,
            "pages": [
                {
                    "path": self.page.name,
                    "sha256": phase7.sha256_file(self.page),
                    "cursor_in": None,
                    "cursor_out": None,
                }
            ],
            "capture_window": {
                "started_at_utc": "2026-08-02T00:00:00Z",
                "ended_at_utc": "2026-08-02T12:00:00Z",
                "closing_margin_seconds": 1800,
            },
            "candidates": self.candidates(),
            "selected_market_tickers": ["KX-A", "KX-C", "KX-D"],
        }
        return {
            "schema": operator.CANDIDATE_SNAPSHOT_SCHEMA,
            "payload": payload,
            "payload_sha256": operator.payload_sha256(payload),
        }

    def write_snapshot(self, document: dict | None = None) -> Path:
        path = self.root / "snapshot.json"
        phase7.write_json(path, self.snapshot() if document is None else document)
        return path

    @staticmethod
    def rehash(document: dict) -> None:
        document["payload_sha256"] = operator.payload_sha256(document["payload"])

    def approval(self, snapshot_path: Path) -> dict:
        specs = []
        spec_root = self.root / "specs"
        spec_root.mkdir(exist_ok=True)
        for ticker in ("KX-A", "KX-C", "KX-D"):
            opening = spec_root / f"{ticker}-opening.json"
            closing = spec_root / f"{ticker}-closing.json"
            phase7.write_json(
                opening,
                {"schema": "synthetic.acquisition", "ticker": ticker, "observation": "opening"},
            )
            phase7.write_json(
                closing,
                {"schema": "synthetic.acquisition", "ticker": ticker, "observation": "closing"},
            )
            specs.append(
                {
                    "ticker": ticker,
                    "opening_path": opening.relative_to(self.root).as_posix(),
                    "opening_sha256": phase7.sha256_file(opening),
                    "closing_path": closing.relative_to(self.root).as_posix(),
                    "closing_sha256": phase7.sha256_file(closing),
                }
            )
        payload = {
            "candidate_snapshot_sha256": phase7.sha256_file(snapshot_path),
            "policy_sha256": phase7.sha256_file(
                phase7.REPOSITORY_ROOT / "configs/phase7/b2c_evidence_policy_v1.json"
            ),
            "selected_market_tickers": ["KX-A", "KX-C", "KX-D"],
            "capture_window": {
                "started_at_utc": "2026-08-02T00:00:00Z",
                "ended_at_utc": "2026-08-02T12:00:00Z",
            },
            "operator": "ronit",
            "reviewer": "ronit",
            "acquisition_specs": specs,
            "storage": {
                "owner": "ronit",
                "readers": ["ronit"],
                "primary_path": str((self.root / "primary").resolve()),
                "backup_path": str((self.root / "backup").resolve()),
                "retention": "project_lifetime",
                "owner_only_writes_during_construction": True,
                "immutable_after_verification": True,
                "hash_restore_check_required": True,
            },
            "approved_by": "ronit",
            "approved_at_utc": "2026-08-01T01:00:00Z",
        }
        return {
            "schema": operator.RUN_APPROVAL_SCHEMA,
            "payload": payload,
            "payload_sha256": operator.payload_sha256(payload),
        }

    def write_approval(self, document: dict) -> Path:
        path = self.root / "approval.json"
        phase7.write_json(path, document)
        return path

    def verify_approval(self, approval_path: Path, snapshot_path: Path) -> dict:
        return operator.verify_run_approval(
            approval_path,
            candidate_snapshot_path=snapshot_path,
            artifact_root=self.root,
        )

    def test_candidate_snapshot_reconstructs_retained_page_union_for_ranking(self) -> None:
        snapshot_path = self.write_snapshot()

        verified = operator.verify_candidate_snapshot(snapshot_path, artifact_root=self.root)

        self.assertEqual(verified["selected_market_tickers"], ["KX-A", "KX-C", "KX-D"])

    def test_candidate_snapshot_requires_complete_linked_cursor_chain(self) -> None:
        rows = self.candidates()
        page_2 = self.root / "page-2.json"
        phase7.write_json(self.page, {"markets": rows[:2], "cursor": "next-page"})
        phase7.write_json(page_2, {"markets": rows[2:], "cursor": None})
        base = self.snapshot()
        base["payload"]["pages"] = [
            {
                "path": self.page.name,
                "sha256": phase7.sha256_file(self.page),
                "cursor_in": None,
                "cursor_out": "next-page",
            },
            {
                "path": page_2.name,
                "sha256": phase7.sha256_file(page_2),
                "cursor_in": "next-page",
                "cursor_out": None,
            },
        ]
        self.rehash(base)
        operator.verify_candidate_snapshot(self.write_snapshot(base), artifact_root=self.root)

        mutations = [
            ("first cursor", 0, "cursor_in", "unexpected"),
            ("broken link", 1, "cursor_in", "wrong-page"),
            ("non-final cursor", 1, "cursor_out", "more-pages"),
        ]
        for label, page_index, field, value in mutations:
            with self.subTest(label=label):
                document = copy.deepcopy(base)
                document["payload"]["pages"][page_index][field] = value
                self.rehash(document)
                with self.assertRaisesRegex(
                    operator.OperatorError, "CandidateSnapshotPaginationMismatch"
                ):
                    operator.verify_candidate_snapshot(
                        self.write_snapshot(document), artifact_root=self.root
                    )

    def test_candidate_snapshot_rejects_page_candidate_mismatch_and_duplicate_market(self) -> None:
        for label, mutate in (
            (
                "candidate projection",
                lambda document: document["payload"]["candidates"][0].__setitem__(
                    "volume_24h_fp", "999"
                ),
            ),
            (
                "duplicate retained market",
                lambda document: phase7.write_json(
                    self.page,
                    {"markets": self.candidates() + [self.candidates()[0]], "cursor": None},
                ),
            ),
        ):
            with self.subTest(label=label):
                phase7.write_json(self.page, {"markets": self.candidates(), "cursor": None})
                document = self.snapshot()
                mutate(document)
                document["payload"]["pages"][0]["sha256"] = phase7.sha256_file(self.page)
                self.rehash(document)
                with self.assertRaisesRegex(
                    operator.OperatorError, "CandidateSnapshotPageMismatch"
                ):
                    operator.verify_candidate_snapshot(
                        self.write_snapshot(document), artifact_root=self.root
                    )

    def test_candidate_snapshot_requires_explicit_retained_cursor(self) -> None:
        phase7.write_json(self.page, {"markets": self.candidates()})
        document = self.snapshot()
        document["payload"]["pages"][0]["sha256"] = phase7.sha256_file(self.page)
        self.rehash(document)

        with self.assertRaisesRegex(operator.OperatorError, "CandidateSnapshotPaginationMismatch"):
            operator.verify_candidate_snapshot(
                self.write_snapshot(document), artifact_root=self.root
            )

    def test_candidate_snapshot_rejects_unsafe_and_symlink_page_paths(self) -> None:
        outside = self.root.parent / f"{self.root.name}-outside-page.json"
        phase7.write_json(outside, {"markets": self.candidates(), "cursor": None})
        self.addCleanup(outside.unlink, missing_ok=True)
        link = self.root / "linked-page.json"
        link.symlink_to(outside)
        for label, relative in (("escape", "../outside.json"), ("symlink", link.name)):
            with self.subTest(label=label):
                document = self.snapshot()
                document["payload"]["pages"][0]["path"] = relative
                document["payload"]["pages"][0]["sha256"] = phase7.sha256_file(outside)
                self.rehash(document)
                with self.assertRaisesRegex(
                    operator.OperatorError, "CandidateSnapshotPageMismatch"
                ):
                    operator.verify_candidate_snapshot(
                        self.write_snapshot(document), artifact_root=self.root
                    )

    def test_candidate_snapshot_requires_retrieval_before_capture_window(self) -> None:
        document = self.snapshot()
        document["payload"]["retrieval_completed_at_utc"] = "2026-08-02T00:00:00Z"
        self.rehash(document)

        with self.assertRaisesRegex(operator.OperatorError, "CandidateSnapshotTimeInvalid"):
            operator.verify_candidate_snapshot(
                self.write_snapshot(document), artifact_root=self.root
            )

    def test_run_approval_binds_snapshot_window_spec_files_and_durable_storage(self) -> None:
        snapshot_path = self.write_snapshot()
        approval_path = self.write_approval(self.approval(snapshot_path))

        verified = self.verify_approval(approval_path, snapshot_path)

        self.assertTrue(verified["approved"])

    def test_run_approval_rejects_unsafe_symlink_or_mismatched_acquisition_spec(self) -> None:
        snapshot_path = self.write_snapshot()
        base = self.approval(snapshot_path)
        outside = self.root.parent / f"{self.root.name}-outside-spec.json"
        phase7.write_json(outside, {"schema": "synthetic.acquisition"})
        self.addCleanup(outside.unlink, missing_ok=True)
        link = self.root / "linked-spec.json"
        link.symlink_to(outside)
        mutations = [
            ("escape", "opening_path", "../outside-spec.json"),
            ("symlink", "opening_path", link.name),
            ("stale hash", "opening_sha256", "0" * 64),
        ]
        for label, field, value in mutations:
            with self.subTest(label=label):
                document = copy.deepcopy(base)
                document["payload"]["acquisition_specs"][0][field] = value
                self.rehash(document)
                with self.assertRaisesRegex(
                    operator.OperatorError, "RunApprovalAcquisitionMismatch"
                ):
                    self.verify_approval(self.write_approval(document), snapshot_path)

    def test_run_approval_rejects_normalized_or_symlinked_storage_overlap(self) -> None:
        snapshot_path = self.write_snapshot()
        base = self.approval(snapshot_path)
        alias = self.root / "storage-alias"
        alias.symlink_to(self.root / "primary", target_is_directory=True)
        mutations = [
            (
                "normalized overlap",
                str(self.root / "primary" / ".." / "backup"),
            ),
            ("symlink alias", str(alias)),
        ]
        for label, backup in mutations:
            with self.subTest(label=label):
                document = copy.deepcopy(base)
                document["payload"]["storage"]["backup_path"] = backup
                self.rehash(document)
                with self.assertRaisesRegex(operator.OperatorError, "RunApprovalStorageMismatch"):
                    self.verify_approval(self.write_approval(document), snapshot_path)

    def test_run_approval_requires_approval_after_retrieval_and_before_capture(self) -> None:
        snapshot_path = self.write_snapshot()
        base = self.approval(snapshot_path)
        for label, approved_at in (
            ("before retrieval", "2026-07-31T23:59:59Z"),
            ("after capture starts", "2026-08-02T00:00:01Z"),
        ):
            with self.subTest(label=label):
                document = copy.deepcopy(base)
                document["payload"]["approved_at_utc"] = approved_at
                self.rehash(document)
                with self.assertRaisesRegex(operator.OperatorError, "RunApprovalTimeInvalid"):
                    self.verify_approval(self.write_approval(document), snapshot_path)


if __name__ == "__main__":
    unittest.main()
