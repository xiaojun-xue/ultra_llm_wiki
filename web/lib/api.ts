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
  task_id: string;
  message: string;
}

export interface ChunkSummary {
  index: number;
  preview: string;
  tokens: number;
  type: string;
}

export interface RelationInfo {
  target_id: string;
  target_title: string;
  target_type: string;
  relation_type: string;
  confidence: number;
  match_reason: string;
}

export interface TaskStep {
  name: string;
  status: "pending" | "done" | "in_progress";
  progress: number;
}

export interface TaskStatus {
  task_id: string;
  status: "pending" | "parsing" | "embedding" | "discovering" | "done" | "failed";
  progress: number;
  steps: TaskStep[];
  created_at: string;
  updated_at: string;
  error: string | null;
  result: {
    document_id: string;
    title: string;
    doc_type: string;
    file_size_bytes: number;
    chunks_count: number;
    chunk_summary: ChunkSummary[];
    relations_count: number;
    relations: RelationInfo[];
  } | null;
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

export async function getTask(taskId: string): Promise<TaskStatus> {
  const res = await fetch(`${API_BASE}/tasks/${taskId}`);
  if (!res.ok) throw new Error(`Task fetch failed: ${res.status}`);
  return res.json();
}

export async function pollTask(
  taskId: string,
  onProgress?: (task: TaskStatus) => void
): Promise<TaskStatus> {
  return new Promise((resolve, reject) => {
    const interval = setInterval(async () => {
      try {
        const task = await getTask(taskId);
        onProgress?.(task);

        if (task.status === "done") {
          clearInterval(interval);
          resolve(task);
        } else if (task.status === "failed") {
          clearInterval(interval);
          reject(new Error(task.error || "Processing failed"));
        }
      } catch (err) {
        clearInterval(interval);
        reject(err);
      }
    }, 1000);
  });
}
