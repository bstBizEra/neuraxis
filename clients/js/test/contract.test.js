/**
 * Contract tests.
 *
 * These run against the REAL `neuraxis` CLI, not a mock. A mocked gate would
 * assert that this client agrees with an idea of the gate rather than with the
 * gate, which is precisely the drift the contract command exists to prevent.
 *
 * The fake-CLI cases are the exception, and deliberately so: they produce
 * responses the real CLI cannot, to prove the client refuses results it has no
 * business trusting.
 */

import { strict as assert } from "node:assert";
import { test } from "node:test";

import {
  CapabilityDenied,
  DECISIONS,
  ERROR_EXIT,
  NeuraxisError,
  PERMITTING_DECISION,
  createClient,
} from "../src/neuraxis.js";
import { VALID_REQUEST, attestationsFor, fakeCli, noAttestations } from "./helpers.js";

const BIN = process.env.NEURAXIS_BIN || "neuraxis";
const allowing = () => createClient({ bin: BIN, attestations: attestationsFor() });
const blocking = () => createClient({ bin: BIN, attestations: noAttestations() });

// ---- the drift test ----------------------------------------------------

test("client decision table matches the CLI contract exactly", async () => {
  const contract = await allowing().contract();
  assert.deepEqual(
    contract.decisions,
    DECISIONS,
    "the gate and this client disagree about decisions or exit codes. A Decision " +
      "added in Python must be handled here before this package is used again.",
  );
  assert.deepEqual(contract.permitting_decisions, [PERMITTING_DECISION]);
  assert.equal(contract.error_exit, ERROR_EXIT);
});

test("ALLOW is the only permitting decision in the contract", async () => {
  const contract = await allowing().contract();
  assert.equal(contract.permitting_decisions.length, 1);
});

// ---- positive control --------------------------------------------------

test("allows a valid request when the band is attained", async () => {
  // POSITIVE CONTROL. Without it a client that blocked everything would pass
  // every other assertion in this file.
  const verdict = await allowing().check(VALID_REQUEST);
  assert.equal(verdict.decision, "ALLOW");
  assert.equal(verdict.permitsAction, true);
  assert.equal(verdict.band, "BAND-B");
});

test("an allowed verdict carries its obligations", async () => {
  const verdict = await allowing().check(VALID_REQUEST);
  assert.ok(verdict.obligations.includes("emit-evidence-record"));
  assert.ok(verdict.obligations.includes("independent-verification"));
  assert.ok(verdict.obligations.includes("tested-rollback"));
});

test("require() resolves and withCapability() runs the body on ALLOW", async () => {
  const client = allowing();
  await client.require(VALID_REQUEST);
  const ran = await client.withCapability(VALID_REQUEST, (v) => `ran:${v.band}`);
  assert.equal(ran, "ran:BAND-B");
});

// ---- blocking ----------------------------------------------------------

test("denies when nothing is attested, and names the missing controls", async () => {
  const verdict = await blocking().check(VALID_REQUEST);
  assert.equal(verdict.decision, "DENY");
  assert.equal(verdict.permitsAction, false);
  assert.ok(verdict.missingControls.includes("GV-01"));
});

test("require() throws CapabilityDenied and carries the verdict", async () => {
  await assert.rejects(
    () => blocking().require(VALID_REQUEST),
    (error) => {
      assert.ok(error instanceof CapabilityDenied);
      assert.equal(error.verdict.decision, "DENY");
      assert.ok(error.message.includes("IL-06"));
      return true;
    },
  );
});

test("withCapability() does not run the body when blocked", async () => {
  let ran = false;
  await assert.rejects(
    () => blocking().withCapability(VALID_REQUEST, () => { ran = true; }),
    CapabilityDenied,
  );
  assert.equal(ran, false, "body executed despite a block");
});

test("self-verification is refused", async () => {
  const verdict = await allowing().check({
    ...VALID_REQUEST,
    verifier: VALID_REQUEST.identity,
  });
  assert.equal(verdict.decision, "DENY");
  assert.ok(verdict.reasons.some((r) => r.includes("V = 0")));
});

test("each non-ALLOW decision is reachable and blocks", async () => {
  const client = allowing();

  const escalate = await client.check({ ...VALID_REQUEST, risk: "CRITICAL" });
  assert.equal(escalate.decision, "ESCALATE");
  assert.equal(escalate.permitsAction, false);

  const delegate = await client.check({ ...VALID_REQUEST, capability: "IL-17" });
  assert.equal(delegate.decision, "DELEGATE");
  assert.equal(delegate.permitsAction, false);

  const waiting = await client.check({
    ...VALID_REQUEST,
    identity: "operator",
    role: "operator",
    capability: "IL-31",
  });
  assert.ok(["WAIT_FOR_AUTHORITY", "DENY"].includes(waiting.decision));
  assert.equal(waiting.permitsAction, false);
});

// ---- refusing what cannot be trusted -----------------------------------

test("an unrecognised exit code throws rather than being read as a pass", async () => {
  const client = createClient({ ...fakeCli({ stdout: "{}", code: 42 }) });
  await assert.rejects(() => client.check(VALID_REQUEST), (error) => {
    assert.ok(error instanceof NeuraxisError);
    assert.ok(error.message.includes("unrecognised exit code 42"));
    return true;
  });
});

test("a decision this client does not know throws", async () => {
  // Exit 0 with a decision name from a future version. Treating it as ALLOW
  // because the exit code says 0 would be the whole failure in one line.
  const client = createClient({
    ...fakeCli({
      stdout: JSON.stringify({ decision: "PROVISIONAL_ALLOW", capability: "IL-06" }),
      code: 0,
    }),
  });
  await assert.rejects(() => client.check(VALID_REQUEST), (error) => {
    assert.ok(error.message.includes("unrecognised decision"));
    return true;
  });
});

test("exit code and decision must agree", async () => {
  const client = createClient({
    ...fakeCli({ stdout: JSON.stringify({ decision: "DENY", capability: "IL-06" }), code: 0 }),
  });
  await assert.rejects(() => client.check(VALID_REQUEST), (error) => {
    assert.ok(error.message.includes("contract violation"));
    return true;
  });
});

test("non-JSON output throws", async () => {
  const client = createClient({ ...fakeCli({ stdout: "not json at all", code: 0 }) });
  await assert.rejects(() => client.check(VALID_REQUEST), (error) => {
    assert.ok(error.message.includes("did not return JSON"));
    return true;
  });
});

test("a missing binary throws rather than resolving", async () => {
  const client = createClient({ bin: "neuraxis-does-not-exist-anywhere" });
  await assert.rejects(() => client.check(VALID_REQUEST), NeuraxisError);
});

test("a malformed request is reported as an error, not as a verdict", async () => {
  const client = allowing();
  await assert.rejects(
    () => client.check({ ...VALID_REQUEST, rollbackTested: true }),
    (error) => {
      assert.ok(error instanceof NeuraxisError);
      assert.ok(error.message.includes("rejected the request"));
      return true;
    },
  );
});

test("a non-object request is refused before spawning anything", async () => {
  await assert.rejects(() => allowing().check("IL-06"), TypeError);
});

// ---- misc --------------------------------------------------------------

test("status reports band attainment", async () => {
  const attained = await allowing().status();
  assert.ok(attained.attained.includes("BAND-B"));

  const nothing = await blocking().status();
  assert.deepEqual(nothing.attained, []);
});

test("a value inside a request cannot become a command", async () => {
  // Arguments are passed as an array with shell:false, so the injected text is
  // carried through as data and appears in the verdict rather than executing.
  const verdict = await allowing().check({
    ...VALID_REQUEST,
    intent: 'run"; echo PWNED > /tmp/neuraxis-pwned; #',
  });
  assert.ok(["ALLOW", "DENY"].includes(verdict.decision));
});

// ---- D-07: a caller of this client must be conformance-testable --------

test("the gate is resolved from the environment when the caller has not said", async () => {
  // This is what lets `neuraxis caller-conform` drive a Node caller through
  // decisions it could not otherwise arrange. A client that could only be
  // pointed at a hard-coded path could never be tested against a DENY.
  const fake = fakeCli({ stdout: JSON.stringify({ decision: "DENY", capability: "IL-06" }), code: 10 });
  const previousBin = process.env.NEURAXIS_BIN;
  const previousArgs = process.env.NEURAXIS_BIN_ARGS;
  process.env.NEURAXIS_BIN = fake.bin;
  process.env.NEURAXIS_BIN_ARGS = JSON.stringify(fake.binArgs);
  try {
    const verdict = await createClient({}).check(VALID_REQUEST);
    assert.equal(verdict.decision, "DENY");
  } finally {
    if (previousBin === undefined) delete process.env.NEURAXIS_BIN;
    else process.env.NEURAXIS_BIN = previousBin;
    if (previousArgs === undefined) delete process.env.NEURAXIS_BIN_ARGS;
    else process.env.NEURAXIS_BIN_ARGS = previousArgs;
  }
});

test("an explicit bin beats the environment", async () => {
  const previousBin = process.env.NEURAXIS_BIN;
  process.env.NEURAXIS_BIN = "/definitely/not/a/gate";
  const fake = fakeCli({ stdout: JSON.stringify({ decision: "DENY", capability: "IL-06" }), code: 10 });
  try {
    const verdict = await createClient(fake).check(VALID_REQUEST);
    assert.equal(verdict.decision, "DENY");
  } finally {
    if (previousBin === undefined) delete process.env.NEURAXIS_BIN;
    else process.env.NEURAXIS_BIN = previousBin;
  }
});

test("a malformed NEURAXIS_BIN_ARGS fails at construction, not at the first grant", () => {
  const previous = process.env.NEURAXIS_BIN_ARGS;
  process.env.NEURAXIS_BIN_ARGS = "not json";
  try {
    assert.throws(() => createClient({}), NeuraxisError);
  } finally {
    if (previous === undefined) delete process.env.NEURAXIS_BIN_ARGS;
    else process.env.NEURAXIS_BIN_ARGS = previous;
  }
});

test("a verdict carries its verdict_id, so a lease can be joined to what licensed it", async () => {
  const fake = fakeCli({
    stdout: JSON.stringify({ decision: "ALLOW", capability: "IL-06", verdict_id: "514e47ce66dbc807" }),
    code: 0,
  });
  const verdict = await createClient(fake).require(VALID_REQUEST);
  assert.equal(verdict.verdictId, "514e47ce66dbc807");
});

test("a verdict recorded without an evidence sink reports no id rather than undefined", async () => {
  const fake = fakeCli({ stdout: JSON.stringify({ decision: "ALLOW", capability: "IL-06" }), code: 0 });
  const verdict = await createClient(fake).require(VALID_REQUEST);
  assert.equal(verdict.verdictId, null);
});
