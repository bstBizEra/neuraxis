# 0003 — Two principal comparisons with opposite folding rules

**Status:** Accepted · **Date:** 2026-09-14 · **Supersedes:** a single fold used everywhere

## Context

Principal names are compared in several places, and Unicode makes "the same
name" ambiguous. `agent-cortex`, `Agent-Cortex`, `agent-cörtex` and
`ａｇｅｎｔ－ｃｏｒｔｅｘ` are four strings that a human reads as one identity
and a naive comparison reads as four.

The package originally had one normalisation: NFKC, drop the invisible
categories, casefold, decompose, drop combining marks. Aggressive on purpose,
and justified in its own docstring — *a collision here produces a denial, so
folding too hard only ever denies more*.

Two adversarial reviews found the same bug twice, one release apart: the
function was reused where a collision **authorises**. `agent-cörtex` could use
`agent-cortex`'s envelope, because folding the two together widened a grant to
a principal the envelope never named. The safety argument was correct and had
been carried one context too far.

## Decision

Two functions, chosen at every call site by one question: **does a collision
here deny, or authorise?**

| | `normalise_principal` | `strict_principal` |
|---|---|---|
| Fold | NFKC, drop Cf/Cc/Cs/Co/Cn, casefold, NFD, drop Mn | NFC and whitespace only; `""` for a name carrying invisibles |
| Use where | a match **denies** | a match **authorises** |
| Callers | verifier independence, self-waiver ban, envelope self-signing, `Envelope.may_bind` | `Envelope.bounds`, the signer allowlist |

NFC rather than NFKC on the strict side, because a test showed fullwidth
`ａｇｅｎｔ－ｃｏｒｔｅｘ` still collapsing into `agent-cortex` under NFKC.

`Envelope.bounds()` and `Envelope.may_bind()` are two methods rather than one
with a flag, and a test asserts they disagree exactly where intended.

## Consequences

Every new comparison must state which it is, in a comment, at the call site.
That is deliberate friction: the failure mode is not writing the wrong
comparison, it is reusing the right one somewhere else.

The class generalises past names. The threat model calls it *a correct argument
applied one context too far*, and all four critical findings across two reviews
were instances of it — including a prefix match made safe against
`lessons-archive` and left unsafe against `lessons/../../kernel`, because the
fix addressed the example rather than the class.

## Reversal

A third context appears where neither fold is right. Add a third function; do
not add a flag to one of these.
