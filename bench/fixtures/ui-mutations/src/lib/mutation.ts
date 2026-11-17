export type MutationStatus = 'idle' | 'pending' | 'success' | 'error';

export interface MutationState<TData, TVars> {
  status: MutationStatus;
  data: TData | undefined;
  error: Error | null;
  variables: TVars | undefined;
}

export interface MutationOptions<TVars, TData, TContext = unknown> {
  mutationFn: (variables: TVars) => Promise<TData>;
  onMutate?: (variables: TVars) => TContext | Promise<TContext>;
  onSuccess?: (data: TData, variables: TVars, context: TContext | undefined) => unknown;
  onError?: (error: Error, variables: TVars, context: TContext | undefined) => unknown;
  onSettled?: (
    data: TData | undefined,
    error: Error | null,
    variables: TVars,
    context: TContext | undefined,
  ) => unknown;
}

export interface MutateCallbacks<TVars, TData> {
  onSuccess?: (data: TData, variables: TVars) => void;
  onError?: (error: Error, variables: TVars) => void;
  onSettled?: (data: TData | undefined, error: Error | null, variables: TVars) => void;
}

function idle<TData, TVars>(): MutationState<TData, TVars> {
  return { status: 'idle', data: undefined, error: null, variables: undefined };
}

function toError(raw: unknown): Error {
  return raw instanceof Error ? raw : new Error(String(raw));
}

export class Mutation<TVars, TData, TContext = unknown> {
  state: MutationState<TData, TVars> = idle();
  private readonly options: MutationOptions<TVars, TData, TContext>;
  private readonly listeners = new Set<() => void>();
  private latestCall = 0;

  constructor(options: MutationOptions<TVars, TData, TContext>) {
    this.options = options;
  }

  get isPending(): boolean {
    return this.state.status === 'pending';
  }

  get isError(): boolean {
    return this.state.status === 'error';
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  mutate(variables: TVars, callbacks?: MutateCallbacks<TVars, TData>): void {
    this.mutateAsync(variables, callbacks).catch(() => {});
  }

  async mutateAsync(variables: TVars, callbacks?: MutateCallbacks<TVars, TData>): Promise<TData> {
    const call = ++this.latestCall;
    const isLatest = () => call === this.latestCall;
    this.setState({ status: 'pending', data: undefined, error: null, variables });

    let context: TContext | undefined;
    try {
      context = await this.options.onMutate?.(variables);
      const data = await this.options.mutationFn(variables);
      await this.options.onSuccess?.(data, variables, context);
      await this.options.onSettled?.(data, null, variables, context);
      if (isLatest()) {
        this.setState({ status: 'success', data, error: null, variables });
        callbacks?.onSuccess?.(data, variables);
        callbacks?.onSettled?.(data, null, variables);
      }
      return data;
    } catch (raw) {
      const error = toError(raw);
      await this.options.onError?.(error, variables, context);
      await this.options.onSettled?.(undefined, error, variables, context);
      if (isLatest()) {
        this.setState({ status: 'error', data: undefined, error, variables });
        callbacks?.onError?.(error, variables);
        callbacks?.onSettled?.(undefined, error, variables);
      }
      throw error;
    }
  }

  reset(): void {
    this.latestCall++;
    this.setState(idle());
  }

  private setState(next: MutationState<TData, TVars>): void {
    this.state = next;
    for (const listener of this.listeners) listener();
  }
}
