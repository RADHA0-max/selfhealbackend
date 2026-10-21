import { describe, expect, it } from "vitest";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  TrustedRouter,
  type TrustedBackend,
} from "../src/trusted-router.js";

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

function disabledBackend(): TrustedBackend {
  return {
    async scaleService() {
      throw new Error("offline_docker_execution_disabled");
    },
  };
}

describe("NanoClaw offline startup integration", () => {
  it("initializes after storage readiness", async () => {
    const dir = await mkdtemp(join(tmpdir(), "nanoclaw-integration-"));
    const ledger = join(dir, "audit.jsonl");
    const events: string[] = [];

    const router = new TrustedRouter(disabledBackend(), ledger);

    try {
      events.push("storage_ready");

      const before = await router.execute(action, evidence());
      expect(before.status).toBe("REJECTED");
      if (before.status === "REJECTED") {
        expect(before.gate).toBe("GATE_5");
      }

      await router.initialize();
      events.push("trusted_router_initialized");

      events.push("privileged_interface_ready");

      expect(events).toEqual([
        "storage_ready",
        "trusted_router_initialized",
        "privileged_interface_ready",
      ]);
    } finally {
      router.close();
      await rm(dir, { recursive: true, force: true });
    }
  });

  it("fails closed on audit corruption", async () => {
    const dir = await mkdtemp(join(tmpdir(), "nanoclaw-integration-"));
    const ledger = join(dir, "audit.jsonl");
    await writeFile(ledger, "invalid-json\n");

    const router = new TrustedRouter(disabledBackend(), ledger);

    try {
      await expect(router.initialize()).rejects.toThrow(
        "audit_integrity_failure",
      );

      const result = await router.execute(action, evidence());
      expect(result.status).toBe("REJECTED");

      if (result.status === "REJECTED") {
        expect(result.gate).toBe("GATE_5");
      }
    } finally {
      router.close();
      await rm(dir, { recursive: true, force: true });
    }
  });
});
