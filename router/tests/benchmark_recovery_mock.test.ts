import { afterEach, expect, test, vi } from 'vitest';
import { mkdtempSync, rmSync, appendFileSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { MockBenchmarkRecovery, mockProposal } from '../offline/benchmark-recovery.js';
import { TrustedRouter } from '../src/trusted-router.js';
import { CAPABILITIES } from '../src/schemas/registry.js';
import { verifyAuditLedger } from '../src/audit-ledger.js';

const dirs: string[] = [];
const sessions: MockBenchmarkRecovery[] = [];
afterEach(() => { vi.restoreAllMocks(); for (const s of sessions.splice(0)) s.close(); for (const d of dirs.splice(0)) rmSync(d, {recursive:true, force:true}); });
function fixtures() {
  return ['api','db','worker','auth'].map((target, i) => ({mode:'mock', target,
    containerId: String(i+1).repeat(64), daemonId:'isolated-fixture', sharedDaemonId:'shared-fixture',
    project:'selfhealbench-pilot', scope:'isolated-pilot', observedAt:Date.now(),
    baselineVerified:true, complete:true, state:'faulted'}));
}
function setup() {
  const dir=mkdtempSync(join(tmpdir(),'mock-recovery-')); dirs.push(dir);
  const rows=fixtures();
  const ledger=join(dir,'audit.jsonl'), database=join(dir,'state.sqlite');
  const session=new MockBenchmarkRecovery(ledger,database,rows); sessions.push(session);
  const payload={mode:'mock',actionId:'action1',campaignId:'campaign1', capability:'clear_fault',target:'db',purpose:'recovery'};
  const evidence=rows[1];
  const grant={...payload, operatorId:'fixture-operator', containerId:evidence.containerId,
    daemonId:evidence.daemonId, issuedAt:Date.now(), expiresAt:Date.now()+60_000};
  return {session,payload,grant,evidence,rows,ledger,database};
}
test('clear_fault changes only a mock and writes durable mock audit',async()=>{
  const e=setup();
  expect((await e.session.execute(e.payload,e.grant,e.evidence)).status).toBe('MOCK_EXECUTED');
  expect(e.session.dispatchCount).toBe(1);
  expect(e.session.status('action1')).toBe('EXECUTED');
  expect((await verifyAuditLedger(e.ledger)).ok).toBe(true);
  expect(readFileSync(e.ledger,'utf8')).toContain('mock_executed');
});
test('start_container is fixture-only',async()=>{
  const e=setup(); e.rows[1].state='stopped';
  const other=new MockBenchmarkRecovery(e.ledger,e.database,e.rows); sessions.push(other);
  e.payload.capability='start_container'; e.grant.capability='start_container';
  expect((await other.execute(e.payload,e.grant,e.rows[1])).status).toBe('MOCK_EXECUTED');
});
test.each([
  ['live mode', (e:any)=>e.payload.mode='live'],
  ['extra parameter', (e:any)=>e.payload.command='docker start other'],
  ['unsafe action', (e:any)=>e.payload.capability='restart_service'],
  ['prefix target', (e:any)=>e.payload.target='db-other'],
  ['missing grant', (e:any)=>e.grant={}],
  ['grant mismatch', (e:any)=>e.grant.actionId='other'],
  ['grant expired', (e:any)=>e.grant.expiresAt=0],
  ['grant future', (e:any)=>e.grant.issuedAt=Date.now()+60_000],
  ['grant excessive lifetime', (e:any)=>e.grant.expiresAt=Date.now()+600_000],
  ['stale evidence', (e:any)=>e.evidence.observedAt=Date.now()-31_000],
  ['future evidence', (e:any)=>e.evidence.observedAt=Date.now()+60_000],
  ['incomplete evidence', (e:any)=>e.evidence.complete=false],
  ['healthy control', (e:any)=>e.evidence.state='healthy'],
  ['shared daemon', (e:any)=>e.evidence.daemonId=e.evidence.sharedDaemonId],
  ['wrong container', (e:any)=>e.evidence.containerId='f'.repeat(64)],
  ['wrong project', (e:any)=>e.evidence.project='other'],
  ['missing parent', (e:any)=>{e.payload.purpose='cleanup';e.grant.purpose='cleanup';}],
  ['unknown parent', (e:any)=>{e.payload.purpose='cleanup';e.payload.parentActionId='missing';e.grant.purpose='cleanup';}],
])('rejects %s without mock dispatch',async(_name,change)=>{
  const e=setup(); change(e);
  expect((await e.session.execute(e.payload,e.grant,e.evidence)).status).toBe('REJECTED');
  expect(e.session.dispatchCount).toBe(0);
});
test('duplicate ID survives restart even after fixture reset',async()=>{
  const e=setup(); await e.session.execute(e.payload,e.grant,e.evidence);
  const restarted=new MockBenchmarkRecovery(e.ledger,e.database,e.rows); sessions.push(restarted);
  expect((await restarted.execute(e.payload,e.grant,e.evidence)).status).toBe('REJECTED');
  expect(restarted.dispatchCount).toBe(0);
});
test('uncertain execution blocks target and requires explicit mock reconciliation',async()=>{
  const e=setup();
  expect((await e.session.execute(e.payload,e.grant,e.evidence,'after_dispatch')).status).toBe('REJECTED');
  expect(e.session.status('action1')).toBe('NEEDS_RECONCILIATION');
  const second={...e.payload,actionId:'action2'};
  expect((await e.session.execute(second,{...e.grant,actionId:'action2'},e.evidence)).status).toBe('REJECTED');
  const healthy={...e.evidence,state:'healthy'};
  await expect(e.session.reconcile({},healthy)).rejects.toThrow();
  await expect(e.session.reconcile({mode:'mock',operatorId:'reviewer',actionId:'action1',issuedAt:Date.now(),expiresAt:Date.now()+60_000},e.evidence)).rejects.toThrow();
  await e.session.reconcile({mode:'mock',operatorId:'reviewer',actionId:'action1',issuedAt:Date.now(),expiresAt:Date.now()+60_000},healthy);
  expect(e.session.status('action1')).toBe('RECONCILED');
  expect(e.session.dispatchCount).toBe(1);
  expect(readFileSync(e.ledger,'utf8')).toContain('clear_fault');
  expect(readFileSync(e.ledger,'utf8')).not.toContain('scale_service');
});
test('cleanup uses same budget, exact parent and independent grant',async()=>{
  const e=setup(); await e.session.execute(e.payload,e.grant,e.evidence);
  // A new fixture session represents a separately observed residual fault.
  const resumed=new MockBenchmarkRecovery(e.ledger,e.database,e.rows); sessions.push(resumed);
  const cleanup={...e.payload,actionId:'cleanup1',purpose:'cleanup',parentActionId:'action1'};
  const grant={...e.grant,actionId:'cleanup1',purpose:'cleanup'};
  expect((await resumed.execute(cleanup,grant,e.evidence)).status).toBe('REJECTED'); // cooldown
  const now=Date.now()+91_000; vi.spyOn(Date,'now').mockReturnValue(now);
  const allowed={...cleanup,actionId:'cleanup2'};
  expect((await resumed.execute(allowed,{...grant,actionId:'cleanup2',issuedAt:now,expiresAt:now+60_000},{...e.evidence,observedAt:now})).status).toBe('MOCK_EXECUTED');
});
test('tampered ledger fails closed',async()=>{
  const e=setup(); appendFileSync(e.ledger,'tampered\n');
  await expect(e.session.execute(e.payload,e.grant,e.evidence)).rejects.toThrow();
  expect(e.session.dispatchCount).toBe(0);
});
test('EXECUTING crash is reconciled without another dispatch',async()=>{
  const e=setup(); await e.session.execute(e.payload,e.grant,e.evidence,'after_dispatch');
  const db=new DatabaseSync(e.database);
  db.prepare("UPDATE action_claims SET status='EXECUTING' WHERE action_id='action1'").run();db.close();
  e.rows[1].state='healthy';
  const restarted=new MockBenchmarkRecovery(e.ledger,e.database,e.rows);sessions.push(restarted);
  await restarted.reconcile({mode:'mock',operatorId:'reviewer',actionId:'action1',issuedAt:Date.now(),expiresAt:Date.now()+60_000},e.rows[1]);
  expect(restarted.status('action1')).toBe('RECONCILED');expect(restarted.dispatchCount).toBe(0);
});
test('production Router still rejects both actions and has no registry entries',async()=>{
  const e=setup(); const backend={scaleService:vi.fn()};
  const router=new TrustedRouter(backend,e.ledger,e.database); await router.initialize();
  try {
    for (const capability of ['clear_fault','start_container']) {
      expect(Object.hasOwn(CAPABILITIES,capability)).toBe(false);
      const result=await router.execute({capability,params:{target:'selfheal-svc-db'}},
        {cause:'organic',rootTarget:'selfheal-svc-db',ipConcentration:.1,tailRatio:1,rps:10,rpsBaseline:10,observedAt:Date.now()});
      expect(result.status).toBe('REJECTED');
    }
    expect(backend.scaleService).not.toHaveBeenCalled();
  } finally {router.close();}
});

test('diagnosis bridge validates root, action and extra fields without granting authority',()=>{
  const diagnosis={root_cause:'db',action:'clear_fault',target:'db',reason:'fixture probe'};
  const context={mode:'mock',actionId:'proposal',campaignId:'campaign',purpose:'recovery'};
  expect(mockProposal(diagnosis,context).capability).toBe('clear_fault');
  for (const patch of [{root_cause:'api'},{action:'shell'},{target:'db-other'},{extra:true},{reason:''}])
    expect(()=>mockProposal({...diagnosis,...patch},context)).toThrow();
});
test('cleanup cannot change campaign or immutable parent target',async()=>{
  const e=setup();await e.session.execute(e.payload,e.grant,e.evidence);
  const resumed=new MockBenchmarkRecovery(e.ledger,e.database,e.rows);sessions.push(resumed);
  const now=Date.now()+91_000;vi.spyOn(Date,'now').mockReturnValue(now);
  const p={...e.payload,actionId:'cleanup-wrong',campaignId:'other',purpose:'cleanup',parentActionId:'action1'};
  const g={...e.grant,actionId:p.actionId,campaignId:'other',purpose:'cleanup',issuedAt:now,expiresAt:now+60_000};
  expect((await resumed.execute(p,g,{...e.evidence,observedAt:now})).status).toBe('REJECTED');
  expect(resumed.dispatchCount).toBe(0);
});
test('target budget survives mock sessions and cleanup cannot exceed it',async()=>{
  const e=setup();const start=Date.now();
  for(let n=0;n<4;n++){
    const now=start+n*91_000;vi.spyOn(Date,'now').mockReturnValue(now);
    const session=new MockBenchmarkRecovery(e.ledger,e.database,e.rows);sessions.push(session);
    const id='attempt'+n;
    const result=await session.execute({...e.payload,actionId:id},
      {...e.grant,actionId:id,issuedAt:now,expiresAt:now+60_000},{...e.evidence,observedAt:now});
    expect(result.status).toBe(n<3?'MOCK_EXECUTED':'REJECTED');
    expect(session.dispatchCount).toBe(n<3?1:0);
  }
});
test('pending reconciliation completion is replayed idempotently without dispatch',async()=>{
  const e=setup();await e.session.execute(e.payload,e.grant,e.evidence,'after_dispatch');
  const db=new DatabaseSync(e.database);
  db.prepare("UPDATE action_claims SET status='RECONCILED' WHERE action_id='action1'").run();
  db.prepare("INSERT INTO reconciliation_outbox VALUES ('action1',0,?)").run(Date.now());db.close();
  const restarted=new MockBenchmarkRecovery(e.ledger,e.database,e.rows);sessions.push(restarted);
  await restarted.recoverPendingAudits();await restarted.recoverPendingAudits();
  expect(restarted.dispatchCount).toBe(0);
  const entries=readFileSync(e.ledger,'utf8').trim().split('\n').map(s=>JSON.parse(s));
  expect(entries.filter(r=>r.event.eventType==='reconciled')).toHaveLength(1);
  expect(entries.find(r=>r.event.eventType==='reconciled').event.capability).toBe('clear_fault');
});
