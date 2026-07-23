"""Focused offline tests for the additive B2c Measurement V2 supervisor."""

from __future__ import annotations

import shutil
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from dataclasses import replace
from pathlib import Path
from unittest import mock

from python import pmm_phase7 as phase7
from python import pmm_phase7_measurement as measurement


class B2cMeasurementV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "package"
        self.root.mkdir()
        self.controls = replace(
            measurement.V2_CONTROLS,
            sigint_grace_seconds=0.05,
            sigterm_grace_seconds=0.05,
            quiescence_grace_seconds=0.2,
            sample_interval_seconds=0.01,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def measure(self, script: str, **kwargs):
        controls = kwargs.pop("controls", self.controls)
        stage = kwargs.pop("stage", "capture-v2")
        package_root = kwargs.pop("package_root", self.root)
        report_path = kwargs.pop("report_path", self.root / "measurements/capture.json")
        raw_roots = kwargs.pop("raw_roots", [self.root / "raw"])
        output_roots = kwargs.pop("output_roots", [self.root / "raw"])
        return measurement.run_measurement_v2(
            stage=stage,
            command=[sys.executable, "-c", script],
            report_path=report_path,
            package_root=package_root,
            raw_roots=raw_roots,
            output_roots=output_roots,
            controls=controls,
            **kwargs,
        )

    def wait_for_pid_exit(self, pid: int, timeout: float = 1.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
            time.sleep(0.01)
        return False

    def schedule_interrupts(self, marker: Path, count: int) -> threading.Thread:
        def send() -> None:
            deadline = time.monotonic() + 2.0
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.005)
            time.sleep(0.03)
            for _ in range(count):
                os.kill(os.getpid(), signal.SIGINT)
                time.sleep(0.01)

        thread = threading.Thread(target=send, daemon=True)
        thread.start()
        return thread

    def stream_flood_script(self, stdout_bytes: int, stderr_bytes: int) -> str:
        return (
            "import os, signal, threading, time; signal.signal(signal.SIGINT, signal.SIG_IGN); "
            "exec(\"def write(fd, remaining):\\n"
            "    chunk = b'x' * 65536\\n"
            "    while remaining:\\n"
            "        data = chunk[:min(len(chunk), remaining)]\\n"
            "        offset = 0\\n"
            "        while offset < len(data):\\n"
            "            offset += os.write(fd, data[offset:])\\n"
            "        remaining -= len(data)\"); "
            f"threads = [threading.Thread(target=write, args=(1, {stdout_bytes})), "
            f"threading.Thread(target=write, args=(2, {stderr_bytes}))]; "
            "[thread.start() for thread in threads]; "
            "[thread.join() for thread in threads]; time.sleep(30)"
        )

    def assert_no_retained_stream_logs(self) -> None:
        retained = [
            path for path in self.root.rglob("*")
            if path.is_file() and (path.suffix in {".log", ".tmp"} or "stream" in path.name)
        ]
        self.assertEqual(retained, [])

    def test_measurement_child_exit_does_not_leave_grandchild_running(self) -> None:
        pid_file = self.root / "grandchild.pid"
        script = (
            "import subprocess, sys; from pathlib import Path; "
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], "
            "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
            f"Path({str(pid_file)!r}).write_text(str(child.pid))"
        )
        grandchild_pid: int | None = None
        try:
            result = self.measure(script)
            grandchild_pid = int(pid_file.read_text(encoding="utf-8"))
            self.assertTrue(
                self.wait_for_pid_exit(grandchild_pid),
                f"grandchild {grandchild_pid} remained alive after measurement returned",
            )
            self.assertTrue(result.report["teardown"]["process_group_quiescent"])
        finally:
            if grandchild_pid is None and pid_file.exists():
                grandchild_pid = int(pid_file.read_text(encoding="utf-8"))
            if grandchild_pid is not None and not self.wait_for_pid_exit(grandchild_pid, 0.05):
                try:
                    os.kill(grandchild_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_measurement_sampler_failure_after_leader_exit_still_terminates_grandchild(self) -> None:
        pid_file = self.root / "sampler-failure-grandchild.pid"
        script = (
            "import subprocess, sys; from pathlib import Path; "
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], "
            "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
            f"Path({str(pid_file)!r}).write_text(str(child.pid))"
        )
        failed_shutdown_sample = False

        def fail_once_then_sample(pgid: int, leader: int, require_leader: bool):
            nonlocal failed_shutdown_sample
            if not require_leader and not failed_shutdown_sample:
                failed_shutdown_sample = True
                raise measurement.SamplerFailure("MeasurementSamplerUnavailable")
            return measurement._sample_process_group(pgid, leader, require_leader)

        grandchild_pid: int | None = None
        try:
            result = self.measure(script, sampler=fail_once_then_sample)
            grandchild_pid = int(pid_file.read_text(encoding="utf-8"))
            self.assertEqual(result.exit_status, 1)
            self.assertTrue(self.wait_for_pid_exit(grandchild_pid))
            self.assertTrue(result.report["teardown"]["direct_child_reaped"])
            self.assertTrue(result.report["teardown"]["process_group_quiescent"])
        finally:
            if grandchild_pid is not None and not self.wait_for_pid_exit(grandchild_pid, 0.05):
                try:
                    os.kill(grandchild_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_measurement_report_must_be_inside_package_root(self) -> None:
        marker = self.root / "spawned"
        with self.assertRaisesRegex(measurement.MeasurementRefusal, "MeasurementPathUnsafe"):
            self.measure(
                f"from pathlib import Path; Path({str(marker)!r}).write_text('spawned')",
                report_path=Path(self.temp.name) / "outside.json",
            )
        self.assertFalse(marker.exists())

    def test_measurement_missing_identity_file_refuses_before_spawn(self) -> None:
        marker = self.root / "spawned"
        with self.assertRaisesRegex(measurement.MeasurementRefusal, "MeasurementPathUnsafe"):
            self.measure(
                f"from pathlib import Path; Path({str(marker)!r}).write_text('spawned')",
                identity_files=[self.root / "control/missing.json"],
            )
        self.assertFalse(marker.exists())

    def test_measurement_directory_identity_file_refuses_before_spawn(self) -> None:
        identity_directory = self.root / "control"
        identity_directory.mkdir()
        marker = self.root / "spawned"
        with self.assertRaisesRegex(measurement.MeasurementRefusal, "MeasurementPathUnsafe"):
            self.measure(
                f"from pathlib import Path; Path({str(marker)!r}).write_text('spawned')",
                identity_files=[identity_directory],
            )
        self.assertFalse(marker.exists())

    def test_measurement_identity_changed_by_child_fails_with_pre_run_hash(self) -> None:
        identity = self.root / "control.json"
        identity.write_text("before", encoding="utf-8")
        expected_sha256 = phase7.sha256_file(identity)

        result = self.measure(
            "from pathlib import Path; import time; "
            f"Path({str(identity)!r}).write_text('after', encoding='utf-8'); "
            "time.sleep(.05)",
            identity_files=[identity],
        )

        self.assertEqual(result.exit_status, 1)
        self.assertEqual(result.diagnostic_code, "MeasurementIdentityChanged")
        self.assertTrue(result.report_published)
        self.assertEqual(result.report["termination"]["reason"], "wrapper_failure")
        self.assertEqual(
            result.report["sampling"]["error_code"], "MeasurementIdentityChanged"
        )
        self.assertEqual(
            result.report["identity_files"],
            [{"path": str(identity.resolve()), "sha256": expected_sha256}],
        )

    def test_measurement_identity_schema_rejects_undeclared_fields(self) -> None:
        identity = self.root / "control.json"
        identity.write_text("unchanged", encoding="utf-8")
        result = self.measure(
            "import time; time.sleep(.05)", identity_files=[identity]
        )
        result.report["identity_files"][0]["unexpected"] = True

        with self.assertRaisesRegex(
            phase7.HistoricalDataError, "MeasurementV2SchemaMismatch"
        ):
            phase7.validate_historical_schema(
                result.report,
                "b2c-measurement-v2.schema.json",
                "MeasurementV2SchemaMismatch",
            )

    def test_measurement_accounting_root_escape_refuses_before_spawn(self) -> None:
        outside = Path(self.temp.name) / "outside"
        with self.assertRaisesRegex(measurement.MeasurementRefusal, "MeasurementPathUnsafe"):
            self.measure("raise SystemExit('spawned')", raw_roots=[outside])

    def test_measurement_duplicate_raw_root_refuses_before_spawn(self) -> None:
        raw = self.root / "raw"
        with self.assertRaisesRegex(measurement.MeasurementRefusal, "MeasurementRootDuplicate"):
            self.measure("raise SystemExit('spawned')", raw_roots=[raw, raw])

    def test_measurement_duplicate_output_root_refuses_before_spawn(self) -> None:
        output = self.root / "output"
        with self.assertRaisesRegex(measurement.MeasurementRefusal, "MeasurementRootDuplicate"):
            self.measure("raise SystemExit('spawned')", output_roots=[output, output])

    def test_measurement_ancestor_descendant_root_overlap_refuses_before_spawn(self) -> None:
        with self.assertRaisesRegex(measurement.MeasurementRefusal, "MeasurementRootOverlap"):
            self.measure(
                "raise SystemExit('spawned')",
                raw_roots=[self.root / "raw"],
                output_roots=[self.root / "raw" / "derived"],
            )

    def test_measurement_capture_stage_allows_exact_raw_output_root_identity(self) -> None:
        result = self.measure("import time; time.sleep(.05)")
        self.assertEqual(result.exit_status, 0)

    def test_measurement_capture_stage_requires_absent_or_empty_raw_root(self) -> None:
        raw = self.root / "raw"
        raw.mkdir()
        (raw / "prior").write_bytes(b"x")
        with self.assertRaisesRegex(measurement.MeasurementRefusal, "MeasurementRawRootNotEmpty"):
            self.measure("raise SystemExit('spawned')")

    def test_measurement_derived_stage_allows_preexisting_immutable_raw_root(self) -> None:
        raw = self.root / "raw"
        raw.mkdir()
        (raw / "prior").write_bytes(b"x")
        result = self.measure(
            "import time; time.sleep(.05)",
            stage="normalization-v3",
            output_roots=[self.root / "normalized"],
        )
        self.assertEqual(result.exit_status, 0)

    def test_measurement_derived_stage_rejects_exact_raw_output_root_identity(self) -> None:
        raw = self.root / "raw"
        with self.assertRaisesRegex(measurement.MeasurementRefusal, "MeasurementRootOverlap"):
            self.measure(
                "raise SystemExit('spawned')",
                stage="normalization-v3",
                raw_roots=[raw],
                output_roots=[raw],
            )

    def test_measurement_symlinked_accounting_member_refuses(self) -> None:
        raw = self.root / "raw"
        raw.mkdir()
        (raw / "link").symlink_to(Path(self.temp.name) / "missing")
        with self.assertRaisesRegex(measurement.MeasurementRefusal, "MeasurementPathUnsafe"):
            self.measure(
                "raise SystemExit('spawned')",
                stage="normalization-v3",
                output_roots=[self.root / "normalized"],
            )

    def test_measurement_package_root_symlink_refuses_before_spawn(self) -> None:
        actual = Path(self.temp.name) / "actual"
        actual.mkdir()
        linked = Path(self.temp.name) / "linked"
        linked.symlink_to(actual, target_is_directory=True)
        with self.assertRaisesRegex(measurement.MeasurementRefusal, "MeasurementPathUnsafe"):
            self.measure(
                "raise SystemExit('spawned')",
                package_root=linked,
                report_path=linked / "measurements/report.json",
                raw_roots=[linked / "raw"],
                output_roots=[linked / "raw"],
            )

    def test_measurement_accounting_root_symlinked_ancestor_refuses_before_spawn(self) -> None:
        real = self.root / "real"
        real.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(real, target_is_directory=True)
        with self.assertRaisesRegex(measurement.MeasurementRefusal, "MeasurementPathUnsafe"):
            self.measure(
                "raise SystemExit('spawned')",
                stage="normalization-v3",
                raw_roots=[alias / "raw"],
                output_roots=[self.root / "normalized"],
            )

    def test_measurement_same_size_path_swap_is_inventory_unstable(self) -> None:
        snapshots = [
            measurement._InventorySnapshot(1, (("a", 1),)),
            measurement._InventorySnapshot(1, (("b", 1),)),
            measurement._InventorySnapshot(1, (("a", 1),)),
            measurement._InventorySnapshot(1, (("b", 1),)),
        ]
        with mock.patch.object(measurement, "_inventory", side_effect=snapshots):
            with self.assertRaisesRegex(measurement.MeasurementRefusal, "MeasurementInventoryUnstable"):
                measurement._package_bytes(self.root)

    def test_measurement_transient_inventory_difference_retries_boundedly(self) -> None:
        snapshots = [
            measurement._InventorySnapshot(1, (("a", 1),)),
            measurement._InventorySnapshot(1, (("b", 1),)),
            measurement._InventorySnapshot(1, (("b", 1),)),
        ]
        with mock.patch.object(measurement, "_inventory", side_effect=snapshots) as inventory:
            self.assertEqual(measurement._package_bytes(self.root), 1)
        self.assertEqual(inventory.call_count, 3)

    def test_measurement_unstable_inventory_fails_closed_and_reaps(self) -> None:
        instability = measurement.MeasurementRefusal(
            "MeasurementInventoryUnstable", "synthetic persistent instability"
        )
        original_package_bytes = measurement._package_bytes
        outcomes = iter((0, instability, 0))

        def unstable_then_stable(root: Path) -> int:
            try:
                outcome = next(outcomes)
            except StopIteration:
                return original_package_bytes(root)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        with mock.patch.object(
            measurement, "_package_bytes", side_effect=unstable_then_stable
        ):
            result = self.measure("import time; time.sleep(30)")
        self.assertEqual(result.exit_status, 1)
        self.assertEqual(
            result.report["sampling"]["error_code"], "MeasurementInventoryUnstable"
        )
        self.assertTrue(result.report_path.exists())
        self.assertTrue(result.report["teardown"]["direct_child_reaped"])
        self.assertTrue(result.report["teardown"]["process_group_quiescent"])

    def test_measurement_exact_aggregate_budget_is_allowed(self) -> None:
        controls = replace(
            self.controls,
            aggregate_budget_bytes=self.controls.publication_reserve_bytes,
        )
        result = self.measure("import time; time.sleep(.05)", controls=controls)
        self.assertEqual(result.exit_status, 0)
        self.assertEqual(
            result.report["storage"]["final_aggregate_bytes"],
            measurement._package_bytes(self.root),
        )
        self.assertLessEqual(
            result.report["storage"]["final_aggregate_bytes"],
            controls.aggregate_budget_bytes,
        )

    def test_measurement_aggregate_budget_one_byte_over_stops_group(self) -> None:
        controls = replace(
            self.controls,
            aggregate_budget_bytes=self.controls.publication_reserve_bytes,
        )
        result = self.measure(
            "from pathlib import Path; Path('late').write_bytes(b'x')",
            controls=controls,
        )
        self.assertEqual(result.exit_status, 130)
        self.assertEqual(result.report["termination"]["reason"], "aggregate_budget_exceeded")
        self.assertEqual(result.diagnostic_code, "MeasurementV2AggregateBudgetExceeded")
        self.assertTrue(result.report_published)

    def test_measurement_final_raw_budget_one_byte_over_stops_group(self) -> None:
        controls = replace(self.controls, raw_budget_bytes=0)
        result = self.measure(
            "from pathlib import Path; Path('raw').mkdir(); Path('raw/late').write_bytes(b'x')",
            controls=controls,
        )
        self.assertEqual(result.exit_status, 130)
        self.assertEqual(result.report["termination"]["reason"], "raw_budget_exceeded")

    def test_measurement_preexisting_aggregate_bytes_are_counted(self) -> None:
        (self.root / "control").write_bytes(b"1234567")
        result = self.measure(
            "import time; time.sleep(.05)",
            stage="normalization-v3",
            output_roots=[self.root / "normalized"],
        )
        self.assertEqual(result.report["storage"]["initial_aggregate_bytes"], 7)

    def test_measurement_free_space_exact_minimum_is_allowed(self) -> None:
        result = self.measure(
            "import time; time.sleep(.05)",
            free_space=lambda _path: self.controls.minimum_free_bytes,
        )
        self.assertEqual(result.exit_status, 0)

    def test_measurement_control_plane_reservation_prevents_aggregate_overrun(self) -> None:
        controls = replace(
            self.controls,
            publication_reserve_bytes=1,
            aggregate_budget_bytes=measurement.MIB,
        )
        result = self.measure("import time; time.sleep(.05)", controls=controls)
        self.assertEqual(result.exit_status, 1)
        self.assertFalse(result.report_path.exists())
        self.assertEqual(result.diagnostic_code, "MeasurementV2PublicationFailed")
        self.assertFalse(result.report_published)
        self.assertFalse(
            result.report_path.with_name(f"{result.report_path.name}.partial").exists()
        )

    def test_measurement_sampler_failure_dominates_final_raw_budget_overrun(self) -> None:
        def broken_sampler(_pgid: int, _leader: int, _require_leader: bool):
            raise measurement.SamplerFailure("MeasurementSamplerUnavailable")

        result = self.measure(
            "from pathlib import Path; import time; Path('raw').mkdir(); "
            "Path('raw/x').write_bytes(b'x'); time.sleep(30)",
            controls=replace(self.controls, raw_budget_bytes=0),
            sampler=broken_sampler,
        )
        self.assertEqual(result.exit_status, 1)
        self.assertEqual(result.report["termination"]["reason"], "sampler_failure")
        self.assertFalse(result.report["teardown"]["process_group_quiescent"])

    def test_measurement_wrapper_failure_dominates_final_raw_budget_overrun(self) -> None:
        def broken_sampler(pgid: int, leader: int, require_leader: bool):
            if require_leader:
                raise OSError("synthetic wrapper failure")
            return measurement._sample_process_group(pgid, leader, False)

        result = self.measure(
            "from pathlib import Path; import time; Path('raw').mkdir(); "
            "Path('raw/x').write_bytes(b'x'); time.sleep(30)",
            controls=replace(self.controls, raw_budget_bytes=0),
            sampler=broken_sampler,
        )
        self.assertEqual(result.exit_status, 1)
        self.assertEqual(result.report["termination"]["reason"], "wrapper_failure")
        self.assertEqual(result.diagnostic_code, "MeasurementV2WrapperFailure")
        self.assertTrue(result.report_published)

    def test_measurement_teardown_failure_dominates_raw_budget_stop(self) -> None:
        calls = 0

        def never_quiescent(_pgid: int, _leader: int, require_leader: bool):
            nonlocal calls
            calls += 1
            return (1, 1, 0)

        result = self.measure(
            "from pathlib import Path; import time; Path('raw').mkdir(); "
            "Path('raw/x').write_bytes(b'x'); time.sleep(30)",
            controls=replace(
                self.controls,
                raw_budget_bytes=0,
                sigint_grace_seconds=0.0,
                sigterm_grace_seconds=0.0,
                quiescence_grace_seconds=0.05,
            ),
            sampler=never_quiescent,
        )
        self.assertGreater(calls, 1)
        self.assertEqual(result.exit_status, 1)
        self.assertEqual(result.report["termination"]["reason"], "teardown_failure")
        self.assertEqual(result.diagnostic_code, "MeasurementV2TeardownFailure")
        self.assertTrue(result.report_published)
        self.assertFalse(result.report["teardown"]["process_group_quiescent"])

    def test_measurement_duplicate_ps_pid_cannot_report_valid_sample(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="10 10 1 S\n10 10 1 S\n", stderr=""
        )
        with mock.patch.object(measurement.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(measurement.SamplerFailure, "MeasurementSamplerMalformed"):
                measurement._sample_process_group(10, 10, True)

    def test_measurement_ps_launch_failure_cannot_report_zero_rss(self) -> None:
        with mock.patch.object(measurement.subprocess, "run", side_effect=OSError("no ps")):
            with self.assertRaisesRegex(measurement.SamplerFailure, "MeasurementSamplerUnavailable"):
                measurement._sample_process_group(10, 10, True)

    def test_measurement_ps_nonzero_exit_cannot_report_zero_rss(self) -> None:
        failure = subprocess.CalledProcessError(1, ["ps"])
        with mock.patch.object(measurement.subprocess, "run", side_effect=failure):
            with self.assertRaisesRegex(measurement.SamplerFailure, "MeasurementSamplerUnavailable"):
                measurement._sample_process_group(10, 10, True)

    def test_measurement_malformed_ps_row_cannot_report_zero_rss(self) -> None:
        malformed_rows = (
            "10 10 1\n",
            "pid 10 1 S\n",
            "10 10 -1 S\n",
        )
        for row in malformed_rows:
            with self.subTest(row=row):
                completed = subprocess.CompletedProcess(
                    args=[], returncode=0, stdout=row, stderr=""
                )
                with mock.patch.object(measurement.subprocess, "run", return_value=completed):
                    with self.assertRaisesRegex(
                        measurement.SamplerFailure, "MeasurementSamplerMalformed"
                    ):
                        measurement._sample_process_group(10, 10, True)

    def test_measurement_zero_rss_requires_successful_zero_sample(self) -> None:
        def zero_sampler(_pgid: int, _leader: int, require_leader: bool):
            return (1, 0, 0) if require_leader else (0, 0, 0)

        result = self.measure("import time; time.sleep(.05)", sampler=zero_sampler)
        self.assertTrue(result.report["sampling"]["valid"])
        self.assertEqual(result.report["sampling"]["peak_rss_kib"], 0)

    def test_measurement_zombie_members_are_recorded_but_not_live(self) -> None:
        def zombie_sampler(_pgid: int, _leader: int, require_leader: bool):
            return (1, 1, 2) if require_leader else (0, 0, 2)

        result = self.measure("import time; time.sleep(.05)", sampler=zombie_sampler)
        self.assertEqual(result.exit_status, 0)
        self.assertEqual(result.report["teardown"]["zombie_members_observed"], 2)

    def test_measurement_signal_eperm_is_teardown_failure(self) -> None:
        class FakeProcess:
            pid = 10
            returncode: int | None = None

            def wait(self, timeout: float | None = None) -> int:
                self.returncode = 0
                return 0

        process = FakeProcess()
        with mock.patch.object(measurement.os, "killpg", side_effect=PermissionError):
            state = measurement._shutdown_owned_group(
                process=process,
                pgid=10,
                reason="wrapper_failure",
                controls=replace(self.controls, quiescence_grace_seconds=0.0),
                sampler=lambda _pgid, _leader, _required: (1, 1, 0),
                expedite_requested=threading.Event(),
            )
        self.assertEqual(state.failure_code, "MeasurementSignalPermissionDenied")
        self.assertTrue(state.direct_child_reaped)
        self.assertFalse(state.process_group_quiescent)

    def test_measurement_signal_esrch_still_reaps_direct_child(self) -> None:
        class FakeProcess:
            pid = 10
            returncode: int | None = None

            def wait(self, timeout: float | None = None) -> int:
                self.returncode = 0
                return 0

        observations = iter(((1, 1, 0), (0, 0, 0)))
        process = FakeProcess()
        with mock.patch.object(measurement.os, "killpg", side_effect=ProcessLookupError):
            state = measurement._shutdown_owned_group(
                process=process,
                pgid=10,
                reason="wrapper_failure",
                controls=self.controls,
                sampler=lambda _pgid, _leader, _required: next(observations),
                expedite_requested=threading.Event(),
            )
        self.assertIn("SIGINT:ESRCH", state.signals)
        self.assertTrue(state.direct_child_reaped)
        self.assertTrue(state.process_group_quiescent)
        self.assertIsNone(state.failure_code)

    def test_measurement_sigint_ignoring_child_escalates_to_sigterm(self) -> None:
        class FakeProcess:
            pid = 10
            returncode: int | None = None

            def wait(self, timeout: float | None = None) -> int:
                self.returncode = 0
                return 0

        observations = iter(((1, 1, 0), (1, 1, 0), (0, 0, 0)))
        sent: list[signal.Signals] = []
        with mock.patch.object(measurement.os, "killpg", side_effect=lambda _pgid, sig: sent.append(sig)):
            state = measurement._shutdown_owned_group(
                process=FakeProcess(), pgid=10, reason="operator_interrupted",
                controls=replace(self.controls, sigint_grace_seconds=0.0),
                sampler=lambda _pgid, _leader, _required: next(observations),
                expedite_requested=threading.Event(),
            )
        self.assertEqual(sent, [signal.SIGINT, signal.SIGTERM])
        self.assertTrue(state.process_group_quiescent)
        self.assertEqual(state.grace_expiries, ["sigint"])
        self.assertEqual(state.escalation_cause, "sigint_grace_expired")
        self.assertTrue(state.group_absence_confirmed)
        self.assertEqual(state.output_finalization, "forced")

    def test_measurement_sigint_and_sigterm_ignoring_child_escalates_to_sigkill(self) -> None:
        class FakeProcess:
            pid = 10
            returncode: int | None = None

            def wait(self, timeout: float | None = None) -> int:
                self.returncode = 0
                return 0

        observations = iter(((1, 1, 0), (1, 1, 0), (1, 1, 0), (0, 0, 0)))
        sent: list[signal.Signals] = []
        with mock.patch.object(measurement.os, "killpg", side_effect=lambda _pgid, sig: sent.append(sig)):
            state = measurement._shutdown_owned_group(
                process=FakeProcess(), pgid=10, reason="operator_interrupted",
                controls=replace(
                    self.controls, sigint_grace_seconds=0.0, sigterm_grace_seconds=0.0
                ),
                sampler=lambda _pgid, _leader, _required: next(observations),
                expedite_requested=threading.Event(),
            )
        self.assertEqual(sent, [signal.SIGINT, signal.SIGTERM, signal.SIGKILL])
        self.assertTrue(state.process_group_quiescent)
        self.assertEqual(state.grace_expiries, ["sigint", "sigterm"])
        self.assertEqual(state.escalation_cause, "sigterm_grace_expired")
        self.assertTrue(state.group_absence_confirmed)
        self.assertEqual(state.output_finalization, "unknown")

    def test_measurement_group_absence_timeout_is_shutdown_failure(self) -> None:
        class FakeProcess:
            pid = 10
            returncode: int | None = None

            def wait(self, timeout: float | None = None) -> int:
                self.returncode = 0
                return 0

        with mock.patch.object(measurement.os, "killpg"):
            state = measurement._shutdown_owned_group(
                process=FakeProcess(), pgid=10, reason="wrapper_failure",
                controls=replace(
                    self.controls,
                    sigint_grace_seconds=0.0,
                    sigterm_grace_seconds=0.0,
                    quiescence_grace_seconds=0.0,
                ),
                sampler=lambda _pgid, _leader, _required: (1, 1, 0),
                expedite_requested=threading.Event(),
            )
        self.assertEqual(state.failure_code, "MeasurementTeardownIncomplete")
        self.assertFalse(state.process_group_quiescent)

    def test_measurement_wrapper_error_after_spawn_still_reaps_group(self) -> None:
        def wrapper_error_sampler(pgid: int, leader: int, require_leader: bool):
            if require_leader:
                raise OSError("synthetic wrapper failure")
            return measurement._sample_process_group(pgid, leader, False)

        result = self.measure("import time; time.sleep(30)", sampler=wrapper_error_sampler)
        self.assertEqual(result.exit_status, 1)
        self.assertEqual(result.report["termination"]["reason"], "wrapper_failure")
        self.assertTrue(result.report["teardown"]["direct_child_reaped"])
        self.assertTrue(result.report["teardown"]["process_group_quiescent"])

    def test_measurement_getpgid_failure_uses_fallback_group_and_reaps_child(self) -> None:
        original_popen = measurement.subprocess.Popen
        measured_processes = []

        def spawn(*args, **kwargs):
            process = original_popen(*args, **kwargs)
            if kwargs.get("start_new_session") is True:
                measured_processes.append(process)
            return process

        with (
            mock.patch.object(measurement.subprocess, "Popen", side_effect=spawn),
            mock.patch.object(measurement.os, "getpgid", side_effect=OSError("synthetic")),
        ):
            result = self.measure("import time; time.sleep(.2)")
        self.assertEqual(result.exit_status, 1)
        self.assertEqual(result.report["termination"]["reason"], "wrapper_failure")
        self.assertIn("SIGINT", result.report["termination"]["signals"])
        self.assertTrue(result.report["teardown"]["direct_child_reaped"])
        self.assertTrue(result.report["teardown"]["group_absence_confirmed"])
        self.assertEqual(len(measured_processes), 1)
        self.assertTrue(measured_processes[0].stdout.closed)
        self.assertTrue(measured_processes[0].stderr.closed)

    def test_measurement_stream_reader_error_is_wrapper_failure(self) -> None:
        original_popen = measurement.subprocess.Popen

        class FailingReader:
            def __init__(self, wrapped):
                self.wrapped = wrapped

            def read1(self, _size: int):
                raise OSError("synthetic reader failure")

            read = read1

            @property
            def closed(self):
                return self.wrapped.closed

            def close(self):
                self.wrapped.close()

        def spawn(*args, **kwargs):
            process = original_popen(*args, **kwargs)
            if kwargs.get("start_new_session") is True:
                process.stdout = FailingReader(process.stdout)
            return process

        with mock.patch.object(measurement.subprocess, "Popen", side_effect=spawn):
            result = self.measure("import time; time.sleep(.05)")
        self.assertEqual(result.exit_status, 1)
        self.assertEqual(result.report["termination"]["reason"], "wrapper_failure")
        self.assertEqual(result.report["sampling"]["error_code"], "MeasurementStreamReadFailed")
        self.assertFalse(result.report["sampling"]["valid"])

    def test_measurement_stream_completion_timeout_is_wrapper_failure(self) -> None:
        original_popen = measurement.subprocess.Popen
        release = threading.Event()
        measured_processes = []

        class BlockingReader:
            def __init__(self, wrapped):
                self.wrapped = wrapped

            def read1(self, _size: int):
                release.wait(timeout=0.3)
                return b""

            read = read1

            @property
            def closed(self):
                return self.wrapped.closed

            def close(self):
                self.wrapped.close()

        def spawn(*args, **kwargs):
            process = original_popen(*args, **kwargs)
            if kwargs.get("start_new_session") is True:
                process.stdout = BlockingReader(process.stdout)
                measured_processes.append(process)
            return process

        try:
            with mock.patch.object(measurement.subprocess, "Popen", side_effect=spawn):
                result = self.measure("import time; time.sleep(.05)")
        finally:
            release.set()
            time.sleep(0.01)
            for process in measured_processes:
                process.stdout.close()
                process.stderr.close()
        self.assertEqual(result.exit_status, 1)
        self.assertEqual(result.report["termination"]["reason"], "wrapper_failure")
        self.assertEqual(
            result.report["sampling"]["error_code"], "MeasurementStreamDrainTimeout"
        )
        self.assertFalse(result.report["sampling"]["valid"])

    def test_measurement_keyboard_interrupt_terminates_child_and_grandchild(self) -> None:
        marker = self.root / "ready"
        pid_file = self.root / "interrupt-grandchild.pid"
        script = (
            "import subprocess, sys, time; from pathlib import Path; "
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], "
            "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
            f"Path({str(pid_file)!r}).write_text(str(child.pid)); "
            f"Path({str(marker)!r}).write_text('ready'); time.sleep(30)"
        )
        interrupt = self.schedule_interrupts(marker, 1)
        grandchild_pid: int | None = None
        try:
            result = self.measure(script)
            interrupt.join(timeout=1.0)
            grandchild_pid = int(pid_file.read_text(encoding="utf-8"))
            self.assertEqual(result.exit_status, 130)
            self.assertEqual(result.diagnostic_code, "MeasurementV2OperatorInterrupted")
            self.assertTrue(result.report_published)
            self.assertTrue(self.wait_for_pid_exit(grandchild_pid))
            self.assertTrue(result.report["teardown"]["direct_child_reaped"])
            self.assertTrue(result.report["teardown"]["process_group_quiescent"])
            self.assertEqual(result.report["termination"]["stop_initiator"], "operator")
            self.assertTrue(result.report["teardown"]["group_absence_confirmed"])
        finally:
            if grandchild_pid is not None and not self.wait_for_pid_exit(grandchild_pid, 0.05):
                try:
                    os.kill(grandchild_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_measurement_second_keyboard_interrupt_accelerates_but_does_not_skip_reap(self) -> None:
        marker = self.root / "ready"
        script = (
            "import signal, time; from pathlib import Path; "
            "signal.signal(signal.SIGINT, signal.SIG_IGN); "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            f"Path({str(marker)!r}).write_text('ready'); time.sleep(30)"
        )
        interrupt = self.schedule_interrupts(marker, 2)
        result = self.measure(script)
        interrupt.join(timeout=1.0)
        self.assertEqual(result.exit_status, 130)
        self.assertIn("SIGKILL", result.report["termination"]["signals"])
        self.assertTrue(result.report["teardown"]["direct_child_reaped"])
        self.assertTrue(result.report["teardown"]["process_group_quiescent"])

    def test_measurement_interrupt_during_natural_exit_cleanup_is_caught_and_accelerates(self) -> None:
        marker = self.root / "cleanup-ready"
        pid_file = self.root / "cleanup-grandchild.pid"
        grandchild_code = (
            "import signal,time; signal.signal(signal.SIGINT,signal.SIG_IGN); "
            "signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(30)"
        )
        script = (
            "import subprocess, sys; from pathlib import Path; "
            f"child = subprocess.Popen([sys.executable, '-c', {grandchild_code!r}], "
            "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
            f"Path({str(pid_file)!r}).write_text(str(child.pid)); "
            f"Path({str(marker)!r}).write_text('ready')"
        )
        interrupt = self.schedule_interrupts(marker, 2)
        grandchild_pid: int | None = None
        controls = replace(
            self.controls,
            sigint_grace_seconds=0.2,
            sigterm_grace_seconds=0.2,
            quiescence_grace_seconds=0.2,
        )
        try:
            result = self.measure(script, controls=controls)
            interrupt.join(timeout=1.0)
            grandchild_pid = int(pid_file.read_text(encoding="utf-8"))
            self.assertEqual(result.exit_status, 130)
            self.assertEqual(result.report["termination"]["reason"], "operator_interrupted")
            self.assertIn("SIGKILL", result.report["termination"]["signals"])
            self.assertTrue(result.report["teardown"]["direct_child_reaped"])
            self.assertTrue(result.report["teardown"]["process_group_quiescent"])
            self.assertTrue(self.wait_for_pid_exit(grandchild_pid))
        finally:
            if grandchild_pid is None and pid_file.exists():
                grandchild_pid = int(pid_file.read_text(encoding="utf-8"))
            if grandchild_pid is not None and not self.wait_for_pid_exit(grandchild_pid, 0.05):
                try:
                    os.kill(grandchild_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_measurement_stdout_flood_is_drained_without_unbounded_storage(self) -> None:
        total = 65 * measurement.MIB + 1
        result = self.measure(self.stream_flood_script(total, 0))
        self.assertEqual(result.exit_status, 130)
        self.assertEqual(result.report["streams"]["stdout"]["bytes_seen"], total)
        self.assertTrue(result.report["streams"]["stdout"]["over_budget"])
        self.assertFalse(result.report["streams"]["stderr"]["over_budget"])
        self.assert_no_retained_stream_logs()

    def test_measurement_operator_sigint_allows_capture_style_cooperative_finalization(self) -> None:
        marker = self.root / "operator-ready"
        finalized = self.root / "raw/finalized"
        script = (
            "import signal, time\nfrom pathlib import Path\n"
            f"marker=Path({str(marker)!r})\nfinalized=Path({str(finalized)!r})\n"
            "def stop(*_):\n"
            "    finalized.parent.mkdir()\n"
            "    finalized.write_text('done')\n"
            "    raise SystemExit(0)\n"
            "signal.signal(signal.SIGINT, stop)\nmarker.write_text('ready')\ntime.sleep(30)\n"
        )
        interrupt = self.schedule_interrupts(marker, 1)
        result = self.measure(script)
        interrupt.join(timeout=1.0)
        self.assertEqual(result.exit_status, 130)
        self.assertTrue(finalized.exists())
        self.assertEqual(result.report["termination"]["stop_initiator"], "operator")
        self.assertEqual(result.report["termination"]["grace_expiries"], [])
        self.assertIsNone(result.report["termination"]["escalation_cause"])
        self.assertTrue(result.report["teardown"]["group_absence_confirmed"])
        self.assertEqual(result.report["teardown"]["output_finalization"], "cooperative")

    def test_measurement_budget_sigint_allows_capture_style_cooperative_finalization(self) -> None:
        finalized = self.root / "raw/finalized"
        script = (
            "import signal, time\nfrom pathlib import Path\nraw=Path('raw')\nraw.mkdir()\n"
            "raw.joinpath('data').write_bytes(b'12345678')\n"
            "def stop(*_):\n"
            "    raw.joinpath('finalized').write_text('done')\n"
            "    raise SystemExit(0)\n"
            "signal.signal(signal.SIGINT, stop)\ntime.sleep(30)\n"
        )
        result = self.measure(script, controls=replace(self.controls, raw_budget_bytes=7))
        self.assertEqual(result.exit_status, 130)
        self.assertTrue(finalized.exists())
        self.assertEqual(result.report["termination"]["stop_initiator"], "policy")
        self.assertEqual(result.report["termination"]["grace_expiries"], [])
        self.assertIsNone(result.report["termination"]["escalation_cause"])
        self.assertTrue(result.report["teardown"]["group_absence_confirmed"])
        self.assertEqual(result.report["teardown"]["output_finalization"], "cooperative")

    def test_measurement_stderr_flood_is_drained_without_unbounded_storage(self) -> None:
        total = 65 * measurement.MIB + 1
        result = self.measure(self.stream_flood_script(0, total))
        self.assertEqual(result.exit_status, 130)
        self.assertEqual(result.report["streams"]["stderr"]["bytes_seen"], total)
        self.assertTrue(result.report["streams"]["stderr"]["over_budget"])
        self.assertFalse(result.report["streams"]["stdout"]["over_budget"])
        self.assert_no_retained_stream_logs()

    def test_measurement_simultaneous_stdout_stderr_floods_do_not_deadlock(self) -> None:
        total = 65 * measurement.MIB + 1
        started = time.monotonic()
        result = self.measure(self.stream_flood_script(total, total))
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertEqual(result.report["streams"]["stdout"]["bytes_seen"], total)
        self.assertEqual(result.report["streams"]["stderr"]["bytes_seen"], total)
        self.assertTrue(result.report["streams"]["stdout"]["over_budget"])
        self.assertTrue(result.report["streams"]["stderr"]["over_budget"])
        self.assert_no_retained_stream_logs()

    def test_measurement_each_stream_has_an_independent_limit(self) -> None:
        exact = 64 * measurement.MIB
        result = self.measure(self.stream_flood_script(exact, exact + 1))
        self.assertEqual(result.report["streams"]["stdout"]["bytes_seen"], exact)
        self.assertFalse(result.report["streams"]["stdout"]["over_budget"])
        self.assertEqual(result.report["streams"]["stderr"]["bytes_seen"], exact + 1)
        self.assertTrue(result.report["streams"]["stderr"]["over_budget"])
        self.assert_no_retained_stream_logs()

    def test_measurement_completed_child_publishes_valid_v2_report(self) -> None:
        result = self.measure(
            "from pathlib import Path; import time; Path('raw').mkdir(); Path('raw/data').write_text('ok'); time.sleep(.05)",
        )
        self.assertEqual(result.exit_status, 0)
        self.assertEqual(result.diagnostic_code, "MeasurementV2Completed")
        self.assertTrue(result.report_published)
        self.assertTrue(result.report_path.is_file())
        self.assertEqual(result.report["schema"], "pmm.phase7.b2c_measurement.v2")
        self.assertEqual(result.report["termination"]["stop_initiator"], "child")
        self.assertEqual(result.report["termination"]["grace_expiries"], [])
        self.assertIsNone(result.report["termination"]["escalation_cause"])
        self.assertTrue(result.report["teardown"]["group_absence_confirmed"])
        self.assertEqual(result.report["teardown"]["output_finalization"], "cooperative")
        self.assertTrue(result.report["sampling"]["valid"])
        phase7.validate_historical_schema(
            result.report, "b2c-measurement-v2.schema.json", "MeasurementV2SchemaMismatch"
        )

    def test_measurement_child_exit_two_publishes_report_and_preserves_exit_status(self) -> None:
        result = self.measure("import time; time.sleep(.05); raise SystemExit(2)")
        self.assertEqual(result.exit_status, 2)
        self.assertEqual(result.diagnostic_code, "MeasurementV2RecordOnly")
        self.assertTrue(result.report_published)
        self.assertEqual(result.report["child"]["exit_code"], 2)
        self.assertTrue(result.report_path.exists())

    def test_measurement_exit_before_first_sample_is_explicitly_invalid(self) -> None:
        result = self.measure("pass")
        self.assertFalse(result.report["sampling"]["valid"])
        self.assertIsNone(result.report["sampling"]["peak_rss_kib"])
        self.assertEqual(result.report["sampling"]["error_code"], "MeasurementNoSuccessfulSample")

    def test_measurement_sampler_failure_cannot_report_zero_rss(self) -> None:
        def broken_sampler(_pgid: int, _leader: int, _require_leader: bool):
            raise measurement.SamplerFailure("MeasurementSamplerUnavailable")

        result = self.measure("import time; time.sleep(10)", sampler=broken_sampler)
        self.assertEqual(result.exit_status, 1)
        self.assertEqual(result.diagnostic_code, "MeasurementV2SamplerFailure")
        self.assertTrue(result.report_published)
        self.assertFalse(result.report["sampling"]["valid"])
        self.assertIsNone(result.report["sampling"]["peak_rss_kib"])
        self.assertEqual(result.report["termination"]["reason"], "sampler_failure")

    def test_measurement_raw_budget_one_byte_over_stops_group(self) -> None:
        controls = replace(self.controls, raw_budget_bytes=7)
        result = self.measure(
            "from pathlib import Path; import time; Path('raw').mkdir(); Path('raw/data').write_bytes(b'12345678'); time.sleep(10)",
            controls=controls,
        )
        self.assertEqual(result.exit_status, 130)
        self.assertEqual(result.diagnostic_code, "MeasurementV2RawBudgetExceeded")
        self.assertTrue(result.report_published)
        self.assertEqual(result.report["termination"]["reason"], "raw_budget_exceeded")

    def test_measurement_exact_raw_budget_is_allowed(self) -> None:
        controls = replace(self.controls, raw_budget_bytes=8)
        result = self.measure(
            "from pathlib import Path; import time; Path('raw').mkdir(); Path('raw/data').write_bytes(b'12345678'); time.sleep(.05)",
            controls=controls,
        )
        self.assertEqual(result.exit_status, 0)

    def test_measurement_free_space_one_byte_below_refuses_before_spawn(self) -> None:
        marker = self.root / "spawned"
        with self.assertRaisesRegex(measurement.MeasurementRefusal, "MeasurementFreeSpaceInsufficient"):
            self.measure(
                f"from pathlib import Path; Path({str(marker)!r}).write_text('spawned')",
                free_space=lambda _path: measurement.V2_CONTROLS.minimum_free_bytes - 1,
            )
        self.assertFalse(marker.exists())
        self.assertFalse((self.root / "measurements/capture.json").exists())

    def test_measurement_existing_partial_report_refuses_before_spawn(self) -> None:
        report = self.root / "measurements/capture.json"
        report.parent.mkdir()
        partial = report.with_name(f"{report.name}.partial")
        partial.write_text("prior")
        with self.assertRaisesRegex(measurement.MeasurementRefusal, "MeasurementOutputExists"):
            self.measure("pass")
        self.assertEqual(partial.read_text(), "prior")

    def test_measurement_stream_budget_one_byte_over_stops_group(self) -> None:
        controls = replace(self.controls, stream_limit_bytes=7)
        result = self.measure("import sys, time; sys.stdout.write('12345678'); sys.stdout.flush(); time.sleep(10)", controls=controls)
        self.assertEqual(result.exit_status, 130)
        self.assertEqual(result.report["termination"]["reason"], "stream_budget_exceeded")
        self.assertEqual(result.diagnostic_code, "MeasurementV2StreamBudgetExceeded")
        self.assertTrue(result.report_published)
        self.assertEqual(result.report["streams"]["stdout"]["bytes_seen"], 8)

    def test_measurement_exact_stream_budget_is_allowed(self) -> None:
        controls = replace(self.controls, stream_limit_bytes=8)
        result = self.measure("import sys, time; sys.stdout.write('12345678'); sys.stdout.flush(); time.sleep(.05)", controls=controls)
        self.assertEqual(result.exit_status, 0)

    def test_measurement_stderr_stream_budget_one_byte_over_stops_group(self) -> None:
        controls = replace(self.controls, stream_limit_bytes=7)
        result = self.measure("import sys, time; sys.stderr.write('12345678'); sys.stderr.flush(); time.sleep(10)", controls=controls)
        self.assertEqual(result.exit_status, 130)
        self.assertTrue(result.report["streams"]["stderr"]["over_budget"])

    def test_measurement_publication_failure_removes_only_owned_partial(self) -> None:
        report = self.root / "measurements/capture.json"
        original = measurement._publish_report
        def fail_after_partial(path: Path, payload: dict) -> None:
            partial = path.with_name(f"{path.name}.partial")
            partial.write_text("owned", encoding="utf-8")
            raise OSError("simulated publication failure")
        measurement._publish_report = fail_after_partial
        try:
            result = self.measure("import time; time.sleep(.05)")
        finally:
            measurement._publish_report = original
        self.assertEqual(result.exit_status, 1)
        self.assertEqual(result.diagnostic_code, "MeasurementV2PublicationFailed")
        self.assertFalse(result.report_published)
        self.assertFalse(report.exists())
        self.assertFalse(report.with_name(f"{report.name}.partial").exists())

    def test_measurement_reaps_child_and_confirms_quiescent_process_group(self) -> None:
        result = self.measure("import time; time.sleep(.05)")
        self.assertTrue(result.report["teardown"]["direct_child_reaped"])
        self.assertTrue(result.report["teardown"]["process_group_quiescent"])

    def test_measure_v2_cli_keeps_v1_cli_contract_separate(self) -> None:
        report = self.root / "measurements/cli.json"
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            from python import pmm_phase7_evidence as evidence
            status = evidence.main([
                "measure-v2", "--stage", "capture-v2", "--report", str(report),
                "--package-root", str(self.root), "--raw-root", str(self.root / "raw"),
                "--output-root", str(self.root / "raw"), "--", sys.executable, "-c",
                "import time; time.sleep(.05)",
            ])
        self.assertEqual(status, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(json.loads(stdout.getvalue())["schema"], "pmm.phase7.b2c_measurement.v2")


if __name__ == "__main__":
    unittest.main()
