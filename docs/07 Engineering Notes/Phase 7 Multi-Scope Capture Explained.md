# Phase 7 Multi-Scope Capture Explained

## The problem in plain language

The old recorder kept enough raw evidence to show that a connection ended and another began, but
the normalizer threw those lifecycle records away. If a new connection delivered a delta, a later
consumer could apply it to the old book as if nothing had been missed.

B2a makes the missing interval impossible to hide.

## Three identities that must not be collapsed

A subscription request is the client's command. An acknowledgement is the venue's response and
assigns a channel SID. A sequence value belongs to some venue-defined stream, but the retained
evidence does not establish exactly how broad that stream is.

The successor records all three. It calls the sequence domain unknown rather than using one
successful capture to invent a venue-wide rule.

## Why ingress order wins

Two market streams may have different sequences and timestamps. Sorting them by timestamp would
create a causal ordering that the source does not prove. The only directly observed total order is
the order in which the single recorder received and wrote the frames.

Each raw row therefore receives an ordinal. Normalization keeps that order, uses source time as an
attribute, clamps logical time monotonically, and marks late events without moving them.

## What a reconnect snapshot does

Suppose the book is valid, the socket disconnects, and a later socket supplies a snapshot. The
snapshot tells us the published book at that later point. It does not tell us what happened during
the gap.

B2a therefore produces two valid observed segments separated by an explicit discontinuity. The
second is valid from its snapshot onward. The combined capture is observed but discontinuous—not
recovered continuous history.

If the snapshot never arrives, deltas are still retained as source messages, but they cannot update
a supported book. Default normalization refuses; record mode preserves the incomplete evidence for
audit.

## Why control records are in the main stream

A separate gap file would be easy for a consumer to forget. `records.jsonl` is instead a versioned
union: market event, discontinuity, or segment boundary. A reader cannot claim support for the new
format while parsing only market events.

Legacy consumers remain safe because their `events.jsonl` and manifest schemas are unchanged.

## Product and truth lineage

Product-map V3 holds one ordered entry per ticker. When reviewed terms are supplied, every entry has
its own exact terms, source, review, and conversion-policy hashes. Existing product maps are not
rewritten.

Real frames remain `Observed`, test captures remain `Synthetic`, and continuity conclusions are
`Reconstructed`. Nothing in B2a changes Level-2 into queue or execution truth.

## What comes next

B2b may build one projection per product and segment, propagate incomplete intervals into features,
and integrate deterministic multi-market replay. Until that work exists, feature generation rejects
normalization V3 before it can silently consume the wrong state.
