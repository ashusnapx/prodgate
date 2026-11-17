import type { FakeBackend, Job } from '../api.ts';

export interface Scheduler {
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
}

export const realScheduler: Scheduler = {
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
};

/** Watches one background job and keeps the status chip on the page current. */
export class JobPoller {
  jobId: string | null = null;
  job: Job | null = null;
  error: string | null = null;
  polling = false;
  onFinished: ((job: Job) => void) | null = null;

  private readonly api: FakeBackend;
  private readonly scheduler: Scheduler;
  private readonly intervalMs: number;
  private timer: unknown = null;
  private generation = 0;

  constructor(api: FakeBackend, scheduler: Scheduler = realScheduler, intervalMs = 2_000) {
    this.api = api;
    this.scheduler = scheduler;
    this.intervalMs = intervalMs;
  }

  get label(): string {
    if (!this.job) return this.polling ? 'Checking…' : '';
    switch (this.job.status) {
      case 'queued':
        return 'Waiting to start';
      case 'running':
        return `Running (${Math.round(this.job.progress * 100)}%)`;
      case 'succeeded':
        return 'Finished';
      case 'failed':
        return `Failed: ${this.job.message ?? 'unknown error'}`;
      case 'cancelled':
        return 'Cancelled';
    }
  }

  watch(jobId: string): void {
    this.stop();
    this.jobId = jobId;
    this.job = null;
    this.error = null;
    this.polling = true;
    void this.check(++this.generation);
  }

  stop(): void {
    this.generation++;
    this.polling = false;
    if (this.timer !== null) this.scheduler.clearTimeout(this.timer);
    this.timer = null;
  }

  private async check(generation: number): Promise<void> {
    const jobId = this.jobId;
    if (!jobId) return;
    try {
      const job = await this.api.getJob(jobId);
      if (generation !== this.generation) return;
      this.job = job;
      this.error = null;
      if (job.status === 'succeeded' || job.status === 'failed') {
        this.polling = false;
        this.onFinished?.(job);
        return;
      }
    } catch (error) {
      if (generation !== this.generation) return;
      this.error = (error as Error).message;
      this.polling = false;
      return;
    }
    this.timer = this.scheduler.setTimeout(() => void this.check(generation), this.intervalMs);
  }
}
