import { execFile } from 'child_process';
import util from 'util';
import path from 'path';
import { log } from '../../log.js';
import { registerDeliveryAction } from '../../delivery.js';
import { requestApproval, registerApprovalHandler, notifyAgent } from '../approvals/index.js';
import { writeAuditLog } from '../../ledger.js';
import type { Session } from '../../types.js';

const execFileAsync = util.promisify(execFile);

// Safety Bounds & Allowlists
const MAX_REPLICAS = 10;
const CONFIDENCE_THRESHOLD = 0.8;
const ALLOWED_TARGETS = new Set(['mock-server']);
const APPROVAL_TTL_MS = 10 * 60 * 1000; // 10 minutes

// Hardcoded for pattern1-traffic-spike demo
const TARGET_DIR = path.join(process.cwd(), 'pattern1-traffic-spike');

async function executeDockerScale(target: string, replicas: number, session: Session, confidence: number): Promise<void> {
  log.info('Executing docker scale', { target, replicas, targetDir: TARGET_DIR });
  try {
    // ARGUMENT ARRAY: No shell interpolation means zero injection risk.
    const { stdout } = await execFileAsync('docker', ['compose', 'up', '--scale', `${target}=${replicas}`, '-d'], { cwd: TARGET_DIR });
    log.info('Docker scale success', { stdout });
    writeAuditLog('docker_scale', { success: true, target, replicas }, confidence);
    // Prefixing with [SYSTEM_RESULT] to help the LLM explicitly identify this as a feedback signal, not a new user prompt.
    notifyAgent(session, `[SYSTEM_RESULT] System action docker_scale completed. Result: Success. Scaled ${target} to ${replicas} replicas.`);
  } catch (err: any) {
    log.error('Docker scale failed', { err: err.message });
    writeAuditLog('docker_scale', { success: false, target, replicas, error: err.message }, confidence);
    notifyAgent(session, `[SYSTEM_RESULT] System action docker_scale failed. Result: Error. ${err.message}`);
  }
}

// 1. Delivery Action: intercepts agent's system action
registerDeliveryAction('docker_scale', async (content, session, inDb) => {
  const replicas = content.replicas;
  const target = content.target as string;
  const confidence = typeof content.confidence === 'number' ? content.confidence : 0;

  // Security Boundary 1: Target Allowlist
  if (!target || !ALLOWED_TARGETS.has(target)) {
    const errorMsg = `Invalid target: '${target}'. Allowed targets: ${Array.from(ALLOWED_TARGETS).join(', ')}.`;
    log.warn('docker_scale target validation failed', { target, sessionId: session.id });
    writeAuditLog('docker_scale', { success: false, error: errorMsg }, confidence);
    notifyAgent(session, `[SYSTEM_RESULT] System action docker_scale failed. Result: ${errorMsg}`);
    return;
  }

  // Security Boundary 2: Strict Integer & Bounds Check
  if (typeof replicas !== 'number' || !Number.isInteger(replicas) || replicas < 1 || replicas > MAX_REPLICAS) {
    const errorMsg = `Invalid scale request: requested ${replicas}, but must be an integer between 1 and ${MAX_REPLICAS}.`;
    log.warn('docker_scale bounds validation failed', { replicas, sessionId: session.id });
    writeAuditLog('docker_scale', { success: false, error: errorMsg }, confidence);
    notifyAgent(session, `[SYSTEM_RESULT] System action docker_scale failed. Result: ${errorMsg}`);
    return;
  }

  // Confidence Tier: Human-in-the-loop
  if (confidence < CONFIDENCE_THRESHOLD) {
    log.info('Low confidence docker_scale request, holding for approval', { confidence, target, replicas });
    await requestApproval({
      session,
      agentName: 'DevOps Agent',
      action: 'docker_scale',
      payload: { target, replicas, confidence },
      title: 'Traffic Spike Scaling Request',
      question: `Agent wants to scale ${target} to ${replicas} replicas (Confidence: ${confidence}). Approve?`,
    });
    
    // Simplistic TTL: Note, a robust implementation would use a Host Sweep hook on pending_approvals
    // to survive process restarts, but this in-memory timeout proves the loop concept.
    setTimeout(() => {
      // Logic to sweep/expire the pending approval row would go here.
      log.info('Approval TTL expired', { target, replicas, sessionId: session.id });
    }, APPROVAL_TTL_MS);

    return;
  }

  // High confidence -> Auto-execute
  await executeDockerScale(target, replicas, session, confidence);
});

// 2. Approval Handler: executes if admin clicks Approve
registerApprovalHandler('docker_scale', async (ctx) => {
  const target = ctx.payload.target as string;
  const replicas = ctx.payload.replicas as number;
  const confidence = ctx.payload.confidence as number;
  ctx.notify(`[SYSTEM_RESULT] Admin approved scale request. Scaling ${target} to ${replicas} replicas.`);
  await executeDockerScale(target, replicas, ctx.session, confidence);
});
