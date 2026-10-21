import { createProvider } from './src/providers/factory.js';

async function run() {
  console.log("[Test] Instantiating broker provider...");
  const provider = createProvider('broker', { model: 'fast', timeoutMs: 30000 });

  const input = {
    messages: [{ role: 'user', content: 'Say exactly and only: REAL_NANOCLAW_BROKER_E2E_OK' }]
  };

  console.log("[Test] Sending query through file-RPC broker (Zone U -> Zone T)...");
  const stream = provider.query(input, {});
  let fullText = "";

  for await (const chunk of stream) {
    if (chunk.type === 'text') fullText += chunk.text;
  }

  console.log("\n=== QWEN RESPONSE ===");
  console.log(fullText.trim());
  console.log("=====================\n");

  if (fullText.includes("REAL_NANOCLAW_BROKER_E2E_OK")) {
    console.log("✅ PHASE 8 COMPLETE: REAL_NANOCLAW_BROKER_E2E_OK");
  } else {
    console.log("❌ Response did not match expected output.");
  }
}

run().catch(console.error);
