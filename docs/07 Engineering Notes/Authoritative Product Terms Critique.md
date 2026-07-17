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

This section records the critique current after commits `dbd6fd8` and `6d489e3`. The B1a tables
above and B1b-1 recommendations below are retained as chronological evidence; later B1b-2 work
closed several of them. The B1b-2 section at the end is authoritative for current product-term
debt. The same 1-to-5 impact scale applies. Ease remains 1 for a large or evidence-heavy change and
5 for a small bounded change.

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

## B1b-2 post-implementation critique

### Scope and current evidence

This is the current critique of commits `b3da27e`, `b28a3ad`, `4ba99a6`, and `ff9dbe6`. It reviews
the code and checked-in HMONTH package, not the design proposal. The validated closeout baseline is
78 CTest tests, 81 Python tests, and 22 focused product-term tests.

B1b-2 is a meaningful improvement. It demonstrates that the boundary can represent a climate
product rather than another sports ticker, retain the linked contract and certification documents,
bind acquisition policy by immutable identity, bracket an interval with two complete acquisitions,
and preserve old V1 artifacts. The decision to add product-terms V2 when the real source contained
an empty secondary-rule value was especially sound: evidence changed the schema instead of the
schema distorting the evidence.

The strongest guarantees remain exact bytes, hashes, selected JSON projections, interval equality,
and offline lineage. The weakest guarantees are legal-document semantics, completeness as a generic
runtime rule, review governance, and scale. The following tables use the repository-wide impact
scale defined at the top of this document. Ease remains 1 for a large or evidence-heavy change and
5 for a small bounded change.

### Unnecessary complexity

| Finding | Impact | Ease | Evidence and tradeoff | Recommendation |
|---|---:|---:|---|---|
| `pmm_product_terms.py` is now 2,284 lines and owns transport, policy, three manifest versions, two terms versions, two review versions, evidence anchors, catalog, conversion, compatibility, copying, and CLI dispatch. | 4 | 2 | Keeping one audit surface helped B1a, but B1b-2 proved real seams. A change to PDF review should not risk acquisition or catalog selection. | Before B2 implementation, make a behavior-preserving split into canonical/errors, acquisition, package/evidence, Kalshi projection, catalog/lineage, and CLI modules. Keep one public refusal registry. |
| Schema and runtime validation are parallel handwritten systems, while several new schemas intentionally use generic nested objects. | 4 | 2 | Runtime is stricter than `source-manifest-v3` redirect/header shapes and much stricter than evidence-map anchor objects or acquisition-policy role policies. “Schema valid” therefore does not mean “runtime valid.” | Make runtime acceptance normative and add a shared positive/one-defect parity corpus. Tighten the schemas or generate only the structural portions from shared typed definitions. |
| The immutable policy repeats values that remain global Python constants, and acquisition executes through those constants rather than through a policy object. | 3 | 3 | Exact hash and payload checks make the current policy safe, but a successor requires coordinated changes in the artifact, constants, loader, fetcher, and tests. | Pass a validated policy object into URL, redirect, media, size, chunk, and timeout enforcement. Preserve a frozen adapter for legacy V2. |
| Opening and closing observations duplicate static Markdown/PDF bytes and duplicate most anchor declarations. | 2 | 2 | The repetition makes endpoint evidence self-contained and auditable, but it is verbose and already produces a 484 KiB package from roughly half that unique content. | Keep the simple layout until several packages establish measured cost; then consider hash-addressed shared bytes with a deterministic self-contained export. |
| Version behavior is increasingly expressed through conditionals inside common loaders. | 3 | 2 | V1/V2/V3 compatibility is correct today, but another venue or V4 can turn local branches into a combinatorial validation matrix. | Dispatch once by schema to version-specific parsers that return a common immutable internal view. Do not weaken old semantics to reduce branch count. |

### Future technical debt and correctness risks

| Finding | Impact | Ease | Evidence and risk | Recommendation |
|---|---:|---:|---|---|
| PDF locators are not mechanically resolved. | 5 | 3 | Runtime checks `%PDF-`, a positive page number, and a nonempty section string. It does not prove the page exists or that the section occurs on that page. The locator is currently a hash-bound human review address, not machine verification. | Extract text with a pinned offline tool or library, verify page bounds and a stable section fingerprint, and retain extraction-tool identity. Until then, document PDF support as human-reviewed only. |
| V3 does not require a complete semantic role set. | 5 | 4 | The HMONTH package has all eight required roles, but generic runtime only requires a nonempty source list, matching membership across endpoints, and whatever anchors/term projection happen to reference. A future review could omit a contract or certification document and still pass if its payload is internally consistent. | Put the required-role profile in the immutable acquisition policy and require exact or explicitly optional role coverage before assembly and review. Add missing-role tests for every required role. |
| Evidence-map coverage is selective, not leaf-complete. | 4 | 3 | HMONTH has 30 term pointers, but fields such as payout bounds/contingency, price and quantity representation metadata, several fee/settlement status fields, `source_refs`, venue/environment, and revision label do not each have anchors. Some remain protected by other runtime checks, but the map alone is not a complete field ledger. | Define which fields require direct anchors, which are local policy/constants, and which are derived. Enforce that coverage profile mechanically. |
| Markdown anchors use substring presence rather than heading structure or section boundaries. | 3 | 4 | A heading phrase in body text can satisfy the check, and the claimed section contents are not fingerprinted. | Parse Markdown headings deterministically and optionally bind a normalized section hash. Keep quoted prose out of control documents unless copyright and stability are handled. |
| The temporal bracket proves two endpoint observations, not continuous immutability. | 4 | 2 | A mutable JSON endpoint could change and revert during the 81-second gap. Static sources were byte-equal, but no event history proves absence of an intermediate change. | Keep the narrow claim. Use shorter brackets, more observations, or an official event/history feed only when a later use requires stronger temporal evidence. |
| Review V2 records identity and responsibility but has no append-only supersession/revocation model. | 4 | 2 | Git history shows who committed bytes, but runtime cannot say that a once-reviewed package was later withdrawn or superseded, nor warn existing results. | Design versioned append-only governance records only when a real review workflow exists; do not imply signatures or institutional approval. |
| Observation assembly flattens each retained path to its basename. | 4 | 4 | Two distinct source paths in one observation can share a basename. Assembly would target the same destination and can overwrite before final verification, despite unique original paths. The current package happens to use unique basenames. | Preserve the full safe relative path below each observation or reject duplicate destination paths before copying. Add a collision and cleanup test. |
| Legacy source-manifest V2 still derives policy semantics from frozen code constants. | 4 | 3 | V3 has an explicit hash; V2 does not. Changing host, role, media, byte, redirect, or timeout constants in place could reinterpret an old V2 package. | Freeze legacy constants behind a named V2 adapter and regression fixture. Any changed policy must use a new policy identity and, where semantics change, a successor schema. |
| Kalshi projection still depends on venue-specific response shapes and source-role conventions inside the generic loader. | 3 | 2 | A third product family may work, but a second venue or non-binary product will add conditionals around assumptions that are currently implicit. | Introduce an explicit, versioned projection-adapter identity after B2 requirements are known. Keep product-terms V1/V2 frozen. |
| No observed market-data capture falls inside the short HMONTH evidence interval. | 3 | 1 | Synthetic captures prove selection and lineage mechanics, not that an actual HMONTH recording was normalized under contemporaneous terms. | Treat this as an evidence limitation, not a code failure. Acquire a real capture only in a separately approved observed-data package. |

### Missing tests

| Missing test | Impact | Ease | Acceptance condition |
|---|---:|---:|---|
| PDF page/section mutation and nonexistent-page cases | 5 | 3 | A wrong page, absent section, replaced PDF, or changed extraction identity refuses with `EvidenceAnchorMismatch`. |
| Exact required-role completeness for V3 | 5 | 4 | Removing each contract, certification, fee, settlement, JSON, or representation role causes `EvidenceIncomplete`, even after all reachable hashes are recomputed. |
| New-schema/runtime negative parity matrix | 4 | 3 | Acquisition-policy V1, acquisition-spec V2, source-manifest V3, evidence-map V1, terms V2, and review V2 share named positive and one-defect negatives across schema and runtime. |
| Markdown structural anchor mutations | 3 | 4 | Body-text lookalikes, missing headings, duplicate headings, and changed section text have explicit behavior. |
| Assembly destination collision and interruption cleanup | 4 | 4 | Same-basename inputs, copy interruption, stale partial directories, and destination reuse refuse without a final or ambiguous partial package. |
| Policy-field mutation and legacy V2 immutability | 4 | 3 | Each role/media/byte/redirect/timeout policy mutation either selects a supported new identity or refuses; an old V2 fixture verifies identically before and after new-policy support. |
| Review V2 governance mutation matrix | 4 | 4 | Missing/duplicate responsibilities, duplicate checklist items, unaccepted status, wrong identity kind, stale evidence/policy hashes, and endpoint disagreement each produce the intended code. |
| HMONTH through complete V3 configuration and result artifacts | 4 | 3 | The second product reaches configuration, result manifest, orders, fills, ledger, and risk trace entirely offline; each single mutation refuses. Current HMONTH coverage stops after normalization/feature lineage while the older market covers the full V3 chain. |
| New public CLI command matrix | 3 | 4 | `assemble-observations`, `build-evidence`, V2 `build`, and V2 `review` have subprocess success/refusal, exit 2, empty stdout, stderr code, overwrite, and cleanup tests. |
| Endpoint-specific source and anchor mutations | 4 | 4 | Opening-only and closing-only JSON, Markdown, PDF, source hash, observation ID, and acquisition-time changes cannot be hidden by recomputing outer hashes. |
| Repeated HMONTH offline verification byte identity | 3 | 5 | Package, catalog, normalization, features, and any V3 result verify repeatedly without modifying files or producing nondeterministic output. |

### Missing documentation

| Gap | Impact | Ease | Needed documentation |
|---|---:|---:|---|
| No pinned extraction semantics or operator procedure exists for stronger document anchors. | 5 | 3 | The companion explanation now states the current narrow guarantee. B1c must document the chosen PDF extraction identity, page/section fingerprint rules, Markdown section normalization, and manual fallback before runtime claims become stronger. |
| No complete two-observation operator walkthrough exists. | 4 | 4 | Show acquisition-spec V2 creation, opening fetch, closing fetch, assembly, terms V2 build, evidence-map build, review V2, package inspection, catalog addition, and offline verification, including failure recovery. |
| Required versus optional source roles are not defined as a reusable profile. | 4 | 3 | Document the exact completeness profile, why each role is required, and what a future product may explicitly mark not applicable. Runtime should ultimately own the same profile. |
| Policy evolution is described conceptually but lacks a compatibility playbook. | 4 | 3 | Explain when a new policy hash is enough, when a schema successor is required, how V2 remains frozen, and how old packages/results are verified after runtime upgrades. |
| Review supersession/revocation has no incident procedure. | 4 | 2 | Define append-only withdrawal/supersession semantics and dependent-result warnings only after the actual governance owner and approval process exist. |
| Evidence-map coverage classes are not enumerated. | 3 | 4 | List mechanically projected, human-reviewed, local-policy, derived, and unsupported fields so “anchored” is not mistaken for “all semantics machine-proven.” |
| No external known-answer verifier example exists for the new formats. | 2 | 3 | Provide language-neutral canonical bytes and expected hashes for policy, V3 manifest, evidence map, terms V2, and review V2. |
| Crash-only recovery and stale partial-directory handling are undocumented. | 2 | 3 | Explain ordinary exception cleanup versus process kill/power loss, operator inspection, and safe retry with a new immutable output path. |

### Possible optimizations

| Optimization | Impact | Ease | When and how |
|---|---:|---:|---|
| Split the 2,284-line module along proven boundaries. | 4 | 2 | Do as a behavior-preserving package before B2 implementation, with import/API/refusal compatibility tests. This is maintainability work, not a redesign. |
| Cache verified immutable packages and source hashes within one process. | 2 | 4 | Add only after profiling repeated catalog/normalization loads. Key by complete control-file identity and never trust path alone. |
| Index catalog entries by market and interval. | 2 | 4 | Linear selection is clearest for two entries. Add a deterministic index before hundreds of revisions. |
| Reuse identical endpoint document bytes by content hash. | 2 | 2 | The first measured package is only 484 KiB. Defer until storage or transfer profiles justify the complexity, and preserve self-contained export. |
| Add bounded concurrent source acquisition. | 2 | 2 | Useful for large batches, but it must preserve aggregate limits, deterministic manifest ordering, timeout semantics, and atomic publication. |
| Parse each retained JSON source once per verification pass. | 2 | 4 | A small in-memory cache can remove repeated reads while remaining bounded by the 2 MiB role limit. Profile first. |
| Share typed definitions for schema-addressable structure. | 3 | 2 | Use after the negative parity corpus exists. Do not generate away cross-file, hash, arithmetic, URL, or filesystem rules that JSON Schema cannot express. |

### Future scalability concerns

| Concern | Impact | Ease | Scaling failure mode and direction |
|---|---:|---:|---|
| Manual semantic review is one package at a time. | 5 | 1 | Frequent revisions become a bottleneck or rubber stamp. Automate diffs and projections while retaining risk-ranked human review for legal meaning. |
| V3 lineage is scalar and single-product. | 5 | 1 | B2 multi-market replay needs an ordered set of selected product revisions and unambiguous per-event binding. Design a successor; do not overload scalar fields. |
| Complete evidence is copied into every endpoint and normalized dataset. | 4 | 2 | Many markets/revisions can multiply shared series documents and PDFs. Measure first, then consider content-addressed storage plus deterministic materialization. |
| Verification rehashes every package and large result artifact. | 3 | 3 | Startup and audit time grow linearly with catalog and corpus size. Use immutable in-process caches, indexes, or tree manifests only after profiles justify them. |
| Kalshi-specific acquisition and projection assumptions do not form a venue adapter contract. | 4 | 1 | More venues or non-binary products create nested version and venue conditionals. Introduce versioned adapters from real evidence rather than a universal schema. |
| Review identity does not scale into team governance. | 4 | 1 | Repository strings cannot express independent approval, delegation, revocation, or responsibility changes. Define the real human process before encoding it. |
| Synchronous all-or-nothing acquisition restarts after any source failure. | 3 | 2 | Large evidence sets are slow and fragile. Bounded concurrency or resumable staging needs explicit ownership and cannot weaken final atomicity. |
| Temporal confidence does not automatically improve with catalog size. | 4 | 1 | Thousands of short two-point brackets still do not prove continuous source history. Match acquisition frequency and evidence strength to the claims each research use requires. |

### Ranked recommendation

| Priority | Next action | Impact | Ease | Why |
|---:|---|---:|---:|---|
| P0 | Make document-anchor and source-completeness guarantees true in runtime and tests. | 5 | 3 | These are the two places where documentation can currently be read more strongly than code. |
| P1 | Add the V3/V2 schema-runtime, policy, assembly, review, and CLI negative matrices. | 4 | 3 | The happy path is strong; successor-format refusal evidence is still too narrow. |
| P2 | Define an honest policy-evolution and append-only review-governance boundary. | 4 | 2 | Old evidence must remain interpretable, and bad reviews eventually need explicit historical handling. |
| P3 | Split `pmm_product_terms.py` without changing behavior before B2 implementation. | 4 | 2 | B1b-2 has now proved the seams; B2 would otherwise deepen coupling. |
| P4 | Prove the HMONTH package through the complete V3 result chain when a suitable approved capture/fixture exists. | 4 | 3 | This closes the gap between second-product metadata selection and complete second-product research lineage. |
| P5 | Design B2 multi-product lineage and recovery separately. | 5 | 1 | A two-market catalog is not multi-market replay; B2 needs a versioned ordered product set and observed-data recovery rules. |
| P6 | Optimize hashing, indexing, concurrency, or storage only after measurement. | 2–3 | 2–4 | The current evidence volume does not justify content-addressed or distributed complexity. |

The recommended immediate package is P0: tighten document-anchor truth and generic source
completeness before B2 builds on this boundary. This does not reopen the reviewed HMONTH package;
it strengthens what future packages must prove. None of these findings authorizes fees, accounting,
settlement processing, calibrated fills, multi-market replay, paper/live behavior, ML, or any
readiness/profitability claim.
