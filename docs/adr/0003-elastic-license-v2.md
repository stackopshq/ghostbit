# ADR-0003: Elastic License 2.0

## Status

Accepted, 2026-08-31.

## Context

The Ghost suite is sold, not given away. The commercial position rests on two
things that have to hold at the same time:

- **The code is public and auditable.** Every product in the suite sells
  zero-knowledge. A claim about what a server cannot decrypt is worth nothing
  unless the reader can go and check it, and unless they can run the thing
  themselves. Closing the source would take the central argument away.
- **Reselling is StackOps' business.** A competitor who takes the source and
  operates it as a paid hosted service captures the revenue without carrying
  the development. Under a permissive or a copyleft licence alike, that is
  entirely lawful.

Neither MIT nor AGPL-3.0-or-later separates those two. MIT permits the hosted
resale outright. AGPL obliges a competing operator to publish their
modifications, which is a disclosure duty, not a limit on resale: an operator
who publishes their diff is in full compliance while competing with us on our
own code.

## Decision

The product is licensed under the **Elastic License 2.0** (`Elastic-2.0`),
effective 2026-08-31.

ELv2 grants use, copying, distribution and derivative works, and adds three
limitations. Only the first one matters here: you may not provide the software
to third parties as a hosted or managed service. Reading, auditing,
self-hosting, modifying, and running it for your own organisation's staff all
remain permitted; operating it for someone else's account does not.

The other two limitations are inert in this product: there is no licence-key
mechanism to circumvent, and the notice-preservation clause restates what any
licence requires.

## What this is not

**ELv2 is not an open source licence** as the OSI defines the term, because it
restricts a field of use. The accurate term is *source available*. Wherever
this repository claims to be open source, that wording is now wrong and should
be revisited as a communications decision, separately from this record.

## Consequences

- Anyone may read, audit, self-host, fork and modify the software, including
  commercially, for their own use.
- Offering it to third parties as a hosted or managed service requires a
  separate agreement with StackOps.
- The software is no longer eligible for distribution channels that require an
  OSI-approved licence, and packaging ecosystems that filter on that will
  reject it.
- Incoming contributions are accepted under ELv2.

## Non-retroactivity

A licence already granted cannot be withdrawn. Every copy obtained before
2026-08-31 keeps the licence it was obtained under, permanently, and so does
every release built from a commit that predates this decision. This change
binds the future only. `NOTICE` records the same statement inside the
distribution, where a recipient will actually find it.

## Alternatives considered

- **Keep the current licence.** Rejected: it leaves hosted resale open, which
  is the one thing the business needs to reserve.
- **Close the source.** Rejected: the zero-knowledge claim is unverifiable
  without published code, and self-hosting is an announced feature.
- **BUSL 1.1.** Rejected: its change-date mechanism converts the code to an
  open source licence after a fixed delay, which reopens hosted resale on a
  timer, and its parameters have to be chosen and defended per repository.
- **SSPL.** Rejected: it reaches far beyond the software into the whole
  service stack, which is a heavier imposition on an honest self-hoster than
  the problem warrants.
