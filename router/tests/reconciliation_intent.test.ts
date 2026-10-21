import { expect, test } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  appendAuditEvent,
  verifyAuditLedger,
} from "../src/audit-ledger.js";

import { ActionStore } from "../src/storage/action-store.js";
import { ReconciliationService } from "../src/recovery/reconciliation.js";

test("reconciliation intent is a valid hash-chained audit event", async () => {
  const dir = mkdtempSync(join(tmpdir(), "nanoclaw-intent-"));
  const ledger = join(dir, "audit.jsonl");

  try {
    await appendAuditEvent(ledger, {
      eventType: "reconciliation_intent",
      actionId: "intent-test",
      capability: "scale_service",
      outcome: "verification_passed",
    });

    const result = await verifyAuditLedger(ledger);

    expect(result.ok).toBe(true);
    expect(result.entries).toBe(1);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("failed verification leaves action unresolved and locked", async () => {
  const dir = mkdtempSync(join(tmpdir(), "nanoclaw-intent-fail-"));
  const db = join(dir, "actions.sqlite");
  const ledger = join(dir, "audit.jsonl");

  const store = new ActionStore(db);
  const id = "intent-failure";
  const target = "selfheal-svc-api";

  try {
    store.claim(id, "scale_service", target);
    store.reserveBudget(id, target);
    store.beginExecution(id);
    store.needsReconciliation(id);

    const service = new ReconciliationService(
      store,
      ledger,
      {
        async authorize() {
          return true;
        },
      },
      {
        async verifySafeState() {
          return false;
        },
      },
    );

    await expect(
      service.reconcile(id, "trusted-operator"),
    ).rejects.toThrow("backend_state_not_verified");

    expect(store.getStatus(id)).toBe("NEEDS_RECONCILIATION");

    expect(() =>
      store.reserveBudget("second-action", target),
    ).toThrow("target_mutex_locked");
  } finally {
    store.close();
    rmSync(dir, { recursive: true, force: true });
  }
});
