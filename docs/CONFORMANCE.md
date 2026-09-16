# Attestation source conformance

**For:** anyone writing a source that Neuraxis will accept attestations from —
the external assurance account's GV-08 probe, L0's lease audit, BADF's gate-log
export, or any provider written outside this repository.

**Run it:**

```bash
neuraxis conform --control GV-08 -- python my_probe.py
#  exit 0  conforms
#  exit 10 does not conform — do not accept attestations from it
#  exit 2  the suite could not run
```

---

## 1. Why this exists

The four provider rules — fail closed, positive control, no vacuous probe, emit
an evidence reference — have been enforced since v0.3, by a harness that only
in-repo providers pass through. The controls that matter most will not be
written here: **GV-01, GV-03 and GV-08 are attested by the external assurance
account**, GV-02 and GV-06 by L0, GV-07 by BADF.

Until now there was no way for any of them to demonstrate conformance before
being trusted. That is how a programme ends up having trusted an attestation
source nobody tested — and an attestation source that does not work is worse
than one that is missing, because a missing one leaves the band closed while a
broken one reports it open.

It is a black box on purpose. The assurance account should not have to write
Python to show its probe is honest.

---

## 2. The contract

A source is an **executable**. It reads one JSON object on stdin and writes one
JSON attestation to stdout.

**In:**

```json
{"control": "GV-08", "scenario": "live"}
```

**Out:**

```json
{
  "control":      "GV-08",
  "result":       true,
  "issued_at":    "2026-09-16T09:00:00+00:00",
  "issuer":       "assurance-account/probe",
  "evidence_ref": "https://ci.example/run/1234#step-7",
  "provenance":   "provider"
}
```

| Field | Requirement |
|---|---|
| `control` | must equal the control the source was asked about |
| `result` | a **JSON boolean**. Not `"true"` — a non-empty string is truthy, so a source could report a pass by spelling it |
| `issued_at` | ISO-8601 **with a timezone**. A naive timestamp is judged fresh or stale in whatever zone the reader happens to be in |
| `issuer` | who ran the check |
| `evidence_ref` | somewhere an auditor can look. `"pass"`, `"ok"`, `"n/a"` and friends are rejected: they satisfy the letter of rule 4 and none of it |
| `provenance` | `provider` for a result a check established, `manual` for one a human asserted |

The **exit code is advisory**. The attestation is the answer. Neuraxis converts
a crash into FAIL, which is why crashing conforms — but a source that says FAIL
is better than one that says nothing, and the suite says so.

---

## 3. The four scenarios

Your source must behave differently for each. **You implement them**, because
only you know what "broken" means for your check.

### `live` — run normally

The output must parse, name the right control, carry a timezone, and carry a
real evidence reference. This is where rule 4 is judged.

### `broken` — run with something you depend on unavailable

**Must not report PASS.** Rule 1.

The failure this catches is a probe that treats *absence of evidence* as
*evidence of absence*: the directory is unreachable, so nobody was denied, so
everything is fine. Report FAIL.

### `negative` — run against a condition you must reject

**Must report FAIL.** Rule 2.

A source that cannot fail is not a check. Point the probe at something it
should refuse and confirm it does. This is the positive control, and it is the
rule most often missing from checks that have quietly died.

### `powerless` — run as an identity with no authority

**Must not report PASS if `live` passed.** Rule 3.

Required only when the control is declared `kind: probe`. A check that returns
the same answer for a powerful and a powerless identity is not checking
authority; it is checking that the machine is switched on.

---

## 4. The kind comes from the registry, not from you

```yaml
GV-01: { name: identity,  attestation: kbs-001/probe,  max_age: 24h, kind: probe }
GV-07: { name: ratification, attestation: badf/gate-log, max_age: 7d, kind: audit }
```

An `audit` of a log legitimately answers the same whoever asks, so it is not
asked the vacuity scenario. A `probe` is.

**Your source does not get to say which it is.** A source that could declare its
own kind could declare its way out of the vacuity check, which is the single
finding class this package has rediscovered most often. The field lives in the
kernel registry, and it **defaults to `probe`** — so an omission tightens the
check rather than relaxing it.

If you believe your control is an audit and the registry says probe, that is a
kernel change, reviewed as one.

---

## 5. Worked example

`examples/conforming_source.py` is the shortest honest implementation. Copy it.
Its check is a stand-in — replace the body of `_has_access` and keep the
scenario wiring.

`examples/vacuous_source.py` is the counter-example, and it is in the repository
deliberately: **a conformance suite nobody has seen fail is itself an unverified
check.** It emits a well-formed attestation with a plausible reference, every
time, for everyone — which is the shape of a probe that has stopped probing.

```
$ neuraxis conform --control GV-01 -- python examples/vacuous_source.py

PASS  live       rule 4 - emit an evidence reference, never a bare pass/fail
FAIL  broken     reported PASS with a dependency unavailable
FAIL  negative   did not report FAIL against a condition it should reject
FAIL  powerless  passes for an identity with no authority, exactly as it does
                 for one with authority; the probe is not probing anything

GV-01: this source DOES NOT conform. Do not accept attestations from it.
```

Note that it passes rule 4. A source can satisfy the visible rule and none of
the substantive ones.

---

## 6. What conformance is not

**Every scenario is implemented by the source.** It decides what `broken` and
`negative` mean for itself. So conformance proves a source *can* fail, *does*
fail closed, and *does* carry evidence.

It does not prove the source fails **when it should**. A determined author can
write a source that passes all four scenarios and reports PASS for everything
in production. No black-box suite can close that, and this one does not pretend
to.

What it closes is the case that actually happens: a check that was correct when
written and has since stopped exercising anything, still reporting green. That
is worth closing on its own — but read §6 of `docs/THREAT-MODEL.md` before
treating a conformance report as trust.

The thing that would make it trust is the same thing as everywhere else in this
package: KBS-001 T1, an authenticated source and a sink nobody can rewrite.

---

## The other end of the same contract

This document is about an attestation **source** — something the gate reads.
Its mirror is [`L0-LEASE-GATE-CONTRACT.md`](L0-LEASE-GATE-CONTRACT.md), about a
gate **caller** — something that acts on what the gate returns — with its own
black-box suite, `neuraxis caller-conform`.

The two failures rhyme. A source that cannot fail is not a check; a caller that
cannot refuse is not a gate client. Both pass every test their authors would
think to write.
