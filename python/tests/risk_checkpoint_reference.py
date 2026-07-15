"""Test-only checkpoint capture/validation/restore for the checkpoint conformance corpus.

This module is the Python side of the pmm.risk_checkpoint.v1 dual-implementation evidence.
It builds on the shared-subset ``ReferenceRisk`` without changing it: ``ReferenceRisk.apply``
still refuses ``checkpoint``/``restore`` operations, and this module is never imported by
production or backtest code.  C++ remains the canonical risk implementation.
"""

from __future__ import annotations

from typing import Any, Optional

from python.tests.risk_conformance_reference import ReferenceRisk

CHECKPOINT_SCHEMA = "pmm.risk_checkpoint.v1"


def capture(reference: ReferenceRisk, account_id: str = "1", strategy_id: str = "1",
            trader_id: str = "1") -> dict[str, Any]:
    """Serialize the reference state as a pmm.risk_checkpoint.v1 document."""
    snapshot = reference.snapshot()
    return {
        "account_id": account_id,
        "contract_id": reference.contract_id,
        "event_watermark": snapshot["event_watermark"],
        "kill_switch_active": snapshot["kill_switch_active"],
        "limits": {
            "maximum_absolute_position_contracts": str(reference.maximum_absolute_position),
            "maximum_active_orders": reference.maximum_active_orders,
            "maximum_buy_exposure_contracts": str(reference.maximum_buy_exposure),
            "maximum_order_quantity_contracts": str(reference.maximum_order_quantity),
            "maximum_pending_exposure_contracts": str(reference.maximum_pending_exposure),
            "maximum_sell_exposure_contracts": str(reference.maximum_sell_exposure),
        },
        "live_orders": snapshot["live_orders"],
        "net_position_contracts": snapshot["net_position_contracts"],
        "pending_orders": snapshot["pending_orders"],
        "schema": CHECKPOINT_SCHEMA,
        "strategy_id": strategy_id,
        "trader_id": trader_id,
    }


def validate_checkpoint(document: dict[str, Any]) -> Optional[str]:
    """First-failure semantic validation mirroring AccountRiskProjection::validate_checkpoint.

    Live orders are scanned in document order (zero quantity, then duplicate identifier), then
    pending orders (contract, zero quantity, post-only, zero ingress, duplicate ingress,
    duplicate intent), then the active-order count, open/pending exposure, and position.
    """
    open_totals = {"buy": 0, "sell": 0}
    seen_orders: set[str] = set()
    for order in document["live_orders"]:
        if int(order["remaining_quantity_contracts"]) == 0:
            return "checkpoint_zero_live_quantity"
        if order["order_id"] in seen_orders:
            return "checkpoint_duplicate_order_id"
        seen_orders.add(order["order_id"])
        open_totals[order["side"]] += int(order["remaining_quantity_contracts"])
    pending_totals = {"buy": 0, "sell": 0}
    seen_intents: set[str] = set()
    seen_ingress: set[str] = set()
    for pending in document["pending_orders"]:
        if pending["contract_id"] != document["contract_id"]:
            return "checkpoint_contract_mismatch"
        if int(pending["quantity_contracts"]) == 0:
            return "checkpoint_zero_pending_quantity"
        if not pending["post_only"]:
            return "checkpoint_non_post_only"
        ingress = pending["ingress_sequence"]
        if ingress is not None:
            if int(ingress) == 0:
                return "checkpoint_zero_ingress"
            if ingress in seen_ingress:
                return "checkpoint_duplicate_ingress"
            seen_ingress.add(ingress)
        if pending["client_intent_id"] in seen_intents:
            return "checkpoint_duplicate_client_intent"
        seen_intents.add(pending["client_intent_id"])
        pending_totals[pending["side"]] += int(pending["quantity_contracts"])
    limits = document["limits"]
    if len(document["live_orders"]) + len(document["pending_orders"]) > int(
            limits["maximum_active_orders"]):
        return "checkpoint_active_order_limit"
    if open_totals["buy"] > int(limits["maximum_buy_exposure_contracts"]):
        return "checkpoint_buy_exposure_limit"
    if open_totals["sell"] > int(limits["maximum_sell_exposure_contracts"]):
        return "checkpoint_sell_exposure_limit"
    if (pending_totals["buy"] > int(limits["maximum_pending_exposure_contracts"])
            or pending_totals["sell"] > int(limits["maximum_pending_exposure_contracts"])):
        return "checkpoint_pending_exposure_limit"
    position = int(document["net_position_contracts"])
    limit = int(limits["maximum_absolute_position_contracts"])
    if (position > limit - (open_totals["buy"] + pending_totals["buy"])
            or position < -limit + open_totals["sell"] + pending_totals["sell"]):
        return "checkpoint_position_limit"
    return None


def restore_reference(document: dict[str, Any]) -> ReferenceRisk:
    """Construct a ReferenceRisk from a semantically valid checkpoint document."""
    limits = document["limits"]
    reference = ReferenceRisk(
        contract_id=document["contract_id"],
        maximum_order_quantity=int(limits["maximum_order_quantity_contracts"]),
        maximum_absolute_position=int(limits["maximum_absolute_position_contracts"]),
        maximum_buy_exposure=int(limits["maximum_buy_exposure_contracts"]),
        maximum_sell_exposure=int(limits["maximum_sell_exposure_contracts"]),
        maximum_pending_exposure=int(limits["maximum_pending_exposure_contracts"]),
        maximum_active_orders=int(limits["maximum_active_orders"]),
        watermark=int(document["event_watermark"]),
        position=int(document["net_position_contracts"]),
        kill_switch=bool(document["kill_switch_active"]),
    )
    for order in document["live_orders"]:
        reference.live[order["order_id"]] = dict(order)
    for pending in document["pending_orders"]:
        reference.pending[pending["client_intent_id"]] = dict(pending)
    return reference
