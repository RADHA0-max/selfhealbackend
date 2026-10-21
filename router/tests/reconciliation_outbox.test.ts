import { expect, test } from "vitest";
import {
  mkdtempSync,
  rmSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { ActionStore } from "../src/storage/action-store.js";
import { ReconciliationService } from "../src/recovery/reconciliation.js";
import {
  appendAuditEvent,
  verifyAuditLedger,
} from "../src/audit-ledger.js";

function setup() {
  const dir = mkdtempSync(join(tmpdir(), "nanoclaw-outbox-"));
  const db = join(dir, "actions.sqlite");
  const ledger = join(dir, "audit.jsonl");
  const id = "outbox-action";
  const target = "selfheal-svc-api";

  const store = new ActionStore(db);

  store.claim(id, "scale_service", target);
  store.reserveBudget(id, target);
  store.beginExecution(id);
  store.needsReconciliation(id);

  return { dir, db, ledger, id, store };
}

function makeService(store: ActionStore, ledger: string) {
  return new ReconciliationService(
    store,
    ledger,
    { async authorize() { return true; } },
    { async verifySafeState() { return true; } },
  );
}

test("reconciliation commit creates pending outbox", () => {
  const env = setup();

  try {
    env.store.resolveReconciliation(env.id);

    expect(env.store.getStatus(env.id)).toBe("RECONCILED");
    expect(env.store.getPendingReconciliationAudits())
      .toEqual([env.id]);
  } finally {
    env.store.close();
    rmSync(env.dir, { recursive: true, force: true });
  }
});

test("pending completion survives SQLite restart", async () => {
  const env = setup();

  try {
    env.store.resolveReconciliation(env.id);
    env.store.close();

    const reopened = new ActionStore(env.db);

    try {
      expect(reopened.getPendingReconciliationAudits())
        .toEqual([env.id]);

      expect(
        await makeService(
          reopened,
          env.ledger,
        ).recoverPendingCompletions()
      ).toBe(1);

      expect(reopened.getPendingReconciliationAudits())
        .toEqual([]);

      expect((await verifyAuditLedger(env.ledger)).ok)
        .toBe(true);
    } finally {
      reopened.close();
    }
  } finally {
    rmSync(env.dir, { recursive: true, force: true });
  }
});

test("audit retry does not duplicate completion event", async () => {
  const env = setup();

  try {
    env.store.resolveReconciliation(env.id);

    await appendAuditEvent(env.ledger, {
      eventType: "reconciliation_intent",
      actionId: env.id,
      capability: "scale_service",
      outcome: "verification_passed",
    });

    await appendAuditEvent(env.ledger, {
      eventType: "reconciled",
      actionId: env.id,
      capability: "scale_service",
      outcome: "operator_verified",
    });

    await makeService(
      env.store,
      env.ledger,
    ).recoverPendingCompletions();

    const entries = readFileSync(env.ledger, "utf8")
      .trim()
      .split("\n")
      .map(line => JSON.parse(line));

    expect(
      entries.filter(
        row => row.event.eventType === "reconciled"
      )
    ).toHaveLength(1);

    expect(env.store.getPendingReconciliationAudits())
      .toEqual([]);
  } finally {
    env.store.close();
    rmSync(env.dir, { recursive: true, force: true });
  }
});

test("tampered ledger blocks recovery", async () => {
  const env = setup();

  try {
    env.store.resolveReconciliation(env.id);

    await appendAuditEvent(env.ledger, {
      eventType: "reconciliation_intent",
      actionId: env.id,
      capability: "scale_service",
      outcome: "verification_passed",
    });

    writeFileSync(env.ledger, "tampered\n");

    await expect(
      makeService(
        env.store,
        env.ledger,
      ).recoverPendingCompletions()
    ).rejects.toThrow("audit_integrity_failure");

    expect(env.store.getPendingReconciliationAudits())
      .toEqual([env.id]);
  } finally {
    env.store.close();
    rmSync(env.dir, { recursive: true, force: true });
  }
});
