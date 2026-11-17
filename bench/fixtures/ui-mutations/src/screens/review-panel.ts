import type { FakeServer } from '../api/fake-server.ts';
import type { ActivityEntry, Doc, DocAction } from '../api/types.ts';
import { Mutation } from '../lib/mutation.ts';
import type { QueryClient } from '../lib/query-client.ts';

export const ACTION_LABELS: Record<DocAction, string> = {
  submit: 'Submit for review',
  approve: 'Approve',
  reject: 'Send back',
  archive: 'Archive',
  reopen: 'Reopen',
};

export function availableActions(doc: Doc): DocAction[] {
  switch (doc.status) {
    case 'draft':
      return ['submit', 'archive'];
    case 'in_review':
      return ['approve', 'reject'];
    case 'rejected':
      return ['submit', 'archive'];
    case 'approved':
      return ['archive'];
    case 'archived':
      return ['reopen'];
  }
}

/** The side panel for one document: its history, the workflow buttons and bulk archive. */
export class ReviewPanelController {
  doc: Doc | null = null;
  activity: ActivityEntry[] = [];
  actionError: string | null = null;
  busy = false;
  notice: string | null = null;
  readonly transition: Mutation<{ id: string; action: DocAction }, Doc>;

  private readonly api: FakeServer;

  constructor(api: FakeServer, client: QueryClient, user: string) {
    this.api = api;
    this.transition = new Mutation({
      mutationFn: ({ id, action }) => api.transition(id, action, user),
      onSuccess: (doc) => {
        client.setQueryData<Doc[]>(['docs', doc.folder], (docs = []) => docs.map((d) => (d.id === doc.id ? doc : d)));
      },
    });
  }

  get actions(): DocAction[] {
    return this.doc ? availableActions(this.doc) : [];
  }

  get canArchiveSelection(): boolean {
    return !this.busy;
  }

  async show(doc: Doc | null): Promise<void> {
    this.doc = doc;
    this.actionError = null;
    this.transition.reset();
    if (!doc) {
      this.activity = [];
      return;
    }
    this.activity = await this.api.listActivity(doc.id);
  }

  run(action: DocAction): void {
    const doc = this.doc;
    if (!doc) return;
    this.actionError = null;
    this.transition.mutate(
      { id: doc.id, action },
      {
        onSuccess: (updated) => {
          this.doc = updated;
        },
        onError: (error) => {
          this.actionError = error.message;
        },
      },
    );
  }

  async archiveMany(ids: string[]): Promise<void> {
    this.busy = true;
    this.notice = null;
    for (const id of ids) {
      await this.transition.mutateAsync({ id, action: 'archive' });
    }
    this.busy = false;
    this.notice = `Archived ${ids.length} document${ids.length === 1 ? '' : 's'}`;
  }
}
