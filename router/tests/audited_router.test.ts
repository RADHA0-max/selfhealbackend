import { afterEach, expect, test } from "vitest";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { processActionPlanAudited } from "../src/audited-router.js";
import { verifyAuditLedger } from "../src/audit-ledger.js";

let tempDir = "";

afterEach(async () => {
  if (tempDir) {
    await rm(tempDir, { recursive: true, force: true });
    tempDir = "";
  }
});

async function makeLedgerPath() {
  tempDir = await mkdtemp(join(tmpdir(), "selfheal-audited-router-"));
  return join(tempDir, "audit.jsonl");
}

test("records a minimal audit event for a rejected infrastructure action", async () => {
  const path = await makeLedgerPath();

  const result = await processActionPlanAudited(
    {
      capability: "scale_service",
      params: { target: "selfheal-svc-api", replicas: 2 },
    },
    path,
  );

  expect(result.status).toBe("REJECTED");
  expect(result.gate).toBe("GATE_5");
  expect(result.audit).toBe("RECORDED");

  const contents = await readFile(path, "utf8");
  expect(contents).toContain('"eventType":"gate_reject"');
  expect(contents).toContain('"reasonCode":"trusted_evidence_missing"');
  expect(contents).not.toContain('"params"');

  const verification = await verifyAuditLedger(path);
  expect(verification.ok).toBe(true);
  expect(verification.entries).toBe(1);
});

test("keeps rejection fail-closed when audit append fails", async () => {
  const dir = await makeLedgerPath();
  await writeFile(dir, "not a directory", "utf8");
  const path = join(dir, "audit.jsonl");

  const result = await processActionPlanAudited(
    {
      capability: "scale_service",
      params: { target: "selfheal-svc-api", replicas: 2 },
    },
    path,
  );

  expect(result.status).toBe("REJECTED");
  expect(result.audit).toBe("FAILED");
});

test("does not write raw prompt content to the audit ledger", async () => {
  const path = await makeLedgerPath();
  const secretPrompt = "PRIVATE_PROMPT_SHOULD_NOT_BE_STORED";

  const result = await processActionPlanAudited(
    {
      capability: "unknown_capability",
      params: { prompt: secretPrompt },
    },
    path,
  );

  expect(result.status).toBe("REJECTED");
  expect(result.gate).toBe("GATE_2");
  expect(result.audit).toBe("RECORDED");

  const contents = await readFile(path, "utf8");
  expect(contents).not.toContain(secretPrompt);
  expect(contents).not.toContain('"params"');
});
