import { expect, test } from "vitest";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawn } from "node:child_process";
import { verifyAuditLedger } from "../src/audit-ledger.js";

test("separate processes serialize audit appends", async () => {
  const dir = await mkdtemp(join(tmpdir(), "nanoclaw-multiprocess-"));
  const ledger = join(dir, "audit.jsonl");
  const workers = 6;

  try {
    const modulePath = resolve("src/audit-ledger.ts");

    const runWorker = (index: number) =>
      new Promise<void>((resolvePromise, reject) => {
        const code = `
          import { appendAuditEvent } from ${JSON.stringify(
            "file://" + modulePath
          )};
          await appendAuditEvent(
            ${JSON.stringify(ledger)},
            {
              eventType: "gate_reject",
              actionId: "worker-${index}",
              gate: "GATE_5",
              reasonCode: "trusted_evidence_missing"
            }
          );
        `;

        const child = spawn(
          process.execPath,
          ["--experimental-strip-types", "--input-type=module", "-e", code],
          { stdio: ["ignore", "pipe", "pipe"] },
        );

        let stderr = "";
        child.stderr.on("data", chunk => {
          stderr += chunk.toString();
        });

        child.on("error", reject);
        child.on("close", code => {
          if (code === 0) resolvePromise();
          else reject(new Error(`worker ${index} exited ${code}: ${stderr}`));
        });
      });

    await Promise.all(
      Array.from({ length: workers }, (_, i) => runWorker(i)),
    );

    const verification = await verifyAuditLedger(ledger);

    expect(verification.ok).toBe(true);
    expect(verification.entries).toBe(workers);

    const contents = await readFile(ledger, "utf8");
    const ids = contents.trim().split("\n").map(
      line => JSON.parse(line).event.actionId,
    );

    expect(new Set(ids).size).toBe(workers);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
