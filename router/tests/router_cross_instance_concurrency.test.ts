import { expect, test } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ActionStore } from "../src/storage/action-store.js";
import { TrustedRouter } from "../src/trusted-router.js";

test("two routers sharing SQLite cannot execute the same target concurrently", async () => {
  const dir = mkdtempSync(join(tmpdir(), "nanoclaw-cross-router-"));
  const database = join(dir, "actions.sqlite");
  const ledger = join(dir, "audit.jsonl");
  const target = "selfheal-svc-api";

  let backendCalls = 0;
  let releaseBackend!: () => void;
  let signalStarted!: () => void;

  const started = new Promise<void>((resolve) => {
    signalStarted = resolve;
  });
  const blocker = new Promise<void>((resolve) => {
    releaseBackend = resolve;
  });

  const backend = {
    async scaleService() {
      backendCalls++;
      signalStarted();
      await blocker;
    },
  };

  const first = new TrustedRouter(backend, ledger, database);
  const second = new TrustedRouter(backend, ledger, database);

  const action = {
    capability: "scale_service",
    params: { target, replicas: 3 },
  };

  const evidence = () => ({
    cause: "organic",
    rootTarget: target,
    ipConcentration: 0.2,
    tailRatio: 2,
    rps: 500,
    rpsBaseline: 200,
    observedAt: Date.now(),
  });

  try {
    await Promise.all([first.initialize(), second.initialize()]);

    const running = first.execute(action, evidence(), "router-one-action");
    await started;

    const competing = await second.execute(
      action,
      evidence(),
      "router-two-action",
    );

    expect(competing.status).toBe("REJECTED");
    if (competing.status === "REJECTED") {
      expect(competing.gate).toBe("GATE_5");
    }
    expect(backendCalls).toBe(1);

    const store = new ActionStore(database);
    try {
      expect(store.getStatus("router-one-action")).toBe("EXECUTING");
      expect(store.getStatus("router-two-action")).toBeNull();
    } finally {
      store.close();
    }

    releaseBackend();
    expect((await running).status).toBe("EXECUTED");
    expect(backendCalls).toBe(1);
  } finally {
    releaseBackend();
    first.close();
    second.close();
    rmSync(dir, { recursive: true, force: true });
  }
});
