export interface BudgetConfig {
  perTargetLimit: number;
  globalLimit: number;
  windowMs: number;
  cooldownMs: number;
}

export const DEFAULT_BUDGET: BudgetConfig = {
  perTargetLimit: 3,
  globalLimit: 8,
  windowMs: 15 * 60 * 1000,
  cooldownMs: 90 * 1000,
};

export type BudgetDecision =
  | { allowed: true }
  | { allowed: false; reason: string };

export class SafetyBudget {
  private readonly history = new Map<string, number[]>();
  private readonly active = new Set<string>();

  constructor(
    private readonly config: BudgetConfig = DEFAULT_BUDGET,
    private readonly now: () => number = Date.now,
  ) {}

  check(target: string): BudgetDecision {
    const currentTime = this.now();

    if (this.active.has(target)) {
      return { allowed: false, reason: "target_mutex_locked" };
    }

    const cutoff = currentTime - this.config.windowMs;
    let globalCount = 0;

    for (const [key, timestamps] of this.history) {
      const recent = timestamps.filter(time => time > cutoff);

      if (recent.length === 0) {
        this.history.delete(key);
      } else {
        this.history.set(key, recent);
        globalCount += recent.length;
      }
    }

    const targetHistory = this.history.get(target) ?? [];

    if (targetHistory.length >= this.config.perTargetLimit) {
      return { allowed: false, reason: "target_budget_exceeded" };
    }

    if (globalCount >= this.config.globalLimit) {
      return { allowed: false, reason: "global_budget_exceeded" };
    }

    const lastAction = targetHistory.at(-1);

    if (
      lastAction !== undefined &&
      currentTime - lastAction < this.config.cooldownMs
    ) {
      return { allowed: false, reason: "target_cooldown_active" };
    }

    return { allowed: true };
  }

  async execute<T>(
    target: string,
    operation: () => Promise<T>,
  ): Promise<T> {
    const decision = this.check(target);

    if (!decision.allowed) {
      throw new Error(decision.reason);
    }

    this.active.add(target);

    // Reserve the budget before executing to prevent concurrent bypasses.
    const timestamps = this.history.get(target) ?? [];
    timestamps.push(this.now());
    this.history.set(target, timestamps);

    try {
      return await operation();
    } finally {
      this.active.delete(target);
    }
  }
}
