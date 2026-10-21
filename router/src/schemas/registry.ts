import { z } from "zod";

export const CAPABILITIES = {
  // --- Infrastructure Control (Tier 1/2) ---
  scale_service: {
    risk: "low",
    backend: "docker",
    reversible: true,
    params: z.object({
      target: z.enum(["selfheal-svc-api", "selfheal-svc-db", "selfheal-svc-worker", "selfheal-svc-auth"]),
      replicas: z.number().int().min(1).max(5), // Min 1 prevents scale-to-zero
      delta: z.number().int().optional()
    }).strict(),
  },
  restart_service: {
    risk: "medium",
    backend: "docker",
    reversible: false, // Cannot un-restart a service
    params: z.object({
      target: z.enum(["selfheal-svc-api", "selfheal-svc-db", "selfheal-svc-worker", "selfheal-svc-auth"]),
      grace_period_s: z.number().int().min(0).max(120).default(30)
    }).strict(),
  },
  
  // --- Code Repair (Tier 3) ---
  propose_patch: {
    risk: "review_only", // Never auto, never approval; requires Zone V then PR
    backend: "none",     // Executes NOTHING
    reversible: true,
    params: z.object({
      files: z.array(z.object({
        path: z.string().min(1).max(256).refine(
          (path) =>
            !path.startsWith("/") &&
            !path.includes("\\") &&
            !/^[A-Za-z]:/.test(path) &&
            path.split("/").every((part) => part !== "" && part !== "." && part !== "..") &&
            !/(^|\/)\.github(\/|$)/i.test(path) &&
            !/(^|\/)(auth|crypto|migrations|payment)(\/|$)/i.test(path) &&
            !/(^|\/)[^/]*secret[^/]*($|\/)/i.test(path) &&
            !/(^|\/)Dockerfile[^/]*$/i.test(path) &&
            !/\.tf$/i.test(path) &&
            !/(^|\/)(package\.json|[^/]*\.lock|requirements[^/]*\.txt|pyproject\.toml|Cargo\.toml|go\.mod|go\.sum)$/i.test(path) &&
            !/(^|\/)(\.github|\.gitlab|\.circleci)(\/|$)/i.test(path),
          { message: "Unsafe, protected, or forbidden patch path" }
        ),
        diff: z.string().min(1).max(20000),
      }).strict()).max(3).superRefine((files, ctx) => {
        let changedLines = 0;

        for (const [index, file] of files.entries()) {
          const lines = file.diff.split(/\r?\n/);

          // Count unified-diff additions/deletions, excluding diff metadata.
          for (const line of lines) {
            if (
              (line.startsWith("+") && !line.startsWith("+++")) ||
              (line.startsWith("-") && !line.startsWith("---"))
            ) {
              changedLines++;
            }
          }

          // Do not allow deletions from test files; the validator cannot
          // establish architecture-approved modifications to existing tests.
          if (
            /(^|\/)(__tests__|tests?|spec)(\/|$)/i.test(file.path) &&
            lines.some((line) => line.startsWith("-") && !line.startsWith("---"))
          ) {
            ctx.addIssue({
              code: "custom",
              path: [index, "diff"],
              message: "Deleting or modifying existing test lines is not allowed",
            });
          }
        }

        if (changedLines > 50) {
          ctx.addIssue({
            code: "custom",
            path: ["files"],
            message: "Patch exceeds the 50 changed-line limit",
          });
        }
      }),
      explanation: z.string().max(2000),
      test_added: z.literal(true), // Literal true: patch without test cannot parse
      confidence: z.number().min(0).max(1),
    }).strict(),
  },
  
  // NOTE: 'exec', 'run_command', 'eval', 'shell', 'raw_sql' are entirely absent by design.
} as const;
