# ADR-011: Bracketed product evidence and review responsibility

- Status: Accepted
- Date: 2026-07-17
- Scope: Phase 7 Track B1b-2

## Context

B1b-1 made acquisition bounded and observable, but source-manifest V2 still identified its
policy only through code constants and a tool-version string. Review V1 bound hashes without
naming the human responsibility boundary. A single acquisition also could not honestly support
both endpoints of a contemporaneous effective interval, and product fields derived from Markdown
or PDF sources had no page or section anchors.

The first proposed second product, `KXHMONTH-26JUL`, exposed one additional real schema boundary:
its official market record contains an empty `rules_secondary` string. Product-terms V1 requires
that field to be non-empty. Inventing disclaimer text or weakening V1 would change historical
semantics.

## Decision

Use two complete, immutable first-party acquisitions around a short evidence interval. The exact
half-open interval is:

```text
[opening acquisition completed_at_utc, closing acquisition started_at_utc)
```

Both observations must have identical source membership, roles, requested URLs, and media types.
Static Markdown and PDF sources must be byte-identical. Every market-specific projected JSON
field must agree with the reviewed terms at both endpoints.

Add these versioned formats:

- `pmm.product_acquisition_policy.v1` fixes the allowed hosts, roles, media, byte limits,
  redirects, timeouts, streaming, and package limits by canonical hash;
- `pmm.product_acquisition_spec.v2` names that policy and one `opening` or `closing` observation;
- `pmm.product_terms_source_manifest.v3` preserves one or two observation summaries, tags every
  source with its observation, and binds the policy hash;
- `pmm.product_evidence_map.v1` maps product-term JSON pointers to retained JSON, Markdown, or PDF
  anchors at both endpoints;
- `pmm.product_terms_review.v2` names a repository-declared reviewer, responsibilities, accepted
  checklist, policy hash, evidence-map hash, source hash, terms hash, limitations, and interval;
  and
- `pmm.venue_product_terms.v2` differs from V1 only by permitting an official empty secondary
  rule. V1 remains non-empty and unchanged.

Review identity is a repository declaration supported by version-control history. It is not a
signature, independent institutional approval, or organizational control.

Catalog V1, conversion-policy V1, normalization/product-map V2, feature V2, and backtest/result V3
remain sufficient because they bind the complete package through exact source, terms, review, and
copied-package identities.

## Compatibility

Source-manifest V1 remains retrospective compatibility evidence. Source-manifest V2 remains bound
to the frozen `product-acquisition.v2` interpretation; future policy changes must not make its
verification consult a changed V3 policy. Product-terms V1 retains its non-empty-secondary rule.
The original reviewed package and all existing normalized, feature, configuration, result, and
risk artifacts keep their bytes and meaning.

Exact reproduction compatibility remains deliberately strict. A changed source, policy, evidence
map, review, or terms hash creates a different research identity even if a later reporting layer
might judge economic terms equivalent.

## Evidence and limitations

The reviewed HMONTH package brackets `2026-07-17T15:07:16.002543Z` through
`2026-07-17T15:08:37.512205Z`. All eight official sources were byte-identical across opening and
closing observations. The package retains the market, event metadata, series, fixed-point, fee,
settlement, contract-terms, and certification bytes.

The bracket does not prove that a mutable public endpoint could not change transiently between
observations. No observed Level-2 capture was made inside this short interval; downstream tests
use explicitly synthetic captures. NCEI is retained only as the settlement-source identity
projected by official Kalshi records. Fees and settlement remain unsupported and unapplied.

## Non-goals

This decision does not add fee charging, accounting, collateral, margin, settlement processing,
PnL, calibrated fills, queue assumptions, multi-market replay, reconnect recovery, paper/live
behavior, ML, new core numeric types, or readiness/profitability claims.
