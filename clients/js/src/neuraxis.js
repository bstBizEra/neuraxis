/**
 * Neuraxis client for Node (maw-js).
 *
 * A thin, dependency-free wrapper over the `neuraxis` CLI. There is one
 * implementation of the gate logic — in Python — and this speaks to it. No
 * rule is re-expressed here, because two implementations of a governance
 * decision is two governance decisions.
 *
 * The client's job is to make the CLI contract impossible to misuse:
 *
 *   - Only ALLOW permits action. Every other decision blocks, including any
 *     decision this client has never heard of.
 *   - An unrecognised exit code or decision throws. It is never treated as a
 *     pass, because "unrecognised" in a gate must not mean "unblocked".
 *   - Exit code and decision field must agree. If they disagree, the CLI or
 *     the transport is faulty and no verdict is trustworthy.
 */

import { execFile } from "node:child_process";

/**
 * Decision → exit code. Asserted against `neuraxis contract` in the test
 * suite, so a Decision added on the Python side fails this package's tests
 * rather than arriving as an exit code that maps to nothing.
 */
export const DECISIONS = Object.freeze({
  ALLOW: 0,
  DENY: 10,
  ESCALATE: 11,
  WAIT_FOR_AUTHORITY: 12,
  DELEGATE: 13,
});

/** The only decision that permits action. */
export const PERMITTING_DECISION = "ALLOW";

/** Exit code for a CLI-level fault: bad input, registry error, unreadable state. */
export const ERROR_EXIT = 2;

const EXIT_TO_DECISION = Object.freeze(
  Object.fromEntries(Object.entries(DECISIONS).map(([name, code]) => [code, name])),
);

/** A fault in the client, the CLI, or the contract between them. Never a verdict. */
export class NeuraxisError extends Error {
  constructor(message, { cause, stdout, stderr, code } = {}) {
    super(message, { cause });
    this.name = "NeuraxisError";
    this.stdout = stdout;
    this.stderr = stderr;
    this.code = code;
  }
}

/**
 * The gate returned something other than ALLOW.
 *
 * Carries the verdict so callers can route on DELEGATE / ESCALATE /
 * WAIT_FOR_AUTHORITY rather than collapsing every block into a failure.
 */
export class CapabilityDenied extends Error {
  constructor(verdict) {
    const reasons = verdict.reasons?.join("; ") || "no reason recorded";
    super(`${verdict.decision} ${verdict.capability}: ${reasons}`);
    this.name = "CapabilityDenied";
    this.verdict = verdict;
  }
}

function normaliseVerdict(raw) {
  return Object.freeze({
    decision: raw.decision,
    capability: raw.capability,
    band: raw.band ?? null,
    reasons: Object.freeze(raw.reasons ?? []),
    obligations: Object.freeze(raw.obligations ?? []),
    missingControls: Object.freeze(raw.missing_controls ?? []),
    evaluatedAt: raw.evaluated_at ?? null,
    get permitsAction() {
      return raw.decision === PERMITTING_DECISION;
    },
  });
}

/**
 * @param {object} options
 * @param {string} [options.bin="neuraxis"]   Path to the CLI executable.
 * @param {string[]} [options.binArgs=[]]     Args before the neuraxis args, e.g.
 *                                            `{bin: "python", binArgs: ["-m", "neuraxis"]}`.
 * @param {string} [options.attestations]     Attestation JSONL path.
 * @param {string} [options.registry]         Registry path; omit for the bundled kernel copy.
 * @param {string} [options.taskLog]          Task log for the verifier-independence provider.
 * @param {number} [options.timeoutMs=15000]  Hard timeout per invocation.
 * @param {string} [options.cwd]              Working directory for the CLI.
 * @param {object} [options.env]              Environment for the CLI.
 */
export function createClient(options = {}) {
  const {
    bin = "neuraxis",
    binArgs = [],
    attestations,
    registry,
    taskLog,
    timeoutMs = 15_000,
    cwd,
    env,
  } = options;

  if (!Array.isArray(binArgs)) throw new TypeError("binArgs must be an array");

  function globalArgs() {
    const args = ["--json"];
    if (registry) args.push("--registry", registry);
    if (attestations) args.push("--attestations", attestations);
    if (taskLog) args.push("--task-log", taskLog);
    return args;
  }

  /**
   * Invoke the CLI. `shell` is never enabled and arguments are always passed
   * as an array, so a value inside a request cannot become a command.
   */
  function run(args, stdin) {
    return new Promise((resolve, reject) => {
      const child = execFile(
        bin,
        [...binArgs, ...args],
        { timeout: timeoutMs, cwd, env, maxBuffer: 8 * 1024 * 1024, shell: false },
        (error, stdout, stderr) => {
          if (error && error.killed) {
            reject(
              new NeuraxisError(`neuraxis timed out after ${timeoutMs}ms`, {
                cause: error,
                stdout,
                stderr,
              }),
            );
            return;
          }
          if (error && typeof error.code !== "number") {
            // Spawn failure: binary missing, not executable, etc.
            reject(
              new NeuraxisError(`could not run ${bin}: ${error.message}`, {
                cause: error,
                stdout,
                stderr,
              }),
            );
            return;
          }
          resolve({ code: error ? error.code : 0, stdout, stderr });
        },
      );

      if (stdin !== undefined) {
        child.stdin.end(stdin);
      }
    });
  }

  function parseJson({ stdout, stderr, code }) {
    try {
      return JSON.parse(stdout);
    } catch (cause) {
      throw new NeuraxisError("neuraxis did not return JSON", {
        cause,
        stdout,
        stderr,
        code,
      });
    }
  }

  return {
    /** The CLI's machine-readable contract. */
    async contract() {
      const result = await run([...globalArgs(), "contract"]);
      if (result.code !== 0) {
        throw new NeuraxisError(`contract failed (exit ${result.code})`, result);
      }
      return parseJson(result);
    },

    /** Band attainment against the current attestations. */
    async status() {
      const result = await run([...globalArgs(), "status"]);
      if (result.code !== 0) {
        throw new NeuraxisError(`status failed (exit ${result.code})`, result);
      }
      return parseJson(result);
    },

    /**
     * Evaluate a request. Returns a verdict for every decision, including
     * blocks. Throws only when the result cannot be trusted.
     */
    async check(request) {
      if (!request || typeof request !== "object") {
        throw new TypeError("request must be an object");
      }
      const result = await run([...globalArgs(), "gate", "-"], JSON.stringify(request));

      if (result.code === ERROR_EXIT) {
        throw new NeuraxisError(
          `neuraxis rejected the request: ${(result.stderr || "").trim() || "no detail"}`,
          result,
        );
      }

      const expectedDecision = EXIT_TO_DECISION[result.code];
      if (expectedDecision === undefined) {
        // An exit code this client does not know. Refusing is the only safe
        // reading: a gate that treats the unrecognised as permitted is not a gate.
        throw new NeuraxisError(
          `unrecognised exit code ${result.code} from neuraxis; refusing to interpret it`,
          result,
        );
      }

      const verdict = normaliseVerdict(parseJson(result));

      if (!(verdict.decision in DECISIONS)) {
        throw new NeuraxisError(
          `unrecognised decision ${JSON.stringify(verdict.decision)}; this client is ` +
            "older than the gate it is talking to — upgrade before relying on it",
          result,
        );
      }
      if (verdict.decision !== expectedDecision) {
        throw new NeuraxisError(
          `contract violation: exit ${result.code} means ${expectedDecision} but the ` +
            `verdict says ${verdict.decision}; no verdict from this run is trustworthy`,
          result,
        );
      }
      return verdict;
    },

    /**
     * Evaluate and block unless allowed.
     *
     * @throws {CapabilityDenied} on any decision other than ALLOW.
     */
    async require(request) {
      const verdict = await this.check(request);
      if (!verdict.permitsAction) throw new CapabilityDenied(verdict);
      return verdict;
    },

    /**
     * Run `fn` only if the capability is allowed, and hand it the verdict so
     * the obligations attached to the ALLOW are visible at the call site.
     */
    async withCapability(request, fn) {
      const verdict = await this.require(request);
      return fn(verdict);
    },
  };
}

export default createClient;
