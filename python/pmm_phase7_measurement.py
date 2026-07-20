"""Additive B2c Measurement V2 process-group supervisor.

This module is intentionally separate from the frozen V1 evidence utility.  It owns a
fresh POSIX process group from preflight through bounded teardown and report publication.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Iterable

try:
    from . import pmm_phase7 as phase7
except ImportError:
    import pmm_phase7 as phase7  # type: ignore[no-redef]


GIB = 1024 ** 3
MIB = 1024 ** 2


class MeasurementRefusal(ValueError):
    """A stable, expected V2 preflight refusal."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class SamplerFailure(RuntimeError):
    """An unusable process-table observation."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class MeasurementControls:
    sample_interval_seconds: float = 1.0
    sigint_grace_seconds: float = 5.0
    sigterm_grace_seconds: float = 5.0
    quiescence_grace_seconds: float = 5.0
    minimum_free_bytes: int = 10 * GIB
    raw_budget_bytes: int = 1 * GIB
    aggregate_budget_bytes: int = 5 * GIB
    stream_limit_bytes: int = 64 * MIB
    publication_reserve_bytes: int = 1 * MIB


V2_CONTROLS = MeasurementControls()


@dataclass
class MeasurementResult:
    exit_status: int
    report_path: Path
    report: dict[str, Any]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_hash(value: Any) -> str:
    return _sha256(phase7.canonical_json(value).encode("utf-8"))


def _safe_relative(root: Path, path: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise MeasurementRefusal("MeasurementPathUnsafe", f"path escapes package root: {path}") from error
    return relative.as_posix()


def _inventory(root: Path) -> tuple[int, list[tuple[str, int]]]:
    """Return stable logical bytes; refuse symlinks and concurrent tree changes."""
    if root.is_symlink():
        raise MeasurementRefusal("MeasurementPathUnsafe", f"symlinked root: {root}")
    if not root.exists():
        return 0, []
    if not root.is_dir():
        raise MeasurementRefusal("MeasurementPathUnsafe", f"root is not a directory: {root}")
    entries: list[tuple[str, int]] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise MeasurementRefusal("MeasurementPathUnsafe", f"symlinked member: {path}")
        if path.is_file():
            entries.append((_safe_relative(root, path), path.stat().st_size))
    entries.sort(key=lambda item: item[0].encode("utf-8"))
    return sum(size for _, size in entries), entries


def _package_bytes(root: Path) -> int:
    first, _ = _inventory(root)
    second, _ = _inventory(root)
    if first != second:
        raise MeasurementRefusal("MeasurementInventoryUnstable", "package inventory changed while sampled")
    return first


def _raw_bytes(roots: Iterable[Path]) -> int:
    total = 0
    seen: set[Path] = set()
    for raw_root in roots:
        resolved = raw_root.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        total += _inventory(resolved)[0]
    return total


def _default_free_space(path: Path) -> int:
    return shutil.disk_usage(path).free


def _sample_process_group(pgid: int, leader: int, require_leader: bool) -> tuple[int, int, int]:
    try:
        completed = subprocess.run(
            ["ps", "-axo", "pid=,pgid=,rss=,state="], check=True, capture_output=True, text=True
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise SamplerFailure("MeasurementSamplerUnavailable") from error
    live = 0
    rss = 0
    zombies = 0
    leader_seen = False
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) != 4:
            raise SamplerFailure("MeasurementSamplerMalformed")
        try:
            pid, observed_pgid, observed_rss = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError as error:
            raise SamplerFailure("MeasurementSamplerMalformed") from error
        if observed_rss < 0:
            raise SamplerFailure("MeasurementSamplerMalformed")
        if observed_pgid != pgid:
            continue
        leader_seen = leader_seen or pid == leader
        if parts[3].startswith("Z"):
            zombies += 1
        else:
            live += 1
            rss += observed_rss
    if require_leader and not leader_seen:
        raise SamplerFailure("MeasurementSamplerLeaderMissing")
    return live, rss, zombies


class _StreamCollector:
    def __init__(self, stream: Any, limit: int) -> None:
        self._stream = stream
        self._limit = limit
        self._hash = hashlib.sha256()
        self.bytes_seen = 0
        self.over_budget = False
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._drain, daemon=True)

    def _drain(self) -> None:
        try:
            while True:
                reader = getattr(self._stream, "read1", self._stream.read)
                chunk = reader(65536)
                if not chunk:
                    return
                self.bytes_seen += len(chunk)
                self._hash.update(chunk)
                if self.bytes_seen > self._limit:
                    self.over_budget = True
        finally:
            self.done.set()

    def start(self) -> None:
        self.thread.start()

    def join(self) -> None:
        self.thread.join(timeout=5)

    @property
    def digest(self) -> str:
        return self._hash.hexdigest()


def _send_group_signal(pgid: int, sent: list[str], value: signal.Signals) -> bool:
    try:
        os.killpg(pgid, value)
        sent.append(value.name)
        return True
    except ProcessLookupError:
        sent.append(f"{value.name}:ESRCH")
        return False
    except PermissionError:
        sent.append(f"{value.name}:EPERM")
        return False


def _publish_report(path: Path, payload: dict[str, Any]) -> None:
    partial = path.with_name(f"{path.name}.partial")
    phase7.write_json(partial, payload)
    partial.rename(path)


def run_measurement_v2(
    *, stage: str, command: list[str], report_path: Path, package_root: Path,
    raw_roots: list[Path], output_roots: list[Path], controls: MeasurementControls = V2_CONTROLS,
    identity_files: list[Path] | None = None,
    sampler: Callable[[int, int, bool], tuple[int, int, int]] = _sample_process_group,
    free_space: Callable[[Path], int] = _default_free_space,
) -> MeasurementResult:
    """Measure an unchanged command with V2 ownership and bounded teardown.

    Output roots are identity/audit declarations; aggregate accounting is deliberately over the
    package root so pre-existing upstream bytes and control documents cannot be hidden.
    """
    if not stage or not command:
        raise MeasurementRefusal("MeasurementConfigInvalid", "stage and command are required")
    if controls.sample_interval_seconds <= 0 or controls.stream_limit_bytes <= 0:
        raise MeasurementRefusal("MeasurementConfigInvalid", "measurement controls must be positive")
    package_root = package_root.resolve()
    report_path = report_path.resolve()
    if report_path.exists() or report_path.with_name(f"{report_path.name}.partial").exists():
        raise MeasurementRefusal("MeasurementOutputExists", "final or partial report already exists")
    if not package_root.is_dir():
        raise MeasurementRefusal("MeasurementPathUnsafe", "package root must exist")
    for root in [*raw_roots, *output_roots]:
        root.resolve(strict=False).relative_to(package_root)
        if root.is_symlink():
            raise MeasurementRefusal("MeasurementPathUnsafe", f"symlinked accounting root: {root}")
    if free_space(package_root) < controls.minimum_free_bytes:
        raise MeasurementRefusal("MeasurementFreeSpaceInsufficient", "available space is below policy minimum")
    initial_aggregate = _package_bytes(package_root)
    if initial_aggregate + controls.publication_reserve_bytes > controls.aggregate_budget_bytes:
        raise MeasurementRefusal("MeasurementAggregateBudgetExceeded", "pre-existing package bytes exhaust reserve")
    initial_raw = _raw_bytes(raw_roots)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    started_at = _utc_now()
    process: subprocess.Popen[bytes] | None = None
    stdout: _StreamCollector | None = None
    stderr: _StreamCollector | None = None
    pgid: int | None = None
    signals: list[str] = []
    termination_reason = "completed"
    sampling_error: str | None = None
    successful_samples = 0
    attempted_samples = 0
    peak_count: int | None = None
    peak_rss: int | None = None
    peak_zombies = 0
    policy_stop = False
    operator_stop = False
    teardown_failure = False
    child_exit: int | None = None
    report: dict[str, Any] | None = None

    def stop_group(reason: str, expedited: bool = False) -> None:
        nonlocal termination_reason, policy_stop, operator_stop, teardown_failure
        if process is None or pgid is None:
            return
        termination_reason = reason
        policy_stop = reason.endswith("exceeded")
        operator_stop = reason == "operator_interrupted"
        if not _send_group_signal(pgid, signals, signal.SIGINT):
            teardown_failure = True
            return
        sequence = [(signal.SIGTERM, controls.sigint_grace_seconds), (signal.SIGKILL, controls.sigterm_grace_seconds)]
        if expedited:
            sequence = [(signal.SIGKILL, 0.0)]
        for next_signal, grace in sequence:
            deadline = time.monotonic() + grace
            while time.monotonic() < deadline:
                try:
                    live, _, _ = sampler(pgid, process.pid, False)
                except SamplerFailure:
                    teardown_failure = True
                    break
                if live == 0:
                    return
                time.sleep(min(0.02, controls.sample_interval_seconds))
            if teardown_failure:
                break
            try:
                live, _, _ = sampler(pgid, process.pid, False)
            except SamplerFailure:
                teardown_failure = True
                break
            if live:
                _send_group_signal(pgid, signals, next_signal)

    try:
        process = subprocess.Popen(
            command, cwd=package_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True,
        )
        pgid = os.getpgid(process.pid)
        if pgid != process.pid:
            raise SamplerFailure("MeasurementProcessGroupInvalid")
        assert process.stdout is not None and process.stderr is not None
        stdout, stderr = _StreamCollector(process.stdout, controls.stream_limit_bytes), _StreamCollector(process.stderr, controls.stream_limit_bytes)
        stdout.start(); stderr.start()
        # A command that exits before the first scheduled sample is unmeasured,
        # rather than being credited with a fabricated zero-RSS sample.
        time.sleep(min(0.01, controls.sample_interval_seconds))
        while process.poll() is None:
            attempted_samples += 1
            try:
                count, rss, zombies = sampler(pgid, process.pid, True)
            except SamplerFailure as error:
                sampling_error = error.code
                termination_reason = "sampler_failure"
                stop_group(termination_reason)
                break
            successful_samples += 1
            peak_count = max(peak_count or 0, count)
            peak_rss = max(peak_rss or 0, rss)
            peak_zombies = max(peak_zombies, zombies)
            aggregate = _package_bytes(package_root)
            raw = _raw_bytes(raw_roots)
            if raw > controls.raw_budget_bytes:
                stop_group("raw_budget_exceeded")
                break
            if aggregate + controls.publication_reserve_bytes > controls.aggregate_budget_bytes:
                stop_group("aggregate_budget_exceeded")
                break
            if stdout.over_budget or stderr.over_budget:
                stop_group("stream_budget_exceeded")
                break
            time.sleep(controls.sample_interval_seconds)
        child_exit = process.wait(timeout=controls.quiescence_grace_seconds)
    except KeyboardInterrupt:
        stop_group("operator_interrupted")
        if process is not None:
            try:
                child_exit = process.wait(timeout=controls.quiescence_grace_seconds)
            except subprocess.TimeoutExpired:
                teardown_failure = True
    except (OSError, SamplerFailure) as error:
        sampling_error = error.code if isinstance(error, SamplerFailure) else type(error).__name__
        termination_reason = "wrapper_failure" if termination_reason == "completed" else termination_reason
        stop_group(termination_reason)
    finally:
        if process is not None and pgid is not None:
            if process.poll() is None:
                stop_group(termination_reason if termination_reason != "completed" else "wrapper_failure")
            try:
                child_exit = process.wait(timeout=controls.quiescence_grace_seconds)
            except subprocess.TimeoutExpired:
                _send_group_signal(pgid, signals, signal.SIGKILL)
                try:
                    child_exit = process.wait(timeout=controls.quiescence_grace_seconds)
                except subprocess.TimeoutExpired:
                    teardown_failure = True
            deadline = time.monotonic() + controls.quiescence_grace_seconds
            while time.monotonic() < deadline:
                try:
                    live, _, zombies = sampler(pgid, process.pid, False)
                except SamplerFailure:
                    teardown_failure = True
                    break
                peak_zombies = max(peak_zombies, zombies)
                if live == 0:
                    break
                time.sleep(0.02)
            else:
                teardown_failure = True
        if stdout is not None:
            stdout.join()
            stdout._stream.close()
        if stderr is not None:
            stderr.join()
            stderr._stream.close()

    sampling_valid = successful_samples > 0 and sampling_error is None
    if successful_samples == 0 and sampling_error is None:
        sampling_error = "MeasurementNoSuccessfulSample"
    if termination_reason == "completed" and child_exit not in (0, 2):
        termination_reason = "child_failure"
    if teardown_failure and termination_reason not in {
        "sampler_failure", "operator_interrupted", "raw_budget_exceeded",
        "aggregate_budget_exceeded", "stream_budget_exceeded",
    }:
        termination_reason = "teardown_failure"
    if sampling_error is not None and termination_reason == "completed":
        termination_reason = "sampler_failure"
    aggregate_final = _package_bytes(package_root)
    raw_final = _raw_bytes(raw_roots)
    report = {
        "schema": "pmm.phase7.b2c_measurement.v2",
        "stage": stage,
        "command_sha256": _canonical_hash(command),
        "started_at_utc": started_at,
        "finished_at_utc": _utc_now(),
        "wall_time_seconds": time.monotonic() - started,
        "child": {"exit_code": child_exit},
        "termination": {"reason": termination_reason, "signals": signals},
        "teardown": {
            "direct_child_reaped": process is not None and child_exit is not None,
            "process_group_quiescent": not teardown_failure,
            "zombie_members_observed": peak_zombies,
        },
        "sampling": {
            "valid": sampling_valid,
            "sampler_identity": "ps-pid-pgid-rss-state-v1",
            "attempted_samples": attempted_samples,
            "successful_samples": successful_samples,
            "error_code": sampling_error,
            "peak_process_count": peak_count if sampling_valid else None,
            "peak_rss_kib": peak_rss if sampling_valid else None,
        },
        "streams": {
            "stdout": {"bytes_seen": stdout.bytes_seen if stdout else 0, "sha256": stdout.digest if stdout else _sha256(b""), "over_budget": stdout.over_budget if stdout else False},
            "stderr": {"bytes_seen": stderr.bytes_seen if stderr else 0, "sha256": stderr.digest if stderr else _sha256(b""), "over_budget": stderr.over_budget if stderr else False},
        },
        "storage": {
            "initial_raw_bytes": initial_raw, "final_raw_bytes": raw_final,
            "initial_aggregate_bytes": initial_aggregate, "final_aggregate_bytes": aggregate_final,
            "minimum_free_bytes": controls.minimum_free_bytes,
            "raw_budget_bytes": controls.raw_budget_bytes,
            "aggregate_budget_bytes": controls.aggregate_budget_bytes,
            "publication_reserve_bytes": controls.publication_reserve_bytes,
        },
        "machine": {"platform": platform.platform(), "architecture": platform.machine(), "python": platform.python_version()},
        "identity_files": [{"path": str(item.resolve()), "sha256": phase7.sha256_file(item.resolve())} for item in (identity_files or [])],
    }
    phase7.validate_historical_schema(report, "b2c-measurement-v2.schema.json", "MeasurementV2SchemaMismatch")
    if termination_reason == "completed" and child_exit == 0 and sampling_valid:
        exit_status = 0
    elif child_exit == 2 and termination_reason == "completed" and sampling_valid:
        exit_status = 2
    elif policy_stop or operator_stop:
        exit_status = 130
    else:
        exit_status = 1
    try:
        _publish_report(report_path, report)
    except OSError:
        report_path.with_name(f"{report_path.name}.partial").unlink(missing_ok=True)
        return MeasurementResult(1, report_path, report)
    return MeasurementResult(exit_status, report_path, report)
