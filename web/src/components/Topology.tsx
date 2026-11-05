import type { TopoLink, TopoNode } from "../lib/api";
import s from "./Topology.module.css";

// Diagram desain dari .clab.yaml + label `design.links` di problem.yaml.
// Isinya kondisi yang SEHARUSNYA (dokumentasi), bukan state runtime.
// Tata letak: lapisan BFS dari host pertama, jadi topologi rantai jadi satu garis
// lurus dan topologi bercabang tetap terbaca tanpa layout engine.

const NODE = 64;

export function layers(nodes: TopoNode[], links: TopoLink[]) {
  const adj = new Map<string, string[]>(nodes.map((n) => [n.id, []]));
  for (const l of links) {
    adj.get(l.a)?.push(l.b);
    adj.get(l.b)?.push(l.a);
  }
  const start = nodes.find((n) => n.role === "host") ?? nodes[0];
  const depth = new Map<string, number>();
  const out: string[][] = [];
  const visit = (root: string, base: number) => {
    const queue = [root];
    depth.set(root, base);
    while (queue.length) {
      const id = queue.shift()!;
      const d = depth.get(id)!;
      (out[d] ??= []).push(id);
      for (const next of adj.get(id) ?? []) {
        if (!depth.has(next)) {
          depth.set(next, d + 1);
          queue.push(next);
        }
      }
    }
  };
  if (start) visit(start.id, 0);
  for (const n of nodes) if (!depth.has(n.id)) visit(n.id, out.length); // komponen terpisah
  return out;
}

export function Topology({
  nodes,
  links,
  orientation = "vertical",
  pitch = orientation === "vertical" ? 104 : 108,
  spread = 96,
  selected,
  running,
  onSelect,
  showLabels = true,
}: {
  nodes: TopoNode[];
  links: TopoLink[];
  orientation?: "vertical" | "horizontal";
  pitch?: number;
  spread?: number;
  selected?: string | null;
  running?: string[] | null;
  onSelect?: (id: string) => void;
  showLabels?: boolean;
}) {
  const rows = layers(nodes, links);
  const widest = Math.max(1, ...rows.map((r) => r.length));
  const cross = (widest - 1) * spread + NODE;
  const main = (rows.length - 1) * pitch + NODE;
  const pos = new Map<string, { x: number; y: number }>();
  rows.forEach((row, i) =>
    row.forEach((id, j) => {
      const along = i * pitch + NODE / 2;
      const across = cross / 2 + (j - (row.length - 1) / 2) * spread;
      pos.set(id, orientation === "vertical" ? { x: across, y: along } : { x: along, y: across });
    }),
  );
  const width = orientation === "vertical" ? cross : main;
  const height = orientation === "vertical" ? main : cross;
  const role = new Map(nodes.map((n) => [n.id, n.role]));

  return (
    <div className={`${s.wrap} ${s[orientation]}`} style={{ width, height }}>
      <svg className={s.lines} width={width} height={height} aria-hidden="true">
        {links.map((l) => {
          const a = pos.get(l.a)!;
          const b = pos.get(l.b)!;
          return <line key={`${l.a}-${l.b}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} />;
        })}
      </svg>
      {showLabels &&
        links.map((l) => {
          if (!l.label) return null;
          const a = pos.get(l.a)!;
          const b = pos.get(l.b)!;
          return (
            <span
              key={`label-${l.a}-${l.b}`}
              className={s.linkLabel}
              style={
                orientation === "vertical"
                  ? { left: (a.x + b.x) / 2 + NODE / 2 + 14, top: (a.y + b.y) / 2 }
                  : { left: (a.x + b.x) / 2, top: (a.y + b.y) / 2 + NODE / 2 + 6 }
              }
              title={`${l.a}:${l.a_if} ↔ ${l.b}:${l.b_if}`}
            >
              {l.label}
            </span>
          );
        })}
      {nodes.map((n) => {
        const p = pos.get(n.id)!;
        const down = running ? !running.includes(n.id) : false;
        const cls = `${s.node} ${s[role.get(n.id) ?? "host"] ?? ""} ${selected === n.id ? s.selected : ""} ${down ? s.down : ""}`;
        const style = { left: p.x - NODE / 2, top: p.y - NODE / 2 };
        return onSelect ? (
          <button
            key={n.id}
            type="button"
            className={cls}
            style={style}
            onClick={() => onSelect(n.id)}
            aria-pressed={selected === n.id}
            title={down ? `${n.id} tidak berjalan` : `Buka terminal ${n.id}`}
          >
            {n.id}
          </button>
        ) : (
          <span key={n.id} className={cls} style={style}>
            {n.id}
          </span>
        );
      })}
    </div>
  );
}
