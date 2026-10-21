import { afterEach, expect, it } from "vitest";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { TrustedRouter } from "../src/trusted-router.js";

const routers: TrustedRouter[] = [];
const dirs: string[] = [];

afterEach(async () => {
  for (const router of routers.splice(0)) router.close();
  for (const dir of dirs.splice(0)) {
    await rm(dir, { recursive: true, force: true });
  }
});

it("does not execute the same action ID twice", async () => {
  const dir = await mkdtemp(join(tmpdir(), "nanoclaw-idempotency-"));
  dirs.push(dir);

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
  routers.push(router);

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

  const actionId = "incident-123-action-1";

  const first = await router.execute(action, evidence, actionId);
  const second = await router.execute(action, evidence, actionId);

  expect(first.status).toBe("EXECUTED");
  expect(second.status).toBe("REJECTED");
  expect(backendCalls).toBe(1);
});
