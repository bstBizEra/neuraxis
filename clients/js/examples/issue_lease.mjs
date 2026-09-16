#!/usr/bin/env node
/**
 * A reference gate caller for Node (ILR-001-DR D-07).
 *
 * L0 is the likely author of the real one, and it is a Node programme, so this
 * is the copy-paste starting point rather than the Python reference.
 *
 * What is worth noticing is how little of it there is. Every refusal rule in
 * `docs/L0-LEASE-GATE-CONTRACT.md` -- test for zero not for 10, refuse an
 * unrecognised exit code, refuse when the exit code and the verdict disagree,
 * refuse a timeout -- is already implemented inside `createClient`, because it
 * was written against the same contract. `require()` throws on every one of
 * them, so the whole of the caller's obligation is: forward the request
 * unchanged, and issue only if nothing threw.
 *
 * The client resolves the gate from NEURAXIS_BIN / NEURAXIS_BIN_ARGS when it
 * is not told otherwise, which is what lets the conformance suite drive this
 * file through decisions it could not otherwise arrange:
 *
 *     neuraxis caller-conform -- node clients/js/examples/issue_lease.mjs
 *
 * Replace `issueLease` with the real L0 grant. Change nothing above it -- in
 * particular, do not filter the request on its way through. Dropping
 * `verifier` is not an error anywhere and switches off W9 entirely.
 */

import { createClient } from "../src/neuraxis.js";

const GATE_TIMEOUT_MS = 15_000;

function readStdin() {
  return new Promise((resolve, reject) => {
    let buf = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (buf += chunk));
    process.stdin.on("end", () => resolve(buf));
    process.stdin.on("error", reject);
  });
}

function issueLease(request, verdict) {
  process.stdout.write(
    JSON.stringify({
      record: "lease",
      principal: request.identity,
      issued_by: "l0-gate",
      scope: [request.scope],
      verdict_id: verdict.verdictId ?? null,
    }) + "\n",
  );
}

async function main() {
  let request;
  try {
    request = JSON.parse(await readStdin());
  } catch (err) {
    process.stderr.write(`lease refused: request is not JSON: ${err.message}\n`);
    return 1;
  }
  if (!request || typeof request !== "object") {
    process.stderr.write("lease refused: request is not a JSON object\n");
    return 1;
  }

  const gate = createClient({ timeoutMs: GATE_TIMEOUT_MS });

  let verdict;
  try {
    // Throws CapabilityDenied on any decision but ALLOW, and NeuraxisError on
    // a fault, an unrecognised exit code, a timeout, a missing binary, or an
    // exit code that disagrees with the verdict. There is no fourth outcome.
    verdict = await gate.require(request);
  } catch (err) {
    process.stderr.write(`lease refused: ${err.message}\n`);
    return 1;
  }

  issueLease(request, verdict);
  return 0;
}

main().then(
  (code) => process.exit(code),
  (err) => {
    // An unexpected throw is still not consent.
    process.stderr.write(`lease refused: ${err?.message ?? err}\n`);
    process.exit(1);
  },
);
