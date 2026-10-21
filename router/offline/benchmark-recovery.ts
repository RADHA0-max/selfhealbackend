/** Offline contract prototype. NOT registered with TrustedRouter.
 * No injectable backend, Docker, HTTP, subprocess or production dispatch path.
 */
import { DatabaseSync } from 'node:sqlite';
import { z } from 'zod';
import { ActionStore } from '../src/storage/action-store.js';
import { appendAuditEvent, verifyAuditLedger } from '../src/audit-ledger.js';

const Id = z.string().regex(/^[A-Za-z0-9_-]{1,128}$/);
const Target = z.enum(['api', 'db', 'worker', 'auth']);
const Capability = z.enum(['clear_fault', 'start_container']);
const Purpose = z.enum(['recovery', 'cleanup']);
const Container = z.string().regex(/^[a-f0-9]{64}$/);
const Stamp = z.number().int().nonnegative();
const Envelope = z.object({
  mode: z.literal('mock'), actionId: Id, campaignId: Id,
  capability: Capability, target: Target, purpose: Purpose,
  parentActionId: Id.optional(),
}).strict().superRefine((p, ctx) => {
  if ((p.purpose === 'cleanup') !== (p.parentActionId !== undefined))
    ctx.addIssue({ code: 'custom', message: 'cleanup requires exactly one parent' });
});
const Grant = z.object({
  mode: z.literal('mock'), operatorId: Id, actionId: Id, campaignId: Id,
  capability: Capability, target: Target, purpose: Purpose,
  containerId: Container, daemonId: Id, issuedAt: Stamp, expiresAt: Stamp,
}).strict();
const Snapshot = z.object({
  mode: z.literal('mock'), target: Target, containerId: Container,
  daemonId: Id, sharedDaemonId: Id, project: z.literal('selfhealbench-pilot'),
  scope: z.literal('isolated-pilot'), observedAt: Stamp,
  baselineVerified: z.literal(true), complete: z.literal(true),
  state: z.enum(['faulted', 'stopped', 'healthy']),
}).strict();
const ReconcileGrant = z.object({
  mode: z.literal('mock'), operatorId: Id, actionId: Id,
  issuedAt: Stamp, expiresAt: Stamp,
}).strict();
export type MockSnapshot = z.infer<typeof Snapshot>;
export type MockEnvelope = z.infer<typeof Envelope>;

function fresh(observedAt: number, now: number) {
  if (observedAt > now || now - observedAt > 30_000) throw new Error('stale_evidence');
}
function grantTime(g: {issuedAt: number; expiresAt: number}, now: number) {
  if (g.issuedAt > now || g.expiresAt <= now || g.expiresAt <= g.issuedAt ||
      g.expiresAt - g.issuedAt > 300_000) throw new Error('invalid_grant_time');
}

/** Validate the diagnosis before forming an inert mock envelope. This function
 * returns a proposal, never authority or an executable production capability. */
export function mockProposal(diagnosis: unknown, context: unknown): MockEnvelope {
  const d = z.object({root_cause: Target, action: Capability, target: Target,
    reason: z.string().trim().min(1).max(500)}).strict().parse(diagnosis);
  if (d.root_cause !== d.target) throw new Error('root_target_mismatch');
  const c = z.object({mode: z.literal('mock'), actionId: Id, campaignId: Id,
    purpose: Purpose, parentActionId: Id.optional()}).strict().parse(context);
  return Envelope.parse({...c, capability: d.action, target: d.target});
}

/** Owns only copies of fixture objects. Even a live-looking grant cannot cause I/O. */
export class MockBenchmarkRecovery {
  private readonly store: ActionStore;
  private readonly bindings: DatabaseSync;
  private readonly resources = new Map<string, MockSnapshot>();
  private dispatches = 0;

  constructor(private readonly ledger: string, database: string, fixtures: unknown) {
    const rows = z.array(Snapshot).length(4).parse(fixtures);
    if (new Set(rows.map(r => r.target)).size !== 4 || new Set(rows.map(r => r.containerId)).size !== 4)
      throw new Error('duplicate_fixture_identity');
    if (new Set(rows.map(r => r.daemonId)).size !== 1 || new Set(rows.map(r => r.sharedDaemonId)).size !== 1)
      throw new Error('fixture_daemon_mismatch');
    for (const row of rows) {
      if (row.daemonId === row.sharedDaemonId) throw new Error('shared_daemon');
      this.resources.set(row.target, structuredClone(row));
    }
    this.store = new ActionStore(database);
    this.bindings = new DatabaseSync(database);
    this.bindings.exec(`CREATE TABLE IF NOT EXISTS mock_bindings (
      id TEXT PRIMARY KEY, envelope TEXT NOT NULL, container TEXT NOT NULL,
      daemon TEXT NOT NULL, operator TEXT NOT NULL
    )`);
  }

  get dispatchCount() { return this.dispatches; }
  status(id: string) { return this.store.getStatus(id); }

  async execute(payload: unknown, authority: unknown, observation: unknown,
                failure: 'none' | 'after_dispatch' = 'none') {
    let id: string | undefined;
    let reserved = false;
    let dispatched = false;
    try {
      if (!['none', 'after_dispatch'].includes(failure)) throw new Error('invalid_fixture_failure');
      const p = Envelope.parse(payload);
      const g = Grant.parse(authority);
      const e = Snapshot.parse(observation);
      const now = Date.now();
      grantTime(g, now);
      fresh(e.observedAt, now);
      const owned = this.resources.get(p.target)!;
      for (const key of ['actionId', 'campaignId', 'capability', 'target', 'purpose'] as const)
        if (p[key] !== g[key]) throw new Error('grant_scope_mismatch');
      if (g.containerId !== owned.containerId || g.daemonId !== owned.daemonId ||
          e.target !== p.target || e.containerId !== owned.containerId || e.daemonId !== owned.daemonId ||
          e.sharedDaemonId !== owned.sharedDaemonId || e.daemonId === e.sharedDaemonId ||
          e.state !== owned.state) throw new Error('ownership_or_evidence_mismatch');
      const requiredState = p.capability === 'clear_fault' ? 'faulted' : 'stopped';
      if (e.state !== requiredState) throw new Error('unsupported_or_healthy_state');
      if (p.parentActionId) {
        const parent = this.bindings.prepare('SELECT envelope,container,daemon FROM mock_bindings WHERE id=?')
          .get(p.parentActionId) as {envelope: string; container: string; daemon: string} | undefined;
        if (!parent || this.store.getStatus(p.parentActionId) !== 'EXECUTED') throw new Error('invalid_cleanup_parent');
        const original = Envelope.parse(JSON.parse(parent.envelope));
        if (original.purpose !== 'recovery' || original.target !== p.target || original.campaignId !== p.campaignId ||
            parent.container !== e.containerId || parent.daemon !== e.daemonId) throw new Error('cleanup_scope_mismatch');
      }
      if (!(await verifyAuditLedger(this.ledger)).ok) throw new Error('audit_integrity');
      if (this.store.getPendingRecoveryTargets().includes(p.target)) throw new Error('unresolved_target');
      // Single-use metadata binding is durable, including crash-before-claim gaps.
      this.bindings.prepare('INSERT INTO mock_bindings VALUES (?,?,?,?,?)')
        .run(p.actionId, JSON.stringify(p), e.containerId, e.daemonId, g.operatorId);
      if (this.store.claim(p.actionId, p.capability, p.target) !== 'CLAIMED') throw new Error('duplicate_action');
      id = p.actionId;
      this.store.reserveBudget(id, p.target);
      reserved = true;
      await appendAuditEvent(this.ledger, {eventType: 'tier_used', actionId: id,
        capability: p.capability, tier: 'TIER_1', outcome: 'mock_reserved'});
      grantTime(g, Date.now());
      fresh(e.observedAt, Date.now());
      this.store.beginExecution(id);
      dispatched = true;
      this.dispatches++;
      // The sole dispatch operation is changing an internal fixture value.
      owned.state = 'healthy';
      if (failure === 'after_dispatch') throw new Error('mock_uncertain');
      await appendAuditEvent(this.ledger, {eventType: 'executed', actionId: id,
        capability: p.capability, outcome: 'mock_executed'});
      this.store.complete(id);
      this.store.releaseBudget(id);
      return {status: 'MOCK_EXECUTED', actionId: id, liveRecoverySuccess: null};
    } catch {
      if (id && dispatched) {
        try { this.store.needsReconciliation(id); } catch { /* unresolved state stays locked */ }
      } else if (id) {
        this.store.fail(id);
        if (reserved) this.store.releaseBudget(id);
      }
      // Constant reason code avoids emitting arbitrary payloads or Zod diagnostics.
      await appendAuditEvent(this.ledger, {eventType: 'gate_reject', gate: 'GATE_5',
        reasonCode: 'mock_recovery_rejected', outcome: 'mock_rejected'});
      return {status: 'REJECTED', liveRecoverySuccess: null};
    }
  }

  async reconcile(authority: unknown, observation: unknown) {
    const g = ReconcileGrant.parse(authority);
    grantTime(g, Date.now());
    const e = Snapshot.parse(observation);
    fresh(e.observedAt, Date.now());
    const row = this.bindings.prepare('SELECT envelope,container,daemon FROM mock_bindings WHERE id=?')
      .get(g.actionId) as {envelope: string; container: string; daemon: string} | undefined;
    if (!row) throw new Error('missing_binding');
    const p = Envelope.parse(JSON.parse(row.envelope));
    const owned = this.resources.get(p.target)!;
    if (e.target !== p.target || e.containerId !== row.container || e.daemonId !== row.daemon ||
        e.containerId !== owned.containerId || e.daemonId !== owned.daemonId ||
        e.sharedDaemonId !== owned.sharedDaemonId || e.state !== 'healthy' || owned.state !== 'healthy')
      throw new Error('safe_state_unverified');
    if (!(await verifyAuditLedger(this.ledger)).ok) throw new Error('audit_integrity');
    // An EXECUTING crash is uncertain. Never redispatch it.
    if (this.store.getStatus(g.actionId) === 'EXECUTING') this.store.needsReconciliation(g.actionId);
    if (this.store.getStatus(g.actionId) !== 'NEEDS_RECONCILIATION') throw new Error('not_reconcilable');
    await appendAuditEvent(this.ledger, {eventType: 'reconciliation_intent', actionId: g.actionId,
      capability: p.capability, outcome: 'mock_verified'});
    this.store.resolveReconciliation(g.actionId);
    await this.recoverPendingAudits();
  }

  async recoverPendingAudits() {
    for (const id of this.store.getPendingReconciliationAudits()) {
      const row = this.bindings.prepare('SELECT envelope FROM mock_bindings WHERE id=?').get(id) as {envelope: string} | undefined;
      if (!row) throw new Error('missing_binding');
      const p = Envelope.parse(JSON.parse(row.envelope));
      await appendAuditEvent(this.ledger, {eventType: 'reconciled', actionId: id,
        capability: p.capability, outcome: 'mock_operator_verified'});
      this.store.markReconciliationAuditDelivered(id);
    }
  }

  close() { this.bindings.close(); this.store.close(); }
}
