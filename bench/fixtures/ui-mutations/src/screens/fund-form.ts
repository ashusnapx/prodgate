import type { FakeServer } from '../api/fake-server.ts';
import type { Fund, FundPatch } from '../api/types.ts';
import { Mutation } from '../lib/mutation.ts';
import type { QueryClient } from '../lib/query-client.ts';

export interface FundDraft {
  name: string;
  vintage: string;
  currency: string;
  targetSize: string;
  notes: string;
}

export type FieldErrors = Partial<Record<keyof FundDraft, string>>;

const CURRENCIES = ['USD', 'EUR', 'GBP', 'INR'];

export function toDraft(fund: Fund): FundDraft {
  return {
    name: fund.name,
    vintage: String(fund.vintage),
    currency: fund.currency,
    targetSize: String(fund.targetSize),
    notes: fund.notes,
  };
}

export function validate(draft: FundDraft): FieldErrors {
  const errors: FieldErrors = {};
  if (!draft.name.trim()) errors.name = 'Name is required';
  const vintage = Number(draft.vintage);
  if (!Number.isInteger(vintage) || vintage < 1980 || vintage > 2100) errors.vintage = 'Enter a year';
  if (!CURRENCIES.includes(draft.currency)) errors.currency = 'Pick a currency';
  if (!(Number(draft.targetSize) > 0)) errors.targetSize = 'Enter a positive amount';
  return errors;
}

export function changes(fund: Fund, draft: FundDraft): FundPatch {
  const patch: FundPatch = {};
  if (draft.name.trim() !== fund.name) patch.name = draft.name.trim();
  if (Number(draft.vintage) !== fund.vintage) patch.vintage = Number(draft.vintage);
  if (draft.currency !== fund.currency) patch.currency = draft.currency;
  if (Number(draft.targetSize) !== fund.targetSize) patch.targetSize = Number(draft.targetSize);
  if (draft.notes !== fund.notes) patch.notes = draft.notes;
  return patch;
}

/** State behind the "Edit fund" form. One controller serves whichever fund is open. */
export class FundFormController {
  fundId: string | null = null;
  fund: Fund | null = null;
  draft: FundDraft | null = null;
  dirty = false;
  loading = false;
  loadError: string | null = null;
  errorMessage: string | null = null;
  fieldErrors: FieldErrors = {};
  savedAt: number | null = null;
  readonly save: Mutation<{ id: string; patch: FundPatch; version: number }, Fund>;

  private readonly api: FakeServer;
  private readonly client: QueryClient;

  constructor(api: FakeServer, client: QueryClient) {
    this.api = api;
    this.client = client;
    this.save = new Mutation({
      mutationFn: ({ id, patch, version }) => api.updateFund(id, patch, version),
      onSuccess: (fund, { id }) => {
        client.setQueryData(['fund', id], fund);
        void client.invalidateQueries(['funds']);
      },
    });
  }

  get canSave(): boolean {
    return this.dirty && !this.save.isPending;
  }

  async open(fundId: string): Promise<void> {
    this.fundId = fundId;
    this.loading = true;
    this.loadError = null;
    this.errorMessage = null;
    this.save.reset();
    try {
      const fund = await this.client.fetchQuery(['fund', fundId], () => this.api.getFund(fundId));
      if (this.fundId !== fundId) return;
      this.fund = fund;
      this.draft ??= toDraft(fund);
    } catch (error) {
      if (this.fundId === fundId) this.loadError = (error as Error).message;
    } finally {
      if (this.fundId === fundId) this.loading = false;
    }
  }

  update(field: keyof FundDraft, value: string): void {
    if (!this.draft) return;
    this.draft = { ...this.draft, [field]: value };
    this.dirty = true;
    const { [field]: _cleared, ...rest } = this.fieldErrors;
    this.fieldErrors = rest;
  }

  submit(): void {
    const fund = this.fund;
    if (!fund || !this.draft) return;
    this.fieldErrors = validate(this.draft);
    if (Object.keys(this.fieldErrors).length > 0) return;
    this.save.mutate(
      { id: fund.id, patch: changes(fund, this.draft), version: fund.version },
      {
        onSuccess: (saved) => {
          this.fund = saved;
          this.draft = toDraft(saved);
          this.dirty = false;
          this.savedAt = Date.now();
        },
        onError: (error) => {
          this.errorMessage = error.message;
        },
      },
    );
  }

  discard(): void {
    if (!this.fund) return;
    this.draft = toDraft(this.fund);
    this.dirty = false;
    this.fieldErrors = {};
  }
}
