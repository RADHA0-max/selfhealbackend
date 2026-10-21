import { expect, test } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { ActionStore } from "../src/storage/action-store.js";

function setup() {
  const dir = mkdtempSync(join(tmpdir(), "nanoclaw-crash-safe-"));
  const db = join(dir, "actions.sqlite");
  const store = new ActionStore(db);

  const id = "crash-safe-action";
  const target = "selfheal-svc-api";

  store.claim(id, "scale_service", target);
  store.reserveBudget(id, target);
  store.beginExecution(id);
  store.needsReconciliation(id);

  return {
    store,
    db,
    dir,
    id,
    target,
    close() {
      store.close();
      rmSync(dir, { recursive: true, force: true });
    },
  };
}

test("reconciliation rejects unknown action without unlocking", () => {
  const env = setup();

  try {
    expect(() =>
      env.store.resolveReconciliation("unknown-action"),
    ).toThrow("action_not_reconcilable");

    expect(env.store.getStatus(env.id))
      .toBe("NEEDS_RECONCILIATION");

    expect(env.store.getPendingRecoveryTargets())
      .toContain(env.target);
  } finally {
    env.close();
  }
});

test("reconciliation refuses missing active reservation", () => {
  const env = setup();

  try {
    env.store.releaseBudget(env.id);

    expect(() =>
      env.store.resolveReconciliation(env.id),
    ).toThrow("reconciliation_lock_missing");

    expect(env.store.getStatus(env.id))
      .toBe("NEEDS_RECONCILIATION");
  } finally {
    env.close();
  }
});

test("unresolved action and mutex survive SQLite restart", () => {
  const env = setup();

  try {
    env.store.close();

    const reopened = new ActionStore(env.db);

    try {
      expect(reopened.getStatus(env.id))
        .toBe("NEEDS_RECONCILIATION");

      expect(reopened.getPendingRecoveryTargets())
        .toContain(env.target);

      expect(() =>
        reopened.reserveBudget("second-action", env.target),
      ).toThrow("target_mutex_locked");
    } finally {
      reopened.close();
    }
  } finally {
    rmSync(env.dir, { recursive: true, force: true });
  }
});

test("successful reconciliation preserves cooldown history", () => {
  const env = setup();

  try {
    env.store.resolveReconciliation(env.id);

    expect(env.store.getStatus(env.id)).toBe("RECONCILED");

    // Pending audit must keep the target locked.
    expect(env.store.getPendingRecoveryTargets())
      .toContain(env.target);

    expect(env.store.getPendingReconciliationAudits())
      .toContain(env.id);

    expect(() =>
      env.store.reserveBudget("second-action", env.target),
    ).toThrow("target_mutex_locked");

    // Simulate confirmed audit delivery at the storage boundary.
    env.store.markReconciliationAuditDelivered(env.id);

    expect(env.store.getPendingRecoveryTargets())
      .not.toContain(env.target);

    expect(env.store.getPendingReconciliationAudits())
      .not.toContain(env.id);

    expect(() =>
      env.store.reserveBudget("second-action", env.target),
    ).toThrow("target_cooldown_active");
  } finally {
    env.close();
  }
});
