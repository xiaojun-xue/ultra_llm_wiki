"use client";

import { useEffect, useState, useCallback, useRef, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import dynamic from "next/dynamic";
import { listDocuments, getRelations, type DocumentSummary, type Relation } from "@/lib/api";

interface GraphNode {
  id: string;
  label: string;
  type: string;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
}

interface GraphLink {
  source: string;
  target: string;
  type: string;
  label: string;
}

const NODE_COLORS: Record<string, string> = {
  source_code: "#22c55e",
  document: "#3b82f6",
  schematic: "#f59e0b",
  note: "#a855f7",
};

const LINK_COLORS: Record<string, string> = {
  references: "#93c5fd",
  implements: "#86efac",
  depends_on: "#fca5a5",
  related_to: "#c4b5fd",
  derived_from: "#fcd34d",
};

/**
 * Simple canvas-based force-directed graph renderer.
 * No heavy dependencies — pure canvas drawing with basic force simulation.
 */
function ForceGraph({
  nodes,
  links,
  focusId,
  onNodeClick,
}: {
  nodes: GraphNode[];
  links: GraphLink[];
  focusId?: string;
  onNodeClick: (id: string) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const nodesRef = useRef<GraphNode[]>([]);
  const animRef = useRef<number>(0);

  useEffect(() => {
    // Initialize node positions
    nodesRef.current = nodes.map((n, i) => ({
      ...n,
      x: 400 + Math.cos((2 * Math.PI * i) / nodes.length) * 200,
      y: 300 + Math.sin((2 * Math.PI * i) / nodes.length) * 200,
      vx: 0,
      vy: 0,
    }));

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const nodeMap = new Map(nodesRef.current.map((n) => [n.id, n]));

    function simulate() {
      const ns = nodesRef.current;
      // Repulsion between all nodes
      for (let i = 0; i < ns.length; i++) {
        for (let j = i + 1; j < ns.length; j++) {
          const dx = ns[j].x! - ns[i].x!;
          const dy = ns[j].y! - ns[i].y!;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = 5000 / (dist * dist);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          ns[i].vx! -= fx;
          ns[i].vy! -= fy;
          ns[j].vx! += fx;
          ns[j].vy! += fy;
        }
      }

      // Attraction along links
      for (const link of links) {
        const src = nodeMap.get(link.source);
        const tgt = nodeMap.get(link.target);
        if (!src || !tgt) continue;
        const dx = tgt.x! - src.x!;
        const dy = tgt.y! - src.y!;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = (dist - 150) * 0.01;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        src.vx! += fx;
        src.vy! += fy;
        tgt.vx! -= fx;
        tgt.vy! -= fy;
      }

      // Center gravity + damping
      for (const n of ns) {
        n.vx! += (400 - n.x!) * 0.001;
        n.vy! += (300 - n.y!) * 0.001;
        n.vx! *= 0.9;
        n.vy! *= 0.9;
        n.x! += n.vx!;
        n.y! += n.vy!;
      }
    }

    function draw() {
      if (!ctx || !canvas) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Draw links
      for (const link of links) {
        const src = nodeMap.get(link.source);
        const tgt = nodeMap.get(link.target);
        if (!src || !tgt) continue;
        ctx.beginPath();
        ctx.moveTo(src.x!, src.y!);
        ctx.lineTo(tgt.x!, tgt.y!);
        ctx.strokeStyle = LINK_COLORS[link.type] || "#cbd5e1";
        ctx.lineWidth = 1.5;
        ctx.stroke();
        // Link label at midpoint
        const mx = (src.x! + tgt.x!) / 2;
        const my = (src.y! + tgt.y!) / 2;
        ctx.fillStyle = "#94a3b8";
        ctx.font = "10px sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(link.type, mx, my - 4);
      }

      // Draw nodes
      for (const n of nodesRef.current) {
        const isFocused = n.id === focusId;
        const radius = isFocused ? 10 : 7;

        ctx.beginPath();
        ctx.arc(n.x!, n.y!, radius, 0, 2 * Math.PI);
        ctx.fillStyle = NODE_COLORS[n.type] || "#94a3b8";
        ctx.fill();
        if (isFocused) {
          ctx.strokeStyle = "#1e40af";
          ctx.lineWidth = 3;
          ctx.stroke();
        }

        // Label
        ctx.fillStyle = "#1e293b";
        ctx.font = isFocused ? "bold 12px sans-serif" : "11px sans-serif";
        ctx.textAlign = "center";
        const label = n.label.length > 25 ? n.label.slice(0, 22) + "..." : n.label;
        ctx.fillText(label, n.x!, n.y! + radius + 14);
      }

      simulate();
      animRef.current = requestAnimationFrame(draw);
    }

    animRef.current = requestAnimationFrame(draw);

    // Click handler
    function handleClick(e: MouseEvent) {
      const rect = canvas!.getBoundingClientRect();
      const cx = e.clientX - rect.left;
      const cy = e.clientY - rect.top;
      for (const n of nodesRef.current) {
        const dx = n.x! - cx;
        const dy = n.y! - cy;
        if (dx * dx + dy * dy < 15 * 15) {
          onNodeClick(n.id);
          return;
        }
      }
    }
    canvas.addEventListener("click", handleClick);

    return () => {
      cancelAnimationFrame(animRef.current);
      canvas.removeEventListener("click", handleClick);
    };
  }, [nodes, links, focusId, onNodeClick]);

  return (
    <canvas
      ref={canvasRef}
      width={800}
      height={600}
      className="w-full border border-slate-200 rounded-lg bg-white"
    />
  );
}

function GraphPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const focusId = searchParams.get("focus") || undefined;

  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [links, setLinks] = useState<GraphLink[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadGraph() {
      try {
        const docs = await listDocuments({ limit: 100 });
        const graphNodes: GraphNode[] = docs.map((d) => ({
          id: d.id,
          label: d.title,
          type: d.doc_type,
        }));

        const graphLinks: GraphLink[] = [];
        const seen = new Set<string>();

        // Fetch relations for all documents
        for (const doc of docs) {
          try {
            const rels = await getRelations(doc.id);
            for (const r of rels) {
              const key = [r.source_id, r.target_id, r.relation_type].sort().join("-");
              if (!seen.has(key)) {
                seen.add(key);
                graphLinks.push({
                  source: r.source_id,
                  target: r.target_id,
                  type: r.relation_type,
                  label: r.relation_type,
                });
              }
            }
          } catch {
            // Some docs may have no relations
          }
        }

        setNodes(graphNodes);
        setLinks(graphLinks);
      } catch (err) {
        console.error("Failed to load graph data:", err);
      } finally {
        setLoading(false);
      }
    }

    loadGraph();
  }, []);

  const handleNodeClick = useCallback(
    (id: string) => router.push(`/docs/${id}`),
    [router]
  );

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 mb-4">Knowledge Graph</h1>

      {/* Legend */}
      <div className="flex space-x-4 mb-4 text-sm">
        {Object.entries(NODE_COLORS).map(([type, color]) => (
          <div key={type} className="flex items-center space-x-1">
            <span
              className="inline-block w-3 h-3 rounded-full"
              style={{ backgroundColor: color }}
            />
            <span className="text-slate-600">{type}</span>
          </div>
        ))}
      </div>

      {loading ? (
        <div className="text-center py-12 text-slate-400">Loading graph data...</div>
      ) : nodes.length === 0 ? (
        <div className="text-center py-12 text-slate-400">
          No documents to display. Upload some documents first.
        </div>
      ) : (
        <ForceGraph
          nodes={nodes}
          links={links}
          focusId={focusId}
          onNodeClick={handleNodeClick}
        />
      )}

      <p className="text-xs text-slate-400 mt-2">
        Click on a node to view the document. Showing {nodes.length} documents, {links.length} relations.
      </p>
    </div>
  );
}

export default function GraphPage() {
  return (
    <Suspense fallback={<div className="text-center py-12 text-slate-400">Loading...</div>}>
      <GraphPageInner />
    </Suspense>
  );
}
