"""Focused offline tests for the additive B2c Measurement V2 supervisor."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from dataclasses import replace
from pathlib import Path

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
        return measurement.run_measurement_v2(
            stage="fixture",
            command=[sys.executable, "-c", script],
            report_path=self.root / "measurements/capture.json",
            package_root=self.root,
            raw_roots=[self.root / "raw"],
            output_roots=[self.root / "raw"],
            controls=controls,
            **kwargs,
        )

    def test_measurement_completed_child_publishes_valid_v2_report(self) -> None:
        result = self.measure(
            "from pathlib import Path; import time; Path('raw').mkdir(); Path('raw/data').write_text('ok'); time.sleep(.05)",
        )
        self.assertEqual(result.exit_status, 0)
        self.assertTrue(result.report_path.is_file())
        self.assertEqual(result.report["schema"], "pmm.phase7.b2c_measurement.v2")
        self.assertTrue(result.report["sampling"]["valid"])
        phase7.validate_historical_schema(
            result.report, "b2c-measurement-v2.schema.json", "MeasurementV2SchemaMismatch"
        )

    def test_measurement_child_exit_two_publishes_report_and_preserves_exit_status(self) -> None:
        result = self.measure("import time; time.sleep(.05); raise SystemExit(2)")
        self.assertEqual(result.exit_status, 2)
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
                "measure-v2", "--stage", "fixture", "--report", str(report),
                "--package-root", str(self.root), "--raw-root", str(self.root / "raw"),
                "--output-root", str(self.root / "raw"), "--", sys.executable, "-c",
                "import time; time.sleep(.05)",
            ])
        self.assertEqual(status, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(json.loads(stdout.getvalue())["schema"], "pmm.phase7.b2c_measurement.v2")


if __name__ == "__main__":
    unittest.main()
