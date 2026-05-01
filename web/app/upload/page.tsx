"use client";

import { useState, useRef, useCallback } from "react";
import Link from "next/link";
import { uploadFile, pollTask, type TaskStatus } from "@/lib/api";

interface TaskCardProps {
  task: TaskStatus;
  filename: string;
  onRemove: () => void;
}

function DocTypeIcon({ docType }: { docType: string }) {
  if (docType === "source_code") return <span className="text-blue-500">📄</span>;
  if (docType === "schematic") return <span className="text-orange-500">⚡</span>;
  return <span className="text-slate-500">📝</span>;
}

function StepIndicator({ task }: { task: TaskStatus }) {
  const labels: Record<string, string> = {
    parsing: "解析与分块",
    embedding: "生成向量嵌入",
    discovering: "发现关联关系",
    done: "处理完成",
  };
  return (
    <div className="mt-3 space-y-1">
      {task.steps.map((step, i) => (
        <div key={i} className="flex items-center gap-2 text-xs">
          {step.status === "done" ? (
            <span className="text-green-500">✅</span>
          ) : step.status === "in_progress" ? (
            <span className="text-blue-400 animate-spin">⏳</span>
          ) : (
            <span className="text-slate-300">⬜</span>
          )}
          <span className={step.status === "done" ? "text-green-600" : "text-slate-500"}>
            {step.name}
          </span>
          {step.status === "in_progress" && step.progress > 0 && (
            <span className="text-slate-400 ml-1">({step.progress}%)</span>
          )}
        </div>
      ))}
    </div>
  );
}

function CompletedView({ task }: { task: TaskStatus }) {
  const r = task.result!;
  const sizeMB = (r.file_size_bytes / 1024 / 1024).toFixed(2);

  return (
    <div className="mt-4 p-4 bg-green-50 border border-green-200 rounded-lg">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="font-semibold text-green-800 flex items-center gap-2">
            <span>✅</span> {r.title}
          </h3>
          <p className="text-sm text-green-600 mt-0.5">
            {sizeMB} MB · {r.chunks_count} 个文本块 · 发现 {r.relations_count} 个关联
          </p>
        </div>
        <Link
          href={`/docs/${r.document_id}`}
          className="text-xs px-3 py-1 bg-green-600 text-white rounded-full hover:bg-green-700 transition-colors"
        >
          查看文档
        </Link>
      </div>

      {/* Chunk summary */}
      {r.chunk_summary.length > 0 && (
        <div className="mt-4">
          <h4 className="text-xs font-semibold text-slate-500 uppercase mb-2">切片详情</h4>
          <div className="space-y-1 max-h-40 overflow-y-auto">
            {r.chunk_summary.map((c) => (
              <div key={c.index} className="flex items-start gap-2 text-xs">
                <span className="text-slate-400 w-6">#{c.index + 1}</span>
                <span className={`px-1.5 py-0.5 rounded text-xs ${
                  c.type === "function" ? "bg-blue-100 text-blue-700" :
                  c.type === "struct" ? "bg-purple-100 text-purple-700" :
                  "bg-slate-100 text-slate-600"
                }`}>
                  {c.type}
                </span>
                <span className="text-slate-600 flex-1 truncate">{c.preview}</span>
                <span className="text-slate-400">{c.tokens} tokens</span>
              </div>
            ))}
            {r.chunks_count > 10 && (
              <p className="text-xs text-slate-400 text-center">
                ... 还有 {r.chunks_count - 10} 个块
              </p>
            )}
          </div>
        </div>
      )}

      {/* Relations */}
      {r.relations.length > 0 && (
        <div className="mt-4">
          <h4 className="text-xs font-semibold text-slate-500 uppercase mb-2">
            知识关联 ({r.relations_count} 个)
          </h4>
          <div className="space-y-2">
            {r.relations.slice(0, 5).map((rel) => (
              <div key={rel.target_id} className="flex items-start gap-2 text-sm border-l-2 border-slate-200 pl-3">
                <span className="mt-0.5"><DocTypeIcon docType={rel.target_type} /></span>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-slate-700 truncate">{rel.target_title}</p>
                  <p className="text-xs text-slate-500">
                    {rel.relation_type === "references" && "📎 文件引用"}
                    {rel.relation_type === "semantic" && "🔗 语义相似"}
                    {rel.relation_type === "calls" && "📞 函数调用"}
                    {rel.relation_type === "related_to" && "🔄 关联关系"}
                    {rel.relation_type !== "references" && rel.relation_type !== "semantic" && rel.relation_type !== "calls" && rel.relation_type !== "related_to" && rel.relation_type}
                    {" · "}
                    置信度 {(rel.confidence * 100).toFixed(0)}%
                    {rel.match_reason && ` · ${rel.match_reason}`}
                  </p>
                </div>
                <Link
                  href={`/docs/${rel.target_id}`}
                  className="text-xs text-blue-500 hover:text-blue-600 whitespace-nowrap"
                >
                  查看 →
                </Link>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function TaskCard({ task, filename, onRemove }: TaskCardProps) {
  const isProcessing = !["done", "failed"].includes(task.status);
  const isFailed = task.status === "failed";

  return (
    <div className={`p-4 rounded-lg border text-sm ${
      isFailed ? "border-red-200 bg-red-50" :
      task.status === "done" ? "border-green-200 bg-white" :
      "border-blue-200 bg-white"
    }`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-lg">
            {isFailed ? "❌" : task.status === "done" ? "✅" : "🔄"}
          </span>
          <span className="font-medium text-slate-700 truncate">{filename}</span>
        </div>
        <div className="flex items-center gap-3">
          {!isFailed && (
            <span className="text-xs font-medium text-blue-500">{task.progress}%</span>
          )}
          {isFailed && (
            <span className="text-xs text-red-500">{task.error}</span>
          )}
          <button
            onClick={onRemove}
            className="text-slate-400 hover:text-slate-600 text-xs"
          >
            ✕
          </button>
        </div>
      </div>

      {!isFailed && (
        <div className="mt-1">
          <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                task.status === "done" ? "bg-green-400" : "bg-blue-400"
              }`}
              style={{ width: `${task.progress}%` }}
            />
          </div>
        </div>
      )}

      {isProcessing && <StepIndicator task={task} />}
      {task.status === "done" && task.result && <CompletedView task={task} />}
    </div>
  );
}

export default function UploadPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [title, setTitle] = useState("");
  const [tags, setTags] = useState("");
  const [tasks, setTasks] = useState<Map<string, { filename: string; status: TaskStatus | null }>>(new Map());
  const fileInputRef = useRef<HTMLInputElement>(null);

  const startUpload = useCallback(async (file: File) => {
    try {
      const { task_id } = await uploadFile(file, title || undefined, tags || undefined);
      setTasks((prev) => new Map(prev).set(task_id, { filename: file.name, status: null }));

      pollTask(task_id, (updated) => {
        setTasks((prev) => {
          const next = new Map(prev);
          next.set(task_id, { filename: file.name, status: updated });
          return next;
        });
      }).catch((err) => {
        setTasks((prev) => {
          const next = new Map(prev);
          const existing = next.get(task_id);
          if (existing) {
            next.set(task_id, {
              filename: file.name,
              status: {
                task_id,
                status: "failed",
                progress: 0,
                steps: [],
                created_at: "",
                updated_at: "",
                error: err.message,
                result: null,
              },
            });
          }
          return next;
        });
      });
    } catch (err: any) {
      console.error("Upload failed:", err);
    }
  }, [title, tags]);

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (files.length === 0) return;

    // Upload each file sequentially to avoid overwhelming the server
    for (const file of files) {
      await startUpload(file);
    }
    setFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function removeTask(taskId: string) {
    setTasks((prev) => {
      const next = new Map(prev);
      next.delete(taskId);
      return next;
    });
  }

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-slate-900 mb-6">上传文档</h1>

      <form onSubmit={handleUpload} className="space-y-4">
        {/* Drag & drop area */}
        <div
          className="border-2 border-dashed border-slate-300 rounded-lg p-8 text-center hover:border-blue-400 transition-colors cursor-pointer"
          onClick={() => fileInputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            e.currentTarget.classList.add("border-blue-400", "bg-blue-50");
          }}
          onDragLeave={(e) => {
            e.currentTarget.classList.remove("border-blue-400", "bg-blue-50");
          }}
          onDrop={(e) => {
            e.preventDefault();
            e.currentTarget.classList.remove("border-blue-400", "bg-blue-50");
            setFiles(Array.from(e.dataTransfer.files));
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
              <p className="font-medium text-slate-700">{files.length} 个文件已选择:</p>
              <ul className="mt-2 text-sm text-slate-500 space-y-1">
                {files.map((f, i) => (
                  <li key={i}>{f.name} ({(f.size / 1024).toFixed(1)} KB)</li>
                ))}
              </ul>
            </div>
          ) : (
            <div>
              <p className="text-slate-500 mb-1">拖拽文件到这里，或点击选择文件</p>
              <p className="text-xs text-slate-400">
                支持: .c .h .cpp .java .py .md .pdf .docx .ini .sch .kicad_sch 等
              </p>
            </div>
          )}
        </div>

        {/* Metadata */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              标题（可选）
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="自定义标题..."
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              标签（逗号分隔）
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
          disabled={files.length === 0}
          className="w-full py-2.5 bg-blue-500 hover:bg-blue-600 text-white rounded-lg font-medium disabled:opacity-50 transition-colors"
        >
          {files.length > 0 ? `上传 ${files.length} 个文件` : "选择文件后上传"}
        </button>
      </form>

      {/* Active tasks / results */}
      {tasks.size > 0 && (
        <div className="mt-8">
          <h2 className="font-semibold text-slate-900 mb-3">处理进度</h2>
          <div className="space-y-3">
            {Array.from(tasks.entries()).map(([taskId, { filename, status }]) => (
              <TaskCard
                key={taskId}
                task={status || {
                  task_id: taskId,
                  status: "pending",
                  progress: 0,
                  steps: [],
                  created_at: "",
                  updated_at: "",
                  error: null,
                  result: null,
                }}
                filename={filename}
                onRemove={() => removeTask(taskId)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
