export type Cause =
  | "organic"
  | "attack_or_bot"
  | "crawler"
  | "cache_transient"
  | "analytics_artifact"
  | "UNKNOWN"
  | "load_proportional"
  | "pathological_request"
  | "code_regression"
  | "noisy_neighbour";

export interface TrustedEvidence {
  cause: Cause;
  ipConcentration?: number;
  tailRatio?: number;
  rps?: number;
  rpsBaseline?: number;
  replicas?: number;
  rootTarget?: string;
}

export interface ProposedAction {
  capability: string;
  params: Record<string, unknown>;
}

export type GateDecision =
  | { allowed: true }
  | { allowed: false; gate: "GATE_5B"; reason: string };

const CAUSE_ALLOWED: Record<Cause, ReadonlySet<string>> = {
  organic: new Set(["scale_service", "enable_cache", "warm_cache"]),
  attack_or_bot: new Set([
    "rate_limit_client",
    "challenge_client",
    "block_asn",
    "enable_waiting_room",
  ]),
  crawler: new Set(["rate_limit_client"]),
  cache_transient: new Set(["warm_cache", "none"]),
  analytics_artifact: new Set(["none"]),
  UNKNOWN: new Set(["enable_waiting_room", "none"]),
  load_proportional: new Set(["scale_service", "enable_cache"]),
  pathological_request: new Set(["rate_limit_client", "set_flag"]),
  code_regression: new Set(["rollback_deploy", "set_flag"]),
  noisy_neighbour: new Set(["none"]),
};

function reject(reason: string): GateDecision {
  return { allowed: false, gate: "GATE_5B", reason };
}

export function checkCauseCoherence(
  action: ProposedAction,
  evidence: TrustedEvidence,
): GateDecision {
  if (
    !evidence ||
    !Object.prototype.hasOwnProperty.call(CAUSE_ALLOWED, evidence.cause)
  ) {
    return reject("Unknown or missing trusted cause");
  }

  const allowed = CAUSE_ALLOWED[evidence.cause];

  if (!allowed.has(action.capability)) {
    return reject("Capability not permitted for trusted cause");
  }

  if (action.capability === "scale_service") {
    if (
      evidence.ipConcentration !== undefined &&
      evidence.ipConcentration > 0.70
    ) {
      return reject("Refusing to scale concentrated traffic");
    }

    if (
      evidence.tailRatio !== undefined &&
      evidence.rps !== undefined &&
      evidence.rpsBaseline !== undefined &&
      evidence.tailRatio > 20 &&
      evidence.rps <= 1.2 * evidence.rpsBaseline
    ) {
      return reject("Refusing to scale pathological request pattern");
    }
  }

  if (
    action.capability === "restart_service" &&
    (evidence.replicas === undefined || evidence.replicas < 2)
  ) {
    return reject("Restart could remove last healthy replica");
  }

  if (
    evidence.rootTarget &&
    action.params.target !== evidence.rootTarget &&
    action.capability !== "open_circuit"
  ) {
    return reject("Action target differs from identified root cause");
  }

  return { allowed: true };
}
