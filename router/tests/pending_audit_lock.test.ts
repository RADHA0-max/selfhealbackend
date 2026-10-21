import { expect, test } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { ActionStore } from "../src/storage/action-store.js";
import { ReconciliationService } from "../src/recovery/reconciliation.js";

test("pending reconciliation audit blocks target across restart", async () => {
  const dir = mkdtempSync(join(tmpdir(), "nanoclaw-audit-lock-"));
  const db = join(dir, "actions.sqlite");
  const ledger = join(dir, "audit.jsonl");
  const target = "selfheal-svc-api";
  const id = "pending-audit-action";

  let store: ActionStore | undefined;

  try {
    store = new ActionStore(db);
    store.claim(id, "scale_service", target);
    store.reserveBudget(id, target);
    store.beginExecution(id);
    store.needsReconciliation(id);

    store.resolveReconciliation(id);

    expect(store.getPendingReconciliationAudits()).toEqual([id]);

    store.close();
    store = new ActionStore(db);

    expect(store.getPendingReconciliationAudits()).toEqual([id]);

    // A fresh reservation must be blocked by the SQLite trigger.
    expect(() => {
      store!.reserveBudget("second-action", target);
    }).toThrow();

    const service = new ReconciliationService(
      store,
      ledger,
      { async authorize() { return true; } },
      { async verifySafeState() { return true; } },
    );

    expect(await service.recoverPendingCompletions()).toBe(1);
    expect(store.getPendingReconciliationAudits()).toEqual([]);

    // Existing cooldown can still block reservations here.
    // This assertion verifies the outbox was delivered, not cooldown expiry.
  } finally {
    store?.close();
    rmSync(dir, { recursive: true, force: true });
  }
});
