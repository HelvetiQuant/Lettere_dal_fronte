import { useRef, useState, useEffect, useCallback, useMemo } from 'react';
import { Maximize2, Minimize2, ZoomIn, ZoomOut, Frame, Download, Image as ImageIcon } from 'lucide-react';

export interface GraphNodeData {
  id: string;
  type: string;
  label: string;
  color?: string;
}

export interface GraphEdgeData {
  source: string;
  target: string;
  relation: string;
  confidence: number;
  status?: string;
}

interface PositionedNode extends GraphNodeData {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  labelWidth: number;
  labelHeight: number;
}

const TYPE_COLORS: Record<string, string> = {
  persona: '#2196F3',
  fatto: '#4CAF50',
  evento: '#FF9800',
  luogo: '#9C27B0',
  data: '#607D8B',
  reparto: '#795548',
  campo: '#F44336',
  documento: '#009688',
  fonte: '#3F51B5',
  pratica: '#E91E63',
  caduti: '#2196F3',
  decorati: '#FF9800',
  internati: '#9C27B0',
  fonti_indice: '#3F51B5',
  archivio_documenti: '#009688',
};

function getNodeColor(type: string): string {
  return TYPE_COLORS[type] || '#666';
}

function splitLabel(label: string, maxCharsPerLine: number): string[] {
  if (label.length <= maxCharsPerLine) return [label];
  const words = label.split(' ');
  const lines: string[] = [];
  let current = '';
  for (const w of words) {
    if ((current + ' ' + w).trim().length > maxCharsPerLine && current) {
      lines.push(current.trim());
      current = w;
    } else {
      current = (current + ' ' + w).trim();
    }
  }
  if (current) lines.push(current.trim());
  return lines.length > 2 ? [lines[0], lines.slice(1).join(' ')] : lines;
}

function computeLayout(
  nodes: GraphNodeData[],
  edges: GraphEdgeData[],
  width: number,
  height: number,
): PositionedNode[] {
  const nodeCount = nodes.length;
  if (nodeCount === 0) return [];

  // Virtual area: expand based on node count
  const minArea = width * height;
  const nodeArea = nodeCount * 8000; // ~8000 px² per node
  const virtualArea = Math.max(minArea, nodeArea);
  const virtualW = Math.sqrt(virtualArea * (width / height));
  const virtualH = virtualArea / virtualW;

  // Initialize nodes in a circle
  const positioned: PositionedNode[] = nodes.map((n, i) => {
    const angle = (i / nodeCount) * Math.PI * 2;
    const r = Math.min(virtualW, virtualH) * 0.35;
    const labelLines = splitLabel(n.label, 18);
    const labelWidth = Math.max(...labelLines.map(l => l.length)) * 7 + 16;
    const labelHeight = labelLines.length * 14 + 8;
    return {
      ...n,
      x: virtualW / 2 + Math.cos(angle) * r + (Math.random() - 0.5) * 20,
      y: virtualH / 2 + Math.sin(angle) * r + (Math.random() - 0.5) * 20,
      vx: 0,
      vy: 0,
      radius: Math.max(8, n.label.length * 0.6),
      labelWidth,
      labelHeight,
    };
  });

  // Build adjacency
  const nodeMap = new Map(positioned.map(n => [n.id, n]));

  // Force simulation: 150 iterations
  const REPULSION = 4500;
  const ATTRACTION = 0.04;
  const CENTER_FORCE = 0.02;
  const MIN_DIST = 60;

  for (let iter = 0; iter < 150; iter++) {
    // Repulsion (all pairs)
    for (let i = 0; i < positioned.length; i++) {
      for (let j = i + 1; j < positioned.length; j++) {
        const dx = positioned[i].x - positioned[j].x;
        const dy = positioned[i].y - positioned[j].y;
        let dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 1) dist = 1;
        // Anti-collision: account for label sizes
        const minDist = MIN_DIST + (positioned[i].labelWidth + positioned[j].labelWidth) / 4;
        if (dist < minDist) {
          const force = (REPULSION / (dist * dist)) * 0.5;
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          positioned[i].vx += fx;
          positioned[i].vy += fy;
          positioned[j].vx -= fx;
          positioned[j].vy -= fy;
        } else {
          const force = REPULSION / (dist * dist);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          positioned[i].vx += fx;
          positioned[i].vy += fy;
          positioned[j].vx -= fx;
          positioned[j].vy -= fy;
        }
      }
    }

    // Attraction (edges)
    for (const e of edges) {
      const s = nodeMap.get(e.source);
      const t = nodeMap.get(e.target);
      if (!s || !t) continue;
      const dx = t.x - s.x;
      const dy = t.y - s.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < 1) continue;
      const force = ATTRACTION * dist;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      s.vx += fx;
      s.vy += fy;
      t.vx -= fx;
      t.vy -= fy;
    }

    // Center force
    for (const n of positioned) {
      n.vx += (virtualW / 2 - n.x) * CENTER_FORCE;
      n.vy += (virtualH / 2 - n.y) * CENTER_FORCE;
    }

    // Apply velocity with damping
    for (const n of positioned) {
      n.vx *= 0.85;
      n.vy *= 0.85;
      n.x += n.vx;
      n.y += n.vy;
      // Keep within bounds
      const margin = n.labelWidth / 2 + 10;
      n.x = Math.max(margin, Math.min(virtualW - margin, n.x));
      n.y = Math.max(n.labelHeight / 2 + 10, Math.min(virtualH - n.labelHeight / 2 - 10, n.y));
    }
  }

  return positioned;
}

function getBoundingBox(nodes: PositionedNode[]): { minX: number; minY: number; maxX: number; maxY: number } {
  if (nodes.length === 0) return { minX: 0, minY: 0, maxX: 100, maxY: 100 };
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const n of nodes) {
    minX = Math.min(minX, n.x - n.labelWidth / 2 - 10);
    minY = Math.min(minY, n.y - n.labelHeight / 2 - 10);
    maxX = Math.max(maxX, n.x + n.labelWidth / 2 + 10);
    maxY = Math.max(maxY, n.y + n.labelHeight / 2 + 10);
  }
  return { minX, minY, maxX, maxY };
}

interface ForceGraphProps {
  nodes: GraphNodeData[];
  edges: GraphEdgeData[];
  height?: number;
  minHeight?: number;
  maxHeight?: number;
}

export function ForceGraph({
  nodes,
  edges,
  minHeight = 750,
  maxHeight = 90, // vh
}: ForceGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [containerSize, setContainerSize] = useState({ width: 800, height: 750 });
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [dragNode, setDragNode] = useState<string | null>(null);
  const dragStartRef = useRef({ x: 0, y: 0, nodeX: 0, nodeY: 0 });
  const panStartRef = useRef({ x: 0, y: 0, panX: 0, panY: 0 });
  const [positionedNodes, setPositionedNodes] = useState<PositionedNode[]>([]);

  // Compute container size
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        setContainerSize({ width: width || 800, height: height || 750 });
      }
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  // Recompute layout when nodes/edges/container change
  useEffect(() => {
    if (nodes.length === 0) {
      setPositionedNodes([]);
      return;
    }
    const layout = computeLayout(nodes, edges, containerSize.width, containerSize.height);
    setPositionedNodes(layout);
    // Auto-fit
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, [nodes, edges, containerSize.width, containerSize.height]);

  const fitToScreen = useCallback(() => {
    if (positionedNodes.length === 0) return;
    const bbox = getBoundingBox(positionedNodes);
    const bw = bbox.maxX - bbox.minX;
    const bh = bbox.maxY - bbox.minY;
    if (bw < 1 || bh < 1) return;
    const padding = 40;
    const scaleX = (containerSize.width - padding * 2) / bw;
    const scaleY = (containerSize.height - padding * 2) / bh;
    const newZoom = Math.min(scaleX, scaleY, 2);
    setZoom(newZoom);
    const cx = (bbox.minX + bbox.maxX) / 2;
    const cy = (bbox.minY + bbox.maxY) / 2;
    setPan({
      x: containerSize.width / 2 - cx * newZoom,
      y: containerSize.height / 2 - cy * newZoom,
    });
  }, [positionedNodes, containerSize]);

  // Auto-fit on first layout
  useEffect(() => {
    if (positionedNodes.length > 0 && zoom === 1 && pan.x === 0 && pan.y === 0) {
      fitToScreen();
    }
  }, [positionedNodes, fitToScreen, zoom, pan]);

  const handleZoomIn = () => setZoom(z => Math.min(z * 1.3, 5));
  const handleZoomOut = () => setZoom(z => Math.max(z / 1.3, 0.1));

  const toggleFullscreen = () => {
    setIsFullscreen(f => !f);
  };

  // Pan handling
  const handleMouseDown = (e: React.MouseEvent) => {
    if (dragNode) return;
    setIsDragging(true);
    panStartRef.current = { x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (dragNode && svgRef.current) {
      const pt = svgRef.current.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const ctm = svgRef.current.getScreenCTM();
      if (ctm) {
        const svgPt = pt.matrixTransform(ctm.inverse());
        setPositionedNodes(prev => prev.map(n =>
          n.id === dragNode ? { ...n, x: svgPt.x, y: svgPt.y, vx: 0, vy: 0 } : n
        ));
      }
      return;
    }
    if (isDragging) {
      const dx = e.clientX - panStartRef.current.x;
      const dy = e.clientY - panStartRef.current.y;
      setPan({ x: panStartRef.current.panX + dx, y: panStartRef.current.panY + dy });
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
    setDragNode(null);
  };

  // Touch support
  const handleTouchStart = (e: React.TouchEvent) => {
    if (e.touches.length === 1) {
      const t = e.touches[0];
      handleMouseDown({ clientX: t.clientX, clientY: t.clientY } as React.MouseEvent);
    }
  };
  const handleTouchMove = (e: React.TouchEvent) => {
    if (e.touches.length === 1) {
      const t = e.touches[0];
      handleMouseMove({ clientX: t.clientX, clientY: t.clientY } as React.MouseEvent);
    }
  };

  // Export SVG
  const exportSVG = () => {
    if (!svgRef.current) return;
    const serializer = new XMLSerializer();
    let svgStr = serializer.serializeToString(svgRef.current);
    // Ensure xmlns
    if (!svgStr.includes('xmlns=')) {
      svgStr = svgStr.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"');
    }
    const blob = new Blob([svgStr], { type: 'image/svg+xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'grafo.svg';
    a.click();
    URL.revokeObjectURL(url);
  };

  // Export PNG
  const exportPNG = () => {
    if (!svgRef.current) return;
    const serializer = new XMLSerializer();
    let svgStr = serializer.serializeToString(svgRef.current);
    if (!svgStr.includes('xmlns=')) {
      svgStr = svgStr.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"');
    }
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = containerSize.width * 2;
      canvas.height = containerSize.height * 2;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      canvas.toBlob((blob) => {
        if (!blob) return;
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'grafo.png';
        a.click();
        URL.revokeObjectURL(url);
      });
    };
    img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svgStr)));
  };

  // Wheel zoom
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    const newZoom = Math.max(0.1, Math.min(zoom * delta, 5));
    // Zoom toward mouse position
    const rect = svgRef.current?.getBoundingClientRect();
    if (rect) {
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const wx = (mx - pan.x) / zoom;
      const wy = (my - pan.y) / zoom;
      setPan({ x: mx - wx * newZoom, y: my - wy * newZoom });
    }
    setZoom(newZoom);
  };

  const nodeMap = useMemo(() => new Map(positionedNodes.map(n => [n.id, n])), [positionedNodes]);

  const containerStyle: React.CSSProperties = isFullscreen
    ? {
        position: 'fixed',
        top: 0, left: 0, right: 0, bottom: 0,
        zIndex: 9999,
        background: '#fff',
        padding: 'var(--s-3)',
      }
    : {
        width: '100%',
        minHeight: `${minHeight}px`,
        maxHeight: `${maxHeight}vh`,
        position: 'relative',
      };

  const svgHeight = isFullscreen
    ? window.innerHeight - 120
    : Math.max(minHeight, containerSize.height);

  if (nodes.length === 0) return null;

  return (
    <div ref={containerRef} style={containerStyle}>
      {/* Toolbar */}
      <div style={{
        display: 'flex',
        gap: 'var(--s-1)',
        alignItems: 'center',
        marginBottom: 'var(--s-2)',
        flexWrap: 'wrap',
      }}>
        <span className="text-sm text-muted" style={{ marginRight: 'auto' }}>
          {nodes.length} nodi · {edges.length} archi · zoom {(zoom * 100).toFixed(0)}%
        </span>
        <button className="btn btn--sm" onClick={handleZoomOut} title="Zoom out" aria-label="Zoom out">
          <ZoomOut size={14} />
        </button>
        <button className="btn btn--sm" onClick={handleZoomIn} title="Zoom in" aria-label="Zoom in">
          <ZoomIn size={14} />
        </button>
        <button className="btn btn--sm" onClick={fitToScreen} title="Adatta alla schermata" aria-label="Adatta">
          <Frame size={14} />
        </button>
        <button className="btn btn--sm" onClick={exportSVG} title="Esporta SVG" aria-label="Esporta SVG">
          <Download size={14} /> SVG
        </button>
        <button className="btn btn--sm" onClick={exportPNG} title="Esporta PNG" aria-label="Esporta PNG">
          <ImageIcon size={14} /> PNG
        </button>
        <button className="btn btn--sm" onClick={toggleFullscreen} title={isFullscreen ? 'Schermo normale' : 'Schermo intero'} aria-label="Fullscreen">
          {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
        </button>
      </div>

      {/* SVG canvas */}
      <div
        style={{
          width: '100%',
          height: svgHeight,
          border: '1px solid var(--c-divider)',
          borderRadius: 'var(--r-sm)',
          overflow: 'hidden',
          background: '#fafafa',
          cursor: isDragging ? 'grabbing' : 'grab',
        }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleMouseUp}
      >
        <svg
          ref={svgRef}
          width="100%"
          height="100%"
          viewBox={`0 0 ${containerSize.width} ${svgHeight}`}
          style={{ display: 'block' }}
        >
          {/* Edges */}
          <g transform={`translate(${pan.x},${pan.y}) scale(${zoom})`}>
            {edges.map((e, i) => {
              const s = nodeMap.get(e.source);
              const t = nodeMap.get(e.target);
              if (!s || !t) return null;
              const midX = (s.x + t.x) / 2;
              const midY = (s.y + t.y) / 2;
              const color = e.status === 'confirmed' ? '#4CAF50' : e.status === 'rejected' ? '#F44336' : '#999';
              const opacity = 0.3 + (e.confidence || 0.5) * 0.4;
              return (
                <g key={i}>
                  <line
                    x1={s.x} y1={s.y} x2={t.x} y2={t.y}
                    stroke={color}
                    strokeWidth={1 + (e.confidence || 0.5)}
                    opacity={opacity}
                  />
                  <text
                    x={midX} y={midY - 4}
                    fontSize={9}
                    fill={color}
                    textAnchor="middle"
                    opacity={0.7}
                    style={{ pointerEvents: 'none', userSelect: 'none' }}
                  >
                    {e.relation.length > 15 ? e.relation.substring(0, 13) + '…' : e.relation}
                  </text>
                </g>
              );
            })}
          </g>

          {/* Nodes */}
          <g transform={`translate(${pan.x},${pan.y}) scale(${zoom})`}>
            {positionedNodes.map((n) => {
              const lines = splitLabel(n.label, 18);
              const color = n.color || getNodeColor(n.type);
              return (
                <g
                  key={n.id}
                  transform={`translate(${n.x},${n.y})`}
                  style={{ cursor: 'pointer' }}
                  onMouseDown={(e) => {
                    e.stopPropagation();
                    setDragNode(n.id);
                    dragStartRef.current = { x: e.clientX, y: e.clientY, nodeX: n.x, nodeY: n.y };
                  }}
                >
                  {/* Background rect for label */}
                  <rect
                    x={-n.labelWidth / 2}
                    y={-n.labelHeight / 2}
                    width={n.labelWidth}
                    height={n.labelHeight}
                    rx={6}
                    ry={6}
                    fill="white"
                    stroke={color}
                    strokeWidth={1.5}
                    opacity={0.95}
                  />
                  {/* Node circle */}
                  <circle
                    cx={0}
                    cy={-n.labelHeight / 2 - 6}
                    r={6}
                    fill={color}
                    stroke="white"
                    strokeWidth={2}
                  />
                  {/* Label lines */}
                  {lines.map((line, li) => (
                    <text
                      key={li}
                      x={0}
                      y={-n.labelHeight / 2 + 14 + li * 14}
                      fontSize={11}
                      fontWeight={600}
                      fill="#333"
                      textAnchor="middle"
                      style={{ pointerEvents: 'none', userSelect: 'none' }}
                    >
                      {line}
                    </text>
                  ))}
                  {/* Type badge */}
                  <text
                    x={0}
                    y={n.labelHeight / 2 + 12}
                    fontSize={8}
                    fill={color}
                    textAnchor="middle"
                    opacity={0.7}
                    style={{ pointerEvents: 'none', userSelect: 'none', textTransform: 'uppercase' }}
                  >
                    {n.type}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>
    </div>
  );
}
