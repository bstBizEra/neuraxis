# @bst/neuraxis-client

Node client for the **BST Neuraxis** governance gate. Zero dependencies.

```js
import { createClient, CapabilityDenied } from "@bst/neuraxis-client";

const gate = createClient({ attestations: "attestations.jsonl" });

try {
  await gate.withCapability({
    intent: "promote lesson to canonical",
    identity: "agent-cortex", role: "cortex", capability: "IL-11",
    scope: "hippocampus/lessons", verifier: "github-ci", rollback_tested: true,
  }, async (verdict) => {
    // verdict.obligations says what you now owe: evidence, provenance, rollback
    await promoteLesson();
  });
} catch (error) {
  if (error instanceof CapabilityDenied) {
    route(error.verdict);   // DENY / ESCALATE / DELEGATE / WAIT_FOR_AUTHORITY
  } else throw error;
}
```

## There is one gate

This package re-implements no rule. Band resolution, attestation freshness,
verifier independence and the non-delegable floor all live in the Python gate,
and this speaks to it over the CLI contract. Two implementations of a
governance decision is two governance decisions.

## What it guarantees

**Only ALLOW permits action.** `permitsAction` is true for exactly one
decision, and `require()` throws for every other — including decisions this
client has never heard of.

**Unrecognised is never unblocked.** An exit code outside the contract, or a
decision name this client does not know, throws `NeuraxisError`. This is the
failure the README of the Python package warns about — a caller that blocks
only on exit 10 will act on an `ESCALATE` — made structurally impossible.

**Exit code and verdict must agree.** If the process exits 0 but the verdict
says DENY, something is wrong with the gate or the transport and *no* result
from that run is trustworthy, so the client throws rather than picking one.

**Requests cannot become commands.** Arguments are passed as an array with
`shell: false`, so a value inside a request is carried as data.

## API

| Call | Behaviour |
|---|---|
| `check(request)` | Verdict for any decision, including blocks. Throws only when the result cannot be trusted. |
| `require(request)` | Verdict on ALLOW; throws `CapabilityDenied` otherwise. |
| `withCapability(request, fn)` | Runs `fn(verdict)` only on ALLOW. |
| `status()` | Band attainment against current attestations. |
| `contract()` | The CLI's machine-readable contract. |

`createClient({ bin, binArgs, attestations, registry, taskLog, timeoutMs, cwd, env })`.
Use `binArgs` when the CLI is not on PATH: `{ bin: "python", binArgs: ["-m", "neuraxis"] }`.

## Drift protection

`DECISIONS` here is asserted against `neuraxis contract` in the test suite. Add
a `Decision` to the Python enum and **this package's tests fail**, with a
message saying it must be handled before the client is used again — rather than
an unmapped exit code arriving in production, where "unmapped" in a gate means
"not recognised as a block".

Verified by deliberately adding a sixth decision in Python and confirming the
suite goes red.

## Tests

```bash
npm test          # 19 tests, against the real CLI
```

Requires `neuraxis` on PATH, or set `NEURAXIS_BIN`. The suite uses a stand-in
CLI only for responses the real one cannot produce — an unknown exit code, a
decision from the future, an exit code that contradicts its verdict — because
the client has to hold even when the thing it talks to misbehaves.
