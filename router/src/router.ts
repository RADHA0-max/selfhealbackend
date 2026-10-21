import { z } from "zod";
import { CAPABILITIES } from "./schemas/registry.js";

const ActionPlanSchema = z.object({
  capability: z.string().min(1),
  params: z.unknown(),
}).strict();

export function processActionPlan(payload: unknown) {
  // GATE 1: Strict top-level ActionPlan shape.
  const actionPlan = ActionPlanSchema.safeParse(payload);
  if (!actionPlan.success) {
    return { status: "REJECTED", gate: "GATE_1", detail: actionPlan.error.message };
  }
  payload = actionPlan.data;

  // GATE 2: Allowlist - Capability must exist in our registry
  if (!Object.prototype.hasOwnProperty.call(CAPABILITIES, actionPlan.data.capability)) {
    return { status: "REJECTED", gate: "GATE_2", detail: `Capability '${actionPlan.data.capability}' does not exist` };
  }

  const capDef = CAPABILITIES[actionPlan.data.capability as keyof typeof CAPABILITIES];

  // Validate against the strict capability schema first.
  const parseResult = capDef.params.safeParse(actionPlan.data.params);

  if (!parseResult.success) {
    const issues = parseResult.error.issues;
    const targetIssue = issues.some(issue => issue.path[0] === "target");

    // GATE 4: Target must be present in the capability's schema allowlist.
    if (targetIssue) {
      return { status: "REJECTED", gate: "GATE_4", detail: parseResult.error.message };
    }

    // GATE 3: Numeric bounds.
    const isBoundsError = issues.some(
      issue => issue.code === z.ZodIssueCode.too_small || issue.code === z.ZodIssueCode.too_big
    );

    if (isBoundsError) {
      return { status: "REJECTED", gate: "GATE_3", detail: parseResult.error.message };
    }

    // GATE 1: Shape, type, and strict-schema errors.
    return { status: "REJECTED", gate: "GATE_1", detail: parseResult.error.message };
  }

  // GATE 6: Review-only capabilities must never receive automatic approval.
  if (capDef.risk === "review_only") {
    return {
      status: "REJECTED",
      gate: "GATE_6",
      detail: "Capability requires external review; automatic approval is prohibited",
    };
  }

  // FAIL CLOSED: schema validation alone cannot authorize execution.
  // Gates 5 (blast radius) and 5b (cause coherence) require trusted evidence
  // that this router does not currently receive or validate.
  return {
    status: "REJECTED",
    gate: "GATE_5",
    detail: "Execution approval disabled: trusted blast-radius and cause-coherence checks are not implemented",
  };
}
