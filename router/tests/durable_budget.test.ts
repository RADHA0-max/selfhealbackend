import { expect, it } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ActionStore } from "../src/storage/action-store.js";

it("preserves cooldown across database reopen", () => {
  const dir = mkdtempSync(join(tmpdir(), "nanoclaw-budget-"));
  const path = join(dir, "actions.sqlite");

  try {
    const first = new ActionStore(path);
    first.reserveBudget("action-1", "selfheal-svc-api");
    first.releaseBudget("action-1");
    first.close();

    const second = new ActionStore(path);

    expect(() =>
      second.reserveBudget("action-2", "selfheal-svc-api")
    ).toThrow("target_cooldown_active");

    second.close();
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

it("blocks simultaneous target reservations across instances", () => {
  const dir = mkdtempSync(join(tmpdir(), "nanoclaw-mutex-"));
  const path = join(dir, "actions.sqlite");

  try {
    const first = new ActionStore(path);
    const second = new ActionStore(path);

    first.reserveBudget("action-1", "selfheal-svc-api");

    expect(() =>
      second.reserveBudget("action-2", "selfheal-svc-api")
    ).toThrow("target_mutex_locked");

    first.releaseBudget("action-1");

    second.close();
    first.close();
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
