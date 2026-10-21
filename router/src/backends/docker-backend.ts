import type { TrustedBackend } from "../trusted-router.js";

export const ALLOWED_DOCKER_TARGETS = [
  "selfheal-svc-api",
  "selfheal-svc-db",
  "selfheal-svc-worker",
  "selfheal-svc-auth",
] as const;

export type DockerTarget = typeof ALLOWED_DOCKER_TARGETS[number];

export interface DockerServiceState {
  name: string;
  replicas: number;
}

export interface DockerAdapter {
  inspectService(target: DockerTarget): Promise<DockerServiceState>;
  scaleService(target: DockerTarget, replicas: number): Promise<void>;
}

export class DockerBackend implements TrustedBackend {
  constructor(private readonly adapter: DockerAdapter) {}

  async scaleService(target: string, replicas: number): Promise<void> {
    if (!ALLOWED_DOCKER_TARGETS.includes(target as DockerTarget)) {
      throw new Error("docker_target_not_allowlisted");
    }

    if (!Number.isInteger(replicas) || replicas < 1 || replicas > 5) {
      throw new Error("invalid_replica_count");
    }

    const allowedTarget = target as DockerTarget;

    const before = await this.adapter.inspectService(allowedTarget);

    if (before.name !== allowedTarget) {
      throw new Error("docker_service_identity_mismatch");
    }

    if (!Number.isInteger(before.replicas) || before.replicas < 0) {
      throw new Error("invalid_docker_service_state");
    }

    if (before.replicas === replicas) {
      return;
    }

    await this.adapter.scaleService(allowedTarget, replicas);

    const after = await this.adapter.inspectService(allowedTarget);

    if (after.name !== allowedTarget || after.replicas !== replicas) {
      throw new Error("docker_scale_verification_failed");
    }
  }
}
