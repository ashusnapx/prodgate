import type { Scheduler } from '../src/flows/job-poller.ts';

export async function settle(rounds = 8): Promise<void> {
  for (let i = 0; i < rounds; i++) await new Promise((resolve) => setImmediate(resolve));
}

export class ManualScheduler implements Scheduler {
  private queue: { at: number; fn: () => void; handle: number }[] = [];
  private now = 0;
  private nextHandle = 1;

  setTimeout(fn: () => void, ms: number): unknown {
    const handle = this.nextHandle++;
    this.queue.push({ at: this.now + ms, fn, handle });
    return handle;
  }

  clearTimeout(handle: unknown): void {
    this.queue = this.queue.filter((t) => t.handle !== handle);
  }

  get pending(): number {
    return this.queue.length;
  }

  async advance(ms: number): Promise<void> {
    this.now += ms;
    const due = this.queue.filter((t) => t.at <= this.now);
    this.queue = this.queue.filter((t) => t.at > this.now);
    for (const t of due) t.fn();
    await settle();
  }
}
