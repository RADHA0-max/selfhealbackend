import { randomUUID } from "node:crypto";
import { appendAuditEvent } from "./audit-ledger.js";
import { processActionPlan } from "./router.js";

export interface AuditedRouterResult {
  status: "REJECTED";
  gate: string;
  detail: string;
  audit: "RECORDED" | "FAILED";
}

function safeReasonCode(gate: string): string {
  switch (gate) {
    case "GATE_1":
      return "schema_rejected";
    case "GATE_2":
      return "capability_rejected";
    case "GATE_3":
      return "bounds_rejected";
    case "GATE_4":
      return "target_rejected";
    case "GATE_5":
      return "trusted_evidence_missing";
    case "GATE_6":
      return "approval_required";
    case "GATE_7":
      return "patch_bounds_rejected";
    default:
      return "action_rejected";
  }
}

export async function processActionPlanAudited(
  payload: unknown,
  ledgerPath: string,
): Promise<AuditedRouterResult> {
  const result = processActionPlan(payload);

  // Defensive fail-closed behavior: this wrapper must never authorize execution.
  if (result.status !== "REJECTED") {
    return {
      status: "REJECTED",
      gate: "GATE_5",
      detail: "Audited wrapper does not authorize execution",
      audit: "FAILED",
    };
  }

  let capability: string | undefined;
  if (
    payload !== null &&
    typeof payload === "object" &&
    !Array.isArray(payload)
  ) {
    const candidate = (payload as Record<string, unknown>).capability;
    if (
      typeof candidate === "string" &&
      /^[A-Za-z0-9_-]{1,80}$/.test(candidate)
    ) {
      capability = candidate;
    }
  }

  try {
    await appendAuditEvent(ledgerPath, {
      eventType: "gate_reject",
      actionId: randomUUID(),
      ...(capability ? { capability } : {}),
      gate: result.gate,
      reasonCode: safeReasonCode(result.gate),
      outcome: "rejected",
    });

    return { status: "REJECTED", gate: result.gate, detail: result.detail, audit: "RECORDED" };
  } catch {
    // Never expose ledger paths, filesystem errors, or payload content.
    return { status: "REJECTED", gate: result.gate, detail: result.detail, audit: "FAILED" };
  }
}
