export type QueryKey = readonly unknown[];
export type QueryStatus = 'idle' | 'loading' | 'success' | 'error';

interface Entry {
  key: QueryKey;
  data: unknown;
  error: Error | null;
  status: QueryStatus;
  updatedAt: number;
  fetcher: (() => Promise<unknown>) | null;
  inflight: Promise<unknown> | null;
  listeners: Set<() => void>;
}

const hashKey = (key: QueryKey): string => JSON.stringify(key);

function startsWith(key: QueryKey, prefix: QueryKey): boolean {
  return prefix.every((part, index) => hashKey([part]) === hashKey([key[index]]));
}

export class QueryClient {
  private readonly entries = new Map<string, Entry>();
  private clock = 0;

  private entry(key: QueryKey): Entry {
    const hash = hashKey(key);
    let found = this.entries.get(hash);
    if (!found) {
      found = {
        key,
        data: undefined,
        error: null,
        status: 'idle',
        updatedAt: 0,
        fetcher: null,
        inflight: null,
        listeners: new Set(),
      };
      this.entries.set(hash, found);
    }
    return found;
  }

  fetchQuery<T>(key: QueryKey, fetcher: () => Promise<T>): Promise<T> {
    const entry = this.entry(key);
    entry.fetcher = fetcher;
    if (entry.inflight) return entry.inflight as Promise<T>;
    entry.status = 'loading';
    const run = fetcher().then(
      (data) => {
        entry.inflight = null;
        this.write(entry, data);
        return data;
      },
      (raw) => {
        entry.inflight = null;
        entry.error = raw instanceof Error ? raw : new Error(String(raw));
        entry.status = 'error';
        this.notify(entry);
        throw entry.error;
      },
    );
    entry.inflight = run;
    return run;
  }

  getQueryData<T>(key: QueryKey): T | undefined {
    return this.entries.get(hashKey(key))?.data as T | undefined;
  }

  getStatus(key: QueryKey): QueryStatus {
    return this.entries.get(hashKey(key))?.status ?? 'idle';
  }

  setQueryData<T>(key: QueryKey, updater: T | ((old: T | undefined) => T)): void {
    const entry = this.entry(key);
    const next =
      typeof updater === 'function' ? (updater as (old: T | undefined) => T)(entry.data as T | undefined) : updater;
    this.write(entry, next);
  }

  async invalidateQueries(prefix: QueryKey): Promise<void> {
    const refetches: Promise<unknown>[] = [];
    for (const entry of this.entries.values()) {
      if (!startsWith(entry.key, prefix)) continue;
      entry.updatedAt = 0;
      if (entry.fetcher && entry.listeners.size > 0) {
        refetches.push(this.fetchQuery(entry.key, entry.fetcher).catch(() => undefined));
      }
    }
    await Promise.all(refetches);
  }

  removeQueries(prefix: QueryKey): void {
    for (const [hash, entry] of this.entries) {
      if (startsWith(entry.key, prefix)) this.entries.delete(hash);
    }
  }

  subscribe(key: QueryKey, listener: () => void): () => void {
    const entry = this.entry(key);
    entry.listeners.add(listener);
    return () => entry.listeners.delete(listener);
  }

  private write(entry: Entry, data: unknown): void {
    entry.data = data;
    entry.error = null;
    entry.status = 'success';
    entry.updatedAt = ++this.clock;
    this.notify(entry);
  }

  private notify(entry: Entry): void {
    for (const listener of entry.listeners) listener();
  }
}
