import type { FakeBackend, ScenarioInputs, ScenarioVersion } from '../api.ts';

export const DEFAULT_INPUTS: ScenarioInputs = { revenueGrowth: 0.08, ebitdaMargin: 0.22, exitMultiple: 10, holdYears: 5 };

export function sameInputs(a: ScenarioInputs, b: ScenarioInputs): boolean {
  return (Object.keys(a) as (keyof ScenarioInputs)[]).every((key) => a[key] === b[key]);
}

/**
 * The bar above the returns model: which scenario is open, whether it has
 * unsaved edits, and Save / Open / Reset.
 */
export class ScenarioBar {
  inputs: ScenarioInputs;
  baseline: ScenarioInputs;
  openedId: string | null = null;
  openedName: string | null = null;
  revision = 0;
  versions: ScenarioVersion[] = [];
  saving = false;
  saveError: string | null = null;

  private readonly api: FakeBackend;
  private readonly defaults: ScenarioInputs;
  private readonly confirmDiscard: () => Promise<boolean>;

  constructor(api: FakeBackend, confirmDiscard: () => Promise<boolean>, defaults: ScenarioInputs = DEFAULT_INPUTS) {
    this.api = api;
    this.confirmDiscard = confirmDiscard;
    this.defaults = { ...defaults };
    this.inputs = { ...defaults };
    this.baseline = { ...defaults };
  }

  get dirty(): boolean {
    return !sameInputs(this.inputs, this.baseline);
  }

  get title(): string {
    return `${this.openedName ?? 'Untitled scenario'}${this.dirty ? ' (edited)' : ''}`;
  }

  edit<K extends keyof ScenarioInputs>(field: K, value: ScenarioInputs[K]): void {
    this.inputs = { ...this.inputs, [field]: value };
  }

  reset(): void {
    this.inputs = { ...this.defaults };
    this.baseline = { ...this.defaults };
    this.saveError = null;
  }

  async open(id: string): Promise<boolean> {
    if (this.openedId !== null && this.dirty && !(await this.confirmDiscard())) return false;
    const version = await this.api.getVersion(id);
    this.inputs = { ...version.inputs };
    this.baseline = { ...version.inputs };
    this.openedId = version.id;
    this.openedName = version.name;
    this.revision = version.revision;
    this.saveError = null;
    return true;
  }

  async loadVersions(): Promise<void> {
    this.versions = await this.api.listVersions();
  }

  async save(name?: string): Promise<void> {
    if (this.saving) return;
    this.saving = true;
    this.saveError = null;
    const snapshot = { ...this.inputs };
    try {
      const version = this.openedId
        ? await this.api.updateVersion(this.openedId, snapshot, this.revision)
        : await this.api.createVersion(name?.trim() || 'Untitled scenario', snapshot);
      this.baseline = snapshot;
      this.openedId = version.id;
      this.openedName = version.name;
      this.revision = version.revision;
      this.versions = [...this.versions.filter((v) => v.id !== version.id), version];
    } catch (error) {
      this.saveError = (error as Error).message;
    } finally {
      this.saving = false;
    }
  }
}
