import { expect, test } from "vitest";
import {
  DockerBackend,
  type DockerAdapter,
  type DockerTarget,
} from "../src/backends/docker-backend.js";

function mockAdapter(initial = 2) {
  let current = initial;
  let calls = 0;

  const adapter: DockerAdapter = {
    async inspectService(target: DockerTarget) {
      return { name: target, replicas: current };
    },

    async scaleService(_target: DockerTarget, replicas: number) {
      calls++;
      current = replicas;
    },
  };

  return {
    adapter,
    get calls() {
      return calls;
    },
  };
}

test("scales an allowlisted service and verifies result", async () => {
  const mock = mockAdapter();
  const backend = new DockerBackend(mock.adapter);

  await backend.scaleService("selfheal-svc-api", 3);

  expect(mock.calls).toBe(1);
});

test("rejects non-allowlisted targets before adapter access", async () => {
  const mock = mockAdapter();
  const backend = new DockerBackend(mock.adapter);

  await expect(
    backend.scaleService("untrusted-container", 3),
  ).rejects.toThrow("docker_target_not_allowlisted");

  expect(mock.calls).toBe(0);
});

test("rejects invalid replica counts", async () => {
  const mock = mockAdapter();
  const backend = new DockerBackend(mock.adapter);

  for (const replicas of [0, -1, 6, 1.5, NaN]) {
    await expect(
      backend.scaleService("selfheal-svc-api", replicas),
    ).rejects.toThrow("invalid_replica_count");
  }

  expect(mock.calls).toBe(0);
});

test("rejects service identity mismatch", async () => {
  const adapter: DockerAdapter = {
    async inspectService() {
      return { name: "wrong-service", replicas: 2 };
    },
    async scaleService() {
      throw new Error("should_not_execute");
    },
  };

  const backend = new DockerBackend(adapter);

  await expect(
    backend.scaleService("selfheal-svc-api", 3),
  ).rejects.toThrow("docker_service_identity_mismatch");
});

test("fails closed when post-scale verification fails", async () => {
  const adapter: DockerAdapter = {
    async inspectService(target) {
      return { name: target, replicas: 2 };
    },
    async scaleService() {},
  };

  const backend = new DockerBackend(adapter);

  await expect(
    backend.scaleService("selfheal-svc-api", 3),
  ).rejects.toThrow("docker_scale_verification_failed");
});

test("does not scale when desired replicas already match", async () => {
  const mock = mockAdapter(3);
  const backend = new DockerBackend(mock.adapter);

  await backend.scaleService("selfheal-svc-api", 3);

  expect(mock.calls).toBe(0);
});
