export type DocStatus = 'draft' | 'in_review' | 'approved' | 'rejected' | 'archived';
export type DocAction = 'submit' | 'approve' | 'reject' | 'archive' | 'reopen';

export interface Doc {
  id: string;
  title: string;
  folder: string;
  author: string;
  status: DocStatus;
  starred: boolean;
  updatedAt: number;
}

export interface ActivityEntry {
  docId: string;
  action: DocAction | 'create';
  actor: string;
  at: number;
}

export interface Fund {
  id: string;
  name: string;
  vintage: number;
  currency: string;
  targetSize: number;
  notes: string;
  version: number;
}

export type FundFields = Omit<Fund, 'id' | 'version'>;
export type FundPatch = Partial<FundFields>;
