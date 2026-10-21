import { describe, expect, it } from "vitest";
import { SafetyBudget } from "../src/security/safety-budget.js";

describe("Gate 5 — Safety Budget", () => {
  it("allows the first action", () => {
    const budget = new SafetyBudget();
    expect(budget.check("api")).toEqual({ allowed: true });
  });

  it("enforces target cooldown", async () => {
    const budget = new SafetyBudget();

    await budget.execute("api", async () => "ok");

    expect(budget.check("api")).toEqual({
      allowed: false,
      reason: "target_cooldown_active",
    });
  });

  it("enforces per-target budget", async () => {
    let time = 1000000;
    const budget = new SafetyBudget(undefined, () => time);

    for (let i = 0; i < 3; i++) {
      await budget.execute("api", async () => "ok");
      time += 91000;
    }

    expect(budget.check("api")).toEqual({
      allowed: false,
      reason: "target_budget_exceeded",
    });
  });

  it("enforces global budget", async () => {
    const budget = new SafetyBudget();

    for (let i = 0; i < 8; i++) {
      await budget.execute(`service-${i}`, async () => "ok");
    }

    expect(budget.check("another-service")).toEqual({
      allowed: false,
      reason: "global_budget_exceeded",
    });
  });

  it("prevents simultaneous actions on the same target", async () => {
    const budget = new SafetyBudget();

    let release!: () => void;
    const blocker = new Promise<void>(resolve => {
      release = resolve;
    });

    const running = budget.execute("api", async () => {
      await blocker;
    });

    expect(budget.check("api")).toEqual({
      allowed: false,
      reason: "target_mutex_locked",
    });

    release();
    await running;
  });

  it("releases mutex after failure", async () => {
    const budget = new SafetyBudget();

    await expect(
      budget.execute("api", async () => {
        throw new Error("backend failed");
      }),
    ).rejects.toThrow("backend failed");

    expect(budget.check("api").reason).toBe(
      "target_cooldown_active",
    );
  });
});
