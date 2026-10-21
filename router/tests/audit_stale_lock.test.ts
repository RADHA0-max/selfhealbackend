import { expect, test } from "vitest";
import { mkdtemp, open, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { appendAuditEvent, verifyAuditLedger } from "../src/audit-ledger.js";

test("existing audit lock blocks writes without deleting the lock", async () => {
  const dir = await mkdtemp(join(tmpdir(), "nanoclaw-lock-"));
  const ledger = join(dir, "audit.jsonl");
  const lockPath = `${ledger}.lock`;

  try {
    const lock = await open(lockPath, "wx", 0o600);
    try {
      await lock.writeFile("999999\n");
      await lock.sync();
    } finally {
      await lock.close();
    }

    await expect(
      appendAuditEvent(ledger, {
        eventType: "gate_reject",
        actionId: "stale-lock-test",
        outcome: "rejected",
      }),
    ).rejects.toThrow("audit_lock_timeout");

    expect(await readFile(lockPath, "utf8")).toBe("999999\n");

    const verification = await verifyAuditLedger(ledger);
    expect(verification.ok).toBe(true);
    expect(verification.entries).toBe(0);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}, 15_000);
