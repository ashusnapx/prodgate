import type { FakeServer } from '../api/fake-server.ts';
import type { Doc } from '../api/types.ts';
import { Mutation } from '../lib/mutation.ts';
import type { QueryClient } from '../lib/query-client.ts';

export interface PendingRow {
  tempId: string;
  title: string;
  failed: boolean;
}

interface StarContext {
  previous: Doc[] | undefined;
}

/** State behind the documents table: rows, selection, quick add, star and delete. */
export class DocumentListController {
  readonly folder: string;
  docs: Doc[] = [];
  loading = false;
  loadError: string | null = null;
  selectedId: string | null = null;
  selected: Doc | null = null;
  pendingRows: PendingRow[] = [];

  readonly create: Mutation<{ title: string }, Doc>;
  readonly star: Mutation<{ id: string; starred: boolean }, Doc, StarContext>;
  readonly remove: Mutation<string, { id: string }>;

  private readonly api: FakeServer;
  private readonly client: QueryClient;
  private readonly unsubscribe: () => void;
  private tempSeq = 0;

  constructor(api: FakeServer, client: QueryClient, folder: string, user: string) {
    this.api = api;
    this.client = client;
    this.folder = folder;
    this.unsubscribe = client.subscribe(this.key, () => {
      this.docs = client.getQueryData<Doc[]>(this.key) ?? [];
    });

    this.create = new Mutation({
      mutationFn: ({ title }) => api.createDoc({ title, folder, author: user }),
      onSuccess: () => client.invalidateQueries(['docs', folder]),
    });

    this.star = new Mutation<{ id: string; starred: boolean }, Doc, StarContext>({
      mutationFn: ({ id, starred }) => api.setStarred(id, starred),
      onMutate: ({ id, starred }) => {
        const previous = client.getQueryData<Doc[]>(this.key);
        const doc = previous?.find((d) => d.id === id);
        if (doc) doc.starred = starred;
        client.setQueryData(this.key, previous);
        return { previous };
      },
      onError: (_error, _vars, context) => {
        if (context?.previous) client.setQueryData(this.key, context.previous);
      },
    });

    this.remove = new Mutation({
      mutationFn: (id: string) => api.deleteDoc(id),
      onSuccess: (_result, id) => {
        client.setQueryData<Doc[]>(this.key, (docs = []) => docs.filter((d) => d.id !== id));
      },
    });
  }

  get key(): readonly unknown[] {
    return ['docs', this.folder];
  }

  async load(): Promise<void> {
    this.loading = true;
    try {
      await this.client.fetchQuery(this.key, () => this.api.listDocs({ folder: this.folder }));
      this.loadError = null;
    } catch (error) {
      this.loadError = (error as Error).message;
    } finally {
      this.loading = false;
    }
  }

  select(id: string | null): void {
    this.selectedId = id;
    this.selected = id ? (this.docs.find((d) => d.id === id) ?? null) : null;
  }

  addDocument(title: string): void {
    const tempId = `pending-${++this.tempSeq}`;
    this.pendingRows = [...this.pendingRows, { tempId, title, failed: false }];
    this.create.mutate(
      { title },
      {
        onSuccess: () => {
          this.pendingRows = this.pendingRows.filter((row) => row.tempId !== tempId);
        },
        onError: () => {
          this.pendingRows = this.pendingRows.map((row) => (row.tempId === tempId ? { ...row, failed: true } : row));
        },
      },
    );
  }

  dismissFailed(tempId: string): void {
    this.pendingRows = this.pendingRows.filter((row) => row.tempId !== tempId);
  }

  toggleStar(id: string): void {
    const doc = this.docs.find((d) => d.id === id);
    if (doc) this.star.mutate({ id, starred: !doc.starred });
  }

  async deleteDocument(id: string): Promise<void> {
    await this.remove.mutateAsync(id);
  }

  dispose(): void {
    this.unsubscribe();
  }
}
