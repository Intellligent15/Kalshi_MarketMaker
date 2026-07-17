# Phase 7 Multi-Scope Capture Critique

## Rating method

Impact is 1 (minor) through 5 (material correctness or research-validity blocker). Ease is 1
(large/uncertain) through 5 (small/local). Findings describe current debt after B2a.

## Findings

| Finding | Impact | Ease | Current handling | Follow-up |
| --- | ---: | ---: | --- | --- |
| Kalshi sequence-domain scope remains undocumented by retained primary evidence. | 4 | 2 | Production records `unknown`; validation and claims remain mechanical. | Retain official specification evidence if the venue publishes an explicit domain; do not infer from a live sample. |
| `capture-v2` has synthetic transport coverage but no retained long-duration real reconnect capture. | 4 | 2 | No new live capture was required or retained in B2a. | B2c should retain a reviewed full-capture regression with counts and hashes. |
| Feature and backtest consumers cannot consume even complete normalization V3. | 4 | 2 | They fail closed with `DownstreamContinuityRequired`. | B2b must add per-product, per-segment projection and causal features. |
| Capture V2 metadata is finalized in place rather than published through a temporary-directory rename. | 3 | 3 | Partial raw evidence is deliberately retained and shutdown status is explicit. | Before operational use, define a durable raw-finalization protocol without discarding interrupted evidence. |
| Raw binary frames are counted and rejected without retaining their bytes. | 3 | 4 | The capture becomes incomplete and reconnects. | Retain bounded base64 bytes or document a protocol guarantee before claiming forensic completeness. |
| Sequence gaps in an unknown domain are conservative defects, not proven missing venue events. | 3 | 5 | Manifests record the unknown scope and limitation. | Keep diagnostics phrased as mechanical/potential gaps. |
| Product-map V3 supports multiple reviewed packages, but the current catalog has no two-product effective interval suitable for one real simultaneous capture. | 3 | 2 | Single-product lineage is tested; multi-product capture identity is tested synthetically. | Add future contemporaneous product packages before a reviewed multi-product experiment. |
| Formal schemas cover new B2a formats, while older historical rows/manifests remain runtime-defined. | 3 | 3 | Frozen legacy adapters preserve their meaning. | Add legacy schemas only as compatibility descriptions without tightening accepted bytes. |
| The one-process recorder still has no concurrent-connection failure isolation. | 2 | 2 | `single_connection_v1` is explicit and other strategies refuse. | Consider multiple connections only after venue limits and cross-socket ingress ownership are designed. |
| Derived artifact publication still lacks a full fsync/directory-fsync durability protocol. | 2 | 3 | Atomic rename and raw reproducibility remain adequate for current research scale. | Revisit with durable full-run continuation, not inside B2a. |

## Closed findings

- Reconnect lifecycle no longer disappears during normalization.
- A post-gap snapshot no longer silently establishes continuous history.
- Multiple markets no longer share one global product/book identity in the normalized contract.
- Request identity, acknowledgement SID, channel, and sequence domain are no longer collapsed.
- Cross-scope ordering is explicit and byte-deterministic.
- Synthetic fixtures no longer become unconditionally labelled `Observed` on the successor path.
- Normalization interruption removes partial output.

## Priority

1. B2b multi-market segment-aware projection/features/replay.
2. B2c retained full-capture regression evidence.
3. Primary sequence-domain evidence if it becomes available.
4. Durability and scaling only after representative larger captures justify them.

The implementation still makes no queue, hidden-liquidity, venue-equivalent execution, accounting,
settlement, paper-readiness, live-readiness, or profitability claim.
