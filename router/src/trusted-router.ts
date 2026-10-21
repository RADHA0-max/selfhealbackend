import { randomUUID } from "node:crypto";
import { z } from "zod";
import { appendAuditEvent, verifyAuditLedger } from "./audit-ledger.js";
import { CAPABILITIES } from "./schemas/registry.js";
import { checkCauseCoherence } from "./security/cause-gate.js";
import { ActionStore } from "./storage/action-store.js";
import {
  ReconciliationService,
  type ReconciliationAuthority,
  type ReconciliationInspector,
} from "./recovery/reconciliation.js";

const Targets = [
  "selfheal-svc-api",
  "selfheal-svc-db",
  "selfheal-svc-worker",
  "selfheal-svc-auth",
] as const;

const EvidenceSchema = z.object({
  cause: z.enum(["organic", "load_proportional"]),
  rootTarget: z.enum(Targets),
  ipConcentration: z.number().finite().min(0).max(1),
  tailRatio: z.number().finite().nonnegative(),
  rps: z.number().finite().nonnegative(),
  rpsBaseline: z.number().finite().positive(),
  observedAt: z.number().int().nonnegative(),
}).strict();

export type TrustedEvidence = z.infer<typeof EvidenceSchema>;

export interface TrustedBackend {
  scaleService(target: string, replicas: number): Promise<void>;
}

export type TrustedResult =
  | { status: "EXECUTED"; actionId: string }
  | { status: "REJECTED"; gate: string; detail: string };

export class TrustedRouter {
  private readonly actionStore: ActionStore;
  private initialized = false;
  private initialization?: Promise<void>;

  constructor(
    private readonly backend: TrustedBackend,
    private readonly ledgerPath: string,
    actionStorePath = `${ledgerPath}.sqlite`,
  ) {
    this.actionStore = new ActionStore(actionStorePath);
  }

  async initialize(): Promise<void> {
    if (this.initialized) return;
    if (this.initialization) return this.initialization;

    this.initialization = (async () => {
      const verification = await verifyAuditLedger(this.ledgerPath);
      if (!verification.ok) {
        throw new Error("audit_integrity_failure");
      }

      // Startup only publishes already-approved reconciliation completions.
      // No operator authorization or backend safety check is bypassed here.
      const authority: ReconciliationAuthority = {
        async authorize() {
          return false;
        },
      };
      const inspector: ReconciliationInspector = {
        async verifySafeState() {
          return false;
        },
      };

      const recovery = new ReconciliationService(
        this.actionStore,
        this.ledgerPath,
        authority,
        inspector,
      );

      await recovery.recoverPendingCompletions();
      this.initialized = true;
    })();

    try {
      await this.initialization;
    } finally {
      this.initialization = undefined;
    }
  }

  async execute(
    payload: unknown,
    trustedEvidence: unknown,
    idempotencyKey = randomUUID(),
  ): Promise<TrustedResult> {
    const reject = (gate: string, detail: string): TrustedResult => ({
      status: "REJECTED",
      gate,
      detail,
    });

    if (!this.initialized) {
      return reject("GATE_5", "Router startup recovery not completed");
    }

    const evidence = EvidenceSchema.safeParse(trustedEvidence);

    if (!evidence.success) {
      return reject("GATE_5B", "Missing or invalid trusted evidence");
    }

    if (
      Math.abs(Date.now() - evidence.data.observedAt) > 60_000
    ) {
      return reject("GATE_5B", "Trusted evidence is stale");
    }

    const action = z.object({
      capability: z.literal("scale_service"),
      params: CAPABILITIES.scale_service.params,
    }).strict().safeParse(payload);

    if (!action.success) {
      return reject("GATE_1", "Invalid or unsupported action");
    }

    const { target, replicas } = action.data.params;

    if (target !== evidence.data.rootTarget) {
      return reject("GATE_5B", "Target does not match root cause");
    }

    const coherence = checkCauseCoherence(action.data, evidence.data);

    if (!coherence.allowed) {
      return reject("GATE_5B", coherence.reason);
    }

    let verification;

    try {
      verification = await verifyAuditLedger(this.ledgerPath);
    } catch {
      return reject("GATE_5", "Audit ledger verification failed");
    }

    if (!verification.ok) {
      return reject("GATE_5", "Audit ledger integrity failure");
    }

    try {
      const pendingTargets = this.actionStore.getPendingRecoveryTargets();

      if (pendingTargets.includes(target)) {
        return reject(
          "GATE_5",
          "Target has unresolved action; reconciliation required",
        );
      }
    } catch {
      return reject("GATE_5", "Recovery state unavailable");
    }

    let claim: "CLAIMED" | "DUPLICATE";

    try {
      claim = this.actionStore.claim(
        idempotencyKey,
        "scale_service",
        target,
      );
    } catch {
      return reject("GATE_5", "Could not reserve action in SQLite");
    }

    if (claim === "DUPLICATE") {
      return reject("GATE_5", "Duplicate action ID; execution blocked");
    }

    let backendStarted = false;
    let reserved = false;

    try {
      this.actionStore.reserveBudget(idempotencyKey, target);
      reserved = true;

      await appendAuditEvent(this.ledgerPath, {
        eventType: "tier_used",
        actionId: idempotencyKey,
        capability: "scale_service",
        tier: "TIER_1",
        outcome: "reserved",
      });

      this.actionStore.beginExecution(idempotencyKey);
      backendStarted = true;

      await this.backend.scaleService(target, replicas);

      await appendAuditEvent(this.ledgerPath, {
        eventType: "executed",
        actionId: idempotencyKey,
        capability: "scale_service",
        outcome: "executed",
      });

      this.actionStore.complete(idempotencyKey);
      this.actionStore.releaseBudget(idempotencyKey);

      return { status: "EXECUTED", actionId: idempotencyKey };
    } catch {
      if (backendStarted) {
        try {
          this.actionStore.needsReconciliation(idempotencyKey);
        } catch {
          // EXECUTING remains unresolved and must not be retried.
        }

        return reject(
          "GATE_5",
          "Execution outcome uncertain; manual reconciliation required",
        );
      }

      try {
        this.actionStore.fail(idempotencyKey);
      } catch {
        // Keep unresolved claim for inspection.
      }

      if (reserved) {
        try {
          this.actionStore.releaseBudget(idempotencyKey);
        } catch {
          // Keep fail-closed if release fails.
        }
      }

      return reject("GATE_5", "Pre-execution safety check failed");
    }
  }

  close(): void {
    this.actionStore.close();
  }
}
