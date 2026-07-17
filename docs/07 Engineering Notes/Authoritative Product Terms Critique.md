# Authoritative Product Terms Critique

## Scope and rating method

This critique reviews Track B1a as implemented by `6dc3000`, documented by `fc2dd88`, and corrected
by `8a867d7`. It evaluates the product package, acquisition and review workflow, formal schemas,
catalog, conversion policy, normalization/feature/backtest lineage, tests, and operator docs.

Impact is rated from 1 to 5:

| Impact | Meaning |
|---:|---|
| 5 | Can invalidate provenance or research identity, or materially block safe expansion |
| 4 | Significant correctness, security, compatibility, or auditability debt |
| 3 | Important maintainability, operability, or scale limitation |
| 2 | Contained friction or optimization opportunity |
| 1 | Cosmetic or low-consequence improvement |

Ease is also rated from 1 to 5, where 1 is a large architectural or evidence-gathering effort and 5
is a small bounded change. Priority is based on impact first, then dependency order—not simply the
easiest work.

## Overall assessment

B1a materially improves the system. A historical run can no longer silently inherit venue terms
from a WebSocket capture or an undocumented integer assumption. The source, terms, review,
conversion policy, normalized data, features, configuration, and result now form a verifiable
offline lineage. Exact conversion refusal and legacy non-reinterpretation are especially strong
choices.

The implementation is not yet a finished product-metadata service. It is a strict, one-venue,
one-reviewed-market foundation whose strongest guarantees apply to byte identity and selected
cross-source fields. Human approval, temporal consistency, schema parity, acquisition security,
document semantics, and multi-market scale need further work before this boundary can support
economic accounting or broad product coverage.

## Unnecessary complexity

| Finding | Impact | Ease | Why it exists and why it matters | Recommended action |
|---|---:|---:|---|---|
| `python/pmm_product_terms.py` combines canonical encoding, validation, venue projection, acquisition, review, catalog, compatibility, migration, copying, and nine CLI commands in one module of more than 1,000 lines. | 3 | 3 | A single file made the first package auditable, but each new venue or schema version will increase coupling and review surface. | Split only when B1b adds a second product: `canonical`, `schemas/models`, `kalshi_projection`, `catalog`, and `cli`. Keep one public error model. |
| The same lineage identity is repeated in normalization, feature, configuration, and result manifests. | 2 | 3 | Repetition makes artifacts inspectable, but manually maintaining parallel field sets risks omission when V4 arrives. | Introduce a typed product-lineage value object and one serializer/verifier used by every stage. Keep hashes repeated in artifacts. |
| Validation is implemented twice: partially in JSON Schema and more completely in handwritten Python. | 4 | 2 | Two authorities already disagree. External schema users can accept documents the runtime rejects. | Make one representation normative and test generated/maintained schemas against the runtime acceptance corpus. Do not leave “formal” schemas as weaker illustrations. |
| Package copying verifies the same files multiple times during catalog load, resolution, normalization, and copy verification. | 2 | 4 | Redundant verification is safe for one small package but adds I/O and code-path noise. | Cache immutable verified package identities within one process; never cache across content/hash changes. |
| Product-specific API field mapping is embedded in generic validation flow and depends on fixed source IDs such as `market_record`. | 3 | 2 | It is clear for the first Kalshi market but makes the supposedly general package loader venue-shaped. | Define a venue projection adapter with an explicit adapter version in the review/package identity. |

## Future technical debt and correctness risks

| Finding | Impact | Ease | Evidence and risk | Recommended action |
|---|---:|---:|---|---|
| Terms, review, and catalog effective intervals are parsed but not required to be identical or consistently nested. | 5 | 4 | `ProductReview.load` compares the effective-time basis but not its interval to the terms interval; catalog entries are not cross-checked against either. A catalog can therefore advertise dates different from the reviewed document. | Add one exact interval contract or explicitly version rules for containment. Reject disagreement and add three-way mutation tests. |
| The acquisition client checks the requested URL host before `requests` follows redirects, but does not validate the final response URL or every redirect hop. | 5 | 4 | An approved URL could redirect to an unapproved host, weakening the “first-party retained bytes” claim and creating a network-security boundary problem. | Disable redirects or validate every hop and final hostname against the allowlist; retain the redirect chain. |
| “Reviewed” is a self-asserted CLI status with no reviewer identity, review policy, signature, or separation between builder and approver. | 4 | 2 | Hashes prove what was approved, not who approved it or under what controls. This becomes material when product terms affect accounting or external demonstrations. | Add reviewer identity/policy metadata and repository review requirements. Consider signatures only after the human workflow is defined. |
| Markdown/PDF evidence is byte-hashed but not semantically tied to projected fields. | 4 | 2 | The `0.01` quantity increment and general settlement/fee semantics depend on reviewed interpretation, while JSON fields are mechanically compared. Hashing detects change but cannot prove the projection is correct. | Record field-level evidence references with document section/page anchors and reviewed quotations or structured extracts within copyright limits. |
| The formal product-terms schema leaves contracts, ranges, payout, rules, lifecycle, settlement, and fees as generic objects. | 4 | 3 | A third-party validator can accept missing or malformed economic fields that the Python runtime refuses. | Fully specify nested structures, uniqueness/order, decimal patterns, and enumerations; add schema/runtime parity tests. |
| Error categories are string literals distributed across code and are not a versioned public schema. | 3 | 3 | Tests match text fragments. Refactoring or adding another language can silently change diagnostic compatibility. | Define an error-code registry with meaning and stability policy; test codes directly rather than formatted messages. |
| Compatibility currently treats different source or review hashes as incompatible even when canonical economic terms and conversion policy are identical. | 3 | 2 | This is safely conservative, but it conflates “not byte-identical evidence” with “not economically comparable.” | Define separate identity levels: exact-reproduction compatibility, economic-terms compatibility, and execution-policy compatibility. Never weaken the default exact gate. |
| Review revocation and supersession appear in JSON Schema status values, but runtime accepts only `reviewed` and the catalog has no revocation operation or incident workflow. | 4 | 2 | A bad package can be removed in Git, but there is no explicit historical revocation record or rule for previously generated results. | Design append-only revocation/supersession records and result warnings before product packages are used for economic claims. |
| Source `retrieved_at_utc` is supplied by an operator specification rather than captured from the acquisition clock, and response status/final URL/headers are not fully retained. | 3 | 3 | The bytes remain exact, but acquisition provenance is partly declarative. | Record acquisition start/end from the tool, status, final URL, selected headers, and tool version; distinguish operator-requested label from observed retrieval time. |
| The source fetch has no maximum response size, streaming hash, content-type allowlist, or per-source policy. | 4 | 3 | A large or wrong response can consume memory/disk or enter review with a misleading media type. | Stream to a bounded temporary file, hash incrementally, validate declared role/media policy, and fail atomically. |
| The initial package is retrospective and omits linked contract and certification PDF bytes. | 4 | 2 | This limitation is honestly propagated, but the complete legal/economic source cannot be reconstructed offline. | B1b should acquire before capture and retain linked authoritative documents or refuse approval. |
| Product-term V1 is intentionally binary, Kalshi-production-only, and one-dollar-notional-only. | 3 | 1 | This is appropriate scope control, but new venues, multivariate markets, or other notionals require versioned adapters/schemas rather than extra conditionals. | Keep V1 frozen; design explicit successor schemas from real second-product evidence. |

## Missing tests

| Missing test | Impact | Ease | Acceptance condition |
|---|---:|---:|---|
| Terms/review/catalog interval disagreement | 5 | 5 | Every mismatch and invalid containment policy fails with a stable code. |
| Redirect from an allowed first-party host to an unapproved host | 5 | 3 | Acquisition refuses before retaining bytes; redirect history is tested without the live network. |
| JSON Schema and runtime parity corpus | 4 | 2 | Every reviewed positive fixture passes both; every schema-addressable negative fixture fails both. |
| Full public CLI subprocess matrix | 4 | 3 | All commands, exit statuses, stdout/stderr separation, overwrite refusal, and partial cleanup are tested through the public entry point. |
| Tampered V3 configuration, normalization manifest, feature manifest, result manifest, and each result artifact | 5 | 4 | Each single defect produces the intended refusal and does not publish a new final directory. |
| Fractional strategy quantity and sub-cent strategy price failure cleanup | 4 | 5 | A V3 run refuses before final output and leaves no `.partial` directory. |
| Catalog overlap, adjacent intervals, gaps, two revisions, and two markets | 5 | 3 | Lookup selects exactly one revision or names the precise gap/overlap; ordering remains deterministic. |
| Symlink at every package/catalog level and encoded/alternate unsafe paths | 4 | 3 | No symlink or escaping member is followed, including catalog package paths. |
| Source semantic mutation with correctly recomputed source hashes | 4 | 3 | Mechanically projected fields still fail `SourceTermsMismatch`; changing both terms and evidence requires a new review. |
| Price range boundaries and multiple ranges | 4 | 4 | Inclusive/exclusive endpoints, adjacent ranges, off-step values, zero, and one behave exactly as declared. |
| Quantity increment boundaries and negative deltas | 4 | 4 | Fractional valid values survive normalization, invalid increments refuse, and only deltas may be negative. |
| Review status, revocation, empty limitations, reviewer policy, and interval edges | 4 | 3 | Approval semantics are explicit and deterministic. |
| Acquisition size/content-type/timeout/cleanup behavior | 4 | 3 | Bounded streamed acquisition refuses wrong or oversized responses and removes partial output. |
| Compatibility levels and field-level diff stability | 3 | 3 | Exact and economic compatibility cannot be confused; diff ordering and path format are frozen. |
| Canonical Unicode, timestamp precision, decimal zero forms, and very large values | 3 | 3 | Python versions and external implementations reproduce identical hashes or refuse unsupported forms. |
| Legacy assessment complementary trade prices | 3 | 5 | Legacy assessment enforces the same yes/no complement rule as normalization V2. |

## Missing documentation

| Gap | Impact | Ease | Needed documentation |
|---|---:|---:|---|
| No complete acquisition-spec example is checked in. | 4 | 5 | A safe template showing roles, URLs, linked-document discovery, expected media types, and review checkpoints without live mutable test dependencies. |
| No stable error-code reference. | 3 | 4 | Code, meaning, affected stage, whether retry can help, and compatibility promise. |
| No schema evolution and deprecation playbook beyond “version it.” | 4 | 3 | Additive versus breaking changes, catalog coexistence, migration evidence, and old-result verification policy. |
| No revocation/supersession incident procedure. | 4 | 3 | How to mark a package bad without erasing history and how to flag dependent normalized/results artifacts. |
| No reviewer checklist or approval responsibility model. | 4 | 4 | Required sources, field checks, effective-time proof, linked documents, limitations, and independent review expectation. |
| No artifact-storage/retention policy. | 3 | 3 | When copied packages can use content-addressed storage, what must stay beside normalized data, and how garbage collection preserves reproducibility. |
| No external consumer example for JSON Schema and hash verification. | 2 | 3 | A small independent verifier or language-neutral known-answer fixture. |
| Operator commands are listed but not presented as a complete new-revision walkthrough with recovery from failure. | 3 | 4 | Fetch → inspect → build → diff → review → catalog → verify → normalize, including immutable retry paths. |

## Possible optimizations

| Optimization | Impact | Ease | When to do it |
|---|---:|---:|---|
| Cache verified packages by path plus complete file identity within one command. | 2 | 4 | When a catalog contains enough entries for repeated hashing to appear in profiles. |
| Index catalog entries by `(venue, environment, market_ticker)` and binary-search effective intervals. | 3 | 4 | Before hundreds or thousands of revisions; current linear lookup is clearer for one entry. |
| Store one content-addressed product package and reference it from normalized datasets. | 3 | 2 | When retained PDFs or many datasets make byte duplication material. Preserve exportable self-contained bundles. |
| Stream legacy assessment rather than `read_text().splitlines()`. | 2 | 5 | Immediately when that tool is touched; it avoids loading long event histories twice. |
| Stream acquisition bytes and compute SHA-256 incrementally. | 4 | 3 | B1b, because it is both a safety improvement and a scale optimization. |
| Generate lineage serialization and possibly JSON Schema from typed definitions. | 3 | 2 | After a second product proves the stable abstractions; premature generation now could hide policy. |
| Avoid copying/revalidating the package until normalized event validation succeeds. | 2 | 4 | After measuring failure-path cost; correctness is already preserved by the temporary directory. |

## Future scalability concerns

| Concern | Impact | Ease | Scaling failure mode | Direction |
|---|---:|---:|---|---|
| Catalog verification and resolution repeatedly load and hash every relevant package. | 3 | 3 | Startup grows with markets, revisions, and document size. | Immutable verification cache plus indexed interval lookup. |
| Every normalized dataset copies all retained evidence. | 4 | 2 | Legal PDFs multiplied across captures can dominate storage. | Content-addressed store with explicit export/materialization for self-contained archives. |
| One package maps one market with hard-coded Kalshi source shapes. | 4 | 1 | Thousands of markets create manual projections and venue conditionals. | Versioned venue adapters, shared series-level evidence, and generated market-specific reviewed projections. |
| Series/event documents are duplicated per market package. | 3 | 2 | Multi-market events repeat large common source bytes. | Hash-address shared evidence while keeping each review's exact dependency set. |
| Manual review does not scale across frequent term changes. | 5 | 1 | Review becomes a bottleneck or devolves into rubber-stamping. | Automated source diffs and field projections, risk-ranked human review, and explicit approval policy. |
| JSON artifacts and full hashing are simple but expensive for large retained documents and remote archives. | 3 | 2 | Verification latency and storage transfer grow linearly. | Manifest trees/content-addressed blobs only after profiling; keep canonical small control documents. |
| Current lineage is single-product per run. | 4 | 1 | Multi-market backtests need a set or ordered map of product identities and effective revisions. | Design a V4 multi-product lineage contract alongside B2, not by overloading V3 fields. |
| Acquisition is synchronous and sequential. | 2 | 3 | Large product batches are slow and one source failure restarts the package. | Bounded concurrency with deterministic manifest ordering and all-or-nothing final publication. |

## Prioritized follow-up

| Priority | Package | Impact | Ease | Rationale |
|---:|---|---:|---:|---|
| P0 | Enforce exact/defined effective-interval consistency and add mutation tests. | 5 | 4 | A small gap in the identity contract can misstate which terms cover a capture. |
| P1 | Harden acquisition redirects, streaming size limits, observed retrieval metadata, and cleanup tests. | 5 | 3 | Protects the first-party provenance boundary before acquisition is reused. |
| P2 | Complete JSON Schemas and establish schema/runtime parity tests. | 4 | 2 | Prevents two conflicting definitions of a valid product package. |
| P3 | Execute B1b: contemporaneous acquisition, linked-document retention, and a second product family. | 5 | 1 | Supplies the evidence needed to validate rather than speculate about generality. |
| P4 | Define reviewer identity, checklist, supersession, and revocation semantics. | 4 | 2 | Turns a hash-stamped status into a durable governance boundary. |
| P5 | Add the full lineage/config/result mutation matrix and public CLI tests. | 5 | 3 | The happy path is strong; negative end-to-end evidence is still too narrow. |
| P6 | Separate exact reproduction compatibility from economic/policy compatibility. | 3 | 2 | Enables honest comparison without weakening the default exact gate. |
| P7 | Refactor the module and optimize catalog/storage only after second-product evidence and profiling. | 3 | 2 | Avoids designing abstractions around a single market while acknowledging real scale pressure. |

## Preserved non-goals

None of these findings justify quietly adding fees, accounting, PnL, settlement processing,
collateral, calibrated fills, queue priority, hidden-liquidity assumptions, multi-market reconnect
recovery, paper trading, gateways, live orders, ML, or broader Phase 3 matching. They also do not
justify changing `AccountRiskProjection`, checkpoint rejection categories or ordinals, risk first-
failure ordering, post-only behavior, watermarks, kill switches, or the closed lifecycle/checkpoint
corpora. Those remain separate packages with separate evidence gates.

## B1b-1 post-implementation critique

### Scope and interpretation

This section is the current critique of commits `dbd6fd8` and `6d489e3`. The B1a tables above are
retained as chronological evidence of why B1b-1 existed; findings shown as closed below are not
current defects. The same 1-to-5 impact scale applies. Ease remains 1 for a large or evidence-heavy
change and 5 for a small bounded change.

B1b-1 is a successful integrity package. It closes the highest-risk ambiguity in temporal
selection, prevents redirect-based escape from the approved source boundary, bounds network input,
separates observed provenance from operator intent, makes refusal categories usable by automation,
and materially deepens offline mutation evidence. It also preserves the existing reviewed package
and downstream artifact identities. The remaining problems are mostly breadth, governance, policy
evolution, and scale. They do not justify weakening the new fail-closed rules.

### Closed B1a findings

| Finding | Evidence |
|---|---|
| Terms/review/catalog intervals could disagree | Exact three-way half-open equality is enforced; adjacent, gap, overlap, and mutation cases are tested. |
| Redirects could leave the first-party boundary | Redirects are manual, bounded, validated at every hop and final URL, and retained in source-manifest V2. |
| Fetch buffered unbounded responses | Role/source/package limits, 64 KiB streaming, incremental SHA-256, deadlines, media validation, and partial cleanup are tested offline. |
| Retrieval time and response provenance were operator-declared | V2 separates operator acquisition intent from tool-observed timing, redirect, status, header, media, byte, hash, and version facts. |
| Formal schemas were materially weaker | Nested V1 structures were completed, acquisition/source V2 schemas were added, and a schema/runtime parity matrix is executable. |
| Error codes and public CLI behavior were undocumented | The refusal registry and compatibility policy define codes, exit statuses, and stream ownership. |
| Happy-path V3 lineage evidence was too narrow | Single-defect normalization, feature, configuration, result-manifest, and result-artifact mutations refuse; nonrepresentable inputs leave no output. |

### Unnecessary complexity

| Finding | Impact | Ease | Tradeoff and recommendation |
|---|---:|---:|---|
| `python/pmm_product_terms.py` is now 1,647 lines and owns canonical JSON, schemas, source validation, Kalshi projection, catalog selection, acquisition transport, compatibility, migration, and CLI dispatch. | 3 | 2 | Keeping one audit surface was reasonable for the first product, but the second adapter will make unrelated changes collide. After B1b-2 proves the seam, split transport, package/catalog, venue projection, and CLI while preserving one error registry and public command behavior. |
| Validity is still described twice: in handwritten JSON Schemas and handwritten runtime checks. | 3 | 2 | The parity corpus prevents known drift, but it does not make the two implementations intrinsically identical. Keep schemas handwritten for reviewability now; expand the shared corpus before considering generation from typed definitions. |
| V3 lineage fields are repeated across normalization, feature, configuration, result creation, and verification. | 3 | 3 | Repetition makes artifacts self-describing, but field-by-field dictionaries and hash comparisons can drift. Introduce one internal typed lineage record and shared verifier without removing repeated artifact fields. |
| Supporting source-manifest V1 and V2 adds branches throughout source loading. | 2 | 2 | This is intentional compatibility complexity: rewriting V1 would invent retrieval facts. Isolate version-specific parsing behind one normalized in-memory representation if a V3 source manifest appears. |
| Role, media, byte, redirect, and timeout policies are module-level constants beside generic parsing code. | 3 | 3 | The policy is easy to audit but difficult to version or reuse. Move it to a versioned, immutable policy definition once real second-product evidence shows which roles are stable. Do not make operators freely configurable at runtime. |

### Future technical debt

| Finding | Impact | Ease | Risk and recommendation |
|---|---:|---:|---|
| The acquisition policy has a tool-version label but no independently hashed policy/version identity. | 4 | 3 | Changing `ROLE_POLICIES` or limits can change whether an old V2 manifest verifies under the same schema. Freeze the V2 validation policy or add an explicit policy identifier whose historical definitions remain loadable. |
| Review approval has no reviewer identity, responsibility rule, independent-approval expectation, revocation record, or supersession incident workflow. | 4 | 2 | Hashes prove what was approved, not who approved it or what dependent results should do after a defect. Define governance before product terms control economic accounting. |
| Markdown and PDF bytes are retained but document-derived fields are not tied to page, section, or stable evidence anchors. | 4 | 2 | Byte identity detects change but cannot demonstrate that a legal or settlement interpretation is correct. Add field-level reviewed evidence references with the contemporaneous package. |
| SIGKILL, power loss, or filesystem failure can leave a unique `.partial` directory. | 3 | 4 | Normal errors and interrupts clean up, retained source files are fsynced, and final publication is atomic, but directory durability and startup scavenging are not promised. Add age-safe scavenging and directory fsync only if acquisition becomes operationally frequent. |
| The refusal-code document and `REFUSAL_CODES` set are separate manual registries. | 3 | 4 | A code can be added in code without a documented compatibility meaning. Add a test that extracts the documented registry or generate the reference table from reviewed structured data. |
| Exact compatibility treats any evidence or review hash change as incompatibility, even if economic terms are unchanged. | 3 | 2 | This is the correct default for reproduction. Later reporting should add separately named economic and execution-policy compatibility levels rather than weakening exact compatibility. |
| Response provenance does not record DNS results, peer certificate identity, or a complete header dump. | 2 | 2 | HTTPS validation plus an exact host allowlist is sufficient for the current research boundary. Record more transport evidence only if a threat model demonstrates that it changes review decisions; avoid retaining sensitive or unstable headers by default. |

### Missing tests

| Missing evidence | Impact | Ease | Acceptance condition |
|---|---:|---:|---|
| Exhaustive acquisition-spec V1 and source-manifest V2 schema/runtime negative parity | 4 | 3 | One-defect cases cover every constrained field family, and both validators agree whenever JSON Schema can express the rule. |
| Redirect edge matrix | 3 | 4 | Cover relative redirects, redirect loops/limit, missing `Location`, unsupported 3xx, HTTPS downgrade, credentials, fragments, non-443 ports, and a response URL changed behind the client's back. |
| Stream-boundary and content matrix | 4 | 4 | Cover absent and false `Content-Length`, streamed overflow, mismatched length, invalid/negative length, invalid UTF-8 text, invalid PDF signature, empty chunks, and multiple-source cumulative limits. |
| Deadline and transport interruption matrix | 4 | 3 | Deterministic clocks exercise source and package deadlines before request and mid-stream; connect/read timeout and non-timeout transport failure retain no final or partial output. |
| Publication and cleanup failure matrix | 3 | 3 | Pre-existing output, `.download` collision, final rename failure, and cleanup failure return stable behavior without deleting unrelated paths. |
| Refusal registry/document parity | 3 | 4 | Every registered code is documented exactly once and every documented code exists in the runtime registry. |
| Complete public CLI command matrix | 3 | 3 | All product-term commands and Phase 7 lineage verification assert success/refusal exit status, stdout/stderr ownership, overwrite behavior, and deterministic JSON shape. |
| Additional interval edges | 3 | 4 | Open-ended revisions, a successor after an open-ended revision, exact start/end boundary captures, multiple markets, and unsorted cross-market entries have named expectations. |
| Complete embedded-lineage field mutation matrix | 4 | 3 | Every repeated product identity, effective-time, limitation, upstream hash, and policy field in V2/V3 artifacts has a single-defect refusal case. |
| Crash residue recovery | 3 | 2 | If scavenging is added, tests distinguish owned stale partials from active or unrelated directories and prove idempotent cleanup. |

The current tests are still valuable: 18 focused tests cover the principal positive path and the
highest-risk failure families without live network calls. The concern is matrix breadth, not the
absence of negative testing.

### Missing documentation

| Gap | Impact | Ease | Needed addition |
|---|---:|---:|---|
| Acquisition policy evolution is not specified. | 4 | 3 | State whether V2 limits and role/media rules are frozen, how tool versions map to policy, and how old manifests remain verifiable after a policy change. |
| Reviewer governance and incident handling remain undefined. | 4 | 2 | Name reviewer responsibilities, independence expectations, revocation/supersession records, and how dependent results are warned without erasing history. |
| No field-level evidence-anchor format or reviewer example exists. | 4 | 2 | Show how a product field cites a retained JSON pointer, Markdown section, or PDF page/section and how that anchor is reviewed. |
| The operator guide is not yet a complete second-product walkthrough. | 3 | 3 | Add a real fetch → inspect → build → diff → review → catalog → normalize walkthrough, including retry and refusal recovery, during B1b-2. |
| Schema/runtime parity has no field-by-field coverage inventory. | 3 | 4 | Document which rules are schema-addressable and which require cross-file, arithmetic, canonical-byte, or filesystem runtime checks. |
| Crash atomicity wording could be more operationally explicit. | 3 | 5 | State that normal failure cleanup and final atomic rename do not promise survival without residue across SIGKILL or power loss. |
| Limit and timeout rationale is recorded as policy, not as measured evidence. | 2 | 3 | Record observed source sizes and acquisition timings from B1b-2 before changing defaults. |

### Possible optimizations

| Optimization | Impact | Ease | Recommendation |
|---|---:|---:|---|
| Cache a verified immutable package within one command. | 2 | 4 | Add only after profiling repeated loads; key the cache by all relevant file identities and never persist it across mutations. |
| Index catalog entries by market and binary-search intervals. | 2 | 4 | Linear lookup is clearer at one package. Add an index when catalog scale makes verification or selection measurable. |
| Reuse one typed lineage serializer/verifier. | 3 | 3 | This is the highest-value near-term code simplification because it reduces omission risk without changing artifact formats. |
| Convert repetitive negative cases to data-driven fixture builders. | 2 | 4 | Do this as the missing matrices grow so each test names one defect and cleanup expectation. |
| Use bounded concurrent acquisition. | 2 | 2 | Defer until batch latency matters. Preserve deterministic manifest ordering, package deadlines, bounded aggregate resources, and all-or-nothing publication. |
| Avoid reparsing small JSON sources after streaming. | 1 | 3 | The 2 MiB cap makes this immaterial. Prefer clarity unless profiling proves otherwise. |

### Future scalability concerns

| Concern | Impact | Ease | Scaling failure mode and direction |
|---|---:|---:|---|
| Manual review is one package at a time. | 5 | 1 | Frequent changes can become a bottleneck or rubber stamp. Automate source diffs and projections, then keep risk-ranked human approval for semantic/legal fields. |
| Product projection and acquisition roles are Kalshi-specific. | 4 | 1 | More venues or genuinely different product families will accumulate conditionals. Use B1b-2 to prove a versioned adapter boundary before refactoring. |
| V3 lineage is single-product per run. | 4 | 1 | B2 multi-market replay needs an ordered product/revision set with capture-specific effective selection. Design a versioned successor instead of overloading scalar V3 fields. |
| Every normalized dataset copies the reviewed source package. | 3 | 2 | Large linked PDFs multiply storage. Measure real duplication first, then consider content-addressed storage with self-contained export/materialization. |
| Catalog verification reloads and rehashes packages. | 3 | 3 | Startup cost grows with revisions and document bytes. Use immutable in-process caching and a market index after measurement. |
| Acquisition is synchronous and restarts the whole unpublished package after failure. | 2 | 2 | Large batches will be slow. Bounded concurrency or resumable staging needs a stronger ownership protocol and must not weaken atomic publication. |
| Full-file hashing scales linearly with retained evidence and result size. | 3 | 2 | Verification cost will rise with corpora. Merkle manifests or content-addressed blobs are later options only after profiles show the simple design is inadequate. |

### Ranked recommendation

| Priority | Next action | Impact | Ease | Reason |
|---:|---|---:|---:|---|
| P0 | Complete B1b-2 with contemporaneous linked documents and a genuinely different second product. | 5 | 1 | This tests the hardened boundary against real evidence and reveals the correct adapter and policy abstractions. |
| P1 | Define reviewer identity, field-level evidence anchors, revocation, and supersession. | 4 | 2 | Governance and semantic interpretation are now the largest integrity gaps. |
| P2 | Freeze or explicitly version acquisition policy semantics. | 4 | 3 | Old source-manifest V2 acceptance must not drift when constants change. |
| P3 | Expand acquisition, schema-parity, CLI, interval-edge, and embedded-lineage mutation matrices. | 4 | 3 | Current tests cover the major families but not every boundary or repeated field. |
| P4 | Introduce a shared typed lineage record and split the module only after the second product proves the seams. | 3 | 2 | This reduces complexity without designing abstractions around one example. |
| P5 | Add caching, indexing, concurrent acquisition, or content-addressed storage only after measurement. | 2–3 | 2–4 | These are credible scale pressures, but none is the present bottleneck. |

The recommendation is to preserve the current exact-equality, first-party, bounded-streaming,
handwritten-schema, and exact-reproduction defaults. B1b-2 should supply missing real evidence;
governance and policy-versioning should follow before accounting or settlement relies on these
terms. Refactoring and performance work should remain measurement-driven.

None of the findings permits fee charging, settlement processing, accounting, calibrated fills,
multi-market replay, paper/live behavior, ML, or readiness/profitability claims.
