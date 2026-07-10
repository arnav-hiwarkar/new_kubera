export type DocumentStatus = 
  | 'uploaded'
  | 'pending_approval'
  | 'action_required'
  | 'verified'
  | 'submitted';

export interface BucketResponse {
  id: string;
  name: string;
  company_id: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface BucketCreate {
  name: string;
}

export interface DocumentVersionResponse {
  id: string;
  document_id: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  checksum: string;
  uploaded_by: string;
  uploaded_at: string;
  version_number: number;
}

export interface DocumentResponse {
  id: string;
  company_id: string;
  current_version_id: string | null;
  bucket_id: string | null;
  status: DocumentStatus;
  title: string;
  doc_type_id: string | null;
  tags: string[];
  is_editable: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
  versions: DocumentVersionResponse[];
}

export interface DocumentUpdate {
  status?: DocumentStatus | null;
  bucket_id?: string | null;
  tags?: string[] | null;
  is_editable?: boolean | null;
}
