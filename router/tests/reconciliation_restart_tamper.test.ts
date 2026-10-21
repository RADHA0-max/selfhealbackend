import { expect, test } from "vitest";
import { mkdtempSync, rmSync, writeFileSync, unlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { ActionStore } from "../src/storage/action-store.js";
import { ReconciliationService } from "../src/recovery/reconciliation.js";
import { verifyAuditLedger } from "../src/audit-ledger.js";

test("restart and tampered audit cannot release reconciliation lock", async () => {
  const dir = mkdtempSync(join(tmpdir(), "nanoclaw-restart-tamper-"));
  const db = join(dir, "actions.sqlite");
  const ledger = join(dir, "audit.jsonl");
  const id = "restart-tamper-action";
  const target = "selfheal-svc-api";

  let store: ActionStore | undefined;

  try {
    store = new ActionStore(db);

    store.claim(id, "scale_service", target);
    store.reserveBudget(id, target);
    store.beginExecution(id);
    store.needsReconciliation(id);
    store.resolveReconciliation(id);

    expect(store.getPendingReconciliationAudits()).toEqual([id]);
    expect(store.getPendingRecoveryTargets()).toContain(target);

    // Simulate process restart.
    store.close();
    store = undefined;
    store = new ActionStore(db);

    expect(store.getStatus(id)).toBe("RECONCILED");
    expect(store.getPendingReconciliationAudits()).toEqual([id]);
    expect(store.getPendingRecoveryTargets()).toContain(target);

    const service = new ReconciliationService(
      store,
      ledger,
      { async authorize() { return true; } },
      { async verifySafeState() { return true; } },
    );

    // Corrupt ledger: recovery must fail closed.
    writeFileSync(ledger, "tampered\n");

    await expect(
      service.recoverPendingCompletions(),
    ).rejects.toThrow("audit_integrity_failure");

    expect(store.getPendingReconciliationAudits()).toEqual([id]);
    expect(store.getPendingRecoveryTargets()).toContain(target);

    expect(() =>
      store!.reserveBudget("blocked-action", target),
    ).toThrow("target_mutex_locked");

    // Restore the test fixture to a valid empty ledger.
    // This is NOT an operational procedure for repairing a real audit ledger.
    unlinkSync(ledger);

    expect(await service.recoverPendingCompletions()).toBe(1);

    expect(store.getPendingReconciliationAudits()).toEqual([]);
    expect(store.getPendingRecoveryTargets()).not.toContain(target);

    const verification = await verifyAuditLedger(ledger);
    expect(verification.ok).toBe(true);

    // Target lock released, but cooldown history remains.
    expect(() =>
      store!.reserveBudget("cooldown-action", target),
    ).toThrow("target_cooldown_active");
  } finally {
    store?.close();
    rmSync(dir, { recursive: true, force: true });
  }
});
