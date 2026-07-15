# Tools

Place project-specific developer or analysis tools here when they are not part of the runtime
application, test suite, or research notebooks.

`risk_fixture_integrity.py` verifies canonical JSON bytes and SHA-256 manifest metadata for the
reviewed lifecycle and checkpoint risk-conformance corpora. It is read-only unless `--write` is
passed, and it never generates or semantically verifies expected transitions.
