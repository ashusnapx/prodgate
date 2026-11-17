import type { FakeBackend } from '../api.ts';

export type UploadStatus = 'queued' | 'uploading' | 'done' | 'failed';

export interface UploadItem {
  id: string;
  name: string;
  bytes: Uint8Array;
  status: UploadStatus;
  error: string | null;
  attempts: number;
}

export interface StoredUpload {
  id: string;
  name: string;
  bytes: Uint8Array;
  status: UploadStatus;
}

/** Where the queue keeps its files so a reload can pick up where it left off (IndexedDB in the app). */
export interface QueueStore {
  save(items: StoredUpload[]): void;
  load(): StoredUpload[];
}

export class MemoryStore implements QueueStore {
  saved: StoredUpload[] = [];

  save(items: StoredUpload[]): void {
    this.saved = items.map((item) => ({ ...item }));
  }

  load(): StoredUpload[] {
    return this.saved.map((item) => ({ ...item }));
  }
}

/** The data-room upload tray: files upload two at a time, failures can be retried. */
export class UploadQueue {
  items: UploadItem[] = [];
  onChange: (() => void) | null = null;

  private readonly api: FakeBackend;
  private readonly store: QueueStore;
  private readonly concurrency: number;
  private active = 0;
  private nextId = 1;

  constructor(api: FakeBackend, store: QueueStore, concurrency = 2) {
    this.api = api;
    this.store = store;
    this.concurrency = concurrency;
  }

  get summary(): { queued: number; uploading: number; done: number; failed: number } {
    const count = (status: UploadStatus) => this.items.filter((item) => item.status === status).length;
    return { queued: count('queued'), uploading: count('uploading'), done: count('done'), failed: count('failed') };
  }

  restore(): void {
    this.items = this.store.load().map((stored) => ({ ...stored, error: null, attempts: 0 }));
    this.nextId = this.items.length + 1;
    this.pump();
  }

  add(files: { name: string; bytes: Uint8Array }[]): void {
    for (const file of files) {
      this.items.push({ id: `u${this.nextId++}`, ...file, status: 'queued', error: null, attempts: 0 });
    }
    this.persist();
    this.pump();
  }

  retry(id: string): void {
    const item = this.items.find((i) => i.id === id);
    if (!item || item.status !== 'failed') return;
    item.error = null;
    void this.upload(item);
  }

  remove(id: string): void {
    this.items = this.items.filter((item) => item.id !== id || item.status === 'uploading');
    this.persist();
  }

  clearFinished(): void {
    this.items = this.items.filter((item) => item.status !== 'done');
    this.persist();
  }

  private pump(): void {
    while (this.active < this.concurrency) {
      const next = this.items.find((item) => item.status === 'queued');
      if (!next) break;
      next.status = 'uploading';
      this.active++;
      void this.upload(next).finally(() => {
        this.active--;
        this.pump();
      });
    }
    this.persist();
  }

  private async upload(item: UploadItem): Promise<void> {
    item.attempts++;
    try {
      const { sessionId } = await this.api.createUploadSession(item.name, item.bytes.length);
      item.status = 'uploading';
      this.changed();
      await this.api.uploadBytes(sessionId, item.bytes);
      await this.api.completeUpload(sessionId);
      item.status = 'done';
    } catch (error) {
      item.status = 'failed';
      item.error = (error as Error).message;
    } finally {
      this.persist();
      this.changed();
    }
  }

  private persist(): void {
    this.store.save(
      this.items
        .filter((item) => item.status === 'queued' || item.status === 'failed')
        .map(({ id, name, bytes, status }) => ({ id, name, bytes, status })),
    );
  }

  private changed(): void {
    this.onChange?.();
  }
}
