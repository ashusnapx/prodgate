import type { FakeBackend, InvestmentPayload } from '../api.ts';

export interface InvestmentAnswers {
  company: string;
  round: string;
  amount: string;
  ownershipPct: string;
  closeDate: string;
}

export type AnswerErrors = Partial<Record<keyof InvestmentAnswers, string>>;

interface Step {
  id: 'company' | 'terms' | 'review';
  title: string;
  validate: (answers: InvestmentAnswers) => AnswerErrors;
}

const EMPTY: InvestmentAnswers = { company: '', round: 'Series A', amount: '', ownershipPct: '', closeDate: '' };

export const STEPS: Step[] = [
  {
    id: 'company',
    title: 'Company',
    validate: (a) => (a.company.trim() ? {} : { company: 'Enter the company name' }),
  },
  {
    id: 'terms',
    title: 'Terms',
    validate: (a) => {
      const errors: AnswerErrors = {};
      if (!(Number(a.amount) > 0)) errors.amount = 'Enter the amount invested';
      const pct = Number(a.ownershipPct);
      if (!(pct > 0 && pct <= 100)) errors.ownershipPct = 'Ownership must be between 0 and 100%';
      if (!/^\d{4}-\d{2}-\d{2}$/.test(a.closeDate)) errors.closeDate = 'Use YYYY-MM-DD';
      return errors;
    },
  },
  { id: 'review', title: 'Review', validate: () => ({}) },
];

export function toPayload(a: InvestmentAnswers): InvestmentPayload {
  return {
    company: a.company.trim(),
    round: a.round,
    amount: Number(a.amount),
    ownershipPct: Number(a.ownershipPct),
    closeDate: a.closeDate,
  };
}

/** "Add investment" wizard shown in the side sheet of a fund. One instance serves every fund. */
export class InvestmentWizard {
  fundId: string | null = null;
  stepIndex = 0;
  furthest = 0;
  answers: InvestmentAnswers = { ...EMPTY };
  errors: AnswerErrors = {};
  submitting = false;
  submitError: string | null = null;
  createdId: string | null = null;

  private readonly api: FakeBackend;

  constructor(api: FakeBackend) {
    this.api = api;
  }

  get step(): Step {
    return STEPS[this.stepIndex];
  }

  open(fundId: string): void {
    if (fundId === this.fundId) return;
    this.fundId = fundId;
    this.stepIndex = 0;
    this.furthest = 0;
    this.errors = {};
    this.submitError = null;
    this.createdId = null;
  }

  set<K extends keyof InvestmentAnswers>(field: K, value: InvestmentAnswers[K]): void {
    this.answers = { ...this.answers, [field]: value };
    const { [field]: _cleared, ...rest } = this.errors;
    this.errors = rest;
  }

  next(): boolean {
    this.errors = this.step.validate(this.answers);
    if (Object.keys(this.errors).length > 0) return false;
    this.stepIndex = Math.min(this.stepIndex + 1, STEPS.length - 1);
    this.furthest = Math.max(this.furthest, this.stepIndex);
    return true;
  }

  back(): void {
    this.stepIndex = Math.max(0, this.stepIndex - 1);
    this.errors = {};
  }

  canGoTo(index: number): boolean {
    return index >= 0 && index <= this.furthest;
  }

  goTo(index: number): boolean {
    if (!this.canGoTo(index)) return false;
    this.stepIndex = index;
    this.errors = {};
    return true;
  }

  async submit(): Promise<void> {
    if (!this.fundId || this.step.id !== 'review' || this.submitting) return;
    this.submitting = true;
    this.submitError = null;
    try {
      const created = await this.api.createInvestment(this.fundId, toPayload(this.answers));
      this.createdId = created.id;
    } catch (error) {
      this.submitError = (error as Error).message;
    } finally {
      this.submitting = false;
    }
  }
}
