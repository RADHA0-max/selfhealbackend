import { describe, expect, it, vi } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  DockerBackend,
  ALLOWED_DOCKER_TARGETS,
  type DockerAdapter,
  type DockerTarget,
} from "../src/backends/docker-backend.js";
import { TrustedRouter } from "../src/trusted-router.js";

function mockAdapter(initial = 2) {
  let replicas = initial;

  const inspectService = vi.fn(async (target: DockerTarget) => ({
    name: target,
    replicas,
  }));

  const scaleService = vi.fn(
    async (_target: DockerTarget, desired: number) => {
      replicas = desired;
    },
  );

  const adapter: DockerAdapter = {
    inspectService,
    scaleService,
  };

  return { adapter, inspectService, scaleService };
}

function trustedEvidence(target: DockerTarget) {
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

describe("Person 2 — DockerAdapter offline contract", () => {
  it.each(ALLOWED_DOCKER_TARGETS)(
    "inspects and scales allowed target %s",
    async (target) => {
      const mock = mockAdapter();
      const backend = new DockerBackend(mock.adapter);

      await backend.scaleService(target, 3);

      expect(mock.inspectService).toHaveBeenCalledTimes(2);
      expect(mock.scaleService).toHaveBeenCalledExactlyOnceWith(
        target,
        3,
      );
    },
  );

  it.each([1, 2, 3, 4, 5])(
    "accepts supported replica count %i",
    async (replicas) => {
      const mock = mockAdapter();
      await new DockerBackend(mock.adapter).scaleService(
        "selfheal-svc-api",
        replicas,
      );

      expect(mock.inspectService).toHaveBeenCalled();
    },
  );

  it.each([0, -1, 6, 8, 1.5, NaN])(
    "rejects unsupported replica count %s",
    async (replicas) => {
      const mock = mockAdapter();

      await expect(
        new DockerBackend(mock.adapter).scaleService(
          "selfheal-svc-api",
          replicas,
        ),
      ).rejects.toThrow("invalid_replica_count");

      expect(mock.scaleService).not.toHaveBeenCalled();
    },
  );

  it("rejects unapproved Docker target", async () => {
    const mock = mockAdapter();

    await expect(
      new DockerBackend(mock.adapter).scaleService(
        "untrusted-service",
        3,
      ),
    ).rejects.toThrow("docker_target_not_allowlisted");

    expect(mock.inspectService).not.toHaveBeenCalled();
    expect(mock.scaleService).not.toHaveBeenCalled();
  });

  it("rejects failed post-scale verification", async () => {
    const adapter: DockerAdapter = {
      inspectService: vi.fn(async (target) => ({
        name: target,
        replicas: 2,
      })),
      scaleService: vi.fn(async () => {}),
    };

    await expect(
      new DockerBackend(adapter).scaleService(
        "selfheal-svc-api",
        3,
      ),
    ).rejects.toThrow("docker_scale_verification_failed");
  });
});

describe("Person 2 — privileged execution boundary", () => {
  it("rejects diagnosis output and restart_service", async () => {
    const dir = mkdtempSync(join(tmpdir(), "person2-contract-"));
    const mock = mockAdapter();
    const router = new TrustedRouter(
      new DockerBackend(mock.adapter),
      join(dir, "audit.jsonl"),
    );

    try {
      await router.initialize();

      const diagnosis = {
        root_cause: "api",
        action: "clear_fault",
        target: "api",
        reason: "Observed service failure",
      };

      const diagnosisResult = await router.execute(
        diagnosis,
        trustedEvidence("selfheal-svc-api"),
      );

      expect(diagnosisResult).toMatchObject({
        status: "REJECTED",
        gate: "GATE_1",
      });

      const restartResult = await router.execute(
        {
          capability: "restart_service",
          params: {
            target: "selfheal-svc-api",
            grace_period_s: 30,
          },
        },
        trustedEvidence("selfheal-svc-api"),
      );

      expect(restartResult).toMatchObject({
        status: "REJECTED",
        gate: "GATE_1",
      });

      expect(mock.scaleService).not.toHaveBeenCalled();
    } finally {
      router.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("rejects privileged action without trusted evidence", async () => {
    const dir = mkdtempSync(join(tmpdir(), "person2-evidence-"));
    const mock = mockAdapter();
    const router = new TrustedRouter(
      new DockerBackend(mock.adapter),
      join(dir, "audit.jsonl"),
    );

    try {
      await router.initialize();

      const result = await router.execute(
        {
          capability: "scale_service",
          params: {
            target: "selfheal-svc-api",
            replicas: 3,
          },
        },
        undefined,
      );

      expect(result).toMatchObject({
        status: "REJECTED",
        gate: "GATE_5B",
      });

      expect(mock.scaleService).not.toHaveBeenCalled();
    } finally {
      router.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
