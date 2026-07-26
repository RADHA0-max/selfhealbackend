import fs from 'fs';
import path from 'path';
import { DATA_DIR } from './config.js';

const LEDGER_PATH = path.join(DATA_DIR, 'audit.jsonl');

export function writeAuditLog(action: string, result: unknown, confidence: number): void {
  const entry = {
    ts: new Date().toISOString(),
    action,
    result,
    confidence
  };
  fs.appendFileSync(LEDGER_PATH, JSON.stringify(entry) + '\n');
}

export function readAuditLog(limit: number = 5): any[] {
  try {
    const content = fs.readFileSync(LEDGER_PATH, 'utf-8');
    const lines = content.trim().split('\n').filter(Boolean);
    return lines.slice(-limit).map(line => JSON.parse(line));
  } catch {
    return [];
  }
}
