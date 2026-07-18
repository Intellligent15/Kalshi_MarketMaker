# Phase 7 Segment-Aware Features Explained

## The short version

Normalization V3 is one interleaved record stream. B2b-1 reads that stream once but never owns one
shared book. It routes each record to the cursor for that record's ticker, and every cursor owns
only the state that an observed snapshot established for its current segment.

## Why two watermarks are not enough

Raw ingress answers what the capture received and in which global order. Normalization ordinal
answers where a record sits after normalization adds segment and discontinuity records. Multiple
normalized records can share one raw ordinal, so both values are needed. A third, product-local
applied watermark prevents an unrelated market event from looking like product state advancement.

The snapshot boundary is the seed position. The snapshot event immediately after it is the valid-
from position. This distinction lets later consumers state exactly when book values became usable.

## Why last trade resets

A trade can be genuinely observed while displayed book continuity is invalid. Keeping that trade
does not justify keeping the old book. B2b-1 therefore refuses to turn the trade into continuity,
emits no valid-book row while invalid, and resets segment-local last trade before a recovery
snapshot starts a later segment.

## Why complete-only publication

The V3 normalization format can represent discontinuity honestly. A feature artifact that spans a
missing interval needs additional downstream eligibility and interpretation rules. B2b-1 chooses
the smaller safe boundary: implement the cursor invalidation rules now, but publish only when the
normalization manifest and the complete record scan both prove a complete observed interval.

## Why cross-market features wait

An interleaved input order shows which records were globally visible; it does not automatically
define a valid latest-value join. Cross-market features still need explicit staleness, missing-
market, segment-alignment, and causal-watermark rules. Each B2b-1 row therefore belongs to one
product only.
