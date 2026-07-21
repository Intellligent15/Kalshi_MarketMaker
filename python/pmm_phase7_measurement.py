"""Additive B2c Measurement V2 process-group supervisor.

This module is intentionally separate from the frozen V1 evidence utility.  It owns a
fresh POSIX process group from preflight through bounded teardown and report publication.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
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
from typing import Any, Callable, Iterable, Sequence

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
    diagnostic_code: str
    report_published: bool


@dataclass
class _ShutdownState:
    reason: str
    signals: list[str]
    direct_child_reaped: bool = False
    process_group_quiescent: bool = False
    zombie_members_observed: int = 0
    failure_code: str | None = None
    grace_expiries: list[str] | None = None
    escalation_cause: str | None = None
    group_absence_confirmed: bool = False
    output_finalization: str = "unknown"

    def __post_init__(self) -> None:
        if self.grace_expiries is None:
            self.grace_expiries = []


class _SignalOutcome(Enum):
    SENT = "sent"
    GROUP_ABSENT = "esrch"
    PERMISSION_DENIED = "eperm"


_TERMINATION_DIAGNOSTICS = {
    "child_failure": "MeasurementV2ChildFailure",
    "operator_interrupted": "MeasurementV2OperatorInterrupted",
    "raw_budget_exceeded": "MeasurementV2RawBudgetExceeded",
    "aggregate_budget_exceeded": "MeasurementV2AggregateBudgetExceeded",
    "stream_budget_exceeded": "MeasurementV2StreamBudgetExceeded",
    "sampler_failure": "MeasurementV2SamplerFailure",
    "wrapper_failure": "MeasurementV2WrapperFailure",
    "teardown_failure": "MeasurementV2TeardownFailure",
}


def _measurement_diagnostic(report: dict[str, Any]) -> str:
    reason = report["termination"]["reason"]
    if reason == "completed":
        return (
            "MeasurementV2RecordOnly"
            if report["child"]["exit_code"] == 2
            else "MeasurementV2Completed"
        )
    return _TERMINATION_DIAGNOSTICS[reason]


def _stop_initiator(reason: str) -> str:
    if reason in {"completed", "child_failure"}:
        return "child"
    if reason.endswith("_budget_exceeded"):
        return "policy"
    return {
        "operator_interrupted": "operator",
        "sampler_failure": "sampler",
        "wrapper_failure": "wrapper",
        "teardown_failure": "teardown",
    }[reason]


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


@dataclass(frozen=True)
class _InventorySnapshot:
    total_bytes: int
    entries: Sequence[tuple[str, int]]


def _inventory(root: Path) -> _InventorySnapshot:
    """Return stable logical bytes; refuse symlinks and concurrent tree changes."""
    if root.is_symlink():
        raise MeasurementRefusal("MeasurementPathUnsafe", f"symlinked root: {root}")
    if not root.exists():
        return _InventorySnapshot(0, ())
    if not root.is_dir():
        raise MeasurementRefusal("MeasurementPathUnsafe", f"root is not a directory: {root}")
    entries: list[tuple[str, int]] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise MeasurementRefusal("MeasurementPathUnsafe", f"symlinked member: {path}")
        if path.is_file():
            entries.append((_safe_relative(root, path), path.stat().st_size))
    entries.sort(key=lambda item: item[0].encode("utf-8"))
    return _InventorySnapshot(sum(size for _, size in entries), tuple(entries))


def _package_bytes(root: Path) -> int:
    previous = _inventory(root)
    for _ in range(3):
        current = _inventory(root)
        if current == previous:
            return current.total_bytes
        previous = current
    raise MeasurementRefusal("MeasurementInventoryUnstable", "package inventory changed while sampled")


def _raw_bytes(roots: Iterable[Path]) -> int:
    total = 0
    seen: set[Path] = set()
    for raw_root in roots:
        resolved = raw_root.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        total += _inventory(resolved).total_bytes
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
    seen_pids: set[int] = set()
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
        if pid in seen_pids:
            raise SamplerFailure("MeasurementSamplerMalformed")
        seen_pids.add(pid)
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
        self.failure_code: str | None = None
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
        except (OSError, ValueError):
            self.failure_code = "MeasurementStreamReadFailed"
        finally:
            self.done.set()

    def start(self) -> None:
        self.thread.start()

    def join(self, timeout_seconds: float = 5.0) -> bool:
        self.thread.join(timeout=timeout_seconds)
        if not self.done.is_set():
            self.failure_code = "MeasurementStreamDrainTimeout"
            return False
        return self.failure_code is None

    @property
    def digest(self) -> str:
        return self._hash.hexdigest()


def _send_group_signal(
    pgid: int, sent: list[str], value: signal.Signals
) -> _SignalOutcome:
    try:
        os.killpg(pgid, value)
        sent.append(value.name)
        return _SignalOutcome.SENT
    except ProcessLookupError:
        sent.append(f"{value.name}:ESRCH")
        return _SignalOutcome.GROUP_ABSENT
    except PermissionError:
        sent.append(f"{value.name}:EPERM")
        return _SignalOutcome.PERMISSION_DENIED


def _shutdown_owned_group(
    *, process: subprocess.Popen[bytes], pgid: int, reason: str,
    controls: MeasurementControls,
    sampler: Callable[[int, int, bool], tuple[int, int, int]],
    expedite_requested: threading.Event,
) -> _ShutdownState:
    state = _ShutdownState(reason=reason, signals=[])

    def observe() -> int | None:
        try:
            live, _, zombies = sampler(pgid, process.pid, False)
        except KeyboardInterrupt:
            expedite_requested.set()
            return None
        except SamplerFailure as error:
            state.failure_code = error.code
            return None
        state.zombie_members_observed = max(state.zombie_members_observed, zombies)
        if live == 0:
            state.process_group_quiescent = True
            state.group_absence_confirmed = True
        return live

    def send(value: signal.Signals) -> bool:
        try:
            outcome = _send_group_signal(pgid, state.signals, value)
        except KeyboardInterrupt:
            expedite_requested.set()
            if value is signal.SIGKILL:
                return False
            outcome = _send_group_signal(pgid, state.signals, signal.SIGKILL)
        if outcome is _SignalOutcome.PERMISSION_DENIED:
            state.failure_code = "MeasurementSignalPermissionDenied"
            return False
        return True

    def wait_for_quiescence(seconds: float, grace_name: str) -> bool:
        deadline = time.monotonic() + seconds
        while True:
            live = observe()
            if live is None or live == 0:
                return live == 0
            if expedite_requested.is_set():
                state.escalation_cause = "second_interrupt"
                return False
            if time.monotonic() >= deadline:
                assert state.grace_expiries is not None
                if grace_name not in state.grace_expiries:
                    state.grace_expiries.append(grace_name)
                state.escalation_cause = f"{grace_name}_grace_expired"
                return False
            try:
                time.sleep(min(0.02, controls.sample_interval_seconds))
            except KeyboardInterrupt:
                expedite_requested.set()
                return False

    live = observe()
    # A failed observation is not evidence that the owned group is absent. Signal
    # conservatively so an exited leader cannot strand an unobserved descendant.
    if live is None or live > 0:
        if send(signal.SIGINT) and not wait_for_quiescence(
            controls.sigint_grace_seconds, "sigint"
        ):
            next_signal = signal.SIGKILL if expedite_requested.is_set() else signal.SIGTERM
            if send(next_signal) and next_signal is signal.SIGTERM:
                if not wait_for_quiescence(controls.sigterm_grace_seconds, "sigterm"):
                    send(signal.SIGKILL)
            if state.failure_code is None and not state.process_group_quiescent:
                wait_for_quiescence(controls.quiescence_grace_seconds, "quiescence")

    deadline = time.monotonic() + controls.quiescence_grace_seconds
    while True:
        try:
            process.wait(timeout=max(0.0, deadline - time.monotonic()))
            state.direct_child_reaped = True
            break
        except subprocess.TimeoutExpired:
            if time.monotonic() >= deadline:
                if send(signal.SIGKILL):
                    try:
                        process.wait(timeout=controls.quiescence_grace_seconds)
                        state.direct_child_reaped = True
                    except subprocess.TimeoutExpired:
                        pass
                break
        except KeyboardInterrupt:
            expedite_requested.set()
            send(signal.SIGKILL)

    if state.failure_code is None and not state.process_group_quiescent:
        wait_for_quiescence(controls.quiescence_grace_seconds, "quiescence")
    if not state.direct_child_reaped or not state.process_group_quiescent:
        state.failure_code = state.failure_code or "MeasurementTeardownIncomplete"
    if state.failure_code is not None or any(
        item.startswith("SIGKILL") for item in state.signals
    ):
        state.output_finalization = "unknown"
    elif any(item.startswith("SIGTERM") for item in state.signals):
        state.output_finalization = "forced"
    else:
        state.output_finalization = "cooperative"
    return state


def _publish_report(path: Path, payload: dict[str, Any]) -> None:
    partial = path.with_name(f"{path.name}.partial")
    partial.write_bytes(_serialized_report(payload))
    partial.rename(path)


def _serialized_report(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _account_for_serialized_report(
    payload: dict[str, Any], aggregate_without_report: int
) -> tuple[bytes, int]:
    """Reach the small fixed point caused by recording the report's own byte length."""
    for _ in range(8):
        rendered = _serialized_report(payload)
        aggregate_with_report = aggregate_without_report + len(rendered)
        if payload["storage"]["final_aggregate_bytes"] == aggregate_with_report:
            return rendered, aggregate_with_report
        payload["storage"]["final_aggregate_bytes"] = aggregate_with_report
    raise MeasurementRefusal(
        "MeasurementInventoryUnstable", "serialized report accounting did not stabilize"
    )


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
    configured_package_root = package_root
    if configured_package_root.is_symlink():
        raise MeasurementRefusal("MeasurementPathUnsafe", "package root must not be a symlink")
    package_root = configured_package_root.resolve()
    configured_report_path = report_path
    report_path = configured_report_path.resolve()
    if report_path.exists() or report_path.with_name(f"{report_path.name}.partial").exists():
        raise MeasurementRefusal("MeasurementOutputExists", "final or partial report already exists")
    if not package_root.is_dir():
        raise MeasurementRefusal("MeasurementPathUnsafe", "package root must exist")
    _safe_relative(package_root, report_path)

    def normalize_roots(roots: list[Path]) -> list[Path]:
        normalized: list[Path] = []
        seen: set[Path] = set()
        for root in roots:
            if root.is_symlink():
                raise MeasurementRefusal("MeasurementPathUnsafe", f"symlinked accounting root: {root}")
            resolved = root.resolve(strict=False)
            _safe_relative(package_root, resolved)
            if resolved in seen:
                raise MeasurementRefusal("MeasurementRootDuplicate", f"duplicate accounting root: {root}")
            seen.add(resolved)
            normalized.append(resolved)
        return normalized

    raw_roots = normalize_roots(raw_roots)
    output_roots = normalize_roots(output_roots)
    all_roots = [("raw", root) for root in raw_roots] + [
        ("output", root) for root in output_roots
    ]
    for index, (left_kind, left) in enumerate(all_roots):
        for right_kind, right in all_roots[index + 1:]:
            if left == right and left_kind != right_kind and stage == "capture-v2":
                continue
            if left == right or left in right.parents or right in left.parents:
                raise MeasurementRefusal(
                    "MeasurementRootOverlap", f"overlapping accounting roots: {left} and {right}"
                )
    for root in [*raw_roots, *output_roots]:
        if root.is_symlink():
            raise MeasurementRefusal("MeasurementPathUnsafe", f"symlinked accounting root: {root}")
    if stage == "capture-v2":
        for raw_root in raw_roots:
            if _inventory(raw_root).entries:
                raise MeasurementRefusal(
                    "MeasurementRawRootNotEmpty", f"capture raw root is not empty: {raw_root}"
                )
    resolved_identity_files: list[Path] = []
    for item in identity_files or []:
        if item.is_symlink():
            raise MeasurementRefusal("MeasurementPathUnsafe", f"symlinked identity file: {item}")
        resolved = item.resolve()
        _safe_relative(package_root, resolved)
        if not resolved.is_file():
            raise MeasurementRefusal(
                "MeasurementPathUnsafe", f"identity path is not a regular file: {item}"
            )
        resolved_identity_files.append(resolved)
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
    shutdown_state: _ShutdownState | None = None
    operator_requested = threading.Event()
    expedite_requested = threading.Event()
    previous_sigint_handler: Any = None

    def stop_group(reason: str, expedited: bool = False) -> None:
        nonlocal termination_reason, policy_stop, operator_stop, teardown_failure, shutdown_state
        if process is None or pgid is None:
            return
        termination_reason = reason
        policy_stop = reason.endswith("exceeded")
        operator_stop = reason == "operator_interrupted"
        if expedited:
            expedite_requested.set()
        if shutdown_state is not None:
            return
        shutdown_state = _shutdown_owned_group(
            process=process,
            pgid=pgid,
            reason=reason,
            controls=controls,
            sampler=sampler,
            expedite_requested=expedite_requested,
        )
        signals.extend(shutdown_state.signals)
        teardown_failure = shutdown_state.failure_code is not None

    def handle_sigint(_signum: int, _frame: Any) -> None:
        if operator_requested.is_set():
            expedite_requested.set()
        else:
            operator_requested.set()

    try:
        process = subprocess.Popen(
            command, cwd=package_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True,
        )
        # start_new_session=True makes the direct child the group leader. Retain
        # that ownership identity even if the diagnostic getpgid call fails.
        pgid = process.pid
        observed_pgid = os.getpgid(process.pid)
        if observed_pgid != process.pid:
            raise SamplerFailure("MeasurementProcessGroupInvalid")
        assert process.stdout is not None and process.stderr is not None
        stdout, stderr = _StreamCollector(process.stdout, controls.stream_limit_bytes), _StreamCollector(process.stderr, controls.stream_limit_bytes)
        stdout.start(); stderr.start()
        if threading.current_thread() is threading.main_thread():
            previous_sigint_handler = signal.getsignal(signal.SIGINT)
            signal.signal(signal.SIGINT, handle_sigint)
        # A command that exits before the first scheduled sample is unmeasured,
        # rather than being credited with a fabricated zero-RSS sample.
        time.sleep(min(0.01, controls.sample_interval_seconds))
        while process.poll() is None:
            stream_failure = stdout.failure_code or stderr.failure_code
            if stream_failure is not None:
                sampling_error = stream_failure
                stop_group("wrapper_failure")
                break
            if operator_requested.is_set():
                stop_group("operator_interrupted")
                break
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
    except KeyboardInterrupt:
        operator_requested.set()
        stop_group("operator_interrupted", expedited=expedite_requested.is_set())
    except (OSError, SamplerFailure, MeasurementRefusal) as error:
        sampling_error = (
            error.code
            if isinstance(error, (SamplerFailure, MeasurementRefusal))
            else type(error).__name__
        )
        termination_reason = "wrapper_failure" if termination_reason == "completed" else termination_reason
        stop_group(termination_reason)
    finally:
        try:
            if process is not None and pgid is not None:
                if shutdown_state is None:
                    stop_group(termination_reason)
                child_exit = process.returncode
                assert shutdown_state is not None
                peak_zombies = max(peak_zombies, shutdown_state.zombie_members_observed)
                if shutdown_state.failure_code is not None and sampling_error is None:
                    sampling_error = shutdown_state.failure_code
            if stdout is not None:
                stdout.join(controls.quiescence_grace_seconds)
            if stderr is not None:
                stderr.join(controls.quiescence_grace_seconds)
            # Popen owns both pipes before collectors are constructed. Close
            # through the process handles so failures between spawn and
            # collector startup cannot leak them; the closed check also avoids
            # double-closing collector-owned streams.
            if process is not None:
                for stream in (process.stdout, process.stderr):
                    if stream is not None and not stream.closed:
                        stream.close()
            stream_failure = (
                stdout.failure_code if stdout is not None else None
            ) or (stderr.failure_code if stderr is not None else None)
            if stream_failure is not None:
                sampling_error = stream_failure
                if termination_reason not in {"sampler_failure", "teardown_failure"}:
                    termination_reason = "wrapper_failure"
                policy_stop = False
                operator_stop = False
        finally:
            if operator_requested.is_set() and termination_reason == "completed":
                termination_reason = "operator_interrupted"
                operator_stop = True
            if previous_sigint_handler is not None:
                signal.signal(signal.SIGINT, previous_sigint_handler)

    try:
        aggregate_final_without_report = _package_bytes(package_root)
        raw_final = _raw_bytes(raw_roots)
    except MeasurementRefusal as error:
        sampling_error = sampling_error or error.code
        termination_reason = "wrapper_failure"
        teardown_failure = True
        aggregate_final_without_report = initial_aggregate
        raw_final = initial_raw

    final_policy_eligible = (
        termination_reason == "completed"
        and sampling_error is None
        and not teardown_failure
        and child_exit in (0, 2)
    )
    if final_policy_eligible and raw_final > controls.raw_budget_bytes:
        termination_reason = "raw_budget_exceeded"
        policy_stop = True
    elif final_policy_eligible and (
        aggregate_final_without_report + controls.publication_reserve_bytes
        > controls.aggregate_budget_bytes
    ):
        termination_reason = "aggregate_budget_exceeded"
        policy_stop = True

    sampling_valid = successful_samples > 0 and sampling_error is None
    if successful_samples == 0 and sampling_error is None:
        sampling_error = "MeasurementNoSuccessfulSample"
    if termination_reason == "completed" and child_exit not in (0, 2):
        termination_reason = "child_failure"
    if teardown_failure and termination_reason not in {"sampler_failure", "wrapper_failure"}:
        termination_reason = "teardown_failure"
        policy_stop = False
        operator_stop = False
    if sampling_error is not None and termination_reason == "completed":
        termination_reason = "sampler_failure"
    report = {
        "schema": "pmm.phase7.b2c_measurement.v2",
        "stage": stage,
        "command_sha256": _canonical_hash(command),
        "started_at_utc": started_at,
        "finished_at_utc": _utc_now(),
        "wall_time_seconds": time.monotonic() - started,
        "child": {"exit_code": child_exit},
        "termination": {
            "reason": termination_reason,
            "stop_initiator": _stop_initiator(termination_reason),
            "signals": signals,
            "grace_expiries": shutdown_state.grace_expiries if shutdown_state else [],
            "escalation_cause": shutdown_state.escalation_cause if shutdown_state else None,
        },
        "teardown": {
            "direct_child_reaped": shutdown_state.direct_child_reaped if shutdown_state else False,
            "process_group_quiescent": shutdown_state.process_group_quiescent if shutdown_state else False,
            "zombie_members_observed": peak_zombies,
            "group_absence_confirmed": (
                shutdown_state.group_absence_confirmed if shutdown_state else False
            ),
            "output_finalization": (
                shutdown_state.output_finalization if shutdown_state else "unknown"
            ),
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
            "initial_aggregate_bytes": initial_aggregate,
            "final_aggregate_bytes": aggregate_final_without_report,
            "minimum_free_bytes": controls.minimum_free_bytes,
            "raw_budget_bytes": controls.raw_budget_bytes,
            "aggregate_budget_bytes": controls.aggregate_budget_bytes,
            "publication_reserve_bytes": controls.publication_reserve_bytes,
        },
        "machine": {"platform": platform.platform(), "architecture": platform.machine(), "python": platform.python_version()},
        "identity_files": [{"path": str(item), "sha256": phase7.sha256_file(item)} for item in resolved_identity_files],
    }
    rendered_report, aggregate_final = _account_for_serialized_report(
        report, aggregate_final_without_report
    )
    phase7.validate_historical_schema(report, "b2c-measurement-v2.schema.json", "MeasurementV2SchemaMismatch")
    if termination_reason in {"sampler_failure", "wrapper_failure", "teardown_failure"}:
        exit_status = 1
    elif termination_reason == "completed" and child_exit == 0 and sampling_valid:
        exit_status = 0
    elif child_exit == 2 and termination_reason == "completed" and sampling_valid:
        exit_status = 2
    elif policy_stop or operator_stop:
        exit_status = 130
    else:
        exit_status = 1
    if (
        len(rendered_report) > controls.publication_reserve_bytes
        or aggregate_final > controls.aggregate_budget_bytes
    ):
        report_path.with_name(f"{report_path.name}.partial").unlink(missing_ok=True)
        return MeasurementResult(
            1, report_path, report, "MeasurementV2PublicationFailed", False
        )
    try:
        _publish_report(report_path, report)
    except OSError:
        report_path.with_name(f"{report_path.name}.partial").unlink(missing_ok=True)
        return MeasurementResult(
            1, report_path, report, "MeasurementV2PublicationFailed", False
        )
    try:
        published_aggregate = _package_bytes(package_root)
    except MeasurementRefusal:
        report_path.unlink(missing_ok=True)
        return MeasurementResult(
            1, report_path, report, "MeasurementV2PublicationFailed", False
        )
    if published_aggregate != aggregate_final or published_aggregate > controls.aggregate_budget_bytes:
        report_path.unlink(missing_ok=True)
        return MeasurementResult(
            1, report_path, report, "MeasurementV2PublicationFailed", False
        )
    return MeasurementResult(
        exit_status, report_path, report, _measurement_diagnostic(report), True
    )
