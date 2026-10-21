import { expect, test } from "vitest";
import { CAPABILITIES } from "../src/schemas/registry.js";

const target = "selfheal-svc-api";

test("scale_service accepts approved replica bounds", () => {
  for (const replicas of [1, 2, 3, 4, 5]) {
    expect(
      CAPABILITIES.scale_service.params.safeParse({
        target,
        replicas,
      }).success,
    ).toBe(true);
  }
});

test("scale_service rejects unsupported replica counts", () => {
  for (const replicas of [0, 6, 8, -1, 1.5]) {
    expect(
      CAPABILITIES.scale_service.params.safeParse({
        target,
        replicas,
      }).success,
    ).toBe(false);
  }
});
