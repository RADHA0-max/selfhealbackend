import { expect, test } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { ActionStore } from "../src/storage/action-store.js";
import { ReconciliationService } from "../src/recovery/reconciliation.js";

function setup(authorized: boolean, safe: boolean) {
  const dir = mkdtempSync(join(tmpdir(), "nanoclaw-reconcile-"));
  const ledger = join(dir, "audit.jsonl");
  const db = join(dir, "actions.sqlite");

  const store = new ActionStore(db);
  const target = "selfheal-svc-api";
  const id = "reconcile-action";

  store.claim(id, "scale_service", target);
  store.reserveBudget(id, target);
  store.beginExecution(id);
  store.needsReconciliation(id);

  const service = new ReconciliationService(
    store,
    ledger,
    {
      async authorize() {
        return authorized;
      },
    },
    {
      async verifySafeState() {
        return safe;
      },
    },
  );

  return {
    store,
    service,
    target,
    id,
    close() {
      store.close();
      rmSync(dir, { recursive: true, force: true });
    },
  };
}

test("authorized verified reconciliation releases target lock", async () => {
  const env = setup(true, true);

  try {
    await env.service.reconcile(env.id, "trusted-operator");

    expect(env.store.getStatus(env.id)).toBe("RECONCILED");
    expect(env.store.getPendingRecoveryTargets()).not.toContain(env.target);

    expect(() =>
      env.store.reserveBudget("new-action", env.target)
    ).toThrow("target_cooldown_active");
  } finally {
    env.close();
  }
});

test("unauthorized reconciliation preserves lock", async () => {
  const env = setup(false, true);

  try {
    await expect(
      env.service.reconcile(env.id, "untrusted-operator"),
    ).rejects.toThrow("reconciliation_unauthorized");

    expect(env.store.getStatus(env.id))
      .toBe("NEEDS_RECONCILIATION");

    expect(() =>
      env.store.reserveBudget("new-action", env.target)
    ).toThrow("target_mutex_locked");
  } finally {
    env.close();
  }
});

test("unverified backend state preserves lock", async () => {
  const env = setup(true, false);

  try {
    await expect(
      env.service.reconcile(env.id, "trusted-operator"),
    ).rejects.toThrow("backend_state_not_verified");

    expect(env.store.getStatus(env.id))
      .toBe("NEEDS_RECONCILIATION");

    expect(() =>
      env.store.reserveBudget("new-action", env.target)
    ).toThrow("target_mutex_locked");
  } finally {
    env.close();
  }
});

test("cannot reconcile the same action twice", async () => {
  const env = setup(true, true);

  try {
    await env.service.reconcile(env.id, "trusted-operator");

    await expect(
      env.service.reconcile(env.id, "trusted-operator"),
    ).rejects.toThrow("action_not_reconcilable");
  } finally {
    env.close();
  }
});
