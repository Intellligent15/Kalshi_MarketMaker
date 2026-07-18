"""Additive B2b-2 deterministic multi-market replay and backtesting."""

from __future__ import annotations

import hashlib
import heapq
import shutil
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import pmm_phase7 as phase7


CONFIG_SCHEMA = "pmm.backtest.v4"
RESULT_SCHEMA = "pmm.backtest_result_manifest.v4"
SCHEDULING_POLICY = "causal_multimarket_v1"
ARTIFACT_SCHEMAS = {
    "decisions": "pmm.backtest_decision.v1",
    "submitted-orders": "pmm.backtest_submitted_order.v1",
    "cancellations": "pmm.backtest_cancellation.v1",
    "acknowledgements": "pmm.backtest_acknowledgement.v1",
    "rejections": "pmm.backtest_rejection.v1",
    "fills": "pmm.backtest_fill.v1",
    "exposure": "pmm.backtest_exposure.v1",
    "risk-events": "pmm.backtest_risk_event.v1",
    "summary": "pmm.backtest_summary.v1",
}
STAGE = {
    "segment": 1,
    "feature": 2,
    "trade": 3,
    "fill": 4,
    "decision": 5,
    "command": 6,
    "risk": 7,
    "ack": 8,
    "cancel": 9,
    "result": 10,
}


def _sha256_value(value: Any) -> str:
    return hashlib.sha256(phase7.canonical_json(value).encode("utf-8")).hexdigest()


def _repo_path(value: Any, field_name: str) -> Path:
    if not isinstance(value, str) or not value:
        raise phase7.HistoricalDataError("BacktestConfigInvalid", f"{field_name} is required")
    path = (phase7.REPOSITORY_ROOT / value).resolve()
    try:
        path.relative_to(phase7.REPOSITORY_ROOT)
    except ValueError as error:
        raise phase7.HistoricalDataError(
            "BacktestPathUnsafe", f"{field_name} must remain inside the repository"
        ) from error
    if not path.is_file() or path.is_symlink():
        raise phase7.HistoricalDataError("BacktestInputMissing", f"{field_name} is not a regular file")
    return path


def _nonnegative_int(value: Any, field_name: str) -> int:
    result = phase7.int_value(value, field_name)
    if result < 0:
        raise phase7.HistoricalDataError("BacktestConfigInvalid", f"{field_name} must be nonnegative")
    return result


def _positive_int(value: Any, field_name: str) -> int:
    result = phase7.int_value(value, field_name)
    if result <= 0:
        raise phase7.HistoricalDataError("BacktestConfigInvalid", f"{field_name} must be positive")
    return result


@dataclass
class MultiMarketOrder:
    order_id: int
    client_intent_id: int
    side: str
    price: Decimal
    remaining: Decimal
    active_at_ns: int
    expires_at_ns: int
    created_from_watermark: int
    ticker: str
    contract_id: int
    segment_id: str
    causal: dict[str, Any]


@dataclass
class ProductRuntime:
    declaration_ordinal: int
    config: dict[str, Any]
    feature_definition_sha256: str
    risk: phase7.CxxRiskOracle
    current_segment: str | None = None
    next_decision_at_ns: int = -1
    local_action_ordinal: int = 0
    pending: dict[int, MultiMarketOrder] = field(default_factory=dict)
    live: dict[int, MultiMarketOrder] = field(default_factory=dict)
    counts: Counter[str] = field(default_factory=Counter)
    segments: list[str] = field(default_factory=list)
    last_visible_row: dict[str, Any] | None = None

    @property
    def ticker(self) -> str:
        return str(self.config["product_identity"]["ticker"])

    @property
    def contract_id(self) -> int:
        return int(self.config["contract_identity"]["contract_id"])

    @property
    def strategy_id(self) -> str:
        return str(self.config["strategy"]["strategy_instance_id"])

    def next_local(self) -> int:
        self.local_action_ordinal += 1
        return self.local_action_ordinal


@dataclass
class Preflight:
    config: dict[str, Any]
    config_path: Path
    config_sha256: str
    normalization_manifest: dict[str, Any]
    feature_manifest: dict[str, Any]
    records: list[dict[str, Any]]
    features: dict[int, dict[str, Any]]
    product_map: dict[str, Any]
    products: list[dict[str, Any]]
    feature_definition_sha256: str


def _declared_file(section: dict[str, Any], path_field: str, hash_field: str) -> Path:
    path = _repo_path(section.get(path_field), path_field)
    expected = section.get(hash_field)
    if expected != phase7.sha256_file(path):
        raise phase7.HistoricalDataError("BacktestInputHashMismatch", f"{hash_field} is stale")
    return path


def _preflight(config_path: Path) -> Preflight:
    config_path = config_path.resolve()
    config = phase7.read_json(config_path)
    phase7.validate_historical_schema(config, "backtest-v4.schema.json", "BacktestConfigSchemaMismatch")
    inputs = config["inputs"]
    normalization = inputs["normalization"]
    features_input = inputs["features"]
    normalization_manifest_path = _declared_file(normalization, "manifest_path", "manifest_sha256")
    records_path = _declared_file(normalization, "records_path", "records_sha256")
    scopes_path = _declared_file(normalization, "source_scopes_path", "source_scopes_sha256")
    product_map_path = _declared_file(normalization, "product_map_path", "product_map_sha256")
    feature_manifest_path = _declared_file(features_input, "manifest_path", "manifest_sha256")
    feature_rows_path = _declared_file(features_input, "rows_path", "rows_sha256")

    normalization_manifest = phase7.read_json(normalization_manifest_path)
    feature_manifest = phase7.read_json(feature_manifest_path)
    product_map = phase7.read_json(product_map_path)
    phase7.validate_historical_schema(
        normalization_manifest, "normalization-manifest-v3.schema.json", "BacktestNormalizationSchemaMismatch"
    )
    phase7.validate_historical_schema(
        feature_manifest, "feature-manifest-v3.schema.json", "BacktestFeatureSchemaMismatch"
    )
    phase7.validate_historical_schema(product_map, "product-map-v3.schema.json", "BacktestProductSchemaMismatch")
    if normalization_manifest.get("completeness") != "complete_observed_interval" or feature_manifest.get(
        "completeness"
    ) != "complete_observed_interval":
        raise phase7.HistoricalDataError(
            "BacktestContinuityRequired", "backtest-v4 accepts only complete_observed_interval input"
        )
    if normalization_manifest.get("output_records_sha256") != phase7.sha256_file(records_path):
        raise phase7.HistoricalDataError("BacktestInputHashMismatch", "normalization records hash differs")
    if normalization_manifest.get("output_source_scopes_sha256") != phase7.sha256_file(scopes_path):
        raise phase7.HistoricalDataError("BacktestInputHashMismatch", "source-scope hash differs")
    if normalization_manifest.get("output_product_sha256") != phase7.sha256_file(product_map_path):
        raise phase7.HistoricalDataError("BacktestInputHashMismatch", "product-map hash differs")
    feature_manifest_input = feature_manifest.get("input", {})
    expected_feature_inputs = {
        "normalization_manifest_sha256": phase7.sha256_file(normalization_manifest_path),
        "records_sha256": phase7.sha256_file(records_path),
        "source_scopes_sha256": phase7.sha256_file(scopes_path),
        "product_map_sha256": phase7.sha256_file(product_map_path),
    }
    if any(feature_manifest_input.get(name) != value for name, value in expected_feature_inputs.items()):
        raise phase7.HistoricalDataError("BacktestFeatureLineageMismatch", "feature input lineage is stale")
    if feature_manifest.get("output", {}).get("feature_rows_sha256") != phase7.sha256_file(feature_rows_path):
        raise phase7.HistoricalDataError("BacktestInputHashMismatch", "feature-row hash differs")
    definition_hash = _sha256_value(feature_manifest.get("feature_definitions"))
    if features_input.get("feature_definition_sha256") != definition_hash:
        raise phase7.HistoricalDataError("BacktestFeatureDefinitionMismatch", "feature definition hash differs")

    map_products = product_map.get("products", [])
    manifest_products = feature_manifest.get("products", [])
    config_products = config.get("products", [])
    tickers = normalization_manifest.get("market_tickers")
    if not (
        isinstance(map_products, list)
        and isinstance(manifest_products, list)
        and isinstance(config_products, list)
        and [item.get("ticker") for item in map_products] == tickers
        and [item.get("product_identity", {}).get("ticker") for item in manifest_products] == tickers
        and [item.get("product_identity", {}).get("ticker") for item in config_products] == tickers
    ):
        raise phase7.HistoricalDataError(
            "BacktestProductIdentityMismatch", "normalization, features, product map, and config differ"
        )
    contract_ids: set[int] = set()
    strategy_ids: set[str] = set()
    for map_entry, manifest_entry, declared in zip(map_products, manifest_products, config_products):
        identity = declared["product_identity"]
        expected_entry_hash = _sha256_value(map_entry)
        if any(identity.get(name) != map_entry.get(name) for name in ("ticker", "venue_market_id")) or identity.get(
            "input_product_entry_sha256"
        ) != expected_entry_hash:
            raise phase7.HistoricalDataError("BacktestProductIdentityMismatch", "declared product identity differs")
        if manifest_entry.get("input_product_entry_sha256") != expected_entry_hash:
            raise phase7.HistoricalDataError("BacktestProductIdentityMismatch", "feature product identity differs")
        reviewed = manifest_entry.get("reviewed_lineage")
        declared_reviewed = declared.get("reviewed_lineage")
        if reviewed != declared_reviewed:
            raise phase7.HistoricalDataError("BacktestProductLineageMismatch", "reviewed product lineage differs")
        contract_id = _positive_int(declared["contract_identity"]["contract_id"], "contract_id")
        strategy_id = str(declared["strategy"]["strategy_instance_id"])
        if contract_id in contract_ids or strategy_id in strategy_ids:
            raise phase7.HistoricalDataError("BacktestProductIdentityMismatch", "contract and strategy IDs must be unique")
        contract_ids.add(contract_id)
        strategy_ids.add(strategy_id)
    risk = config["risk"]
    risk_contract = risk["risk_contract"]
    if (
        risk_contract.get("schema") != "pmm.research_risk_contract.v1"
        or risk_contract.get("quantity_unit") != "whole_contract"
        or risk_contract.get("price_unit") != "cent"
        or risk_contract.get("post_only") is not True
    ):
        raise phase7.HistoricalDataError("BacktestRiskContractMismatch", "V4 requires the canonical integer post-only risk contract")
    limit_contracts = [int(item["contract_id"]) for item in risk["limits_by_contract"]]
    if len(set(limit_contracts)) != len(limit_contracts) or set(limit_contracts) != contract_ids:
        raise phase7.HistoricalDataError("BacktestRiskBindingMismatch", "risk limits must name every contract exactly once")

    rows: dict[int, dict[str, Any]] = {}
    product_watermarks: dict[str, tuple[int, int]] = {}
    for row in phase7.iter_jsonl(feature_rows_path):
        phase7.validate_historical_schema(row, "feature-row-v2.schema.json", "BacktestFeatureRowSchemaMismatch")
        ordinal = phase7.int_value(row.get("as_of", {}).get("normalization_watermark"), "normalization watermark")
        if ordinal in rows:
            raise phase7.HistoricalDataError("BacktestFeatureOrderingInvalid", "feature rows repeat an ordinal")
        rows[ordinal] = row
        ticker = str(row["product_identity"]["ticker"])
        product_watermark = row["as_of"]["product_applied_watermark"]
        watermark_pair = (
            int(product_watermark["raw_ingress_ordinal"]),
            int(product_watermark["normalization_ordinal"]),
        )
        if watermark_pair[1] != ordinal or watermark_pair[0] != int(
            row["as_of"]["capture_raw_ingress_watermark"]
        ):
            raise phase7.HistoricalDataError(
                "BacktestFeatureCausalityMismatch", "product-local watermark differs from global row identity"
            )
        if ticker in product_watermarks and watermark_pair <= product_watermarks[ticker]:
            raise phase7.HistoricalDataError(
                "BacktestFeatureCausalityMismatch", "product-local watermark does not advance"
            )
        product_watermarks[ticker] = watermark_pair
    records: list[dict[str, Any]] = []
    prior_raw = 0
    prior_logical = 0
    pending_boundary: dict[str, Any] | None = None
    market_ordinals: set[int] = set()
    for expected_ordinal, record in enumerate(phase7.iter_jsonl(records_path), start=1):
        phase7.validate_historical_schema(record, "normalized-record-v2.schema.json", "BacktestRecordSchemaMismatch")
        if record.get("normalization_ordinal") != expected_ordinal or int(record["raw_ingress_ordinal"]) < prior_raw:
            raise phase7.HistoricalDataError("BacktestOrderingInvalid", "normalization records are not canonical")
        prior_raw = int(record["raw_ingress_ordinal"])
        logical = int(record["logical_time_utc_ns"])
        if logical < prior_logical:
            raise phase7.HistoricalDataError("BacktestOrderingInvalid", "logical time regresses")
        prior_logical = logical
        if pending_boundary is not None:
            if not (
                record.get("kind") == "market_event"
                and record.get("event_type") == "book_snapshot"
                and record.get("ticker") == pending_boundary.get("ticker")
                and record.get("book_segment_id") == pending_boundary.get("book_segment_id")
                and record.get("source_scope_id") == pending_boundary.get("source_scope_id")
                and record.get("raw_ingress_ordinal") == pending_boundary.get("raw_ingress_ordinal")
            ):
                raise phase7.HistoricalDataError(
                    "BacktestSegmentMismatch", "segment boundary is not immediately followed by its snapshot"
                )
            pending_boundary = None
        if record.get("kind") == "discontinuity":
            raise phase7.HistoricalDataError("BacktestContinuityRequired", "complete input contains discontinuity")
        if record.get("kind") == "market_event":
            market_ordinals.add(expected_ordinal)
            row = rows.get(expected_ordinal)
            if row is None:
                raise phase7.HistoricalDataError("BacktestFeatureMissing", "market event has no feature row")
            if (
                row.get("product_identity", {}).get("ticker") != record.get("ticker")
                or row.get("segment_identity", {}).get("book_segment_id") != record.get("book_segment_id")
                or row.get("as_of", {}).get("capture_raw_ingress_watermark") != record.get("raw_ingress_ordinal")
                or row.get("as_of", {}).get("logical_time_utc_ns") != record.get("logical_time_utc_ns")
            ):
                raise phase7.HistoricalDataError("BacktestFeatureCausalityMismatch", "feature row differs from record")
        elif record.get("kind") == "segment_boundary":
            pending_boundary = record
        records.append(record)
    if pending_boundary is not None:
        raise phase7.HistoricalDataError("BacktestSegmentMismatch", "input ends with an unmatched segment boundary")
    if set(rows) != market_ordinals:
        raise phase7.HistoricalDataError("BacktestFeatureOrderingInvalid", "feature rows are not a market-event bijection")
    if feature_manifest.get("output", {}).get("feature_row_count") != len(rows):
        raise phase7.HistoricalDataError("BacktestFeatureOrderingInvalid", "feature row count differs")
    return Preflight(
        config=config,
        config_path=config_path,
        config_sha256=phase7.sha256_file(config_path),
        normalization_manifest=normalization_manifest,
        feature_manifest=feature_manifest,
        records=records,
        features=rows,
        product_map=product_map,
        products=config_products,
        feature_definition_sha256=definition_hash,
    )


def run_backtest_v4(config_path: Path, output_dir: Path) -> dict[str, Any]:
    preflight = _preflight(config_path)
    output_dir = phase7.ensure_new_output(output_dir)
    temporary = output_dir.with_name(f"{output_dir.name}.partial")
    if temporary.exists():
        raise phase7.HistoricalDataError("PartialOutputExists", f"temporary output already exists: {temporary}")
    temporary.mkdir(parents=True)
    runtimes: dict[str, ProductRuntime] = {}
    artifacts: dict[str, list[dict[str, Any]]] = {name: [] for name in ARTIFACT_SCHEMAS}
    action_heap: list[tuple[int, int, int, int, int, int, str, dict[str, Any]]] = []
    global_action_ordinal = 0
    next_order_id = 1
    next_decision_id = 1
    artifact_ordinal = 0

    def push(runtime: ProductRuntime, kind: str, time_ns: int, causal: int, payload: dict[str, Any]) -> None:
        nonlocal global_action_ordinal
        if time_ns < 0 or time_ns > 9_223_372_036_854_775_807:
            raise phase7.HistoricalDataError("BacktestLatencyOverflow", "derived action time is invalid")
        global_action_ordinal += 1
        heapq.heappush(
            action_heap,
            (
                time_ns,
                causal,
                STAGE[kind],
                runtime.declaration_ordinal,
                runtime.next_local(),
                global_action_ordinal,
                kind,
                payload,
            ),
        )

    def emit(name: str, runtime: ProductRuntime, time_ns: int, row: dict[str, Any], values: dict[str, Any]) -> None:
        nonlocal artifact_ordinal
        artifact_ordinal += 1
        causal = {
            "capture_raw_ingress_watermark": row["as_of"]["capture_raw_ingress_watermark"],
            "normalization_watermark": row["as_of"]["normalization_watermark"],
            "product_applied_watermark": row["as_of"]["product_applied_watermark"],
        }
        record = {
            "schema": ARTIFACT_SCHEMAS[name],
            "run_id": preflight.config["run_id"],
            "artifact_ordinal": artifact_ordinal,
            "effective_time_utc_ns": time_ns,
            "product_identity": runtime.config["product_identity"],
            "contract_identity": runtime.config["contract_identity"],
            "segment_identity": row["segment_identity"],
            "strategy_instance_id": runtime.strategy_id,
            "causal_watermark": causal,
            "truth": {
                "truth_category": "ModelDerived",
                "source_fidelity": "level_2",
                "derivation": SCHEDULING_POLICY,
            },
            "fidelity": {"execution_model": preflight.config["execution"]["model"]},
            "configuration_sha256": preflight.config_sha256,
            "feature_definition_sha256": preflight.feature_definition_sha256,
            **values,
        }
        phase7.validate_historical_schema(
            record, "backtest-artifact-v1.schema.json", "BacktestArtifactSchemaMismatch"
        )
        artifacts[name].append(record)
        runtime.counts[name] += 1

    try:
        risk_config = preflight.config["risk"]
        limits_by_contract = {
            int(item["contract_id"]): item["limits"] for item in risk_config["limits_by_contract"]
        }
        for ordinal, product in enumerate(preflight.products, start=1):
            contract_id = int(product["contract_identity"]["contract_id"])
            binding = product["risk_binding"]
            if int(binding["contract_id"]) != contract_id:
                raise phase7.HistoricalDataError("BacktestRiskBindingMismatch", "risk contract binding differs")
            oracle_config = {
                "oracle": risk_config["launcher"],
                "limits": limits_by_contract[contract_id],
                "binding": binding,
            }
            runtimes[product["product_identity"]["ticker"]] = ProductRuntime(
                declaration_ordinal=ordinal,
                config=product,
                feature_definition_sha256=preflight.feature_definition_sha256,
                risk=phase7.CxxRiskOracle(oracle_config, canonical_trace=True),
            )

        for record in preflight.records:
            ticker = str(record.get("ticker"))
            runtime = runtimes[ticker]
            ordinal = int(record["normalization_ordinal"])
            time_ns = int(record["logical_time_utc_ns"])
            if record["kind"] == "segment_boundary":
                push(runtime, "segment", time_ns, ordinal, {"record": record})
                continue
            row = preflight.features[ordinal]
            market_latency = _nonnegative_int(runtime.config["latency"]["market_data_ns"], "market_data_ns")
            visible = time_ns + market_latency
            push(runtime, "feature", visible, ordinal, {"row": row, "record": record})
            if record.get("event_type") == "trade":
                push(runtime, "trade", visible, ordinal, {"row": row, "record": record})

        terminal_time = max((int(record["logical_time_utc_ns"]) for record in preflight.records), default=0)
        while action_heap:
            time_ns, causal_ordinal, _, _, _, _, kind, payload = heapq.heappop(action_heap)
            if time_ns > terminal_time:
                break
            row = payload.get("row")
            record = payload.get("record")
            ticker = str((row or record).get("product_identity", {}).get("ticker") if row else record.get("ticker"))
            runtime = runtimes[ticker]
            if kind == "segment":
                segment = str(record["book_segment_id"])
                if runtime.current_segment is not None and runtime.current_segment != segment:
                    for order in list(runtime.pending.values()):
                        runtime.risk.reject_pending(order, time_ns)
                        del runtime.pending[order.order_id]
                        if runtime.last_visible_row is not None:
                            emit(
                                "risk-events", runtime, time_ns, runtime.last_visible_row,
                                {"operation": "command_reject", "order_id": order.order_id, "result": "segment_transition", "risk_view": runtime.risk.view()},
                            )
                            emit(
                                "cancellations", runtime, time_ns, runtime.last_visible_row,
                                {"order_id": order.order_id, "reason": "segment_transition"},
                            )
                    for order in list(runtime.live.values()):
                        runtime.risk.cancel(order, "segment_transition", time_ns)
                        del runtime.live[order.order_id]
                        if runtime.last_visible_row is not None:
                            emit(
                                "risk-events", runtime, time_ns, runtime.last_visible_row,
                                {"operation": "cancel", "order_id": order.order_id, "result": "segment_transition", "risk_view": runtime.risk.view()},
                            )
                            emit(
                                "cancellations", runtime, time_ns, runtime.last_visible_row,
                                {"order_id": order.order_id, "reason": "segment_transition"},
                            )
                    runtime.next_decision_at_ns = -1
                    runtime.last_visible_row = None
                runtime.current_segment = segment
                if segment not in runtime.segments:
                    runtime.segments.append(segment)
                continue
            assert row is not None
            if row["segment_identity"]["book_segment_id"] != runtime.current_segment:
                if kind in {"feature", "trade"}:
                    raise phase7.HistoricalDataError("BacktestSegmentMismatch", "input action crossed a segment boundary")
                continue
            latency = runtime.config["latency"]
            strategy = runtime.config["strategy"]
            if kind == "feature":
                runtime.last_visible_row = row
                if time_ns >= runtime.next_decision_at_ns:
                    decision_time = time_ns + _nonnegative_int(latency["decision_ns"], "decision_ns")
                    push(runtime, "decision", decision_time, causal_ordinal, {"row": row})
                    runtime.next_decision_at_ns = time_ns + _positive_int(
                        strategy["decision_interval_ns"], "decision_interval_ns"
                    )
            elif kind == "trade":
                if preflight.config["execution"]["model"] != "trade_touch_v1":
                    continue
                trade_price = Decimal(str(record["payload"]["yes_price_dollars"]))
                remaining = Decimal(str(record["payload"]["quantity_contracts"]))
                for order in sorted(runtime.live.values(), key=lambda item: item.order_id):
                    eligible = (order.side == "buy" and trade_price <= order.price) or (
                        order.side == "sell" and trade_price >= order.price
                    )
                    if not eligible or remaining <= 0:
                        continue
                    quantity = min(order.remaining, remaining)
                    remaining -= quantity
                    push(
                        runtime,
                        "fill",
                        time_ns + _nonnegative_int(latency["fill_ns"], "fill_ns"),
                        causal_ordinal,
                        {"row": row, "order_id": order.order_id, "quantity": format(quantity, "f"), "record": record},
                    )
            elif kind == "fill":
                order = runtime.live.get(payload["order_id"])
                if order is None or order.segment_id != runtime.current_segment:
                    continue
                quantity = min(order.remaining, Decimal(payload["quantity"]))
                if quantity <= 0:
                    continue
                order.remaining -= quantity
                runtime.risk.apply_fill(order, quantity, time_ns)
                emit(
                    "risk-events",
                    runtime,
                    time_ns,
                    row,
                    {"operation": "fill", "order_id": order.order_id, "result": "applied", "risk_view": runtime.risk.view()},
                )
                emit(
                    "fills",
                    runtime,
                    time_ns,
                    row,
                    {
                        "order_id": order.order_id,
                        "side": order.side,
                        "price_dollars": format(order.price, "f"),
                        "quantity_contracts": format(quantity, "f"),
                        "public_trade_event_id": record["event_id"],
                        "fill_model": "trade_touch_v1",
                    },
                )
                if order.remaining == 0:
                    del runtime.live[order.order_id]
            elif kind == "decision":
                decision_id = next_decision_id
                next_decision_id += 1
                values = row["values"]
                bid, ask = values.get("best_yes_bid_dollars"), values.get("best_yes_ask_dollars")
                emit("decisions", runtime, time_ns, row, {"decision_id": decision_id})
                if bid is None or ask is None:
                    emit("rejections", runtime, time_ns, row, {"stage": "decision", "reason": "missing_two_sided_book"})
                    continue
                bid_price, ask_price = Decimal(str(bid)), Decimal(str(ask))
                minimum = Decimal(str(strategy["minimum_spread_dollars"]))
                if bid_price >= ask_price or ask_price - bid_price < minimum:
                    emit("rejections", runtime, time_ns, row, {"stage": "decision", "reason": "post_only_or_spread"})
                    continue
                for order in list(runtime.pending.values()) + list(runtime.live.values()):
                    push(
                        runtime,
                        "cancel",
                        time_ns + _nonnegative_int(latency["cancellation_ns"], "cancellation_ns"),
                        causal_ordinal,
                        {"row": row, "order_id": order.order_id, "reason": "quote_replacement"},
                    )
                arrival = time_ns + _nonnegative_int(latency["order_ns"], "order_ns")
                for side, price in (("buy", bid_price), ("sell", ask_price)):
                    push(runtime, "command", arrival, causal_ordinal, {"row": row, "side": side, "price": format(price, "f")})
            elif kind == "command":
                quantity = Decimal(str(strategy["quote_quantity_contracts"]))
                if quantity <= 0 or quantity != quantity.to_integral_value() or Decimal(payload["price"]) * 100 != (
                    Decimal(payload["price"]) * 100
                ).to_integral_value():
                    raise phase7.HistoricalDataError("BacktestExactConversionRequired", "order is not exactly representable")
                order_id = next_order_id
                next_order_id += 1
                order = MultiMarketOrder(
                    order_id=order_id,
                    client_intent_id=order_id,
                    side=payload["side"],
                    price=Decimal(payload["price"]),
                    remaining=quantity,
                    active_at_ns=time_ns,
                    expires_at_ns=time_ns + _positive_int(strategy["order_lifetime_ns"], "order_lifetime_ns"),
                    created_from_watermark=causal_ordinal,
                    ticker=runtime.ticker,
                    contract_id=runtime.contract_id,
                    segment_id=runtime.current_segment or "",
                    causal=row["as_of"],
                )
                emit(
                    "submitted-orders",
                    runtime,
                    time_ns,
                    row,
                    {
                        "client_intent_id": order_id,
                        "side": order.side,
                        "price_dollars": format(order.price, "f"),
                        "quantity_contracts": format(quantity, "f"),
                        "planned_expires_at_utc_ns": order.expires_at_ns,
                    },
                )
                push(runtime, "risk", time_ns, causal_ordinal, {"row": row, "order": order})
            elif kind == "risk":
                order = payload["order"]
                rejection = runtime.risk.admit(
                    order.client_intent_id, order.side, order.remaining, order.price, time_ns, runtime.live.values()
                )
                emit(
                    "risk-events",
                    runtime,
                    time_ns,
                    row,
                    {
                        "operation": "admit",
                        "order_id": order.order_id,
                        "result": rejection or "approved",
                        "risk_view": runtime.risk.view(),
                    },
                )
                if rejection is not None:
                    emit("rejections", runtime, time_ns, row, {"stage": "risk", "reason": rejection})
                    continue
                runtime.pending[order.order_id] = order
                push(
                    runtime,
                    "ack",
                    time_ns + _nonnegative_int(latency["acknowledgement_ns"], "acknowledgement_ns"),
                    causal_ordinal,
                    {"row": row, "order_id": order.order_id},
                )
            elif kind == "ack":
                order = runtime.pending.pop(payload["order_id"], None)
                if order is None:
                    continue
                if order.segment_id != runtime.current_segment:
                    runtime.risk.reject_pending(order, time_ns)
                    emit("rejections", runtime, time_ns, row, {"stage": "acknowledgement", "reason": "segment_changed"})
                    continue
                order.active_at_ns = time_ns
                order.expires_at_ns = time_ns + _positive_int(strategy["order_lifetime_ns"], "order_lifetime_ns")
                runtime.risk.acknowledge(order)
                runtime.live[order.order_id] = order
                emit(
                    "risk-events",
                    runtime,
                    time_ns,
                    row,
                    {"operation": "acknowledge", "order_id": order.order_id, "result": "applied", "risk_view": runtime.risk.view()},
                )
                emit(
                    "acknowledgements",
                    runtime,
                    time_ns,
                    row,
                    {"order_id": order.order_id, "expires_at_utc_ns": order.expires_at_ns},
                )
                push(runtime, "cancel", order.expires_at_ns, causal_ordinal, {"row": row, "order_id": order.order_id, "reason": "logical_expiry"})
            elif kind == "cancel":
                order = runtime.pending.pop(payload["order_id"], None)
                if order is not None:
                    runtime.risk.reject_pending(order, time_ns)
                    operation = "command_reject"
                else:
                    order = runtime.live.pop(payload["order_id"], None)
                    if order is None:
                        continue
                    runtime.risk.cancel(order, payload["reason"], time_ns)
                    operation = "cancel"
                emit(
                    "risk-events",
                    runtime,
                    time_ns,
                    row,
                    {"operation": operation, "order_id": order.order_id, "result": "applied", "risk_view": runtime.risk.view()},
                )
                emit("cancellations", runtime, time_ns, row, {"order_id": order.order_id, "reason": payload["reason"]})

        terminal_row_by_ticker = {
            ticker: max(
                (row for row in preflight.features.values() if row["product_identity"]["ticker"] == ticker),
                key=lambda value: value["as_of"]["normalization_watermark"],
            )
            for ticker in runtimes
        }
        for ticker, runtime in runtimes.items():
            row = terminal_row_by_ticker[ticker]
            for order in list(runtime.pending.values()):
                runtime.risk.reject_pending(order, terminal_time)
                del runtime.pending[order.order_id]
                emit(
                    "risk-events", runtime, terminal_time, row,
                    {"operation": "command_reject", "order_id": order.order_id, "result": "end_of_run", "risk_view": runtime.risk.view()},
                )
                emit("cancellations", runtime, terminal_time, row, {"order_id": order.order_id, "reason": "end_of_run"})
            for order in list(runtime.live.values()):
                runtime.risk.cancel(order, "end_of_run", terminal_time)
                del runtime.live[order.order_id]
                emit(
                    "risk-events", runtime, terminal_time, row,
                    {"operation": "cancel", "order_id": order.order_id, "result": "end_of_run", "risk_view": runtime.risk.view()},
                )
                emit("cancellations", runtime, terminal_time, row, {"order_id": order.order_id, "reason": "end_of_run"})
            view = runtime.risk.view()
            emit("exposure", runtime, terminal_time, row, {"risk_view": view})
            emit("summary", runtime, terminal_time, row, {"scope": "product", "counts": dict(sorted(runtime.counts.items()))})

        output_descriptors = []
        for name, records in artifacts.items():
            path = temporary / f"{name}.jsonl"
            with path.open("x", encoding="utf-8") as destination:
                for record in records:
                    destination.write(phase7.canonical_json(record) + "\n")
            output_descriptors.append(
                {"name": name, "schema": ARTIFACT_SCHEMAS[name], "path": path.name, "sha256": phase7.sha256_file(path), "row_count": len(records)}
            )
        risk_descriptors = []
        result_products = []
        for ticker, runtime in runtimes.items():
            trace_path = temporary / f"risk-trace-{runtime.contract_id}.jsonl"
            with trace_path.open("x", encoding="utf-8") as destination:
                for record in runtime.risk.trace:
                    destination.write(phase7.canonical_json(record) + "\n")
            trace = {
                "ticker": ticker,
                "contract_id": runtime.contract_id,
                "path": trace_path.name,
                "sha256": phase7.sha256_file(trace_path),
                "row_count": len(runtime.risk.trace),
            }
            risk_descriptors.append(trace)
            result_products.append(
                {
                    "product_identity": runtime.config["product_identity"],
                    "contract_identity": runtime.config["contract_identity"],
                    "reviewed_lineage": runtime.config["reviewed_lineage"],
                    "segments": runtime.segments,
                    "counts": dict(sorted(runtime.counts.items())),
                    "terminal_risk_view": runtime.risk.view(),
                    "risk_trace": trace,
                }
            )
        aggregate = Counter()
        for runtime in runtimes.values():
            aggregate.update(runtime.counts)
        manifest = {
            "schema": RESULT_SCHEMA,
            "run_id": preflight.config["run_id"],
            "config_sha256": preflight.config_sha256,
            "inputs": preflight.config["inputs"],
            "feature_definition_sha256": preflight.feature_definition_sha256,
            "scheduling_policy": SCHEDULING_POLICY,
            "execution": preflight.config["execution"],
            "risk": {"engine": "cxx_oracle_v2", "ownership": "per_contract_projection", "traces": risk_descriptors},
            "completeness": "complete_observed_interval",
            "limitations": preflight.config["limitations"],
            "non_claims": {
                "fees": "not_applied",
                "accounting": "not_applied",
                "pnl": "not_applied",
                "collateral": "not_applied",
                "margin": "not_applied",
                "settlement": "not_applied",
                "portfolio_risk": "not_implemented",
            },
            "products": result_products,
            "aggregate_counts": dict(sorted(aggregate.items())),
            "artifacts": output_descriptors,
        }
        phase7.validate_historical_schema(manifest, "backtest-result-manifest-v4.schema.json", "BacktestResultSchemaMismatch")
        phase7.write_json(temporary / "manifest.json", manifest)
        temporary.rename(output_dir)
        for runtime in runtimes.values():
            runtime.risk.close()
        return manifest
    except BaseException:
        for runtime in runtimes.values():
            try:
                runtime.risk.close()
            except Exception:
                pass
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def verify_backtest_v4(config_path: Path, result_dir: Path) -> dict[str, Any]:
    preflight = _preflight(config_path)
    result_dir = result_dir.resolve()
    manifest_path = result_dir / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise phase7.HistoricalDataError("BacktestResultMissing", "result manifest is missing")
    manifest = phase7.read_json(manifest_path)
    phase7.validate_historical_schema(
        manifest, "backtest-result-manifest-v4.schema.json", "BacktestResultSchemaMismatch"
    )
    if manifest.get("config_sha256") != preflight.config_sha256 or manifest.get("inputs") != preflight.config.get(
        "inputs"
    ):
        raise phase7.HistoricalDataError("BacktestResultLineageMismatch", "result configuration lineage differs")
    declared_products = [item["product_identity"] for item in preflight.products]
    result_products = [item.get("product_identity") for item in manifest.get("products", [])]
    if declared_products != result_products:
        raise phase7.HistoricalDataError("BacktestResultLineageMismatch", "result product identities differ")
    counts: Counter[str] = Counter()
    for artifact in manifest.get("artifacts", []):
        path = result_dir / str(artifact.get("path", ""))
        try:
            path.resolve().relative_to(result_dir)
        except ValueError as error:
            raise phase7.HistoricalDataError("BacktestResultPathUnsafe", "artifact path escapes result") from error
        if not path.is_file() or path.is_symlink() or artifact.get("sha256") != phase7.sha256_file(path):
            raise phase7.HistoricalDataError("BacktestResultHashMismatch", "result artifact hash is stale")
        rows = list(phase7.iter_jsonl(path))
        if artifact.get("row_count") != len(rows):
            raise phase7.HistoricalDataError("BacktestResultCountMismatch", "artifact row count differs")
        counts[str(artifact["name"])] = len(rows)
    product_sum: Counter[str] = Counter()
    for product in manifest.get("products", []):
        product_sum.update(product.get("counts", {}))
        trace = product.get("risk_trace", {})
        trace_path = result_dir / str(trace.get("path", ""))
        if not trace_path.is_file() or trace_path.is_symlink() or trace.get("sha256") != phase7.sha256_file(trace_path):
            raise phase7.HistoricalDataError("BacktestResultHashMismatch", "risk trace hash is stale")
        if trace.get("row_count") != sum(1 for _ in phase7.iter_jsonl(trace_path)):
            raise phase7.HistoricalDataError("BacktestResultCountMismatch", "risk trace row count differs")
    if dict(sorted(product_sum.items())) != manifest.get("aggregate_counts") or any(
        counts[name] != manifest["aggregate_counts"].get(name, 0) for name in ARTIFACT_SCHEMAS
    ):
        raise phase7.HistoricalDataError("BacktestResultCountMismatch", "aggregate counts do not match products")
    return {
        "schema": RESULT_SCHEMA,
        "config_sha256": preflight.config_sha256,
        "result_manifest_sha256": phase7.sha256_file(manifest_path),
        "verified": True,
    }
