import { expect, test } from "vitest";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ActionStore } from "../src/storage/action-store.js";

test("SQLite prevents duplicate action IDs across restarts", async () => {
  const dir = await mkdtemp(join(tmpdir(), "nanoclaw-sqlite-"));
  const path = join(dir, "actions.db");

  try {
    const first = new ActionStore(path);

    expect(first.claim(
      "repair-123",
      "scale_service",
      "selfheal-svc-api",
    )).toBe("CLAIMED");

    first.beginExecution("repair-123");
    first.complete("repair-123");
    first.close();

    const second = new ActionStore(path);

    expect(second.claim(
      "repair-123",
      "scale_service",
      "selfheal-svc-api",
    )).toBe("DUPLICATE");

    expect(second.getStatus("repair-123")).toBe("EXECUTED");

    second.close();
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test("SQLite prevents duplicate claims from two connections", async () => {
  const dir = await mkdtemp(join(tmpdir(), "nanoclaw-sqlite-"));
  const path = join(dir, "actions.db");

  const first = new ActionStore(path);
  const second = new ActionStore(path);

  try {
    const results = [
      first.claim("repair-456", "scale_service", "selfheal-svc-api"),
      second.claim("repair-456", "scale_service", "selfheal-svc-api"),
    ];

    expect(results.sort()).toEqual(["CLAIMED", "DUPLICATE"]);
  } finally {
    first.close();
    second.close();
    await rm(dir, { recursive: true, force: true });
  }
});
