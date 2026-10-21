import { createHash } from "node:crypto";
import { open, readFile, mkdir, stat, unlink } from "node:fs/promises";
import { resolve, dirname } from "node:path";

const GENESIS_HASH = "0".repeat(64);

const LOCK_TIMEOUT_MS = 10_000;
const LOCK_RETRY_MS = 25;

async function withAuditFileLock<T>(
  path: string,
  work: () => Promise<T>,
): Promise<T> {
  const lockPath = `${resolve(path)}.lock`;
  const started = Date.now();

  while (true) {
    let lock: Awaited<ReturnType<typeof open>> | undefined;

    try {
      lock = await open(lockPath, "wx", 0o600);

      try {
        await lock.writeFile(`${process.pid}\n`);
        await lock.sync();
        return await work();
      } finally {
        try {
          await lock.close();
        } finally {
          await unlink(lockPath);
        }
      }
    } catch (error) {
      if (lock) throw error;

      const code =
        error instanceof Error && "code" in error
          ? error.code
          : undefined;

      if (code !== "EEXIST") throw error;

      if (Date.now() - started > LOCK_TIMEOUT_MS) {
        throw new Error("audit_lock_timeout");
      }

      await new Promise((resolve) => setTimeout(resolve, LOCK_RETRY_MS));
    }
  }
}

async function syncParentDirectory(path: string): Promise<void> {
  const directory = await open(dirname(resolve(path)), "r");

  try {
    await directory.sync();
  } finally {
    await directory.close();
  }
}


// Serializes concurrent appends within this Node.js process, per resolved path.
const appendQueues = new Map<string, Promise<void>>();

const EVENT_TYPES = [
  "gate_reject", "executed", "verified", "rolled_back",
  "patch_validated", "patch_rejected", "pr_opened", "merged", "tier_used",
  "reconciliation_intent",
  "reconciled",
] as const;

type AuditEventType = (typeof EVENT_TYPES)[number];

export interface AuditEvent {
  eventType: AuditEventType;
  actionId?: string;
  capability?: string;
  gate?: string;
  reasonCode?: string;
  outcome?: string;
  tier?: string;
}

interface LedgerEntry {
  seq: number;
  timestamp: string;
  event: AuditEvent;
  prevHash: string;
  hash: string;
}

export interface LedgerVerification {
  ok: boolean;
  entries: number;
  headHash: string;
  error?: string;
}

const ALLOWED_FIELDS = new Set([
  "eventType", "actionId", "capability", "gate",
  "reasonCode", "outcome", "tier"
]);

function validateEvent(input: unknown): AuditEvent {
  if (input === null || typeof input !== "object" || Array.isArray(input)) {
    throw new Error("Audit event must be an object");
  }

  const raw = input as Record<string, unknown>;
  for (const key of Object.keys(raw)) {
    if (!ALLOWED_FIELDS.has(key)) throw new Error(`Unsupported audit field: ${key}`);
  }

  if (typeof raw.eventType !== "string" ||
      !EVENT_TYPES.includes(raw.eventType as AuditEventType)) {
    throw new Error("Unsupported audit event type");
  }

  const result: Record<string, string> = { eventType: raw.eventType };
  const patterns: Record<string, RegExp> = {
    actionId: /^[A-Za-z0-9._:-]{1,128}$/,
    capability: /^[A-Za-z0-9_-]{1,80}$/,
    gate: /^GATE_[1-7](?:B)?$/,
    reasonCode: /^[a-z][a-z0-9_]{0,79}$/,
    outcome: /^[a-z][a-z0-9_]{0,39}$/,
    tier: /^TIER_[1-3]$/
  };

  for (const [field, pattern] of Object.entries(patterns)) {
    const value = raw[field];
    if (value === undefined) continue;
    if (typeof value !== "string" || !pattern.test(value)) {
      throw new Error(`Invalid audit field: ${field}`);
    }
    result[field] = value;
  }

  return result as unknown as AuditEvent;
}

function hashEntry(entry: Omit<LedgerEntry, "hash">): string {
  return createHash("sha256").update(JSON.stringify(entry), "utf8").digest("hex");
}

async function readLedger(path: string): Promise<string> {
  try {
    return await readFile(path, "utf8");
  } catch (error) {
    if (
      error instanceof Error &&
      "code" in error &&
      error.code === "ENOENT"
    ) {
      return "";
    }
    throw error;
  }
}

export async function verifyAuditLedger(
  path: string,
): Promise<LedgerVerification> {
  const contents = await readLedger(path);

  if (contents.length === 0) {
    return { ok: true, entries: 0, headHash: GENESIS_HASH };
  }

  if (!contents.endsWith("\n")) {
    return {
      ok: false,
      entries: 0,
      headHash: GENESIS_HASH,
      error: "Ledger ends with an incomplete record",
    };
  }

  const lines = contents.slice(0, -1).split("\n");
  let previousHash = GENESIS_HASH;
  let verifiedEntries = 0;

  for (let index = 0; index < lines.length; index += 1) {
    try {
      const parsed: unknown = JSON.parse(lines[index]);

      if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("Record is not an object");
      }

      const entry = parsed as Record<string, unknown>;

      if (
        typeof entry.seq !== "number" ||
        !Number.isSafeInteger(entry.seq) ||
        entry.seq !== index + 1 ||
        typeof entry.timestamp !== "string" ||
        Number.isNaN(Date.parse(entry.timestamp)) ||
        typeof entry.prevHash !== "string" ||
        !/^[a-f0-9]{64}$/.test(entry.prevHash) ||
        typeof entry.hash !== "string" ||
        !/^[a-f0-9]{64}$/.test(entry.hash)
      ) {
        throw new Error("Invalid ledger record structure");
      }

      const event = validateEvent(entry.event);

      if (entry.prevHash !== previousHash) {
        throw new Error("Previous hash mismatch");
      }

      const core = {
        seq: entry.seq,
        timestamp: entry.timestamp,
        event,
        prevHash: entry.prevHash,
      };

      if (hashEntry(core) !== entry.hash) {
        throw new Error("Record hash mismatch");
      }

      previousHash = entry.hash;
      verifiedEntries += 1;
    } catch (error) {
      return {
        ok: false,
        entries: verifiedEntries,
        headHash: previousHash,
        error: `Invalid record ${index + 1}: ${
          error instanceof Error ? error.message : "unknown error"
        }`,
      };
    }
  }

  return {
    ok: true,
    entries: verifiedEntries,
    headHash: previousHash,
  };
}

export async function appendAuditEvent(
  path: string,
  input: AuditEvent,
): Promise<LedgerEntry> {
  const event = validateEvent(input);
  const queueKey = resolve(path);
  const previous = appendQueues.get(queueKey) ?? Promise.resolve();

  let release!: () => void;
  const current = new Promise<void>((resolve) => {
    release = resolve;
  });
  const queued = previous.then(() => current);
  appendQueues.set(queueKey, queued);

  await previous;

  try {
    return await withAuditFileLock(path, async () => {
    // Verify only after earlier appends for this path have completed.
    const verification = await verifyAuditLedger(path);

    if (!verification.ok) {
      throw new Error(
        `Refusing to append to an invalid audit ledger: ${verification.error}`,
      );
    }

    if (event.eventType === "reconciled") {
      if (!event.actionId) {
        throw new Error("reconciled_action_id_required");
      }

      const contents = await readLedger(path);

      for (const line of contents.split("\n")) {
        if (!line) continue;

        const existing = JSON.parse(line) as LedgerEntry;

        if (
          existing.event.eventType === "reconciled" &&
          existing.event.actionId === event.actionId
        ) {
          if (
            JSON.stringify(existing.event) !== JSON.stringify(event)
          ) {
            throw new Error("reconciled_audit_conflict");
          }

          return existing;
        }
      }
    }

    const core = {
      seq: verification.entries + 1,
      timestamp: new Date().toISOString(),
      event,
      prevHash: verification.headHash,
    };

    const entry: LedgerEntry = {
      ...core,
      hash: hashEntry(core),
    };

    let existed = true;

    try {
      await stat(path);
    } catch (error) {
      if (
        error instanceof Error &&
        "code" in error &&
        error.code === "ENOENT"
      ) {
        existed = false;
      } else {
        throw error;
      }
    }

    const handle = await open(path, "a", 0o600);

  try {
    const record = Buffer.from(`${JSON.stringify(entry)}\n`, "utf8");
    let offset = 0;

    while (offset < record.length) {
      const { bytesWritten } = await handle.write(
        record,
        offset,
        record.length - offset,
      );

      if (bytesWritten <= 0) {
        throw new Error("audit_write_no_progress");
      }

      offset += bytesWritten;
    }

    // Acknowledge only after the audit file is synchronized.
    await handle.sync();

    if (!existed) {
      await syncParentDirectory(path);
    }
  } finally {
    await handle.close();
  }

    return entry;
    });
  } finally {
    release();
    if (appendQueues.get(queueKey) === queued) {
      appendQueues.delete(queueKey);
    }
  }
}
