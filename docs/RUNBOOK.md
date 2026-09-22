# Operator runbook

**For:** whoever is holding the pager. **Package:** `neuraxis` v0.22.0.

The roadmap asks this document to answer one question: *what do you do when a
band closes at 02:00?* The short version is **usually nothing**, and the rest
of this page is about telling that case apart from the others.

---

## 0. The thirty-second version

```bash
neuraxis status                 # which bands are open, and why not
neuraxis drift --expect-file REGISTRY-DIGEST.txt    # is the kernel the ratified one?
neuraxis waivers                # what is being held open by exception
neuraxis envelopes --audit      # is bounded self-tuning being leaned on
neuraxis obligations --grace 30m  # what the gate's ALLOWs owe and nobody has paid
```

**A closed band is not an incident by default.** It means a control stopped
being proven. That is the system working — an unproven control is not a
control. It becomes an incident when a band something depends on closed and
nobody noticed, which is what the daily report is for.

---

## 1. Exit codes

Every command uses the same table. **Test for zero, not for a code.** A caller
that checks only for `10` will act on an `ESCALATE`.

| Code | Meaning | Where it comes from |
|---:|---|---|
| 0 | ALLOW, or a clean report | `gate`, and every reporting command with nothing to flag |
| 10 | DENY, or a report with something to flag | `gate`; `obligations` with outstanding debt; `waivers` and `envelopes --audit` with an armed trigger; `drift` on a mismatch |
| 11 | ESCALATE — risk at or above the threshold, even though the band is attained | `gate` |
| 12 | WAIT_FOR_AUTHORITY — a human ratification reference is required and absent | `gate` |
| 13 | DELEGATE — this role does not hold the band; another one does | `gate` |
| 2 | Error — the registry will not load, input is malformed, a file is unreadable | any command |

**2 is the one to page on.** 10 through 13 are the gate doing its job. A `2`
means the gate could not answer, and a gate that cannot answer denies
everything by construction.

---

## 2. A band closed. Now what?

```bash
neuraxis status
```

Read the first reason line for the band. It is one of four things.

### 2.1 `GV-0n: attestation expired (Xh old, max Yh)`

**Cause.** The assurance run did not happen, or the provider failed and the
last passing attestation aged out.

**Do.** Run it and look at the result:

```bash
neuraxis assure --control GV-0n
neuraxis status
```

**If the provider now passes**, the band reopens and nothing else is needed.
Find out why the scheduled run did not fire; that is the actual fault.

**If the provider fails**, the control genuinely does not hold. That is not a
neuraxis problem — the thing the control checks is broken. Fix that.

**Do not** extend the window to make the red go away. That is gate erosion, and
the roadmap names it explicitly: *change the window deliberately through a
ratified registry change, or fix the drill.*

### 2.2 `GV-0n: last attestation FAILED at ... (<evidence-ref>)`

**Cause.** A provider ran and said no. Follow the evidence reference — it names
the record that failed, not just the fact of failure.

**This is the case most likely to be a real incident.** A control that was
holding has stopped. Treat the evidence reference as the start of the
investigation, not the end of it.

### 2.3 `GV-0n: no attestation on file`

**Cause.** Either a fresh deployment, or the control has no wired provider.

```bash
neuraxis providers
```

If it reports `UNWIRED`, the control has never been provable here and the band
has never been open. Nothing has broken. See §6.

### 2.4 `BAND-X: prerequisite band not attained`

**Cause.** Something below closed. The status output already reports the *root*
blocker rather than the band you asked about — that is deliberate, because
`BAND-G` is never the real problem. Go to the band it names.

---

## 3. `CONDITIONAL` instead of `ATTAINED`

The band is open **on a waiver**: a required control is not proven and an
exception is carrying it.

```bash
neuraxis waivers
```

This is a countdown, not a steady state. Every waiver has a hard expiry, at
most two may be active, and each may be renewed once. When `waivers` exits 10,
a reversal trigger is armed:

| Trigger | What it means | Do |
|---|---|---|
| More than 2 active | **Every waiver is void right now** and the gate is denying as if none existed | Nothing here is fixed by adding a third. The matrix is mis-calibrated against real capacity — re-cut it (ILR-001-DR D-05) |
| A waiver is a renewal | The next renewal on that scope is refused *at load* | Close the gap before the current one expires. There is no third window |

**A waiver cannot be issued for GV-01, GV-02, GV-03 or GV-08 at any TTL.** If
one of those is what closed the band, the exception path is not available and
was never going to be. See §6.

---

## 4. The kernel registry does not match

```bash
neuraxis drift --expect-file REGISTRY-DIGEST.txt   # from the release you believe you are running
```

Exit 10 means the kernel config on disk is not the ratified one. Two causes,
and they need opposite responses:

**Someone changed it without a release.** Do not attest anything against it.
Every attestation records that a control held — against *which* matrix? Revert,
or cut a release so the change is ratified, and only then re-run assurance.

**You are not running the version you think you are.** Check
`neuraxis validate` for the package version, then get the right
`REGISTRY-DIGEST.txt`. This is the benign case, and the digest is how you tell
them apart at 02:00 instead of at the next audit.

The weekly `drift` workflow reports a difference every run and fails only once
the kernel has been unratified for more than 7 days. If it is failing, the
answer is a release or a revert — not a longer grace window.

### 4.1 `the newest ratified version is vX, N behind the package`

The drift check compares the kernel against the **latest release**. This says
that release is no longer a current reference: versions have shipped past it
and none of them was ever published.

```bash
python scripts/ratification_gap.py --released "$(gh release list --limit 1 --json tagName --jq '.[0].tagName')"
```

It warns inside the same 7-day window the kernel rule uses and fails past it.
The cause is almost always that a tag was never pushed — a release is a tag,
and a tag that fails to push leaves `main` ahead of anything ratified while
every other check stays green. Push the missing tags; `release.yml` publishes
`REGISTRY-DIGEST.txt` and the reference is current again.

**Why this matters when the kernel has not changed.** It does not, yet. It
matters the moment it does: section 4 tells you to compare against "the release
you believe you are running", and if that release is three versions old you are
reading a true digest for the wrong baseline. The gap is reported so the answer
to "unratified since when?" is not "since a date nobody recorded".

---

## 5. Obligations are outstanding

```bash
neuraxis obligations --grace 30m
```

Without `--grace`, every in-flight ALLOW reads as outstanding, which is noise.
With it, what remains is debt.

A **FAULT** line is different from an outstanding one and is worth attention:

```
FAULT verdict <id>: emit-evidence-record discharged by the performer 'agent-x'
```

The performer paid its own obligation. That is NX-INV-2 at the obligation
layer, and it means the discharge proves nothing. Find out who was supposed to
verify.

**What this command cannot tell you.** It reads a sink the audited party can
also write. It shows what the records say; it cannot show what is missing from
them. That is GV-03, and GV-03 is unwired until KBS-001 T1.

---

## 6. When the answer is "this was never going to work yet"

Four controls are wired. Six are not. **Zero bands are attainable**, and that
is the plan rather than a fault.

GV-01, GV-02, GV-03 and GV-08 are non-compensable integrity controls; GV-01,
GV-03 and GV-08 have no provider until KBS-001 T1 lands. So Band A cannot open,
and every band inherits the block.

If you are paging because a band will not open: check whether its blocker is
one of those four. If it is, there is no operational fix and there is no waiver
path. Stop, and escalate to whoever owns T1.

`docs/THREAT-MODEL.md` §6 has the per-control table of what each wired provider
actually proves. It is shorter than people expect.

---

## 7. Restoring service, in order

1. `neuraxis validate` — if this exits 2, nothing else matters. The registry is
   the kernel; a gate with no registry denies everything.
2. `neuraxis drift --expect-file ...` — is it the *right* registry?
3. `neuraxis status` — what is actually closed, and what is the root blocker?
4. `neuraxis assure --control GV-0n` — re-run the provider for that control.
5. `neuraxis status` again — did it open?
6. If not, §2.2 or §6.

**Never** in that list: editing the registry, extending a window, issuing a
waiver for a non-compensable control, or re-running `attest` by hand with
`--result pass`. The last one is the worst: it records an assertion where a
provider result should be, and `provenance` will say `manual` in the evidence
forever.

---

## 8. What to hand to whoever comes next

The three questions worth answering in the handover, in this order:

1. **What closed, and was it proven-and-stopped, or never-proven?** §2.2 versus
   §2.3. They are completely different problems.
2. **Is the kernel the ratified one?** One command, §4. Ask it before believing
   anything else on the page.
3. **Did anything get attested while the answer to 2 was no?** If so, those
   attestations are against an unknown matrix and should be re-run, not trusted.
