# Data

- `raw/`: immutable source captures.
- `external/`: data obtained from third parties.
- `processed/`: derived datasets.

Phase 7 captures are written beneath `raw/<capture-id>/`. A raw capture contains append-only
verbatim source frames and separate run metadata (including reconnect/gap records); it is not a
normalized market-data dataset and must not be edited after capture.

Raw capture V2 additionally gives every lifecycle/frame record a capture-global ingress ordinal,
binds request/channel/SID scopes, and records reconnect segments. `capture_continuity` is a bounded
assessment, not proof that an unknown venue sequence domain had no missing messages.

Normalized event streams and materialized causal features are generated beneath `processed/`. Their manifests link output hashes to raw-capture hashes, schema/normalizer or feature versions, ordering policy, validation outcome, and source fidelity. They are generated and ignored by Git; the command and versioned configuration that produced them are version controlled.

Normalization V3 writes `records.jsonl`, `source_scopes.json`, `product.json`, and `manifest.json`.
The ordered record stream includes discontinuities and segment starts beside market events so a
consumer cannot silently ignore invalidation. B2b owns feature consumption of this format.

Data contents are ignored by Git by default. Add small fixtures deliberately beside their
tests, or document and version an exception when a dataset must be shared.

B2c large raw and derived evidence remains ignored and must have an approved durable owner,
location, read policy, and backup promise before capture. Git retains only the compact policy,
evidence index, measurement summaries, review record, and an explicitly approved complete V4 bundle
of at most 10 MiB. A manifest without mounted bytes is an index claim, not full byte verification.
