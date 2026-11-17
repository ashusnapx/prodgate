export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';

export interface Job {
  id: string;
  kind: string;
  status: JobStatus;
  progress: number;
  message: string | null;
}

export interface ScenarioInputs {
  revenueGrowth: number;
  ebitdaMargin: number;
  exitMultiple: number;
  holdYears: number;
}

export interface ScenarioVersion {
  id: string;
  name: string;
  inputs: ScenarioInputs;
  revision: number;
}

export interface InvestmentPayload {
  company: string;
  round: string;
  amount: number;
  ownershipPct: number;
  closeDate: string;
}

export type BeforeHook = (op: string, args: unknown[]) => Promise<void> | void;

/** In-memory stand-in for the jobs, investments, scenarios and uploads endpoints. */
export class FakeBackend {
  before: BeforeHook | null = null;
  readonly jobs = new Map<string, Job>();
  readonly versions = new Map<string, ScenarioVersion>();
  readonly investments: (InvestmentPayload & { id: string; fundId: string })[] = [];
  readonly uploads: { sessionId: string; name: string; size: number; received: number; complete: boolean }[] = [];
  private readonly failures = new Map<string, ApiError[]>();
  private nextId = 1;

  failNext(op: string, error: ApiError = new ApiError(503, 'Service unavailable')): void {
    const queue = this.failures.get(op) ?? [];
    queue.push(error);
    this.failures.set(op, queue);
  }

  setJob(job: Partial<Job> & { id: string }): void {
    const current = this.jobs.get(job.id);
    this.jobs.set(job.id, { kind: 'import', status: 'queued', progress: 0, message: null, ...current, ...job });
  }

  getJob(id: string): Promise<Job> {
    return this.call('getJob', [id], () => {
      const job = this.jobs.get(id);
      if (!job) throw new ApiError(404, `Job ${id} not found`);
      return job;
    });
  }

  createInvestment(fundId: string, payload: InvestmentPayload): Promise<{ id: string }> {
    return this.call('createInvestment', [fundId, payload], () => {
      if (!payload.company.trim()) throw new ApiError(422, 'Company is required');
      const record = { id: `inv-${this.nextId++}`, fundId, ...payload };
      this.investments.push(record);
      return { id: record.id };
    });
  }

  listVersions(): Promise<ScenarioVersion[]> {
    return this.call('listVersions', [], () => [...this.versions.values()]);
  }

  getVersion(id: string): Promise<ScenarioVersion> {
    return this.call('getVersion', [id], () => {
      const version = this.versions.get(id);
      if (!version) throw new ApiError(404, `Scenario ${id} not found`);
      return version;
    });
  }

  createVersion(name: string, inputs: ScenarioInputs): Promise<ScenarioVersion> {
    return this.call('createVersion', [name, inputs], () => {
      const version = { id: `sc-${this.nextId++}`, name, inputs: { ...inputs }, revision: 1 };
      this.versions.set(version.id, version);
      return version;
    });
  }

  updateVersion(id: string, inputs: ScenarioInputs, revision: number): Promise<ScenarioVersion> {
    return this.call('updateVersion', [id, inputs, revision], () => {
      const version = this.versions.get(id);
      if (!version) throw new ApiError(404, `Scenario ${id} not found`);
      if (version.revision !== revision) throw new ApiError(409, 'Someone saved this scenario after you opened it');
      Object.assign(version, { inputs: { ...inputs }, revision: revision + 1 });
      return version;
    });
  }

  createUploadSession(name: string, size: number): Promise<{ sessionId: string }> {
    return this.call('createUploadSession', [name, size], () => {
      const sessionId = `up-${this.nextId++}`;
      this.uploads.push({ sessionId, name, size, received: 0, complete: false });
      return { sessionId };
    });
  }

  uploadBytes(sessionId: string, bytes: Uint8Array): Promise<void> {
    return this.call('uploadBytes', [sessionId, bytes.length], () => {
      this.session(sessionId).received += bytes.length;
    });
  }

  completeUpload(sessionId: string): Promise<void> {
    return this.call('completeUpload', [sessionId], () => {
      const session = this.session(sessionId);
      if (session.received !== session.size) throw new ApiError(400, 'Upload is incomplete');
      session.complete = true;
    });
  }

  private session(sessionId: string) {
    const session = this.uploads.find((u) => u.sessionId === sessionId);
    if (!session) throw new ApiError(404, `Upload ${sessionId} not found`);
    return session;
  }

  private async call<T>(op: string, args: unknown[], fn: () => T): Promise<T> {
    await this.before?.(op, args);
    const failure = this.failures.get(op)?.shift();
    if (failure) throw failure;
    return structuredClone(fn());
  }
}
