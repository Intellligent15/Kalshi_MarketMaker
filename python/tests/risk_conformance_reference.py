"""Test-only reference for the deliberately small canonical-risk conformance subset.

It is intentionally not imported by the Phase-7 runner and raises rather than approximating
operations outside the fixture contract.  C++ remains the production risk implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class UnsupportedSharedOperation(ValueError):
    pass


@dataclass
class ReferenceRisk:
    contract_id: str = "1"
    watermark: int = 0
    position: int = 0
    kill_switch: bool = False
    live: dict[str, dict[str, Any]] = field(default_factory=dict)
    pending: dict[str, dict[str, Any]] = field(default_factory=dict)

    def snapshot(self) -> dict[str, Any]:
        def total(side: str, pending: bool) -> str:
            records = self.pending.values() if pending else self.live.values()
            key = "quantity_contracts" if pending else "remaining_quantity_contracts"
            return str(sum(int(record[key]) for record in records if record["side"] == side))
        return {
            "event_watermark": str(self.watermark), "kill_switch_active": self.kill_switch,
            "live_orders": [dict(self.live[key]) for key in sorted(self.live, key=int)],
            "net_position_contracts": str(self.position), "open_buy_contracts": total("buy", False),
            "open_sell_contracts": total("sell", False), "pending_buy_contracts": total("buy", True),
            "pending_orders": [dict(self.pending[key]) for key in sorted(self.pending, key=int)],
            "pending_sell_contracts": total("sell", True),
        }

    def apply(self, operation: dict[str, Any]) -> dict[str, Any]:
        kind = operation.get("operation")
        if kind == "admit":
            client = str(operation["client_intent_id"])
            quantity = int(operation["quantity_contracts"])
            if self.kill_switch:
                result = "kill_switch_active"
            elif str(operation["contract_id"]) != self.contract_id:
                result = "contract_mismatch"
            elif quantity <= 0:
                result = "order_quantity_limit"
            elif client in self.pending:
                result = "duplicate_client_intent"
            else:
                self.pending[client] = {"client_intent_id": client, "contract_id": self.contract_id,
                    "ingress_sequence": None, "limit_price_cents": str(operation["limit_price_cents"]),
                    "post_only": True, "quantity_contracts": str(quantity), "side": operation["side"]}
                result = "approved"
            return {"result": result, "state": self.snapshot()}
        if kind == "bind_ingress":
            client, ingress = str(operation["client_intent_id"]), int(operation["ingress_sequence"])
            if (client not in self.pending or self.pending[client]["ingress_sequence"] is not None or
                    ingress == 0 or any(record["ingress_sequence"] == str(ingress)
                                        for record in self.pending.values())):
                return {"result": "domain_error", "state": self.snapshot()}
            self.pending[client]["ingress_sequence"] = str(ingress)
            return {"result": "applied", "state": self.snapshot()}
        if kind == "acknowledge":
            return self._event(operation, "acknowledge")
        if kind == "fill":
            return self._event(operation, "fill")
        if kind in {"cancel", "logical_expiry"}:
            return self._event(operation, "cancel")
        if kind == "command_rejected":
            return self._event(operation, "command_rejected")
        if kind == "kill_switch":
            self.kill_switch = bool(operation["active"])
            return {"result": "applied", "state": self.snapshot()}
        raise UnsupportedSharedOperation(f"unsupported shared conformance operation: {kind!r}")

    def _event(self, operation: dict[str, Any], kind: str) -> dict[str, Any]:
        sequence = int(operation["sequence"])
        if sequence != self.watermark + 1:
            return {"result": "domain_error", "state": self.snapshot()}
        if kind == "acknowledge":
            ingress = str(operation["ingress_sequence"])
            candidates = [record for record in self.pending.values() if record["ingress_sequence"] == ingress]
            if len(candidates) != 1:
                return {"result": "domain_error", "state": self.snapshot()}
            pending = candidates[0]
            if (pending["side"] != operation["side"] or pending["quantity_contracts"] != str(operation["quantity_contracts"])
                    or pending["limit_price_cents"] != str(operation["limit_price_cents"])):
                return {"result": "domain_error", "state": self.snapshot()}
            order_id = str(operation["order_id"])
            if order_id in self.live:
                return {"result": "domain_error", "state": self.snapshot()}
            self.live[order_id] = {"acknowledged_at_utc_ns": str(operation["time_utc_ns"]),
                "limit_price_cents": pending["limit_price_cents"], "order_id": order_id,
                "remaining_quantity_contracts": pending["quantity_contracts"], "side": pending["side"]}
            del self.pending[pending["client_intent_id"]]
        elif kind == "fill":
            order = self.live.get(str(operation["order_id"]))
            quantity = int(operation["quantity_contracts"])
            if (order is None or order["side"] != operation["side"] or quantity <= 0 or
                    quantity > int(order["remaining_quantity_contracts"])):
                return {"result": "domain_error", "state": self.snapshot()}
            self.position += quantity if order["side"] == "buy" else -quantity
            remaining = int(order["remaining_quantity_contracts"]) - quantity
            if remaining:
                order["remaining_quantity_contracts"] = str(remaining)
            else:
                del self.live[str(operation["order_id"])]
        elif kind == "cancel":
            self.live.pop(str(operation["order_id"]), None)
        else:
            ingress = str(operation["ingress_sequence"])
            for client, pending in list(self.pending.items()):
                if pending["ingress_sequence"] == ingress:
                    del self.pending[client]
                    break
        self.watermark = sequence
        return {"result": "applied", "state": self.snapshot()}
