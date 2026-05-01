/**
 * API client for the LLM Wiki backend.
 */

const API_BASE = "/api";

export interface DocumentSummary {
  id: string;
  title: string;
  doc_type: string;
  mime_type: string | null;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface DocumentDetail extends DocumentSummary {
  content: string | null;
  content_html: string | null;
  metadata: Record<string, any>;
  file_path: string | null;
  created_by: string | null;
  relations: Relation[];
}

export interface Relation {
  id: string;
  source_id: string;
  target_id: string;
  source_title: string | null;
  target_title: string | null;
  relation_type: string;
  description: string | null;
  confidence: number;
  created_at: string;
}

export interface SearchResult {
  document_id: string;
  title: string;
  doc_type: string;
  chunk_content: string;
  score: number;
  metadata: Record<string, any>;
}

export interface SearchResponse {
  results: SearchResult[];
  total: number;
  query: string;
}

export interface UploadResponse {
  document_id: string;
  title: string;
  doc_type: string;
  chunks_count: number;
  relations_found: number;
}

// ── Fetchers ──────────────────────────────────

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export async function listDocuments(params?: {
  doc_type?: string;
  tag?: string;
  skip?: number;
  limit?: number;
}): Promise<DocumentSummary[]> {
  const query = new URLSearchParams();
  if (params?.doc_type) query.set("doc_type", params.doc_type);
  if (params?.tag) query.set("tag", params.tag);
  if (params?.skip) query.set("skip", String(params.skip));
  if (params?.limit) query.set("limit", String(params.limit));
  const qs = query.toString();
  return apiFetch(`/documents/${qs ? `?${qs}` : ""}`);
}

export async function getDocument(id: string): Promise<DocumentDetail> {
  return apiFetch(`/documents/${id}`);
}

export async function searchDocuments(
  query: string,
  doc_type?: string,
  limit?: number
): Promise<SearchResponse> {
  return apiFetch("/search/", {
    method: "POST",
    body: JSON.stringify({ query, doc_type, limit: limit || 10 }),
  });
}

export async function getRelations(docId: string): Promise<Relation[]> {
  return apiFetch(`/relations/${docId}`);
}

export async function uploadFile(
  file: File,
  title?: string,
  tags?: string
): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  if (title) formData.append("title", title);
  if (tags) formData.append("tags", tags);

  const res = await fetch(`${API_BASE}/upload/`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return res.json();
}
