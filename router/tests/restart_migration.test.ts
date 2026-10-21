import { expect, test } from "vitest";
import { DatabaseSync } from "node:sqlite";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ActionStore } from "../src/storage/action-store.js";

test("migrates legacy SQLite without losing action records", () => {
  const dir = mkdtempSync(join(tmpdir(), "nanoclaw-migration-"));
  const path = join(dir, "actions.sqlite");

  try {
    const legacy = new DatabaseSync(path);

    legacy.exec(`
      CREATE TABLE action_claims (
        action_id TEXT PRIMARY KEY NOT NULL,
        capability TEXT NOT NULL,
        target TEXT NOT NULL,
        status TEXT NOT NULL
          CHECK (status IN ('CLAIMED', 'EXECUTED', 'FAILED')),
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
      );
    `);

    legacy.prepare(`
      INSERT INTO action_claims
        (action_id, capability, target, status, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?)
    `).run(
      "legacy-action",
      "scale_service",
      "selfheal-svc-api",
      "EXECUTED",
      Date.now(),
      Date.now(),
    );

    legacy.close();

    const store = new ActionStore(path);

    expect(store.getStatus("legacy-action")).toBe("EXECUTED");
    expect(
      store.claim("legacy-action", "scale_service", "selfheal-svc-api")
    ).toBe("DUPLICATE");

    expect(
      store.claim("new-action", "scale_service", "selfheal-svc-api")
    ).toBe("CLAIMED");

    store.beginExecution("new-action");
    store.needsReconciliation("new-action");

    expect(store.getStatus("new-action"))
      .toBe("NEEDS_RECONCILIATION");

    store.close();
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("detects unresolved targets after process-style restart", () => {
  const dir = mkdtempSync(join(tmpdir(), "nanoclaw-restart-"));
  const path = join(dir, "actions.sqlite");

  try {
    const first = new ActionStore(path);

    first.claim(
      "uncertain-action",
      "scale_service",
      "selfheal-svc-worker",
    );
    first.reserveBudget(
      "uncertain-action",
      "selfheal-svc-worker",
    );
    first.beginExecution("uncertain-action");
    first.close();

    const restarted = new ActionStore(path);

    expect(restarted.getStatus("uncertain-action"))
      .toBe("EXECUTING");

    expect(restarted.getPendingRecoveryTargets())
      .toContain("selfheal-svc-worker");

    expect(() =>
      restarted.reserveBudget(
        "another-action",
        "selfheal-svc-worker",
      )
    ).toThrow("target_mutex_locked");

    restarted.close();
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
