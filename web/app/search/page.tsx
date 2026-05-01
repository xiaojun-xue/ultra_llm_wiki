"use client";

import { useState } from "react";
import Link from "next/link";
import { searchDocuments, type SearchResult } from "@/lib/api";

const TYPE_COLORS: Record<string, string> = {
  source_code: "bg-green-100 text-green-800",
  document: "bg-blue-100 text-blue-800",
  schematic: "bg-amber-100 text-amber-800",
};

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [docType, setDocType] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;

    setSearching(true);
    try {
      const response = await searchDocuments(query, docType || undefined);
      setResults(response.results);
    } catch (err) {
      console.error(err);
    } finally {
      setSearching(false);
      setSearched(true);
    }
  }

  return (
    <div className="max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Search Knowledge Base</h1>

      {/* Search form */}
      <form onSubmit={handleSearch} className="mb-8">
        <div className="flex gap-3">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by keyword or natural language question..."
            className="flex-1 px-4 py-2.5 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          <select
            value={docType}
            onChange={(e) => setDocType(e.target.value)}
            className="px-3 py-2.5 border border-slate-300 rounded-lg bg-white text-sm"
          >
            <option value="">All Types</option>
            <option value="source_code">Source Code</option>
            <option value="document">Documents</option>
            <option value="schematic">Schematics</option>
          </select>
          <button
            type="submit"
            disabled={searching}
            className="px-6 py-2.5 bg-blue-500 hover:bg-blue-600 text-white rounded-lg font-medium disabled:opacity-50 transition-colors"
          >
            {searching ? "Searching..." : "Search"}
          </button>
        </div>
      </form>

      {/* Results */}
      {searching && (
        <div className="text-center py-8 text-slate-400">Searching...</div>
      )}

      {!searching && searched && results.length === 0 && (
        <div className="text-center py-8 text-slate-400">
          No results found for "{query}".
        </div>
      )}

      {results.length > 0 && (
        <div className="space-y-4">
          <p className="text-sm text-slate-500">{results.length} results found</p>
          {results.map((r, i) => (
            <Link
              key={`${r.document_id}-${i}`}
              href={`/docs/${r.document_id}`}
              className="block bg-white rounded-lg border border-slate-200 p-4 hover:shadow-md hover:border-blue-300 transition-all"
            >
              <div className="flex items-center space-x-2 mb-2">
                <h3 className="font-semibold text-slate-900">{r.title}</h3>
                <span
                  className={`text-xs px-2 py-0.5 rounded-full ${
                    TYPE_COLORS[r.doc_type] || "bg-slate-100"
                  }`}
                >
                  {r.doc_type}
                </span>
                <span className="text-xs text-slate-400">
                  score: {r.score.toFixed(4)}
                </span>
              </div>
              <p className="text-sm text-slate-600 line-clamp-3">{r.chunk_content}</p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
