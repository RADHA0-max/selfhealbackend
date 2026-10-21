import { expect, test } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { TrustedRouter } from "../src/trusted-router.js";
import { ActionStore } from "../src/storage/action-store.js";
import {
  DockerBackend,
  type DockerAdapter,
  type DockerTarget,
} from "../src/backends/docker-backend.js";

async function setup(initialReplicas = 2) {
  const dir = mkdtempSync(join(tmpdir(), "nanoclaw-e2e-"));
  const ledger = join(dir, "audit.jsonl");
  const database = join(dir, "actions.sqlite");

  let replicas = initialReplicas;
  let scaleCalls = 0;

  const adapter: DockerAdapter = {
    async inspectService(target: DockerTarget) {
      return { name: target, replicas };
    },

    async scaleService(_target: DockerTarget, desired: number) {
      scaleCalls++;
      replicas = desired;
    },
  };

  const backend = new DockerBackend(adapter);
  const router = new TrustedRouter(backend, ledger, database);
  await router.initialize();

  return {
    router,
    database,
    get replicas() {
      return replicas;
    },
    get scaleCalls() {
      return scaleCalls;
    },
    close() {
      router.close();
      rmSync(dir, { recursive: true, force: true });
    },
  };
}

function action(target = "selfheal-svc-api", replicas = 3) {
  return {
    capability: "scale_service",
    params: { target, replicas },
  };
}

function evidence(target = "selfheal-svc-api") {
  return {
    cause: "organic",
    rootTarget: target,
    ipConcentration: 0.2,
    tailRatio: 2,
    rps: 500,
    rpsBaseline: 200,
    observedAt: Date.now(),
  };
}

test("trusted router executes verified DockerBackend scale", async () => {
  const env = await setup();

  try {
    const result = await env.router.execute(
      action(),
      evidence(),
      "docker-e2e-success",
    );

    expect(result.status).toBe("EXECUTED");
    expect(env.replicas).toBe(3);
    expect(env.scaleCalls).toBe(1);

    const store = new ActionStore(env.database);

    expect(store.getStatus("docker-e2e-success"))
      .toBe("EXECUTED");

    store.close();
  } finally {
    env.close();
  }
});

test("duplicate action never scales twice", async () => {
  const env = await setup();

  try {
    const first = await env.router.execute(
      action(),
      evidence(),
      "docker-e2e-duplicate",
    );

    const second = await env.router.execute(
      action(),
      evidence(),
      "docker-e2e-duplicate",
    );

    expect(first.status).toBe("EXECUTED");
    expect(second.status).toBe("REJECTED");
    expect(env.scaleCalls).toBe(1);
  } finally {
    env.close();
  }
});

test("untrusted target cannot reach Docker adapter", async () => {
  const env = await setup();

  try {
    const result = await env.router.execute(
      action("untrusted-container"),
      evidence(),
      "docker-e2e-attack",
    );

    expect(result.status).toBe("REJECTED");
    expect(env.scaleCalls).toBe(0);
  } finally {
    env.close();
  }
});

test("mismatched root cause cannot reach Docker adapter", async () => {
  const env = await setup();

  try {
    const result = await env.router.execute(
      action("selfheal-svc-api"),
      evidence("selfheal-svc-db"),
      "docker-e2e-cause",
    );

    expect(result.status).toBe("REJECTED");
    expect(env.scaleCalls).toBe(0);
  } finally {
    env.close();
  }
});

test("Docker verification failure requires reconciliation", async () => {
  const dir = mkdtempSync(join(tmpdir(), "nanoclaw-e2e-failure-"));
  const ledger = join(dir, "audit.jsonl");
  const database = join(dir, "actions.sqlite");

  const adapter: DockerAdapter = {
    async inspectService(target) {
      return { name: target, replicas: 2 };
    },
    async scaleService() {
      // Simulate an accepted command without observed state change.
    },
  };

  const router = new TrustedRouter(
    new DockerBackend(adapter),
    ledger,
    database,
  );
  await router.initialize();

  try {
    const result = await router.execute(
      action(),
      evidence(),
      "docker-e2e-failure",
    );

    expect(result.status).toBe("REJECTED");

    const store = new ActionStore(database);

    expect(store.getStatus("docker-e2e-failure"))
      .toBe("NEEDS_RECONCILIATION");

    expect(store.getPendingRecoveryTargets())
      .toContain("selfheal-svc-api");

    expect(() =>
      store.reserveBudget(
        "docker-e2e-next",
        "selfheal-svc-api",
      ),
    ).toThrow("target_mutex_locked");

    store.close();
  } finally {
    router.close();
    rmSync(dir, { recursive: true, force: true });
  }
});
