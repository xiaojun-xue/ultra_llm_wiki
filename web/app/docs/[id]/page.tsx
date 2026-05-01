"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import DOMPurify from "isomorphic-dompurify";
import { getDocument, type DocumentDetail, type Relation } from "@/lib/api";

const RELATION_COLORS: Record<string, string> = {
  references: "border-blue-300 bg-blue-50",
  implements: "border-green-300 bg-green-50",
  depends_on: "border-red-300 bg-red-50",
  related_to: "border-purple-300 bg-purple-50",
  derived_from: "border-amber-300 bg-amber-50",
};

const RELATION_LABELS: Record<string, string> = {
  references: "References",
  implements: "Implements",
  depends_on: "Depends On",
  related_to: "Related To",
  derived_from: "Derived From",
};

function RelationCard({ relation, currentDocId }: { relation: Relation; currentDocId: string }) {
  const isOutgoing = relation.source_id === currentDocId;
  const otherId = isOutgoing ? relation.target_id : relation.source_id;
  const otherTitle = isOutgoing ? relation.target_title : relation.source_title;
  const arrow = isOutgoing ? "\u2192" : "\u2190";

  return (
    <Link
      href={`/docs/${otherId}`}
      className={`block p-3 rounded-lg border ${
        RELATION_COLORS[relation.relation_type] || "border-slate-200 bg-slate-50"
      } hover:shadow-sm transition-shadow`}
    >
      <div className="flex items-center space-x-2">
        <span className="text-lg">{arrow}</span>
        <span className="font-medium text-sm text-slate-800 truncate">
          {otherTitle || otherId}
        </span>
      </div>
      <div className="flex items-center space-x-2 mt-1">
        <span className="text-xs text-slate-500">
          {RELATION_LABELS[relation.relation_type] || relation.relation_type}
        </span>
        <span className="text-xs text-slate-400">
          confidence: {(relation.confidence * 100).toFixed(0)}%
        </span>
      </div>
      {relation.description && (
        <p className="text-xs text-slate-400 mt-1 truncate">{relation.description}</p>
      )}
    </Link>
  );
}

function SafeHtml({ html }: { html: string }) {
  const sanitized = DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      "h1", "h2", "h3", "h4", "h5", "h6", "p", "br", "hr",
      "ul", "ol", "li", "a", "strong", "em", "code", "pre",
      "blockquote", "table", "thead", "tbody", "tr", "th", "td",
      "img", "span", "div",
    ],
    ALLOWED_ATTR: ["href", "src", "alt", "class", "title"],
  });
  return <div className="prose max-w-none" dangerouslySetInnerHTML={{ __html: sanitized }} />;
}

function CodeBlock({ content }: { content: string }) {
  return (
    <pre className="bg-slate-900 text-slate-100 rounded-lg p-4 overflow-x-auto text-sm leading-relaxed">
      <code>{content}</code>
    </pre>
  );
}

export default function DocumentPage() {
  const params = useParams();
  const docId = params.id as string;
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    getDocument(docId)
      .then(setDoc)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [docId]);

  if (loading) return <div className="text-center py-12 text-slate-400">Loading...</div>;
  if (error) return <div className="text-center py-12 text-red-500">{error}</div>;
  if (!doc) return <div className="text-center py-12 text-slate-400">Document not found</div>;

  const isCode = doc.doc_type === "source_code";

  return (
    <div className="flex gap-6">
      {/* Main content */}
      <div className="flex-1 min-w-0">
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center space-x-2 mb-2">
            <Link href="/" className="text-blue-500 hover:text-blue-600 text-sm">
              Home
            </Link>
            <span className="text-slate-300">/</span>
            <span className="text-sm text-slate-500">{doc.doc_type}</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900">{doc.title}</h1>
          <div className="flex items-center space-x-3 mt-2 text-sm text-slate-500">
            <span>Type: {doc.doc_type}</span>
            {doc.mime_type && <span>MIME: {doc.mime_type}</span>}
            <span>Updated: {new Date(doc.updated_at).toLocaleString("zh-CN")}</span>
          </div>
          {doc.tags.length > 0 && (
            <div className="flex space-x-2 mt-2">
              {doc.tags.map((tag) => (
                <span
                  key={tag}
                  className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-700"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Content */}
        <div className="bg-white rounded-lg border border-slate-200 p-6">
          {doc.content_html && !isCode ? (
            <SafeHtml html={doc.content_html} />
          ) : isCode && doc.content ? (
            <CodeBlock content={doc.content} />
          ) : doc.content ? (
            <pre className="whitespace-pre-wrap text-sm text-slate-700">{doc.content}</pre>
          ) : (
            <p className="text-slate-400 italic">
              No text content available. This is a file-based document.
            </p>
          )}
        </div>

        {/* Metadata */}
        {doc.metadata && Object.keys(doc.metadata).length > 0 && (
          <details className="mt-4">
            <summary className="text-sm text-slate-500 cursor-pointer hover:text-slate-700">
              Metadata
            </summary>
            <pre className="mt-2 bg-slate-100 rounded-lg p-3 text-xs overflow-x-auto">
              {JSON.stringify(doc.metadata, null, 2)}
            </pre>
          </details>
        )}
      </div>

      {/* Sidebar: Relations */}
      <div className="w-80 flex-shrink-0">
        <h2 className="font-semibold text-slate-900 mb-3">Relations</h2>
        {doc.relations.length === 0 ? (
          <p className="text-sm text-slate-400">No relations found.</p>
        ) : (
          <div className="space-y-2">
            {doc.relations.map((r) => (
              <RelationCard key={r.id} relation={r} currentDocId={docId} />
            ))}
          </div>
        )}

        {/* Quick link to graph view */}
        <Link
          href={`/graph?focus=${docId}`}
          className="block mt-4 text-center text-sm text-blue-500 hover:text-blue-600 underline"
        >
          View in Knowledge Graph
        </Link>
      </div>
    </div>
  );
}
