"use client";

import { useState, useRef } from "react";
import { uploadFile, type UploadResponse } from "@/lib/api";

export default function UploadPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [title, setTitle] = useState("");
  const [tags, setTags] = useState("");
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState<(UploadResponse & { error?: string })[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (files.length === 0) return;

    setUploading(true);
    const newResults: (UploadResponse & { error?: string })[] = [];

    for (const file of files) {
      try {
        const result = await uploadFile(file, title || undefined, tags || undefined);
        newResults.push(result);
      } catch (err: any) {
        newResults.push({
          document_id: "",
          title: file.name,
          doc_type: "unknown",
          chunks_count: 0,
          relations_found: 0,
          error: err.message,
        });
      }
    }

    setResults(newResults);
    setUploading(false);
    setFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Upload Documents</h1>

      <form onSubmit={handleUpload} className="space-y-4">
        {/* File input with drag & drop area */}
        <div
          className="border-2 border-dashed border-slate-300 rounded-lg p-8 text-center hover:border-blue-400 transition-colors cursor-pointer"
          onClick={() => fileInputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); e.currentTarget.classList.add("border-blue-400"); }}
          onDragLeave={(e) => e.currentTarget.classList.remove("border-blue-400")}
          onDrop={(e) => {
            e.preventDefault();
            e.currentTarget.classList.remove("border-blue-400");
            const droppedFiles = Array.from(e.dataTransfer.files);
            setFiles(droppedFiles);
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => setFiles(Array.from(e.target.files || []))}
          />
          {files.length > 0 ? (
            <div>
              <p className="font-medium text-slate-700">{files.length} file(s) selected:</p>
              <ul className="mt-2 text-sm text-slate-500">
                {files.map((f, i) => (
                  <li key={i}>{f.name} ({(f.size / 1024).toFixed(1)} KB)</li>
                ))}
              </ul>
            </div>
          ) : (
            <div>
              <p className="text-slate-500 mb-1">Drop files here or click to browse</p>
              <p className="text-xs text-slate-400">
                Supports: .c .h .cpp .java .py .md .pdf .docx .ini .sch .kicad_sch and more
              </p>
            </div>
          )}
        </div>

        {/* Optional metadata */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Title (optional)
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Custom title..."
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Tags (comma-separated)
            </label>
            <input
              type="text"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="spi, driver, stm32"
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={uploading || files.length === 0}
          className="w-full py-2.5 bg-blue-500 hover:bg-blue-600 text-white rounded-lg font-medium disabled:opacity-50 transition-colors"
        >
          {uploading ? "Uploading & Processing..." : "Upload"}
        </button>
      </form>

      {/* Results */}
      {results.length > 0 && (
        <div className="mt-8">
          <h2 className="font-semibold text-slate-900 mb-3">Upload Results</h2>
          <div className="space-y-2">
            {results.map((r, i) => (
              <div
                key={i}
                className={`p-3 rounded-lg border text-sm ${
                  r.error
                    ? "border-red-200 bg-red-50 text-red-700"
                    : "border-green-200 bg-green-50 text-green-700"
                }`}
              >
                {r.error ? (
                  <span>Failed: {r.title} - {r.error}</span>
                ) : (
                  <span>
                    {r.title} ({r.doc_type}) - {r.chunks_count} chunks, {r.relations_found} relations found
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
