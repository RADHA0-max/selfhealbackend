/* Explicit allowlist for isolated NanoClaw test traffic. */

const ALLOWED_TARGETS = [
  'http://127.0.0.1:10000',
  'http://localhost:10000',
  'http://testbed-envoy:10000',
];

export function safeTarget(value) {
  if (typeof value !== 'string' || !ALLOWED_TARGETS.includes(value)) {
    throw new Error('Unsafe TARGET_URL: isolated testbed targets only');
  }
  return value;
}
