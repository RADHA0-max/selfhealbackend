import { DatabaseSync } from "node:sqlite";

export type ClaimResult = "CLAIMED" | "DUPLICATE";

export class ActionStore {
  private readonly db: DatabaseSync;

  constructor(path: string) {
    this.db = new DatabaseSync(path);

    this.db.exec(`
      PRAGMA busy_timeout = 5000;
      PRAGMA journal_mode = WAL;


      CREATE TABLE IF NOT EXISTS budget_reservations (
        action_id TEXT PRIMARY KEY NOT NULL,
        target TEXT NOT NULL,
        reserved_at INTEGER NOT NULL,
        active INTEGER NOT NULL CHECK (active IN (0, 1))
      );

      CREATE INDEX IF NOT EXISTS idx_budget_time
        ON budget_reservations(reserved_at);

      CREATE INDEX IF NOT EXISTS idx_budget_target_time
        ON budget_reservations(target, reserved_at);

      CREATE UNIQUE INDEX IF NOT EXISTS idx_budget_active_target
        ON budget_reservations(target) WHERE active = 1;

      CREATE TABLE IF NOT EXISTS action_claims (
        action_id TEXT PRIMARY KEY NOT NULL,
        capability TEXT NOT NULL,
        target TEXT NOT NULL,
        status TEXT NOT NULL
          CHECK (status IN ('CLAIMED', 'EXECUTING', 'EXECUTED', 'FAILED', 'NEEDS_RECONCILIATION', 'RECONCILED')),
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
      );
    `);
    this.migrateLegacyActionClaims();

    this.db.exec(`
      CREATE TABLE IF NOT EXISTS reconciliation_outbox (
        action_id TEXT PRIMARY KEY NOT NULL,
        delivered INTEGER NOT NULL DEFAULT 0
          CHECK (delivered IN (0, 1)),
        created_at INTEGER NOT NULL
      );

      CREATE TRIGGER IF NOT EXISTS block_pending_audit_reservation
      BEFORE INSERT ON budget_reservations
      WHEN NEW.active = 1
        AND EXISTS (
          SELECT 1
          FROM reconciliation_outbox o
          JOIN action_claims a ON a.action_id = o.action_id
          WHERE o.delivered = 0
            AND a.target = NEW.target
        )
      BEGIN
        SELECT RAISE(ABORT, 'pending_reconciliation_audit');
      END;

      CREATE TRIGGER IF NOT EXISTS block_pending_audit_reactivation
      BEFORE UPDATE OF active ON budget_reservations
      WHEN NEW.active = 1
        AND EXISTS (
          SELECT 1
          FROM reconciliation_outbox o
          JOIN action_claims a ON a.action_id = o.action_id
          WHERE o.delivered = 0
            AND a.target = NEW.target
        )
      BEGIN
        SELECT RAISE(ABORT, 'pending_reconciliation_audit');
      END;
    `);
  }


  private migrateLegacyActionClaims(): void {
    const row = this.db.prepare(`
      SELECT sql FROM sqlite_master
      WHERE type = 'table' AND name = 'action_claims'
    `).get() as { sql: string } | undefined;

    if (!row?.sql) {
      throw new Error("action_claims table missing");
    }

    if (row.sql.includes("RECONCILED")) {
      return;
    }

    this.db.exec("BEGIN IMMEDIATE");

    try {
      this.db.exec(`
        CREATE TABLE action_claims_v2 (
          action_id TEXT PRIMARY KEY NOT NULL,
          capability TEXT NOT NULL,
          target TEXT NOT NULL,
          status TEXT NOT NULL CHECK (
            status IN (
              'CLAIMED',
              'EXECUTING',
              'EXECUTED',
              'FAILED',
              'NEEDS_RECONCILIATION',
              'RECONCILED'
            )
          ),
          created_at INTEGER NOT NULL,
          updated_at INTEGER NOT NULL
        );

        INSERT INTO action_claims_v2
          (action_id, capability, target, status, created_at, updated_at)
        SELECT
          action_id, capability, target, status, created_at, updated_at
        FROM action_claims;

        DROP TABLE action_claims;
        ALTER TABLE action_claims_v2 RENAME TO action_claims;
      `);

      this.db.exec("COMMIT");
    } catch (error) {
      this.db.exec("ROLLBACK");
      throw error;
    }
  }


  resolveReconciliation(actionId: string): void {
    this.db.exec("BEGIN IMMEDIATE");

    try {
      const action = this.db.prepare(`
        SELECT target, status
        FROM action_claims
        WHERE action_id = ?
      `).get(actionId) as
        | { target: string; status: string }
        | undefined;

      if (!action || action.status !== "NEEDS_RECONCILIATION") {
        throw new Error("action_not_reconcilable");
      }

      const reservation = this.db.prepare(`
        SELECT target, active
        FROM budget_reservations
        WHERE action_id = ?
      `).get(actionId) as
        | { target: string; active: number }
        | undefined;

      if (
        !reservation ||
        reservation.target !== action.target ||
        reservation.active !== 1
      ) {
        throw new Error("reconciliation_lock_missing");
      }

      const updated = this.db.prepare(`
        UPDATE action_claims
        SET status = 'RECONCILED', updated_at = ?
        WHERE action_id = ?
          AND status = 'NEEDS_RECONCILIATION'
      `).run(Date.now(), actionId);

      if (updated.changes !== 1) {
        throw new Error("reconciliation_state_conflict");
      }

      this.db.prepare(`
        INSERT INTO reconciliation_outbox
          (action_id, delivered, created_at)
        VALUES (?, 0, ?)
      `).run(actionId, Date.now());

      this.db.exec("COMMIT");
    } catch (error) {
      this.db.exec("ROLLBACK");
      throw error;
    }
  }

  getPendingReconciliationAudits(): string[] {
    const rows = this.db.prepare(`
      SELECT action_id
      FROM reconciliation_outbox
      WHERE delivered = 0
      ORDER BY created_at, action_id
    `).all() as Array<{ action_id: string }>;

    return rows.map(row => row.action_id);
  }

  markReconciliationAuditDelivered(actionId: string): void {
    this.db.exec("BEGIN IMMEDIATE");

    try {
      const action = this.db.prepare(`
        SELECT target, status
        FROM action_claims
        WHERE action_id = ?
      `).get(actionId) as
        | { target: string; status: string }
        | undefined;

      if (!action || action.status !== "RECONCILED") {
        throw new Error("outbox_action_state_conflict");
      }

      const reservation = this.db.prepare(`
        SELECT target, active
        FROM budget_reservations
        WHERE action_id = ?
      `).get(actionId) as
        | { target: string; active: number }
        | undefined;

      if (
        !reservation ||
        reservation.target !== action.target ||
        reservation.active !== 1
      ) {
        throw new Error("outbox_lock_missing");
      }

      const result = this.db.prepare(`
        UPDATE reconciliation_outbox
        SET delivered = 1
        WHERE action_id = ? AND delivered = 0
      `).run(actionId);

      if (result.changes !== 1) {
        throw new Error("outbox_delivery_conflict");
      }

      const released = this.db.prepare(`
        UPDATE budget_reservations
        SET active = 0
        WHERE action_id = ?
          AND target = ?
          AND active = 1
      `).run(actionId, action.target);

      if (released.changes !== 1) {
        throw new Error("outbox_release_failed");
      }

      this.db.exec("COMMIT");
    } catch (error) {
      this.db.exec("ROLLBACK");
      throw error;
    }
  }

  getPendingRecoveryTargets(): string[] {
    const rows = this.db.prepare(`
      SELECT DISTINCT a.target
      FROM action_claims a
      WHERE a.status IN (
        'CLAIMED',
        'EXECUTING',
        'NEEDS_RECONCILIATION'
      )
      OR (
        a.status = 'RECONCILED'
        AND EXISTS (
          SELECT 1
          FROM reconciliation_outbox o
          WHERE o.action_id = a.action_id
            AND o.delivered = 0
        )
      )
      ORDER BY a.target
    `).all() as Array<{ target: string }>;

    return rows.map(row => row.target);
  }

  claim(actionId: string, capability: string, target: string): ClaimResult {
    if (!/^[a-zA-Z0-9_-]{1,128}$/.test(actionId)) {
      throw new Error("Invalid action ID");
    }

    const now = Date.now();
    const result = this.db.prepare(`
      INSERT INTO action_claims
        (action_id, capability, target, status, created_at, updated_at)
      VALUES (?, ?, ?, 'CLAIMED', ?, ?)
      ON CONFLICT(action_id) DO NOTHING
    `).run(actionId, capability, target, now, now);

    return result.changes === 1 ? "CLAIMED" : "DUPLICATE";
  }

  complete(actionId: string): void {
    const result = this.db.prepare(`
      UPDATE action_claims
      SET status = 'EXECUTED', updated_at = ?
      WHERE action_id = ? AND status = 'EXECUTING'
    `).run(Date.now(), actionId);

    if (result.changes !== 1) {
      throw new Error("Action is not in EXECUTING state");
    }
  }

  fail(actionId: string): void {
    const result = this.db.prepare(`
      UPDATE action_claims
      SET status = 'FAILED', updated_at = ?
      WHERE action_id = ? AND status = 'CLAIMED'
    `).run(Date.now(), actionId);

    if (result.changes !== 1) {
      throw new Error("Action is not in CLAIMED state");
    }
  }

  getStatus(actionId: string): string | null {
    const row = this.db.prepare(`
      SELECT status FROM action_claims WHERE action_id = ?
    `).get(actionId) as { status: string } | undefined;

    return row?.status ?? null;
  }


  reserveBudget(actionId: string, target: string): void {
    this.db.exec("BEGIN IMMEDIATE");

    try {
      const now = Date.now();
      const cutoff = now - 15 * 60_000;

      const active = this.db.prepare(`
        SELECT action_id FROM budget_reservations
        WHERE target = ? AND active = 1
      `).get(target);

      if (active) {
        throw new Error("target_mutex_locked");
      }

      const targetCount = this.db.prepare(`
        SELECT COUNT(*) AS count FROM budget_reservations
        WHERE target = ? AND reserved_at > ?
      `).get(target, cutoff) as { count: number };

      if (targetCount.count >= 3) {
        throw new Error("target_budget_exceeded");
      }

      const globalCount = this.db.prepare(`
        SELECT COUNT(*) AS count FROM budget_reservations
        WHERE reserved_at > ?
      `).get(cutoff) as { count: number };

      if (globalCount.count >= 8) {
        throw new Error("global_budget_exceeded");
      }

      const last = this.db.prepare(`
        SELECT MAX(reserved_at) AS last_at
        FROM budget_reservations WHERE target = ?
      `).get(target) as { last_at: number | null };

      if (last.last_at !== null && now - last.last_at < 90_000) {
        throw new Error("target_cooldown_active");
      }

      this.db.prepare(`
        INSERT INTO budget_reservations
          (action_id, target, reserved_at, active)
        VALUES (?, ?, ?, 1)
      `).run(actionId, target, now);

      this.db.exec("COMMIT");
    } catch (error) {
      this.db.exec("ROLLBACK");
      throw error;
    }
  }

  releaseBudget(actionId: string): void {
    const result = this.db.prepare(`
      UPDATE budget_reservations
      SET active = 0
      WHERE action_id = ? AND active = 1
    `).run(actionId);

    if (result.changes !== 1) {
      throw new Error("Budget reservation not active");
    }
  }

  getIncompleteActions(): Array<{
    action_id: string;
    capability: string;
    target: string;
    status: string;
  }> {
    return this.db.prepare(`
      SELECT action_id, capability, target, status
      FROM action_claims
      WHERE status = 'CLAIMED'
      ORDER BY created_at
    `).all() as Array<{
      action_id: string;
      capability: string;
      target: string;
      status: string;
    }>;
  }


  beginExecution(actionId: string): void {
    const result = this.db.prepare(`
      UPDATE action_claims
      SET status = 'EXECUTING', updated_at = ?
      WHERE action_id = ? AND status = 'CLAIMED'
    `).run(Date.now(), actionId);

    if (result.changes !== 1) {
      throw new Error("Action cannot enter EXECUTING");
    }
  }

  needsReconciliation(actionId: string): void {
    const result = this.db.prepare(`
      UPDATE action_claims
      SET status = 'NEEDS_RECONCILIATION', updated_at = ?
      WHERE action_id = ? AND status = 'EXECUTING'
    `).run(Date.now(), actionId);

    if (result.changes !== 1) {
      throw new Error("Action cannot enter NEEDS_RECONCILIATION");
    }
  }

  getUnresolvedActions(): Array<{
    action_id: string;
    target: string;
    status: string;
  }> {
    return this.db.prepare(`
      SELECT action_id, target, status
      FROM action_claims
      WHERE status IN ('CLAIMED', 'EXECUTING', 'NEEDS_RECONCILIATION')
      ORDER BY created_at
    `).all() as Array<{
      action_id: string;
      target: string;
      status: string;
    }>;
  }

  close(): void {
    this.db.close();
  }
}
