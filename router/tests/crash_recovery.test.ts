import { expect, it } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ActionStore } from "../src/storage/action-store.js";
import { TrustedRouter } from "../src/trusted-router.js";

it("keeps target locked after uncertain backend failure", async () => {
  const dir = mkdtempSync(join(tmpdir(), "nanoclaw-recovery-"));
  const ledgerPath = join(dir, "audit.jsonl");
  const dbPath = join(dir, "actions.sqlite");

  const router = new TrustedRouter(
    {
      async scaleService() {
        throw new Error("Backend connection lost");
      },
    },
    ledgerPath,
    dbPath,
  );
  await router.initialize();

  try {
    const action = {
      capability: "scale_service",
      params: {
        target: "selfheal-svc-api",
        replicas: 3,
      },
    };

    const evidence = {
      cause: "organic",
      rootTarget: "selfheal-svc-api",
      ipConcentration: 0.2,
      tailRatio: 2,
      rps: 500,
      rpsBaseline: 200,
      observedAt: Date.now(),
    };

    const result = await router.execute(
      action,
      evidence,
      "recovery-action-1",
    );

    expect(result.status).toBe("REJECTED");

    const store = new ActionStore(dbPath);

    expect(store.getStatus("recovery-action-1"))
      .toBe("NEEDS_RECONCILIATION");

    expect(() =>
      store.reserveBudget("recovery-action-2", "selfheal-svc-api")
    ).toThrow("target_mutex_locked");

    store.close();
  } finally {
    router.close();
    rmSync(dir, { recursive: true, force: true });
  }
});
