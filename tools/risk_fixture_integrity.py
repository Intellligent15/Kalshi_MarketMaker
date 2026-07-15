#!/usr/bin/env python3
"""Canonicalize and rehash reviewed risk-conformance fixture corpora.

This developer tool manages byte representation and manifest integrity only.  It never executes a
risk implementation and never derives, repairs, or verifies semantic expected transitions.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Any, NoReturn


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPOSITORY_ROOT / "python" / "tests" / "fixtures" / "risk_conformance"
CORPORA = {
    "v1": (
        FIXTURE_ROOT / "v1",
        "pmm.risk_conformance_fixture_manifest.v1",
    ),
    "checkpoint_v1": (
        FIXTURE_ROOT / "checkpoint_v1",
        "pmm.risk_checkpoint_conformance_fixture_manifest.v1",
    ),
}
ENTRY_KEYS = {
    "expected_trace",
    "expected_trace_sha256",
    "fixture",
    "fixture_sha256",
}


class CorpusError(ValueError):
    """The corpus cannot be canonicalized safely."""


@dataclass(frozen=True)
class CorpusPlan:
    root: Path
    candidates: dict[Path, bytes]
    originals: dict[Path, bytes]
    changes: tuple[Path, ...]


def _fail(location: Path | str, message: str) -> NoReturn:
    raise CorpusError(f"{location}: {message}")


def _reject_float(value: str) -> NoReturn:
    _fail("JSON number", f"floating-point value {value!r} is not supported")


def _reject_constant(value: str) -> NoReturn:
    _fail("JSON number", f"nonstandard value {value!r} is not supported")


def _parse_integer(value: str) -> int:
    parsed = int(value)
    minimum = -(2**63)
    maximum = 2**64 - 1
    if parsed < minimum or parsed > maximum:
        _fail("JSON integer", f"{value!r} is outside the C++ reader's 64-bit range")
    return parsed


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("JSON object", f"contains duplicate key {key!r}")
        result[key] = value
    return result


def canonical_bytes(value: Any) -> bytes:
    """Return the canonical bytes used by both conformance readers."""
    return (
        json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _read_json_object(path: Path) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        _fail(path, f"cannot read file: {error}")
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail(path, "must not contain a UTF-8 byte-order mark")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        _fail(path, f"is not valid UTF-8: {error}")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_float=_reject_float,
            parse_int=_parse_integer,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, CorpusError) as error:
        if isinstance(error, CorpusError):
            _fail(path, str(error))
        _fail(path, f"invalid JSON: {error}")
    if not isinstance(value, dict):
        _fail(path, "must contain a JSON object")
    return raw, value


def _check_exact_keys(
    value: object,
    expected: set[str],
    location: Path | str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(location, "must be an object")
    actual = set(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        _fail(location, f"is missing required field {missing[0]!r}")
    if unknown:
        _fail(location, f"has unknown field {unknown[0]!r}")
    return value


def _string_field(value: dict[str, Any], key: str, location: Path | str) -> str:
    field = value[key]
    if not isinstance(field, str):
        _fail(f"{location}.{key}", "must be a string")
    return field


def _check_root(root: Path) -> None:
    if root.is_symlink():
        _fail(root, "fixture root must not be a symlink")
    if not root.is_dir():
        _fail(root, "fixture root must be a directory")
    manifest = root / "manifest.json"
    if manifest.is_symlink() or not manifest.is_file():
        _fail(manifest, "must be a regular non-symlink file")


def _member_path(root: Path, name: str, location: str) -> Path:
    if (
        not name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or "\x00" in name
        or Path(name).is_absolute()
        or Path(name).name != name
    ):
        _fail(location, "must be a bare filename inside the fixture root")
    path = root / name
    if path.is_symlink() or not path.is_file():
        _fail(location, "must name a regular non-symlink file")
    return path


def build_plan(root: Path, manifest_schema: str) -> CorpusPlan:
    """Validate one integrity envelope and construct every candidate output in memory."""
    _check_root(root)
    manifest_path = root / "manifest.json"
    manifest_raw, manifest = _read_json_object(manifest_path)
    _check_exact_keys(manifest, {"payload", "payload_sha256", "schema"}, manifest_path)
    if _string_field(manifest, "schema", manifest_path) != manifest_schema:
        _fail(f"{manifest_path}.schema", f"must be {manifest_schema!r}")
    if not isinstance(manifest["payload_sha256"], str):
        _fail(f"{manifest_path}.payload_sha256", "must be a string")

    payload = _check_exact_keys(
        manifest["payload"], {"entries", "schema"}, f"{manifest_path}.payload"
    )
    if _string_field(payload, "schema", f"{manifest_path}.payload") != manifest_schema:
        _fail(f"{manifest_path}.payload.schema", f"must be {manifest_schema!r}")
    entries = payload["entries"]
    if not isinstance(entries, list) or not entries:
        _fail(f"{manifest_path}.payload.entries", "must be a non-empty array")

    candidates: dict[Path, bytes] = {}
    originals: dict[Path, bytes] = {}
    expected_members = {"manifest.json"}
    prior_fixture = ""
    for index, item in enumerate(entries):
        location = f"{manifest_path}.payload.entries[{index}]"
        entry = _check_exact_keys(item, ENTRY_KEYS, location)
        fixture_name = _string_field(entry, "fixture", location)
        trace_name = _string_field(entry, "expected_trace", location)
        if not isinstance(entry["fixture_sha256"], str):
            _fail(f"{location}.fixture_sha256", "must be a string")
        if not isinstance(entry["expected_trace_sha256"], str):
            _fail(f"{location}.expected_trace_sha256", "must be a string")
        if prior_fixture and fixture_name <= prior_fixture:
            _fail(f"{location}.fixture", "entries must be strictly fixture-name sorted")
        prior_fixture = fixture_name
        for name, field in (
            (fixture_name, "fixture"),
            (trace_name, "expected_trace"),
        ):
            if name in expected_members:
                _fail(location, f"must not reference duplicate member {name!r}")
            expected_members.add(name)
            member = _member_path(root, name, f"{location}.{field}")
            original, document = _read_json_object(member)
            originals[member] = original
            candidates[member] = canonical_bytes(document)
        entry["fixture_sha256"] = hashlib.sha256(candidates[root / fixture_name]).hexdigest()
        entry["expected_trace_sha256"] = hashlib.sha256(
            candidates[root / trace_name]
        ).hexdigest()

    for path in root.iterdir():
        if path.name.endswith(".json") and path.name not in expected_members:
            _fail(path, "is an unreferenced fixture JSON document")

    manifest["payload_sha256"] = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    originals[manifest_path] = manifest_raw
    candidates[manifest_path] = canonical_bytes(manifest)
    changes = tuple(
        sorted(
            (path for path, candidate in candidates.items() if originals[path] != candidate),
            key=lambda path: (path.name == "manifest.json", path.name),
        )
    )
    return CorpusPlan(root=root, candidates=candidates, originals=originals, changes=changes)


def _fsync_directory(path: Path) -> None:
    flags = getattr(os, "O_DIRECTORY", 0) | os.O_RDONLY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_plans(plans: list[CorpusPlan]) -> None:
    """Stage all changed files, then atomically replace members before each manifest."""
    staged: dict[Path, Path] = {}
    try:
        for plan in plans:
            for target in plan.changes:
                if target.is_symlink() or not target.is_file():
                    _fail(target, "changed after validation and is no longer a regular file")
                if target.read_bytes() != plan.originals[target]:
                    _fail(target, "changed after validation; refusing to overwrite newer bytes")
        for plan in plans:
            for target in plan.changes:
                descriptor, temporary_name = tempfile.mkstemp(
                    dir=plan.root,
                    prefix=f".{target.name}.",
                    suffix=".tmp",
                )
                temporary = Path(temporary_name)
                staged[target] = temporary
                try:
                    with os.fdopen(descriptor, "wb") as output:
                        output.write(plan.candidates[target])
                        output.flush()
                        os.fsync(output.fileno())
                    mode = stat.S_IMODE(target.stat(follow_symlinks=False).st_mode)
                    os.chmod(temporary, mode, follow_symlinks=False)
                except BaseException:
                    temporary.unlink(missing_ok=True)
                    staged.pop(target, None)
                    raise

        for plan in plans:
            ordered = sorted(
                plan.changes,
                key=lambda path: (path.name == "manifest.json", path.name),
            )
            for target in ordered:
                os.replace(staged[target], target)
                del staged[target]
            if ordered:
                _fsync_directory(plan.root)
    except OSError as error:
        raise CorpusError(
            "atomic replacement failed; the manifest-last order leaves any interrupted corpus "
            f"fail-closed: {error}"
        ) from error
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)


def _selected_corpora(selection: str) -> list[tuple[Path, str]]:
    if selection == "all":
        return [CORPORA[name] for name in ("v1", "checkpoint_v1")]
    return [CORPORA[selection]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify canonical bytes and manifest hashes for reviewed risk fixtures. "
            "This does not verify semantic expected answers."
        )
    )
    parser.add_argument("--corpus", required=True, choices=("v1", "checkpoint_v1", "all"))
    parser.add_argument(
        "--write",
        action="store_true",
        help="atomically canonicalize members and update integrity metadata",
    )
    arguments = parser.parse_args(argv)
    try:
        plans = [build_plan(root, schema) for root, schema in _selected_corpora(arguments.corpus)]
        changes = [path for plan in plans for path in plan.changes]
        if arguments.write:
            write_plans(plans)
            if changes:
                for path in changes:
                    print(f"updated {path.relative_to(REPOSITORY_ROOT)}")
            else:
                print("fixture integrity metadata is already canonical and current")
            return 0
        if changes:
            for path in changes:
                print(f"would update {path.relative_to(REPOSITORY_ROOT)}", file=sys.stderr)
            print("rerun with --write after reviewing the authored JSON values", file=sys.stderr)
            return 1
        print("fixture integrity metadata is canonical and current")
        return 0
    except CorpusError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
