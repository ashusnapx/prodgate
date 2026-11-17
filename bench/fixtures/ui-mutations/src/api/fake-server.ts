import type { ActivityEntry, Doc, DocAction, DocStatus, Fund, FundPatch } from './types.ts';

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export const TRANSITIONS: Record<DocAction, { from: DocStatus[]; to: DocStatus }> = {
  submit: { from: ['draft', 'rejected'], to: 'in_review' },
  approve: { from: ['in_review'], to: 'approved' },
  reject: { from: ['in_review'], to: 'rejected' },
  archive: { from: ['draft', 'approved', 'rejected'], to: 'archived' },
  reopen: { from: ['archived'], to: 'draft' },
};

export type BeforeHook = (op: string, args: unknown[]) => Promise<void> | void;

/** In-memory stand-in for the documents and funds HTTP API, with the same rules. */
export class FakeServer {
  before: BeforeHook | null = null;
  private readonly docs = new Map<string, Doc>();
  private readonly funds = new Map<string, Fund>();
  private readonly failures = new Map<string, ApiError[]>();
  private readonly activity: ActivityEntry[] = [];
  private nextId = 1;
  private clock = 1_000;

  failNext(op: string, error: ApiError = new ApiError(500, 'Something went wrong')): void {
    const queue = this.failures.get(op) ?? [];
    queue.push(error);
    this.failures.set(op, queue);
  }

  seedDoc(fields: Partial<Doc> & { title: string }): Doc {
    const doc: Doc = {
      id: `doc-${this.nextId++}`,
      folder: 'inbox',
      author: 'ana',
      status: 'draft',
      starred: false,
      updatedAt: ++this.clock,
      ...fields,
    };
    this.docs.set(doc.id, doc);
    return structuredClone(doc);
  }

  seedFund(fields: Partial<Fund> & { name: string }): Fund {
    const fund: Fund = {
      id: `fund-${this.nextId++}`,
      vintage: 2024,
      currency: 'USD',
      targetSize: 100_000_000,
      notes: '',
      version: 1,
      ...fields,
    };
    this.funds.set(fund.id, fund);
    return structuredClone(fund);
  }

  listDocs(query: { folder: string; search?: string }): Promise<Doc[]> {
    return this.call('listDocs', [query], () => {
      const needle = query.search?.trim().toLowerCase() ?? '';
      return [...this.docs.values()]
        .filter((doc) => doc.folder === query.folder && doc.title.toLowerCase().includes(needle))
        .sort((a, b) => b.updatedAt - a.updatedAt);
    });
  }

  createDoc(input: { title: string; folder: string; author: string }): Promise<Doc> {
    return this.call('createDoc', [input], () => {
      if (!input.title.trim()) throw new ApiError(422, 'Title is required');
      const doc: Doc = { id: `doc-${this.nextId++}`, status: 'draft', starred: false, updatedAt: ++this.clock, ...input };
      this.docs.set(doc.id, doc);
      this.activity.push({ docId: doc.id, action: 'create', actor: input.author, at: doc.updatedAt });
      return doc;
    });
  }

  setStarred(id: string, starred: boolean): Promise<Doc> {
    return this.call('setStarred', [id, starred], () => this.update(id, { starred }));
  }

  deleteDoc(id: string): Promise<{ id: string }> {
    return this.call('deleteDoc', [id], () => {
      this.doc(id);
      this.docs.delete(id);
      return { id };
    });
  }

  transition(id: string, action: DocAction, actor: string): Promise<Doc> {
    return this.call('transition', [id, action, actor], () => {
      const doc = this.doc(id);
      const rule = TRANSITIONS[action];
      if (!rule.from.includes(doc.status)) {
        throw new ApiError(409, `Cannot ${action} a document that is ${doc.status}`);
      }
      if ((action === 'approve' || action === 'reject') && doc.author === actor) {
        throw new ApiError(403, 'You cannot review your own document');
      }
      const updated = this.update(id, { status: rule.to });
      this.activity.push({ docId: id, action, actor, at: updated.updatedAt });
      return updated;
    });
  }

  listActivity(docId: string): Promise<ActivityEntry[]> {
    return this.call('listActivity', [docId], () => this.activity.filter((entry) => entry.docId === docId));
  }

  getFund(id: string): Promise<Fund> {
    return this.call('getFund', [id], () => this.fund(id));
  }

  updateFund(id: string, patch: FundPatch, version: number): Promise<Fund> {
    return this.call('updateFund', [id, patch, version], () => {
      const fund = this.fund(id);
      if (fund.version !== version) throw new ApiError(409, 'This fund was changed by someone else. Reload it.');
      if (patch.targetSize !== undefined && patch.targetSize <= 0) {
        throw new ApiError(422, 'Target size must be positive');
      }
      Object.assign(fund, patch, { version: fund.version + 1 });
      return fund;
    });
  }

  private async call<T>(op: string, args: unknown[], fn: () => T): Promise<T> {
    await this.before?.(op, args);
    const failure = this.failures.get(op)?.shift();
    if (failure) throw failure;
    return structuredClone(fn());
  }

  private doc(id: string): Doc {
    const doc = this.docs.get(id);
    if (!doc) throw new ApiError(404, `Document ${id} not found`);
    return doc;
  }

  private fund(id: string): Fund {
    const fund = this.funds.get(id);
    if (!fund) throw new ApiError(404, `Fund ${id} not found`);
    return fund;
  }

  private update(id: string, fields: Partial<Doc>): Doc {
    const doc = this.doc(id);
    Object.assign(doc, fields, { updatedAt: ++this.clock });
    return doc;
  }
}
