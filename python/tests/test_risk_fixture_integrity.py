"""Tests for the integrity-only risk fixture authoring workflow."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from python import pmm_phase7 as phase7
from tools import risk_fixture_integrity as integrity


class RiskFixtureIntegrityTests(unittest.TestCase):
    def _copy_corpus(self, name: str = "checkpoint_v1") -> tuple[tempfile.TemporaryDirectory[str], Path]:
        scratch = tempfile.TemporaryDirectory(prefix="pmm-risk-integrity-")
        root = Path(scratch.name) / name
        shutil.copytree(integrity.CORPORA[name][0], root)
        return scratch, root

    def _copy_cli_repository(
        self, *corpora: str
    ) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        scratch = tempfile.TemporaryDirectory(prefix="pmm-risk-integrity-cli-")
        repository = Path(scratch.name) / "repository"
        tools_root = repository / "tools"
        tools_root.mkdir(parents=True)
        shutil.copy2(Path(integrity.__file__).resolve(), tools_root / "risk_fixture_integrity.py")
        fixture_root = repository / "python" / "tests" / "fixtures" / "risk_conformance"
        fixture_root.mkdir(parents=True)
        for corpus in corpora:
            shutil.copytree(integrity.CORPORA[corpus][0], fixture_root / corpus)
        return scratch, repository

    @staticmethod
    def _snapshot(root: Path) -> dict[str, bytes]:
        return {
            path.name: path.read_bytes()
            for path in sorted(root.iterdir())
            if path.is_file() and not path.is_symlink()
        }

    @staticmethod
    def _snapshot_cli_corpora(repository: Path) -> dict[str, bytes]:
        root = repository / "python" / "tests" / "fixtures" / "risk_conformance"
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file() and not path.is_symlink()
        }

    @staticmethod
    def _run_cli(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(repository / "tools" / "risk_fixture_integrity.py"),
                *arguments,
            ],
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
        )

    def _make_cli_member_stale(
        self, repository: Path, corpus: str, member_name: str
    ) -> dict[str, object]:
        member = (
            repository
            / "python"
            / "tests"
            / "fixtures"
            / "risk_conformance"
            / corpus
            / member_name
        )
        document = self._load(member)
        document["fixture_id"] = f"{document['fixture_id']}_cli_edited"
        member.write_text(json.dumps(document, indent=2), encoding="utf-8")
        return document

    @staticmethod
    def _load(path: Path) -> dict[str, object]:
        value = json.loads(path.read_bytes())
        if not isinstance(value, dict):
            raise AssertionError(f"{path} is not an object")
        return value

    def test_checked_in_corpora_are_unchanged_byte_for_byte(self) -> None:
        for name, (root, schema) in integrity.CORPORA.items():
            with self.subTest(corpus=name):
                before = self._snapshot(root)
                plan = integrity.build_plan(root, schema)
                self.assertEqual(plan.changes, ())
                integrity.write_plans([plan])
                self.assertEqual(self._snapshot(root), before)

    def test_cli_canonical_verification_is_read_only(self) -> None:
        scratch, repository = self._copy_cli_repository("checkpoint_v1")
        self.addCleanup(scratch.cleanup)
        before = self._snapshot_cli_corpora(repository)

        completed = self._run_cli(repository, "--corpus", "checkpoint_v1")

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(
            completed.stdout,
            "fixture integrity metadata is canonical and current\n",
        )
        self.assertEqual(completed.stderr, "")
        self.assertEqual(self._snapshot_cli_corpora(repository), before)

    def test_cli_verification_selects_only_requested_corpora_without_writing(self) -> None:
        cases = (
            (
                "checkpoint_v1",
                ("checkpoint_v1",),
                (("checkpoint_v1", "roundtrip_empty_state.json"),),
            ),
            (
                "v1",
                ("v1",),
                (("v1", "lifecycle.json"),),
            ),
            (
                "all",
                ("v1", "checkpoint_v1"),
                (
                    ("v1", "lifecycle.json"),
                    ("checkpoint_v1", "roundtrip_empty_state.json"),
                ),
            ),
        )
        for selection, copied_corpora, mutations in cases:
            with self.subTest(selection=selection):
                scratch, repository = self._copy_cli_repository(*copied_corpora)
                try:
                    for corpus, member_name in mutations:
                        self._make_cli_member_stale(repository, corpus, member_name)
                    before = self._snapshot_cli_corpora(repository)

                    completed = self._run_cli(repository, "--corpus", selection)

                    expected_lines: list[str] = []
                    for corpus, member_name in mutations:
                        prefix = f"python/tests/fixtures/risk_conformance/{corpus}"
                        expected_lines.extend(
                            (
                                f"would update {prefix}/{member_name}",
                                f"would update {prefix}/manifest.json",
                            )
                        )
                    expected_lines.append(
                        "rerun with --write after reviewing the authored JSON values"
                    )
                    self.assertEqual(completed.returncode, 1)
                    self.assertEqual(completed.stdout, "")
                    self.assertEqual(completed.stderr, "\n".join(expected_lines) + "\n")
                    self.assertEqual(self._snapshot_cli_corpora(repository), before)
                finally:
                    scratch.cleanup()

    def test_cli_structural_refusal_is_read_only(self) -> None:
        scratch, repository = self._copy_cli_repository("checkpoint_v1")
        self.addCleanup(scratch.cleanup)
        manifest = (
            repository
            / "python"
            / "tests"
            / "fixtures"
            / "risk_conformance"
            / "checkpoint_v1"
            / "manifest.json"
        )
        manifest.write_bytes(b"\xef\xbb\xbf" + manifest.read_bytes())
        before = self._snapshot_cli_corpora(repository)

        completed = self._run_cli(repository, "--corpus", "checkpoint_v1")

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertTrue(completed.stderr.startswith("error: "))
        self.assertNotIn("usage:", completed.stderr)
        self.assertIn("must not contain a UTF-8 byte-order mark", completed.stderr)
        self.assertEqual(self._snapshot_cli_corpora(repository), before)

    def test_cli_write_repairs_then_verifies_and_repeats_as_no_op(self) -> None:
        scratch, repository = self._copy_cli_repository("checkpoint_v1")
        self.addCleanup(scratch.cleanup)
        member_name = "roundtrip_empty_state.json"
        document = self._make_cli_member_stale(repository, "checkpoint_v1", member_name)
        before = self._snapshot_cli_corpora(repository)

        written = self._run_cli(repository, "--corpus", "checkpoint_v1", "--write")

        member_relative = f"checkpoint_v1/{member_name}"
        manifest_relative = "checkpoint_v1/manifest.json"
        after = self._snapshot_cli_corpora(repository)
        changed = {
            path for path in before | after if before.get(path) != after.get(path)
        }
        self.assertEqual(written.returncode, 0)
        self.assertEqual(
            written.stdout,
            "updated python/tests/fixtures/risk_conformance/checkpoint_v1/"
            f"{member_name}\n"
            "updated python/tests/fixtures/risk_conformance/checkpoint_v1/manifest.json\n",
        )
        self.assertEqual(written.stderr, "")
        self.assertEqual(changed, {member_relative, manifest_relative})
        self.assertEqual(after[member_relative], integrity.canonical_bytes(document))

        manifest = json.loads(after[manifest_relative])
        entry = next(
            item
            for item in manifest["payload"]["entries"]
            if item["fixture"] == member_name
        )
        self.assertEqual(
            entry["fixture_sha256"], hashlib.sha256(after[member_relative]).hexdigest()
        )
        self.assertEqual(
            manifest["payload_sha256"],
            hashlib.sha256(integrity.canonical_bytes(manifest["payload"])).hexdigest(),
        )

        verified = self._run_cli(repository, "--corpus", "checkpoint_v1")
        self.assertEqual(verified.returncode, 0)
        self.assertEqual(
            verified.stdout,
            "fixture integrity metadata is canonical and current\n",
        )
        self.assertEqual(verified.stderr, "")
        self.assertEqual(self._snapshot_cli_corpora(repository), after)

        repeated = self._run_cli(repository, "--corpus", "checkpoint_v1", "--write")
        self.assertEqual(repeated.returncode, 0)
        self.assertEqual(
            repeated.stdout,
            "fixture integrity metadata is already canonical and current\n",
        )
        self.assertEqual(repeated.stderr, "")
        self.assertEqual(self._snapshot_cli_corpora(repository), after)

    def test_cli_argparse_refusals_are_distinct_from_corpus_errors(self) -> None:
        scratch, repository = self._copy_cli_repository()
        self.addCleanup(scratch.cleanup)
        cases = (
            ((), "the following arguments are required: --corpus"),
            (("--corpus", "invalid"), "invalid choice: 'invalid'"),
        )
        for arguments, expected_diagnostic in cases:
            with self.subTest(arguments=arguments):
                completed = self._run_cli(repository, *arguments)
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(completed.stdout, "")
                self.assertTrue(completed.stderr.startswith("usage: "))
                self.assertIn("risk_fixture_integrity.py: error:", completed.stderr)
                self.assertIn(expected_diagnostic, completed.stderr)

    def test_stale_hashes_and_noncanonical_json_are_repaired(self) -> None:
        scratch, root = self._copy_corpus()
        self.addCleanup(scratch.cleanup)
        member = root / "roundtrip_empty_state.json"
        document = self._load(member)
        member.write_text(json.dumps(document, indent=2), encoding="utf-8")
        manifest_path = root / "manifest.json"
        manifest = self._load(manifest_path)
        entry = next(
            item
            for item in manifest["payload"]["entries"]
            if item["fixture"] == member.name
        )
        entry["fixture_sha256"] = "a" * 64
        manifest_path.write_bytes(integrity.canonical_bytes(manifest))

        plan = integrity.build_plan(root, integrity.CORPORA["checkpoint_v1"][1])
        self.assertEqual(
            {path.name for path in plan.changes},
            {"manifest.json", "roundtrip_empty_state.json"},
        )
        integrity.write_plans([plan])

        expected = (phase7.canonical_json(document) + "\n").encode("utf-8")
        self.assertEqual(member.read_bytes(), expected)
        manifest = self._load(root / "manifest.json")
        entry = next(
            item
            for item in manifest["payload"]["entries"]
            if item["fixture"] == member.name
        )
        self.assertEqual(entry["fixture_sha256"], hashlib.sha256(expected).hexdigest())
        self.assertEqual(
            manifest["payload_sha256"],
            hashlib.sha256(integrity.canonical_bytes(manifest["payload"])).hexdigest(),
        )

    def test_repeated_write_is_byte_identical(self) -> None:
        scratch, root = self._copy_corpus()
        self.addCleanup(scratch.cleanup)
        member = root / "roundtrip_empty_state.expected.json"
        member.write_bytes(member.read_bytes().rstrip(b"\n") + b"  \n")
        schema = integrity.CORPORA["checkpoint_v1"][1]

        integrity.write_plans([integrity.build_plan(root, schema)])
        first = self._snapshot(root)
        second_plan = integrity.build_plan(root, schema)
        self.assertEqual(second_plan.changes, ())
        integrity.write_plans([second_plan])
        self.assertEqual(self._snapshot(root), first)

    def test_semantic_expected_answer_is_preserved_not_derived(self) -> None:
        scratch, root = self._copy_corpus()
        self.addCleanup(scratch.cleanup)
        trace_path = root / "checkpoint_zero_ingress.expected.json"
        trace = self._load(trace_path)
        trace["transitions"][0]["result"] = "checkpoint_duplicate_ingress"
        trace_path.write_text(json.dumps(trace, indent=2), encoding="utf-8")
        schema = integrity.CORPORA["checkpoint_v1"][1]

        integrity.write_plans([integrity.build_plan(root, schema)])

        rewritten = self._load(trace_path)
        self.assertEqual(
            rewritten["transitions"][0]["result"],
            "checkpoint_duplicate_ingress",
        )
        self.assertEqual(
            trace_path.read_bytes(),
            (phase7.canonical_json(rewritten) + "\n").encode("utf-8"),
        )

    def test_verify_mode_reports_changes_without_writing(self) -> None:
        scratch, root = self._copy_corpus()
        self.addCleanup(scratch.cleanup)
        member = root / "roundtrip_empty_state.json"
        document = self._load(member)
        document["fixture_id"] = "deliberately_edited_identifier"
        member.write_text(json.dumps(document, indent=2), encoding="utf-8")
        before = self._snapshot(root)

        plan = integrity.build_plan(root, integrity.CORPORA["checkpoint_v1"][1])

        self.assertTrue(plan.changes)
        self.assertEqual(self._snapshot(root), before)

    def test_unsafe_and_incomplete_manifests_are_refused_without_writes(self) -> None:
        mutations = {
            "unsafe path": lambda manifest: manifest["payload"]["entries"][0].__setitem__(
                "fixture", "../escape.json"
            ),
            "duplicate member": lambda manifest: manifest["payload"]["entries"][1].__setitem__(
                "fixture", manifest["payload"]["entries"][0]["fixture"]
            ),
            "missing field": lambda manifest: manifest.pop("payload_sha256"),
            "unknown field": lambda manifest: manifest.__setitem__("surprise", True),
        }
        schema = integrity.CORPORA["checkpoint_v1"][1]
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                scratch, root = self._copy_corpus()
                try:
                    manifest_path = root / "manifest.json"
                    manifest = self._load(manifest_path)
                    mutate(manifest)
                    manifest_path.write_bytes(integrity.canonical_bytes(manifest))
                    before = self._snapshot(root)
                    with self.assertRaises(integrity.CorpusError):
                        integrity.build_plan(root, schema)
                    self.assertEqual(self._snapshot(root), before)
                finally:
                    scratch.cleanup()

    def test_missing_symlink_and_unreferenced_members_are_refused(self) -> None:
        schema = integrity.CORPORA["checkpoint_v1"][1]

        scratch, root = self._copy_corpus()
        self.addCleanup(scratch.cleanup)
        missing = root / "roundtrip_empty_state.json"
        missing.unlink()
        with self.assertRaises(integrity.CorpusError):
            integrity.build_plan(root, schema)

        scratch_link, root_link = self._copy_corpus()
        self.addCleanup(scratch_link.cleanup)
        member = root_link / "roundtrip_empty_state.json"
        real_member = root_link / "real-member"
        member.rename(real_member)
        member.symlink_to(real_member)
        with self.assertRaises(integrity.CorpusError):
            integrity.build_plan(root_link, schema)

        scratch_extra, root_extra = self._copy_corpus()
        self.addCleanup(scratch_extra.cleanup)
        (root_extra / "extra.json").write_bytes(b"{}\n")
        with self.assertRaises(integrity.CorpusError):
            integrity.build_plan(root_extra, schema)

    def test_ambiguous_json_is_refused(self) -> None:
        cases = {
            "duplicate key": b'{"schema":"x","schema":"y"}\n',
            "float": b'{"value":1.5}\n',
            "nonstandard number": b'{"value":NaN}\n',
            "array": b'[]\n',
        }
        schema = integrity.CORPORA["checkpoint_v1"][1]
        for name, bytes_value in cases.items():
            with self.subTest(name=name):
                scratch, root = self._copy_corpus()
                try:
                    member = root / "roundtrip_empty_state.json"
                    member.write_bytes(bytes_value)
                    with self.assertRaises(integrity.CorpusError):
                        integrity.build_plan(root, schema)
                finally:
                    scratch.cleanup()

    def test_every_documented_parser_refusal_is_specific_and_read_only(self) -> None:
        schema = integrity.CORPORA["checkpoint_v1"][1]

        def write_manifest(root: Path, manifest: dict[str, object]) -> None:
            manifest["payload_sha256"] = hashlib.sha256(
                integrity.canonical_bytes(manifest["payload"])
            ).hexdigest()
            (root / "manifest.json").write_bytes(integrity.canonical_bytes(manifest))

        def mutate_manifest(
            root: Path, mutation: Callable[[dict[str, object]], None]
        ) -> Path:
            manifest = self._load(root / "manifest.json")
            mutation(manifest)
            write_manifest(root, manifest)
            return root

        def add_utf8_bom(root: Path) -> Path:
            manifest = root / "manifest.json"
            manifest.write_bytes(b"\xef\xbb\xbf" + manifest.read_bytes())
            return root

        def add_invalid_utf8(root: Path) -> Path:
            manifest = root / "manifest.json"
            manifest.write_bytes(manifest.read_bytes() + b"\xff")
            return root

        def set_integer(root: Path, value: int) -> Path:
            member = root / "checkpoint_active_order_limit.json"
            document = self._load(member)
            document["checkpoint"]["limits"]["maximum_active_orders"] = value
            member_bytes = integrity.canonical_bytes(document)
            member.write_bytes(member_bytes)

            manifest = self._load(root / "manifest.json")
            entry = next(
                item
                for item in manifest["payload"]["entries"]
                if item["fixture"] == member.name
            )
            entry["fixture_sha256"] = hashlib.sha256(member_bytes).hexdigest()
            write_manifest(root, manifest)
            return root

        def use_root_symlink(root: Path) -> Path:
            real_root = root.with_name(f"{root.name}-real")
            root.rename(real_root)
            root.symlink_to(real_root, target_is_directory=True)
            return root

        def use_absolute_member(root: Path) -> Path:
            def mutate(manifest: dict[str, object]) -> None:
                entry = manifest["payload"]["entries"][0]
                entry["fixture"] = str((root / entry["fixture"]).resolve())

            return mutate_manifest(root, mutate)

        def use_backslash_member(root: Path) -> Path:
            def mutate(manifest: dict[str, object]) -> None:
                entry = manifest["payload"]["entries"][0]
                original = root / entry["expected_trace"]
                unsafe_name = original.name.replace(".", "\\.", 1)
                original.rename(root / unsafe_name)
                entry["expected_trace"] = unsafe_name

            return mutate_manifest(root, mutate)

        def unsort_entries(root: Path) -> Path:
            def mutate(manifest: dict[str, object]) -> None:
                entries = manifest["payload"]["entries"]
                entries[0], entries[1] = entries[1], entries[0]

            return mutate_manifest(root, mutate)

        def change_top_level_schema(root: Path) -> Path:
            return mutate_manifest(
                root,
                lambda manifest: manifest.__setitem__(
                    "schema", "pmm.wrong_fixture_manifest.v1"
                ),
            )

        def change_payload_schema(root: Path) -> Path:
            return mutate_manifest(
                root,
                lambda manifest: manifest["payload"].__setitem__(
                    "schema", "pmm.wrong_fixture_manifest.v1"
                ),
            )

        mutations = (
            (
                "UTF-8 BOM",
                add_utf8_bom,
                "must not contain a UTF-8 byte-order mark",
            ),
            ("invalid UTF-8", add_invalid_utf8, "is not valid UTF-8"),
            (
                "signed 64-bit underflow",
                lambda root: set_integer(root, -(2**63) - 1),
                "JSON integer: '-9223372036854775809' is outside the C++ reader's "
                "64-bit range",
            ),
            (
                "unsigned 64-bit overflow",
                lambda root: set_integer(root, 2**64),
                "JSON integer: '18446744073709551616' is outside the C++ reader's "
                "64-bit range",
            ),
            (
                "fixture-root symlink",
                use_root_symlink,
                "fixture root must not be a symlink",
            ),
            (
                "absolute manifest member name",
                use_absolute_member,
                ".payload.entries[0].fixture: must be a bare filename inside the fixture root",
            ),
            (
                "backslash-containing manifest member name",
                use_backslash_member,
                ".payload.entries[0].expected_trace: must be a bare filename inside the "
                "fixture root",
            ),
            (
                "unsorted manifest entries",
                unsort_entries,
                ".payload.entries[1].fixture: entries must be strictly fixture-name sorted",
            ),
            (
                "mismatched top-level manifest schema",
                change_top_level_schema,
                ".schema: must be 'pmm.risk_checkpoint_conformance_fixture_manifest.v1'",
            ),
            (
                "mismatched manifest-payload schema",
                change_payload_schema,
                ".payload.schema: must be "
                "'pmm.risk_checkpoint_conformance_fixture_manifest.v1'",
            ),
        )
        self.assertEqual(len(mutations), 10)

        for name, mutate, expected_diagnostic in mutations:
            with self.subTest(name=name):
                scratch, root = self._copy_corpus()
                try:
                    validation_root = mutate(root)
                    before = self._snapshot(validation_root)
                    with self.assertRaises(integrity.CorpusError) as caught:
                        integrity.build_plan(validation_root, schema)
                    self.assertIn(expected_diagnostic, str(caught.exception))
                    self.assertEqual(self._snapshot(validation_root), before)
                finally:
                    scratch.cleanup()

    def test_failed_atomic_replacement_does_not_truncate_destination(self) -> None:
        scratch, root = self._copy_corpus()
        self.addCleanup(scratch.cleanup)
        member = root / "roundtrip_empty_state.json"
        member.write_bytes(member.read_bytes() + b" ")
        plan = integrity.build_plan(root, integrity.CORPORA["checkpoint_v1"][1])
        before = self._snapshot(root)

        with mock.patch.object(os, "replace", side_effect=OSError("injected failure")):
            with self.assertRaises(integrity.CorpusError):
                integrity.write_plans([plan])

        self.assertEqual(self._snapshot(root), before)
        self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_interrupted_member_then_manifest_write_fails_closed_and_is_repairable(self) -> None:
        scratch, root = self._copy_corpus()
        self.addCleanup(scratch.cleanup)
        member = root / "roundtrip_empty_state.json"
        document = self._load(member)
        document["fixture_id"] = "deliberately_edited_identifier"
        member.write_text(json.dumps(document, indent=2), encoding="utf-8")
        schema = integrity.CORPORA["checkpoint_v1"][1]
        plan = integrity.build_plan(root, schema)
        real_replace = os.replace
        calls = 0

        def interrupt_second_replace(source, destination) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected manifest failure")
            real_replace(source, destination)

        with mock.patch.object(os, "replace", side_effect=interrupt_second_replace):
            with self.assertRaises(integrity.CorpusError):
                integrity.write_plans([plan])

        repair = integrity.build_plan(root, schema)
        self.assertEqual([path.name for path in repair.changes], ["manifest.json"])
        integrity.write_plans([repair])
        self.assertEqual(integrity.build_plan(root, schema).changes, ())
        self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_write_refuses_bytes_changed_after_validation(self) -> None:
        scratch, root = self._copy_corpus()
        self.addCleanup(scratch.cleanup)
        member = root / "roundtrip_empty_state.json"
        member.write_bytes(member.read_bytes() + b" ")
        plan = integrity.build_plan(root, integrity.CORPORA["checkpoint_v1"][1])
        member.write_bytes(member.read_bytes() + b"newer edit")
        before = self._snapshot(root)

        with self.assertRaises(integrity.CorpusError):
            integrity.write_plans([plan])

        self.assertEqual(self._snapshot(root), before)


if __name__ == "__main__":
    unittest.main()
