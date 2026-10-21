import { appendAuditEvent, verifyAuditLedger } from "../audit-ledger.js";
import { ActionStore } from "../storage/action-store.js";

export interface ReconciliationAuthority {
  authorize(operatorId: string, actionId: string): Promise<boolean>;
}

export interface ReconciliationInspector {
  verifySafeState(actionId: string, target: string): Promise<boolean>;
}

export class ReconciliationService {
  constructor(
    private readonly store: ActionStore,
    private readonly ledgerPath: string,
    private readonly authority: ReconciliationAuthority,
    private readonly inspector: ReconciliationInspector,
  ) {}

  async reconcile(
    actionId: string,
    operatorId: string,
  ): Promise<void> {
    if (!/^[a-zA-Z0-9_-]{1,128}$/.test(actionId)) {
      throw new Error("invalid_action_id");
    }

    if (!/^[a-zA-Z0-9_-]{1,128}$/.test(operatorId)) {
      throw new Error("invalid_operator_id");
    }

    const approved = await this.authority.authorize(
      operatorId,
      actionId,
    );

    if (!approved) {
      throw new Error("reconciliation_unauthorized");
    }

    const actions = this.store.getUnresolvedActions();
    const action = actions.find(row => row.action_id === actionId);

    if (!action || action.status !== "NEEDS_RECONCILIATION") {
      throw new Error("action_not_reconcilable");
    }

    const verification = await verifyAuditLedger(this.ledgerPath);

    if (!verification.ok) {
      throw new Error("audit_integrity_failure");
    }

    const safe = await this.inspector.verifySafeState(
      actionId,
      action.target,
    );

    if (!safe) {
      throw new Error("backend_state_not_verified");
    }

    await appendAuditEvent(this.ledgerPath, {
      eventType: "reconciliation_intent",
      actionId,
      capability: "scale_service",
      outcome: "verification_passed",
    });

    this.store.resolveReconciliation(actionId);
    await this.publishPendingCompletion(actionId);
  }

  private async publishPendingCompletion(actionId: string): Promise<void> {
    if (!this.store.getPendingReconciliationAudits().includes(actionId)) {
      throw new Error("reconciliation_outbox_missing");
    }

    const verification = await verifyAuditLedger(this.ledgerPath);
    if (!verification.ok) {
      throw new Error("audit_integrity_failure");
    }

    await appendAuditEvent(this.ledgerPath, {
      eventType: "reconciled",
      actionId,
      capability: "scale_service",
      outcome: "operator_verified",
    });

    this.store.markReconciliationAuditDelivered(actionId);
  }

  async recoverPendingCompletions(): Promise<number> {
    const pending = this.store.getPendingReconciliationAudits();

    for (const actionId of pending) {
      await this.publishPendingCompletion(actionId);
    }

    return pending.length;
  }
}
