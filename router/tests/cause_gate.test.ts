import { describe, expect, it } from "vitest";
import { checkCauseCoherence } from "../src/security/cause-gate.js";

describe("Gate 5b — Cause coherence", () => {
  const scale = {
    capability: "scale_service",
    params: { target: "selfheal-svc-api", replicas: 3 },
  };

  it("allows scaling for organic traffic", () => {
    expect(
      checkCauseCoherence(scale, {
        cause: "organic",
        ipConcentration: 0.2,
        rootTarget: "selfheal-svc-api",
      }),
    ).toEqual({ allowed: true });
  });

  it("rejects scaling during attack traffic", () => {
    expect(
      checkCauseCoherence(scale, {
        cause: "attack_or_bot",
      }).allowed,
    ).toBe(false);
  });

  it("rejects scaling concentrated traffic", () => {
    expect(
      checkCauseCoherence(scale, {
        cause: "organic",
        ipConcentration: 0.95,
      }),
    ).toMatchObject({
      allowed: false,
      gate: "GATE_5B",
    });
  });

  it("rejects scaling for pathological latency", () => {
    expect(
      checkCauseCoherence(scale, {
        cause: "organic",
        tailRatio: 25,
        rps: 100,
        rpsBaseline: 100,
      }).allowed,
    ).toBe(false);
  });

  it("rejects mismatched root-cause targets", () => {
    expect(
      checkCauseCoherence(scale, {
        cause: "organic",
        rootTarget: "selfheal-svc-db",
      }).allowed,
    ).toBe(false);
  });

  it("rejects unknown causes", () => {
    expect(
      checkCauseCoherence(scale, {
        cause: "invalid_cause" as never,
      }).allowed,
    ).toBe(false);
  });
});
