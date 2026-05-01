"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listDocuments, type DocumentSummary } from "@/lib/api";

const TYPE_COLORS: Record<string, string> = {
  source_code: "bg-green-100 text-green-800",
  document: "bg-blue-100 text-blue-800",
  schematic: "bg-amber-100 text-amber-800",
  note: "bg-purple-100 text-purple-800",
};

const TYPE_LABELS: Record<string, string> = {
  source_code: "Source Code",
  document: "Document",
  schematic: "Schematic",
  note: "Note",
};

export default function HomePage() {
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [filter, setFilter] = useState<string>("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    listDocuments({ doc_type: filter || undefined, limit: 50 })
      .then(setDocs)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [filter]);

  return (
    <div>
      {/* Hero / Search bar */}
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-bold text-slate-900 mb-2">LLM Wiki Knowledge Base</h1>
        <p className="text-slate-500 mb-4">
          Source code, documents, and schematics — all connected.
        </p>
        <Link
          href="/search"
          className="inline-block bg-blue-500 hover:bg-blue-600 text-white px-6 py-2 rounded-lg transition-colors"
        >
          Search Knowledge Base
        </Link>
      </div>

      {/* Type filter tabs */}
      <div className="flex space-x-2 mb-6">
        {["", "source_code", "document", "schematic"].map((type) => (
          <button
            key={type}
            onClick={() => setFilter(type)}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
              filter === type
                ? "bg-slate-900 text-white"
                : "bg-slate-200 text-slate-600 hover:bg-slate-300"
            }`}
          >
            {type ? TYPE_LABELS[type] : "All"}
          </button>
        ))}
      </div>

      {/* Document list */}
      {loading ? (
        <div className="text-center py-12 text-slate-400">Loading...</div>
      ) : docs.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-slate-400 mb-4">No documents yet.</p>
          <Link
            href="/upload"
            className="text-blue-500 hover:text-blue-600 underline"
          >
            Upload your first document
          </Link>
        </div>
      ) : (
        <div className="grid gap-3">
          {docs.map((doc) => (
            <Link
              key={doc.id}
              href={`/docs/${doc.id}`}
              className="block bg-white rounded-lg border border-slate-200 p-4 hover:shadow-md hover:border-blue-300 transition-all"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-slate-900 truncate">{doc.title}</h3>
                  <div className="flex items-center space-x-2 mt-1">
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full ${
                        TYPE_COLORS[doc.doc_type] || "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {TYPE_LABELS[doc.doc_type] || doc.doc_type}
                    </span>
                    {doc.tags.map((tag) => (
                      <span
                        key={tag}
                        className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-500"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
                <time className="text-xs text-slate-400 whitespace-nowrap ml-4">
                  {new Date(doc.updated_at).toLocaleDateString("zh-CN")}
                </time>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
