/** Shared fixtures. Every test runs against the REAL CLI, never a mock. */
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

/** Controls needed to open BAND-A and BAND-B. */
export const BAND_B_CONTROLS = ["GV-01", "GV-02", "GV-03", "GV-04", "GV-05"];

export function tempDir() {
  return mkdtempSync(join(tmpdir(), "neuraxis-js-"));
}

/** An attestation file that opens BAND-B. */
export function attestationsFor(controls = BAND_B_CONTROLS) {
  const dir = tempDir();
  const path = join(dir, "attestations.jsonl");
  const now = new Date().toISOString();
  writeFileSync(
    path,
    controls
      .map((control) =>
        JSON.stringify({
          control,
          result: true,
          issued_at: now,
          issuer: "js-contract-test",
          evidence_ref: `test://${control}`,
        }),
      )
      .join("\n") + "\n",
    "utf8",
  );
  return path;
}

/** A path that does not exist, so nothing is attested. */
export function noAttestations() {
  return join(tempDir(), "absent.jsonl");
}

export const VALID_REQUEST = Object.freeze({
  intent: "run the coffee cost pipeline",
  identity: "agent-drafter",
  role: "drafter",
  capability: "IL-06",
  scope: "bst-sa/pipelines",
  verifier: "github-ci",
  rollback_tested: true,
});

/**
 * A stand-in CLI that emits chosen stdout and exits with a chosen code.
 *
 * Used to prove the client refuses results it cannot trust. These cases cannot
 * be produced by the real CLI — which is the point: the client must hold even
 * when the thing it talks to misbehaves.
 */
export function fakeCli({ stdout = "", code = 0 }) {
  const dir = tempDir();
  const path = join(dir, "fake-neuraxis.mjs");
  writeFileSync(
    path,
    `process.stdin.resume();\nprocess.stdout.write(${JSON.stringify(stdout)});\nprocess.exit(${code});\n`,
    "utf8",
  );
  // Invoked as `node <script>` rather than relying on a shebang, so the
  // fixture works identically on Windows.
  return { bin: process.execPath, binArgs: [path] };
}
