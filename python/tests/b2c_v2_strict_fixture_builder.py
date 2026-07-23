"""Real, fully mounted Synthetic B2c-H pipeline fixture construction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

PYTHON_ROOT = Path(__file__).resolve().parents[1]
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

import pmm_phase7 as phase7
import pmm_phase7_evidence as evidence
import pmm_product_terms as product_terms
from python.tests.synthetic_product_package_builder import (
    build_synthetic_product_catalog,
)


_TICKERS = ("SYNTH-A", "SYNTH-B", "SYNTH-C")
_CAPTURE_START = datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc)
_CAPTURE_SECONDS = 43_200
_CONVERSION_POLICY = (
    phase7.REPOSITORY_ROOT
    / "configs/product_catalog/conversion_policies/integer_cents_whole_contracts_v1.json"
)


def _multimarket_module() -> Any:
    # Test discovery can replace ``sys.modules['pmm_phase7']`` with the canonical
    # fixture-loaded module. Importing this adapter lazily prevents it from
    # retaining a stale HistoricalDataError class across that replacement.
    import pmm_phase7_multimarket

    return pmm_phase7_multimarket


@dataclass(frozen=True)
class StrictV2PipelineFixture:
    root: Path
    capture_root: Path
    catalog_root: Path
    conversion_policy_path: Path
    normalization_roots: tuple[Path, Path, Path]
    normalization_telemetry_path: Path
    feature_roots: tuple[Path, Path, Path]
    backtest_config_path: Path
    backtest_roots: tuple[Path, Path, Path]
    risk_telemetry_path: Path

    def primary_members(self) -> dict[str, Path]:
        multimarket = _multimarket_module()
        normalization = self.normalization_roots[0]
        features = self.feature_roots[0]
        backtest = self.backtest_roots[0]
        result: dict[str, Path] = {
            "raw_frames": self.capture_root / "frames.jsonl",
            "raw_metadata": self.capture_root / "metadata.json",
            "normalized_records": normalization / "records.jsonl",
            "normalization_manifest": normalization / "manifest.json",
            "source_scopes": normalization / "source_scopes.json",
            "product_map": normalization / "product.json",
            "normalization_telemetry": self.normalization_telemetry_path,
            "feature_rows": features / "features.jsonl",
            "feature_manifest": features / "manifest.json",
            "backtest_config": self.backtest_config_path,
            "result_manifest": backtest / "manifest.json",
            "risk_telemetry": self.risk_telemetry_path,
        }
        for name in multimarket.ARTIFACT_SCHEMAS:
            result[f"v4_{name}"] = backtest / f"{name}.jsonl"
        for contract_id in range(1, len(_TICKERS) + 1):
            result[f"risk_trace_{contract_id}"] = (
                backtest / f"risk-trace-{contract_id}.jsonl"
            )
        return result

    def repetition_roots(self) -> dict[str, tuple[Path, Path, Path]]:
        return {
            "normalization_v3": self.normalization_roots,
            "features_v3": self.feature_roots,
            "backtest_v4": self.backtest_roots,
        }

    def assert_repetitions_byte_identical(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for stage, roots in self.repetition_roots().items():
            inventories = []
            for root in roots:
                inventories.append({
                    path.relative_to(root).as_posix(): path.read_bytes()
                    for path in sorted(root.rglob("*"))
                    if path.is_file()
                })
            if inventories[1:] != [inventories[0], inventories[0]]:
                raise AssertionError(f"{stage} repetitions are not byte-identical")
            counts[stage] = len(inventories[0])
        return counts


@dataclass
class StrictV2EvidenceFixture:
    root: Path
    manifest_path: Path
    manifest: dict[str, Any]

    def verify(self) -> dict[str, Any]:
        return evidence.verify_evidence_manifest_v2(
            self.manifest_path,
            artifact_root=self.root,
            require_artifacts=True,
        )


def _repo_relative(path: Path) -> str:
    return path.resolve().relative_to(phase7.REPOSITORY_ROOT).as_posix()


def _write_capture(root: Path) -> Path:
    capture = root / "raw"
    capture.mkdir(parents=True)
    start_ns = int(_CAPTURE_START.timestamp() * 1_000_000_000)
    end_ns = int(
        (_CAPTURE_START + timedelta(seconds=_CAPTURE_SECONDS)).timestamp()
        * 1_000_000_000
    )
    records: list[dict[str, Any]] = []

    def add(kind: str, **values: Any) -> None:
        records.append({
            "schema": phase7.RAW_CAPTURE_RECORD_V2_SCHEMA,
            "kind": kind,
            "raw_ingress_ordinal": len(records) + 1,
            "received_at_utc_ns": start_ns + len(records) + 1,
            "connection_segment_id": 1,
            **values,
        })

    def inbound(message: dict[str, Any]) -> None:
        payload = message.get("msg") or {}
        add(
            "inbound_frame",
            message_type=message["type"],
            subscription_id=message.get("sid"),
            source_sequence=message.get("seq"),
            market_ticker=payload.get("market_ticker"),
            venue_market_id=payload.get("market_id"),
            raw_frame_utf8=json.dumps(message, separators=(",", ":")),
        )

    endpoint = "wss://synthetic.invalid"
    subscription = {
        "id": 1,
        "cmd": "subscribe",
        "params": {
            "channels": ["orderbook_delta", "trade"],
            "market_tickers": list(_TICKERS),
            "use_yes_price": True,
        },
    }
    add("connection_attempt", websocket_url=endpoint)
    add("connection_opened", websocket_url=endpoint)
    add(
        "subscription_sent",
        subscription_request_id="c1:r1",
        wire_request_id=1,
        subscription=subscription,
    )
    for channel, sid in (("orderbook_delta", 11), ("trade", 12)):
        inbound({"id": 1, "type": "subscribed", "msg": {"channel": channel, "sid": sid}})
        add(
            "subscription_acknowledged",
            subscription_request_id="c1:r1",
            wire_request_id=1,
            channel=channel,
            venue_subscription_id=str(sid),
            requested_market_tickers=list(_TICKERS),
            membership_claim="request_bound_not_echoed_by_acknowledgement",
        )
    for sequence, ticker in enumerate(_TICKERS, start=1):
        inbound({
            "type": "orderbook_snapshot",
            "sid": 11,
            "seq": sequence,
            "msg": {
                "market_ticker": ticker,
                "market_id": f"synthetic-market-{sequence}",
                "yes_dollars_fp": [["0.50", "3"]],
                "no_dollars_fp": [["0.51", "4"]],
            },
        })
    for sequence, ticker in enumerate(_TICKERS, start=4):
        inbound({
            "type": "orderbook_delta",
            "sid": 11,
            "seq": sequence,
            "msg": {
                "market_ticker": ticker,
                "market_id": f"synthetic-market-{sequence - 3}",
                "side": "yes",
                "price_dollars": "0.50",
                "delta_fp": "1",
                "ts_ms": int(_CAPTURE_START.timestamp() * 1000) + sequence,
            },
        })
    add("connection_closed", close_reason="capture_deadline", clean=True)

    frames = capture / "frames.jsonl"
    frames.write_text(
        "".join(phase7.canonical_json(record) + "\n" for record in records),
        encoding="utf-8",
    )
    metadata = {
        "schema": phase7.RAW_CAPTURE_V2_SCHEMA,
        "source": "kalshi",
        "environment": "production",
        "truth_category": "Synthetic",
        "source_fidelity": "level_2",
        "market_tickers": list(_TICKERS),
        "capture_started_at_utc_ns": start_ns,
        "capture_ended_at_utc_ns": end_ns,
        "requested_duration_seconds": _CAPTURE_SECONDS,
        "connection_strategy": "single_connection_v1",
        "websocket_endpoint": endpoint,
        "subscription_template": subscription,
        "sequence_domain": {
            "status": "fixture_declared",
            "topology": "shared",
            "components": ["connection_segment_id", "venue_subscription_id"],
            "mechanical_validation_key": [
                "connection_segment_id",
                "venue_subscription_id",
            ],
            "limitation": "Synthetic fixture scope only.",
        },
        "credential_environment_variables": [],
        "credential_values_persisted": False,
        "git_revision": None,
        "package_versions": {},
        "message_counts_by_type": {
            "subscribed": 2,
            "orderbook_snapshot": 3,
            "orderbook_delta": 3,
        },
        "message_counts_by_market": {
            ticker: {"orderbook_delta": 1, "orderbook_snapshot": 1}
            for ticker in _TICKERS
        },
        "connections": 1,
        "disconnects": 0,
        "connection_segments": [],
        "sequence_gaps": [],
        "non_monotonic_sequences": [],
        "raw_record_count": len(records),
        "capture_continuity": "continuous_within_recorded_mechanical_scopes",
        "data_usability": "strict_eligible",
        "shutdown": {"status": "completed", "clean": True},
    }
    phase7.validate_historical_schema(
        metadata, "raw-capture-v2.schema.json", "CaptureSchemaMismatch"
    )
    phase7.write_json(capture / "metadata.json", metadata)
    return capture


def _backtest_config(
    root: Path, normalization: Path, features: Path
) -> Path:
    multimarket = _multimarket_module()
    feature_manifest = phase7.read_json(features / "manifest.json")
    products = []
    for ordinal, item in enumerate(feature_manifest["products"], start=1):
        identity = item["product_identity"]
        products.append({
            "product_identity": {
                "venue": "kalshi",
                "environment": "production",
                "ticker": identity["ticker"],
                "venue_market_id": identity["venue_market_id"],
                "input_product_entry_sha256": item["input_product_entry_sha256"],
            },
            "contract_identity": {"contract_id": ordinal, "side": "yes"},
            "strategy": {
                "schema": "pmm.baseline_market_maker.v1",
                "strategy_instance_id": f"synthetic-strategy-{ordinal}",
                "decision_interval_ns": 1,
                "order_lifetime_ns": 1_000_000_000,
                "minimum_spread_dollars": "0.01",
                "quote_quantity_contracts": "1",
            },
            "latency": {
                "market_data_ns": 0,
                "decision_ns": 0,
                "order_ns": 0,
                "acknowledgement_ns": 0,
                "cancellation_ns": 0,
                "fill_ns": 0,
            },
            "reviewed_lineage": item["reviewed_lineage"],
            "risk_binding": {
                "account_id": 1,
                "strategy_id": ordinal,
                "trader_id": ordinal,
                "contract_id": ordinal,
            },
        })
    config = {
        "schema": multimarket.CONFIG_SCHEMA,
        "run_id": "b2c-h-strict-synthetic-v1",
        "seed": 7,
        "inputs": {
            "normalization": {
                "manifest_path": _repo_relative(normalization / "manifest.json"),
                "manifest_sha256": phase7.sha256_file(normalization / "manifest.json"),
                "records_path": _repo_relative(normalization / "records.jsonl"),
                "records_sha256": phase7.sha256_file(normalization / "records.jsonl"),
                "source_scopes_path": _repo_relative(normalization / "source_scopes.json"),
                "source_scopes_sha256": phase7.sha256_file(normalization / "source_scopes.json"),
                "product_map_path": _repo_relative(normalization / "product.json"),
                "product_map_sha256": phase7.sha256_file(normalization / "product.json"),
            },
            "features": {
                "manifest_path": _repo_relative(features / "manifest.json"),
                "manifest_sha256": phase7.sha256_file(features / "manifest.json"),
                "rows_path": _repo_relative(features / "features.jsonl"),
                "rows_sha256": phase7.sha256_file(features / "features.jsonl"),
                "feature_definition_sha256": multimarket._sha256_value(
                    feature_manifest["feature_definitions"]
                ),
            },
        },
        "products": products,
        "execution": {
            "model": "no_fill_v1",
            "truth_category": "ModelDerived",
            "scheduling_policy": multimarket.SCHEDULING_POLICY,
        },
        "risk": {
            "engine": "cxx_oracle_v2",
            "ownership": "per_contract_projection",
            "launcher": {
                "schema": "pmm.risk_oracle_launcher.v1",
                "build_dir": "build",
                "cmake_target": "pmm_risk_oracle",
            },
            "risk_contract": {
                "schema": "pmm.research_risk_contract.v1",
                "quantity_unit": "whole_contract",
                "price_unit": "cent",
                "post_only": True,
            },
            "limits_by_contract": [
                {
                    "contract_id": ordinal,
                    "limits": {
                        "maximum_order_quantity_contracts": "2",
                        "maximum_absolute_position_contracts": "10",
                        "maximum_buy_exposure_contracts": "10",
                        "maximum_sell_exposure_contracts": "10",
                        "maximum_pending_exposure_contracts": "10",
                        "maximum_active_orders": 4,
                    },
                }
                for ordinal in range(1, len(_TICKERS) + 1)
            ],
        },
        "completeness": {"required": "complete_observed_interval"},
        "limitations": [
            "Synthetic test-only run; no venue-performance claim.",
            "Independent per-contract risk; no portfolio aggregation.",
        ],
    }
    path = root / "control" / "backtest-v4.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    phase7.validate_historical_schema(
        config, "backtest-v4.schema.json", "BacktestConfigSchemaMismatch"
    )
    phase7.write_json(path, config)
    return path


def build_strict_v2_pipeline(root: Path) -> StrictV2PipelineFixture:
    """Build three deterministic real pipeline executions under a new repo root."""
    resolved = root.resolve()
    resolved.relative_to(phase7.REPOSITORY_ROOT)
    if root.exists():
        raise FileExistsError(f"strict fixture root already exists: {root}")
    root.mkdir(parents=True)
    try:
        multimarket = _multimarket_module()
        catalog_root = root / "product-catalog"
        catalog = build_synthetic_product_catalog(catalog_root)
        conversion_policy_path = root / "control" / "conversion-policy.json"
        conversion_policy_path.parent.mkdir(parents=True)
        shutil.copyfile(_CONVERSION_POLICY, conversion_policy_path)
        conversion_policy = product_terms.ConversionPolicy.load(conversion_policy_path)
        capture_root = _write_capture(root)

        normalization_roots = tuple(
            root / "runs" / f"normalization-{index}" for index in range(1, 4)
        )
        normalization_telemetry = root / "telemetry" / "normalization.json"
        for index, output in enumerate(normalization_roots):
            phase7.normalize_capture_v3(
                capture_root,
                output,
                product_catalog=catalog,
                conversion_policy=conversion_policy,
                instrumentation_output=(normalization_telemetry if index == 0 else None),
            )

        feature_roots = tuple(
            root / "runs" / f"features-{index}" for index in range(1, 4)
        )
        for output in feature_roots:
            phase7.materialize_features_v3(normalization_roots[0], output)

        config_path = _backtest_config(root, normalization_roots[0], feature_roots[0])
        backtest_roots = tuple(
            root / "runs" / f"backtest-{index}" for index in range(1, 4)
        )
        risk_telemetry = root / "telemetry" / "risk.json"
        for index, output in enumerate(backtest_roots):
            multimarket.run_backtest_v4(
                config_path,
                output,
                instrumentation_output=(risk_telemetry if index == 0 else None),
            )
            multimarket.verify_backtest_v4(config_path, output)

        fixture = StrictV2PipelineFixture(
            root=root,
            capture_root=capture_root,
            catalog_root=catalog_root,
            conversion_policy_path=conversion_policy_path,
            normalization_roots=normalization_roots,  # type: ignore[arg-type]
            normalization_telemetry_path=normalization_telemetry,
            feature_roots=feature_roots,  # type: ignore[arg-type]
            backtest_config_path=config_path,
            backtest_roots=backtest_roots,  # type: ignore[arg-type]
            risk_telemetry_path=risk_telemetry,
        )
        fixture.assert_repetitions_byte_identical()
        return fixture
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise


def _copy_member(source: Path, root: Path, relative: str) -> Path:
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return destination


def _rewrite_mounted_result(
    result_root: Path, config: dict[str, Any], config_sha256: str
) -> None:
    manifest_path = result_root / "manifest.json"
    manifest = phase7.read_json(manifest_path)
    manifest["config_sha256"] = config_sha256
    manifest["inputs"] = config["inputs"]
    for descriptor in manifest["artifacts"]:
        artifact_path = result_root / descriptor["path"]
        rows = list(phase7.iter_jsonl(artifact_path))
        for row in rows:
            row["configuration_sha256"] = config_sha256
        artifact_path.write_text(
            "".join(phase7.canonical_json(row) + "\n" for row in rows),
            encoding="utf-8",
        )
        descriptor["sha256"] = phase7.sha256_file(artifact_path)
        descriptor["row_count"] = len(rows)
    phase7.write_json(manifest_path, manifest)


def _measurement(stage: str, identities: list[tuple[str, str]]) -> dict[str, Any]:
    empty_hash = hashlib.sha256(b"").hexdigest()
    return {
        "schema": "pmm.phase7.b2c_measurement.v2",
        "stage": stage,
        "command_sha256": hashlib.sha256(stage.encode("utf-8")).hexdigest(),
        "started_at_utc": "2026-01-01T00:00:00Z",
        "finished_at_utc": "2026-01-01T00:00:01Z",
        "wall_time_seconds": 1,
        "child": {"exit_code": 0},
        "termination": {
            "reason": "completed",
            "stop_initiator": "child",
            "signals": [],
            "grace_expiries": [],
            "escalation_cause": None,
        },
        "teardown": {
            "direct_child_reaped": True,
            "process_group_quiescent": True,
            "zombie_members_observed": 0,
            "group_absence_confirmed": True,
            "output_finalization": "cooperative",
        },
        "sampling": {
            "valid": True,
            "sampler_identity": "synthetic-fixture-v1",
            "attempted_samples": 1,
            "successful_samples": 1,
            "error_code": None,
            "peak_process_count": 1,
            "peak_rss_kib": 0,
        },
        "streams": {
            "stdout": {"bytes_seen": 0, "sha256": empty_hash, "over_budget": False},
            "stderr": {"bytes_seen": 0, "sha256": empty_hash, "over_budget": False},
        },
        "storage": {
            "initial_raw_bytes": 0,
            "final_raw_bytes": 0,
            "initial_aggregate_bytes": 0,
            "final_aggregate_bytes": 0,
            "minimum_free_bytes": 10_737_418_240,
            "raw_budget_bytes": 1_073_741_824,
            "aggregate_budget_bytes": 5_368_709_120,
            "publication_reserve_bytes": 1_048_576,
        },
        "machine": {"system": "synthetic-fixture"},
        "identity_files": [
            {"path": path, "sha256": sha256} for path, sha256 in identities
        ],
    }


def _member(
    root: Path,
    role: str,
    path: Path,
    *,
    schema_file: str | None,
    kind: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "role": role,
        "path": path.relative_to(root).as_posix(),
        "schema_file": schema_file,
        "kind": kind,
        "byte_length": path.stat().st_size,
        "sha256": phase7.sha256_file(path),
    }
    if kind == "jsonl":
        result["record_count"] = sum(1 for _ in phase7.iter_jsonl(path))
    if role.startswith("risk_trace_"):
        result["contract_id"] = int(role.rsplit("_", 1)[1])
    return result


def _write_inventory(path: Path, repeated_root: Path) -> None:
    phase7.write_json(path, evidence.build_repetition_inventory(repeated_root))


def build_strict_v2_evidence_package(root: Path) -> StrictV2EvidenceFixture:
    """Mount a complete real-pipeline Synthetic V2 package with no extra bytes."""
    resolved = root.resolve()
    resolved.relative_to(phase7.REPOSITORY_ROOT)
    if root.exists():
        raise FileExistsError(f"strict evidence root already exists: {root}")
    root.parent.mkdir(parents=True, exist_ok=True)
    scratch_parent = Path(
        tempfile.mkdtemp(prefix=f".{root.name}-scratch-", dir=root.parent)
    )
    try:
        multimarket = _multimarket_module()
        pipeline = build_strict_v2_pipeline(scratch_parent / "pipeline")
        root.mkdir()
        fixed: dict[str, tuple[Path, str, str]] = {}

        capture_policy = {
            "schema": "pmm.phase7.b2c_evidence_policy.v2",
            "base_policy_sha256": phase7.sha256_file(
                phase7.REPOSITORY_ROOT / "configs/phase7/b2c_evidence_policy_v1.json"
            ),
            "measurement": {
                "sample_interval_seconds": 1,
                "sigint_grace_seconds": 5,
                "sigterm_grace_seconds": 5,
                "quiescence_grace_seconds": 5,
                "stream_limit_bytes": 67_108_864,
                "publication_reserve_bytes": 1_048_576,
            },
        }
        policy_path = root / "control/capture-policy.json"
        policy_path.parent.mkdir(parents=True)
        phase7.write_json(policy_path, capture_policy)
        fixed["capture_policy"] = (
            policy_path,
            "b2c-evidence-policy-v2.schema.json",
            "json",
        )
        fixed["raw_frames"] = (
            _copy_member(pipeline.capture_root / "frames.jsonl", root, "raw/frames.jsonl"),
            "raw-capture-record-v2.schema.json",
            "jsonl",
        )
        fixed["raw_metadata"] = (
            _copy_member(pipeline.capture_root / "metadata.json", root, "raw/metadata.json"),
            "raw-capture-v2.schema.json",
            "json",
        )

        canonical_normalization = pipeline.normalization_roots[0]
        for role, filename, schema_file, kind in (
            ("normalized_records", "records.jsonl", "normalized-record-v2.schema.json", "jsonl"),
            ("normalization_manifest", "manifest.json", "normalization-manifest-v3.schema.json", "json"),
            ("source_scopes", "source_scopes.json", "source-scope-map-v1.schema.json", "json"),
            ("product_map", "product.json", "product-map-v3.schema.json", "json"),
        ):
            fixed[role] = (
                _copy_member(canonical_normalization / filename, root, f"normalization/{filename}"),
                schema_file,
                kind,
            )
        fixed["normalization_telemetry"] = (
            _copy_member(
                pipeline.normalization_telemetry_path,
                root,
                "telemetry/normalization.json",
            ),
            "b2c-normalization-telemetry-v1.schema.json",
            "json",
        )

        canonical_features = pipeline.feature_roots[0]
        fixed["feature_rows"] = (
            _copy_member(canonical_features / "features.jsonl", root, "features/features.jsonl"),
            "feature-row-v2.schema.json",
            "jsonl",
        )
        fixed["feature_manifest"] = (
            _copy_member(canonical_features / "manifest.json", root, "features/manifest.json"),
            "feature-manifest-v3.schema.json",
            "json",
        )

        mounted_config = phase7.read_json(pipeline.backtest_config_path)
        mounted_config["inputs"]["normalization"].update({
            "manifest_path": _repo_relative(root / "normalization/manifest.json"),
            "records_path": _repo_relative(root / "normalization/records.jsonl"),
            "source_scopes_path": _repo_relative(root / "normalization/source_scopes.json"),
            "product_map_path": _repo_relative(root / "normalization/product.json"),
        })
        mounted_config["inputs"]["features"].update({
            "manifest_path": _repo_relative(root / "features/manifest.json"),
            "rows_path": _repo_relative(root / "features/features.jsonl"),
        })
        mounted_config_path = root / "backtest/config.json"
        mounted_config_path.parent.mkdir(parents=True)
        phase7.write_json(mounted_config_path, mounted_config)
        mounted_config_sha256 = phase7.sha256_file(mounted_config_path)
        fixed["backtest_config"] = (
            mounted_config_path,
            "backtest-v4.schema.json",
            "json",
        )
        canonical_result = pipeline.backtest_roots[0]
        fixed["result_manifest"] = (
            _copy_member(canonical_result / "manifest.json", root, "backtest/result/manifest.json"),
            "backtest-result-manifest-v4.schema.json",
            "json",
        )
        for name in multimarket.ARTIFACT_SCHEMAS:
            fixed[f"v4_{name}"] = (
                _copy_member(
                    canonical_result / f"{name}.jsonl",
                    root,
                    f"backtest/result/{name}.jsonl",
                ),
                "backtest-artifact-v1.schema.json",
                "jsonl",
            )
        for contract_id in range(1, len(_TICKERS) + 1):
            fixed[f"risk_trace_{contract_id}"] = (
                _copy_member(
                    canonical_result / f"risk-trace-{contract_id}.jsonl",
                    root,
                    f"backtest/result/risk-trace-{contract_id}.jsonl",
                ),
                "risk-conformance-trace-v2.schema.json",
                "jsonl",
            )
        _rewrite_mounted_result(
            root / "backtest/result", mounted_config, mounted_config_sha256
        )
        fixed["risk_telemetry"] = (
            _copy_member(pipeline.risk_telemetry_path, root, "telemetry/risk.json"),
            "b2c-risk-telemetry-v1.schema.json",
            "json",
        )
        risk_telemetry = phase7.read_json(fixed["risk_telemetry"][0])
        risk_telemetry["config_sha256"] = mounted_config_sha256
        phase7.write_json(fixed["risk_telemetry"][0], risk_telemetry)

        catalog_root = root / "catalog"
        shutil.copytree(pipeline.catalog_root, catalog_root)
        conversion_path = _copy_member(
            pipeline.conversion_policy_path,
            root,
            "control/conversion-policy.json",
        )
        product_paths = sorted(
            (path for path in catalog_root.rglob("*") if path.is_file()),
            key=lambda path: path.relative_to(root).as_posix().encode("utf-8"),
        )
        product_paths.append(conversion_path)

        repetition_members: list[dict[str, Any]] = []
        repetitions = []
        for stage, prefix, source_roots in (
            ("normalization_v3", "normalization", pipeline.normalization_roots[1:]),
            ("features_v3", "feature", pipeline.feature_roots[1:]),
            ("backtest_v4", "backtest", pipeline.backtest_roots[1:]),
        ):
            mounted_roots = []
            inventory_roles = []
            for ordinal, (label, source_root) in enumerate(
                zip(("first", "second"), source_roots), start=1
            ):
                mounted_root = root / "repetitions" / prefix / label
                shutil.copytree(source_root, mounted_root)
                if stage == "backtest_v4":
                    _rewrite_mounted_result(
                        mounted_root, mounted_config, mounted_config_sha256
                    )
                mounted_roots.append(mounted_root)
                for path in sorted(mounted_root.rglob("*")):
                    if path.is_file():
                        repetition_members.append(
                            _member(
                                root,
                                "repetition_member",
                                path,
                                schema_file=None,
                                kind="opaque",
                            )
                        )
                inventory_role = f"{prefix}_inventory_{label}"
                inventory_path = root / "inventories" / f"{prefix}-{ordinal}.json"
                inventory_path.parent.mkdir(parents=True, exist_ok=True)
                _write_inventory(inventory_path, mounted_root)
                fixed[inventory_role] = (
                    inventory_path,
                    "b2c-repetition-inventory-v1.schema.json",
                    "json",
                )
                inventory_roles.append(inventory_role)
            repetitions.append({
                "stage": stage,
                "first_root": mounted_roots[0].relative_to(root).as_posix(),
                "second_root": mounted_roots[1].relative_to(root).as_posix(),
                "first_inventory_role": inventory_roles[0],
                "second_inventory_role": inventory_roles[1],
            })

        product_members = [
            _member(
                root,
                "product_package_member",
                path,
                schema_file=None,
                kind="opaque",
            )
            for path in product_paths
        ]
        identity_sources = {
            role: (path.relative_to(root).as_posix(), phase7.sha256_file(path))
            for role, (path, _, _) in fixed.items()
        }
        product_identities = [
            (member["path"], member["sha256"]) for member in product_members
        ]
        measurements = {
            "capture_measurement": _measurement(
                "capture-v2", [identity_sources["capture_policy"]]
            ),
            "normalization_measurement": _measurement(
                "normalization-v3",
                [identity_sources["raw_frames"], identity_sources["raw_metadata"]]
                + product_identities,
            ),
            "feature_measurement": _measurement(
                "features-v3",
                [
                    identity_sources[role]
                    for role in (
                        "normalization_manifest",
                        "normalized_records",
                        "source_scopes",
                        "product_map",
                    )
                ],
            ),
            "backtest_measurement": _measurement(
                "backtest-v4",
                [
                    identity_sources[role]
                    for role in (
                        "backtest_config",
                        "normalization_manifest",
                        "normalized_records",
                        "source_scopes",
                        "product_map",
                        "feature_manifest",
                        "feature_rows",
                    )
                ],
            ),
        }
        for role, document in measurements.items():
            path = root / "measurements" / f"{role.removesuffix('_measurement')}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            phase7.validate_historical_schema(
                document,
                "b2c-measurement-v2.schema.json",
                "MeasurementSchemaMismatch",
            )
            phase7.write_json(path, document)
            fixed[role] = (path, "b2c-measurement-v2.schema.json", "json")

        members = [
            _member(root, role, path, schema_file=schema_file, kind=kind)
            for role, (path, schema_file, kind) in fixed.items()
        ]
        members.extend(product_members)
        members.extend(repetition_members)
        payload_entries = [
            {
                "path": member["path"],
                "byte_length": member["byte_length"],
                "sha256": member["sha256"],
            }
            for member in members
        ]
        payload_entries.sort(key=lambda item: item["path"].encode("utf-8"))
        scan_path = root / "control/credential-scan-report.json"
        phase7.write_json(
            scan_path,
            {
                "schema": "pmm.phase7.b2c_credential_scan.v1",
                "scanner_identity": "pmm-b2c-deterministic-scanner-v1",
                "ruleset_sha256": evidence.CREDENTIAL_RULESET_SHA256,
                "payload_inventory_sha256": evidence._payload_sha256(payload_entries),
                "member_count": len(payload_entries),
                "byte_count": sum(item["byte_length"] for item in payload_entries),
                "status": "clean",
            },
        )
        fixed["credential_scan_report"] = (
            scan_path,
            "b2c-credential-scan-v1.schema.json",
            "json",
        )
        members.append(
            _member(
                root,
                "credential_scan_report",
                scan_path,
                schema_file="b2c-credential-scan-v1.schema.json",
                kind="json",
            )
        )

        declarations = []
        for ticker in _TICKERS:
            package_root = catalog_root / "packages" / ticker
            declarations.append({
                "ticker": ticker,
                "package_root": package_root.relative_to(root).as_posix(),
                "conversion_policy_path": conversion_path.relative_to(root).as_posix(),
                "truth_category": "Synthetic",
            })
        capture_end = _CAPTURE_START + timedelta(seconds=_CAPTURE_SECONDS)
        payload = {
            "evidence_id": "b2c-h-strict-synthetic-v1",
            "capture_spec": {
                "policy_sha256": phase7.sha256_file(policy_path),
                "started_at_utc": _CAPTURE_START.isoformat().replace("+00:00", "Z"),
                "ended_at_utc": capture_end.isoformat().replace("+00:00", "Z"),
                "duration_seconds": _CAPTURE_SECONDS,
                "market_count": len(_TICKERS),
                "minimum_free_bytes": 10_737_418_240,
                "raw_budget_bytes": 1_073_741_824,
                "total_budget_bytes": 5_368_709_120,
                "selection": {
                    "environment": "production",
                    "contract_kind": "binary",
                    "distinct_series_required": True,
                    "activity_order": "descending",
                    "tie_breaker": "market_ticker_ascending",
                    "fallback_selection_allowed": False,
                    "substitution_after_opening_allowed": False,
                },
            },
            "capture_outcome": {
                "exit_code": 0,
                "shutdown_status": "completed",
                "capture_continuity": "continuous_within_recorded_mechanical_scopes",
                "data_usability": "strict_eligible",
            },
            "market_tickers": list(_TICKERS),
            "retention": {"large_bytes_in_git": False},
            "product_lineage": [
                {"ticker": ticker, "status": "bracketed"} for ticker in _TICKERS
            ],
            "product_packages": declarations,
            "product_catalog_path": "catalog/manifest.json",
            "furthest_materialized_stage": "backtest_v4",
            "furthest_eligible_stage": "backtest_v4",
            "members": members,
            "lineage_edges": evidence._derive_role_lineage(members, "backtest_v4"),
            "repetitions": repetitions,
            "credential_scan": {"status": "clean"},
        }
        manifest = {
            "schema": evidence.EVIDENCE_V2_SCHEMA,
            "payload": payload,
            "payload_sha256": evidence._payload_sha256(payload),
        }
        manifest_path = root / "evidence-manifest.json"
        phase7.write_json(manifest_path, manifest)
        return StrictV2EvidenceFixture(root, manifest_path, manifest)
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(scratch_parent, ignore_errors=True)
