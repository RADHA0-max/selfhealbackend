import { describe, expect, it } from "vitest";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { TrustedRouter } from "../src/trusted-router.js";

const action = {
  capability: "scale_service",
  params: { target: "selfheal-svc-api", replicas: 3 },
};

function evidence() {
  return {
    cause: "organic",
    rootTarget: "selfheal-svc-api",
    ipConcentration: 0.2,
    tailRatio: 2,
    rps: 500,
    rpsBaseline: 200,
    observedAt: Date.now(),
  };
}

describe("startup recovery security", () => {
  it("blocks execution before initialization", async () => {
    const dir = await mkdtemp(join(tmpdir(), "nanoclaw-startup-"));
    let calls = 0;
    const router = new TrustedRouter(
      { async scaleService() { calls++; } },
      join(dir, "audit.jsonl"),
    );

    try {
      const result = await router.execute(action, evidence());

      expect(result.status).toBe("REJECTED");
      expect(calls).toBe(0);

      await router.initialize();

      const afterInit = await router.execute(action, evidence());
      expect(afterInit.status).toBe("EXECUTED");
      expect(calls).toBe(1);
    } finally {
      router.close();
      await rm(dir, { recursive: true, force: true });
    }
  });

  it("fails closed when ledger is corrupted", async () => {
    const dir = await mkdtemp(join(tmpdir(), "nanoclaw-startup-"));
    const ledger = join(dir, "audit.jsonl");
    await writeFile(ledger, '{"corrupted":true}\n');

    let calls = 0;
    const router = new TrustedRouter(
      { async scaleService() { calls++; } },
      ledger,
    );

    try {
      await expect(router.initialize()).rejects.toThrow(
        "audit_integrity_failure",
      );

      const result = await router.execute(action, evidence());

      expect(result.status).toBe("REJECTED");
      expect(calls).toBe(0);
    } finally {
      router.close();
      await rm(dir, { recursive: true, force: true });
    }
  });

  it("does not mark failed initialization as completed", async () => {
    const dir = await mkdtemp(join(tmpdir(), "nanoclaw-startup-"));
    const ledger = join(dir, "audit.jsonl");
    await writeFile(ledger, "invalid-json\n");

    const router = new TrustedRouter(
      { async scaleService() { throw new Error("must_not_execute"); } },
      ledger,
    );

    try {
      await expect(router.initialize()).rejects.toThrow(
        "audit_integrity_failure",
      );

      await expect(router.initialize()).rejects.toThrow(
        "audit_integrity_failure",
      );

      const result = await router.execute(action, evidence());
      expect(result.status).toBe("REJECTED");
    } finally {
      router.close();
      await rm(dir, { recursive: true, force: true });
    }
  });
});
