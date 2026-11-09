import { describe, expect, it } from "vitest";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { TrustedRouter } from "../src/trusted-router.js";
import { verifyAuditLedger } from "../src/audit-ledger.js";

describe("Trusted Router Integration", () => {
  it("executes a safe scale action and records audit events", async () => {
    const dir = await mkdtemp(join(tmpdir(), "nanoclaw-trusted-"));

    try {
      const calls: Array<{ target: string; replicas: number }> = [];

      const backend = {
        async scaleService(target: string, replicas: number) {
          calls.push({ target, replicas });
        },
      };

      const ledgerPath = join(dir, "audit.jsonl");
      const router = new TrustedRouter(backend, ledgerPath);
      await router.initialize();

      const result = await router.execute(
        {
          capability: "scale_service",
          params: { target: "selfheal-svc-api", replicas: 3 },
        },
        {
          cause: "organic",
          rootTarget: "selfheal-svc-api",
          ipConcentration: 0.2,
          tailRatio: 2,
          rps: 500,
          rpsBaseline: 200,
          observedAt: Date.now(),
        },
      );

      expect(result.status).toBe("EXECUTED");
      expect(calls).toEqual([
        { target: "selfheal-svc-api", replicas: 3 },
      ]);

      const audit = await verifyAuditLedger(ledgerPath);
      expect(audit.ok).toBe(true);
      expect(audit.entries).toBe(2);
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });

  it("rejects attack traffic without calling backend", async () => {
    const dir = await mkdtemp(join(tmpdir(), "nanoclaw-trusted-"));

    try {
      let backendCalls = 0;

      const router = new TrustedRouter(
        {
          async scaleService() {
            backendCalls++;
          },
        },
        join(dir, "audit.jsonl"),
      );
      await router.initialize();

      const result = await router.execute(
        {
          capability: "scale_service",
          params: { target: "selfheal-svc-api", replicas: 3 },
        },
        {
          cause: "organic",
          rootTarget: "selfheal-svc-api",
          ipConcentration: 0.95,
          tailRatio: 2,
          rps: 500,
          rpsBaseline: 200,
          observedAt: Date.now(),
        },
      );

      expect(result.status).toBe("REJECTED");
      expect(backendCalls).toBe(0);
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });
});

describe("Trusted Router concurrency safety", () => {
  it("rejects a second action on a target while the first is executing", async () => {
    const dir = await mkdtemp(join(tmpdir(), "nanoclaw-concurrency-"));
    const ledgerPath = join(dir, "audit.jsonl");

    let signalStarted!: () => void;
    const started = new Promise<void>((resolve) => {
      signalStarted = resolve;
    });

    let releaseBackend!: () => void;
    const blocker = new Promise<void>((resolve) => {
      releaseBackend = resolve;
    });

    let backendCalls = 0;

    const router = new TrustedRouter(
      {
        async scaleService() {
          backendCalls++;
          signalStarted();
          await blocker;
        },
      },
      ledgerPath,
    );

    try {
      await router.initialize();

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

      const first = router.execute(
        action,
        evidence,
        "concurrency-action-1",
      );

      await started;

      const second = await router.execute(
        action,
        evidence,
        "concurrency-action-2",
      );

      expect(second.status).toBe("REJECTED");
      expect(backendCalls).toBe(1);

      releaseBackend();

      const firstResult = await first;
      expect(firstResult.status).toBe("EXECUTED");

      const audit = await verifyAuditLedger(ledgerPath);
      expect(audit.ok).toBe(true);
      expect(audit.entries).toBe(2);
    } finally {
      releaseBackend();
      router.close();
      await rm(dir, { recursive: true, force: true });
    }
  });
});

describe("Trusted Router evidence security", () => {
  const action = {
    capability: "scale_service",
    params: { target: "selfheal-svc-api", replicas: 3 },
  };

  const validEvidence = () => ({
    cause: "organic",
    rootTarget: "selfheal-svc-api",
    ipConcentration: 0.2,
    tailRatio: 2,
    rps: 500,
    rpsBaseline: 200,
    observedAt: Date.now(),
  });

  const cases = [
    {
      name: "missing evidence",
      evidence: () => undefined,
    },
    {
      name: "injected evidence field",
      evidence: () => ({ ...validEvidence(), bypass: true }),
    },
    {
      name: "stale evidence",
      evidence: () => ({
        ...validEvidence(),
        observedAt: Date.now() - 120_000,
      }),
    },
    {
      name: "mismatched root target",
      evidence: () => ({
        ...validEvidence(),
        rootTarget: "selfheal-svc-db",
      }),
    },
  ];

  it.each(cases)("rejects $name before execution", async ({ evidence }) => {
    const dir = await mkdtemp(join(tmpdir(), "nanoclaw-evidence-"));
    let backendCalls = 0;

    const router = new TrustedRouter(
      {
        async scaleService() {
          backendCalls++;
        },
      },
      join(dir, "audit.jsonl"),
    );

    try {
      await router.initialize();

      const result = await router.execute(
        action,
        evidence(),
      );

      expect(result.status).toBe("REJECTED");

      if (result.status === "REJECTED") {
        expect(result.gate).toBe("GATE_5B");
      }

      expect(backendCalls).toBe(0);
    } finally {
      router.close();
      await rm(dir, { recursive: true, force: true });
    }
  });
});
