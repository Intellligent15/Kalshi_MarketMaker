# Data

- `raw/`: immutable source captures.
- `external/`: data obtained from third parties.
- `processed/`: derived datasets.

Phase 7 captures are written beneath `raw/<capture-id>/`. A raw capture contains append-only
verbatim source frames and separate run metadata (including reconnect/gap records); it is not a
normalized market-data dataset and must not be edited after capture.

Normalized event streams and materialized causal features are generated beneath `processed/`. Their manifests link output hashes to raw-capture hashes, schema/normalizer or feature versions, ordering policy, validation outcome, and source fidelity. They are generated and ignored by Git; the command and versioned configuration that produced them are version controlled.

Data contents are ignored by Git by default. Add small fixtures deliberately beside their
tests, or document and version an exception when a dataset must be shared.
