import { expect, test } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ActionStore } from "../src/storage/action-store.js";
import { TrustedRouter } from "../src/trusted-router.js";

test("restarted router never re-executes an unresolved target", async () => {
  const dir = mkdtempSync(join(tmpdir(), "nanoclaw-router-restart-"));
  const database = join(dir, "actions.sqlite");
  const ledger = join(dir, "audit.jsonl");
  const target = "selfheal-svc-api";
  const originalId = "interrupted-execution";
  let backendCalls = 0;

  const original = new ActionStore(database);
  try {
    expect(original.claim(originalId, "scale_service", target))
      .toBe("CLAIMED");
    original.reserveBudget(originalId, target);
    original.beginExecution(originalId);
  } finally {
    original.close();
  }

  const router = new TrustedRouter(
    {
      async scaleService() {
        backendCalls++;
      },
    },
    ledger,
    database,
  );

  try {
    await router.initialize();

    const result = await router.execute(
      {
        capability: "scale_service",
        params: { target, replicas: 3 },
      },
      {
        cause: "organic",
        rootTarget: target,
        ipConcentration: 0.2,
        tailRatio: 2,
        rps: 500,
        rpsBaseline: 200,
        observedAt: Date.now(),
      },
      "different-action-after-restart",
    );

    expect(result.status).toBe("REJECTED");
    if (result.status === "REJECTED") {
      expect(result.gate).toBe("GATE_5");
      expect(result.detail).toContain("reconciliation required");
    }
    expect(backendCalls).toBe(0);

    const reopened = new ActionStore(database);
    try {
      expect(reopened.getStatus(originalId)).toBe("EXECUTING");
      expect(reopened.getStatus("different-action-after-restart"))
        .toBeNull();
      expect(reopened.getPendingRecoveryTargets()).toContain(target);
      expect(() =>
        reopened.reserveBudget("another-action", target)
      ).toThrow("target_mutex_locked");
    } finally {
      reopened.close();
    }
  } finally {
    router.close();
    rmSync(dir, { recursive: true, force: true });
  }
});
