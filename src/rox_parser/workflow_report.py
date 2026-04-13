"""Standalone HTML reporting for ROX workflow inspection."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from html import escape
from typing import Any

from .workflow import WorkflowDocument
from .workflow_graph import WorkflowGraph, WorkflowGraphNode, build_workflow_graph
from .workflow_trigger import WorkflowTriggerModel, build_workflow_trigger_model

_CANVAS_PADDING = 0
_CANVAS_X_SCALE = 1.6
_CANVAS_Y_SCALE = 1.6


def build_workflow_report_html(
    workflow: WorkflowDocument,
    *,
    document_name: str,
    title: str = "ROX Workflow Inspector",
    generated_at: datetime | None = None,
) -> str:
    """Build a standalone HTML workflow inspector."""

    graph = build_workflow_graph(workflow) or WorkflowGraph(nodes={}, edges=())
    trigger = build_workflow_trigger_model(workflow)
    payload = _safe_json_for_html_script(
        _workflow_report_payload(
            workflow=workflow,
            graph=graph,
            trigger=trigger,
            title=title,
        )
    )
    timestamp_iso = _report_timestamp_iso(generated_at)

    return _build_html(
        payload=payload,
        title=title,
        document_name=document_name,
        workflow_name=workflow.definition_name or "(unnamed workflow)",
        timestamp_iso=timestamp_iso,
    )


def _workflow_report_payload(
    *,
    workflow: WorkflowDocument,
    graph: WorkflowGraph,
    trigger: WorkflowTriggerModel | None,
    title: str,
) -> dict[str, Any]:
    quick_action_lookup = {
        str(item.id).casefold(): item for item in workflow.quick_actions if item.id
    }
    nodes = _canvas_nodes(graph, quick_action_lookup)
    return {
        "title": title,
        "workflow_name": workflow.definition_name,
        "summary": {
            "cards": [
                {"label": "Blocks", "value": str(len(nodes))},
                {"label": "Connections", "value": str(len(graph.edges))},
                {"label": "Quick Actions", "value": str(len(workflow.quick_actions))},
                {
                    "label": "Trigger Conditions",
                    "value": str(len(trigger.conditions) if trigger is not None else 0),
                },
            ],
            "block_type_counts": _block_type_counts(graph),
        },
        "graph": {
            "nodes": nodes,
            "edges": [edge.to_dict() for edge in graph.edges],
            "canvas_width": _canvas_width(nodes),
            "canvas_height": _canvas_height(nodes),
        },
        "quick_actions": [
            {
                "id": item.id,
                "name": item.name,
                "action_type": item.action_type,
                "group_name": item.group_name,
                "definition_json": item.definition_json,
            }
            for item in workflow.quick_actions
        ],
        "initial_selected_block_id": _initial_selected_block_id(graph),
    }


def _canvas_nodes(
    graph: WorkflowGraph, quick_action_lookup: dict[str, Any]
) -> list[dict[str, Any]]:
    ordered_nodes = sorted(
        graph.nodes.values(),
        key=lambda node: (
            node.y if node.y is not None else 10**9,
            node.x if node.x is not None else 10**9,
            node.title or node.block_id,
        ),
    )
    if not ordered_nodes:
        return []

    known_x_values = [node.x for node in ordered_nodes if node.x is not None]
    known_y_values = [node.y for node in ordered_nodes if node.y is not None]
    fallback_x = min(known_x_values) if known_x_values else 0
    fallback_y = max(known_y_values) if known_y_values else 0
    exit_label_counts = _exit_label_counts(graph)
    positioned_nodes: list[tuple[WorkflowGraphNode, int, int]] = []
    for node in ordered_nodes:
        raw_x = node.x if node.x is not None else fallback_x
        raw_y = node.y if node.y is not None else fallback_y
        positioned_nodes.append((node, raw_x, raw_y))

    x_values = [raw_x for _, raw_x, _ in positioned_nodes]
    y_values = [raw_y for _, _, raw_y in positioned_nodes]
    min_x = min(x_values) if x_values else 0
    min_y = min(y_values) if y_values else 0

    nodes: list[dict[str, Any]] = []

    for node, raw_x, raw_y in positioned_nodes:
        visuals = _node_visuals(node, exit_label_counts.get(node.block_id, 0))
        display_x = int((raw_x - min_x) * _CANVAS_X_SCALE + _CANVAS_PADDING)
        display_y = int((raw_y - min_y) * _CANVAS_Y_SCALE + _CANVAS_PADDING)

        nodes.append(
            {
                **node.to_dict(),
                "x": raw_x,
                "y": raw_y,
                "original_x": node.x,
                "original_y": node.y,
                "display_x": display_x,
                "display_y": display_y,
                "source_x": raw_x,
                "source_y": raw_y,
                **visuals,
                "search_text": _node_search_text(node, quick_action_lookup),
            }
        )

    return nodes


def _exit_label_counts(graph: WorkflowGraph) -> dict[str, int]:
    labels_by_block: dict[str, set[str]] = {}
    for node in graph.nodes.values():
        labels = {
            (block_exit.title or block_exit.condition or "").strip().casefold()
            for block_exit in node.exits
            if (block_exit.title or block_exit.condition or "").strip()
        }
        if labels:
            labels_by_block[node.block_id] = labels
    return {block_id: len(labels) for block_id, labels in labels_by_block.items()}


def _expanded_rect_height(default_height: int, exit_label_count: int) -> int:
    if exit_label_count <= 2:
        return default_height
    return max(default_height, 90 + 24 * (exit_label_count - 1))


def _node_visuals(node: WorkflowGraphNode, exit_label_count: int = 0) -> dict[str, Any]:
    block_type = (node.block_type or "").casefold()

    if block_type in {"start", "stop"}:
        return {
            "shape": "circle",
            "width": 104,
            "height": 104,
        }

    if block_type == "if":
        return {
            "shape": "diamond",
            "width": 92,
            "height": 92,
        }

    if block_type == "switch":
        return {
            "shape": "rect",
            "width": 132,
            "height": _expanded_rect_height(94, exit_label_count),
        }

    if block_type in {"wait", "waitforchild", "waitforevent"}:
        return {
            "shape": "rect",
            "width": 220,
            "height": _expanded_rect_height(82, exit_label_count),
        }

    return {
        "shape": "rect",
        "width": 232,
        "height": _expanded_rect_height(110, exit_label_count),
    }


def _node_search_text(
    node: WorkflowGraphNode, quick_action_lookup: dict[str, Any]
) -> str:
    parts = [node.block_id, node.block_type or "", node.title or ""]
    for property_ in node.properties:
        parts.append(property_.name)
        for group in property_.groups:
            for name, value in group.params.items():
                parts.append(name)
                if value:
                    parts.append(value)
    for block_exit in node.exits:
        if block_exit.title:
            parts.append(block_exit.title)
        if block_exit.condition:
            parts.append(block_exit.condition)
        for property_ in block_exit.properties:
            parts.append(property_.name)
            for group in property_.groups:
                for name, value in group.params.items():
                    parts.append(name)
                    if value:
                        parts.append(value)
    quick_action = _linked_quick_action(node, quick_action_lookup)
    if quick_action is not None:
        parts.extend(_quick_action_search_parts(quick_action))
    return " ".join(part.casefold() for part in parts if part)


def _linked_quick_action(
    node: WorkflowGraphNode, quick_action_lookup: dict[str, Any]
) -> Any | None:
    for property_ in node.properties:
        if property_.name.casefold() != "quickaction":
            continue
        for group in property_.groups:
            qaid = group.params.get("QAID")
            if qaid:
                return quick_action_lookup.get(str(qaid).casefold())
    return None


def _quick_action_search_parts(quick_action: Any) -> list[str]:
    parts = [
        quick_action.name or "",
        quick_action.action_type or "",
        quick_action.group_name or "",
    ]
    definition = quick_action.definition_json
    if isinstance(definition, dict):
        parts.extend(_meaningful_definition_search_parts(definition))
    return [part for part in parts if part]


def _meaningful_definition_search_parts(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, bool):
        return ["true"] if value else []
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            parts.extend(_meaningful_definition_search_parts(item))
        return parts
    if isinstance(value, dict):
        parts: list[str] = []
        field_name = value.get("FieldName")
        expression_text = value.get("ExpressionText")
        overwrite = value.get("Overwrite")
        if field_name and (expression_text or overwrite):
            parts.append(str(field_name))
        if expression_text:
            parts.append(str(expression_text))
        if overwrite:
            parts.append("overwrite")
        if field_name and (expression_text or overwrite):
            return parts
        for key, item in value.items():
            child_parts = _meaningful_definition_search_parts(item)
            if child_parts:
                parts.append(str(key))
                parts.extend(child_parts)
        return parts
    return []


def _block_type_counts(graph: WorkflowGraph) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for node in graph.nodes.values():
        key = node.block_type or "(unknown)"
        counts[key] = counts.get(key, 0) + 1
    return [
        {"type": block_type, "count": count}
        for block_type, count in sorted(
            counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]


def _canvas_width(nodes: list[dict[str, Any]]) -> int:
    return (
        max(node["display_x"] + node["width"] + _CANVAS_PADDING for node in nodes)
        if nodes
        else 800
    )


def _canvas_height(nodes: list[dict[str, Any]]) -> int:
    return (
        max(node["display_y"] + node["height"] + _CANVAS_PADDING for node in nodes)
        if nodes
        else 500
    )


def _initial_selected_block_id(graph: WorkflowGraph) -> str | None:
    return None


def _safe_json_for_html_script(payload: dict[str, Any]) -> str:
    return (
        json.dumps(payload, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _report_timestamp_iso(generated_at: datetime | None) -> str:
    moment = generated_at or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    else:
        moment = moment.astimezone(UTC)
    return moment.isoformat().replace("+00:00", "Z")


def _build_html(
    *,
    payload: str,
    title: str,
    document_name: str,
    workflow_name: str,
    timestamp_iso: str,
) -> str:
    return (
        f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{
      --bg: #eef3f8; --panel: #fff; --line: #d7e0eb; --text: #142033; --muted: #5f6f85;
      --accent: #2458a6; --shadow: 0 14px 34px rgba(20, 32, 51, 0.09);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Segoe UI", sans-serif; background: linear-gradient(180deg, #f4f7fb, #edf2f8); color: var(--text); }}
    .page {{ width: 100%; max-width: none; margin: 0; padding: 24px; }}
    .sticky {{ position: sticky; top: 0; z-index: 4; padding-bottom: 14px; background: linear-gradient(180deg, rgba(244,247,251,.98), rgba(237,242,248,.95)); }}
    .header, .toolbar, .panel, .stats {{ background: var(--panel); border: 1px solid var(--line); border-radius: 18px; box-shadow: var(--shadow); }}
    .header {{ padding: 18px; margin-bottom: 14px; }}
    .toolbar {{ padding: 14px 18px; margin-bottom: 14px; }}
    h1, h2, h3 {{ margin: 0; }}
    h1 {{ font-size: 1.85rem; }}
    .subtitle, .muted, .small {{ color: var(--muted); }}
    .meta {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px; font-size: .92rem; }}
    .chip {{ display: inline-flex; gap: 8px; padding: 8px 12px; border-radius: 999px; border: 1px solid var(--line); background: #fbfcfe; }}
    .toolbar-row {{ display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }}
    .search {{ flex: 1 1 420px; min-width: 260px; padding: 12px 14px; border: 1px solid #b8c6d7; border-radius: 12px; font: inherit; }}
    button {{ appearance: none; border: 1px solid #b8c6d7; border-radius: 12px; background: #fbfcfe; padding: 10px 12px; font: inherit; font-weight: 650; cursor: pointer; }}
    button:hover {{ border-color: var(--accent); background: #f1f5fb; }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; padding: 14px; margin-bottom: 14px; }}
    .stat {{ padding: 10px 12px; border-radius: 14px; background: #fbfcfe; border: 1px solid var(--line); }}
    .stat-label {{ display: block; font-size: .8rem; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; font-weight: 700; margin-bottom: 4px; }}
    .stat-value {{ font-size: 1.55rem; font-weight: 750; }}
    .legend, .badges {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .legend {{ margin-bottom: 14px; }}
    .workspace {{ display: grid; gap: 14px; }}
    .workspace {{ grid-template-columns: minmax(0, 4fr) minmax(320px, 1fr); margin-bottom: 14px; }}
    .panel-header {{ padding: 14px 16px; border-bottom: 1px solid var(--line); background: #f7f9fc; }}
    .panel-body {{ padding: 16px; min-width: 0; overflow-x: hidden; }}
    .canvas-wrap {{ height: 72vh; min-height: 620px; overflow: auto; cursor: grab; user-select: none; background:
      linear-gradient(90deg, rgba(36,88,166,.04) 1px, transparent 1px),
      linear-gradient(rgba(36,88,166,.04) 1px, transparent 1px),
      linear-gradient(180deg, #fbfcfe, #f5f8fc); background-size: 32px 32px, 32px 32px, auto; }}
    .canvas-wrap.dragging, .canvas-wrap.block-dragging {{ cursor: grabbing; }}
    .canvas-wrap.zooming .node-shape {{ filter: none; }}
    .canvas-wrap.zooming .node, .canvas-wrap.zooming .edge {{ transition: none !important; }}
    .canvas-stage {{ min-width: 100%; min-height: 100%; position: relative; }}
    .canvas-spacer {{ pointer-events: none; }}
    .canvas-content {{ position: absolute; left: 24px; top: 24px; transform-origin: top left; will-change: transform; contain: layout paint style; }}
    .canvas-content svg {{ display: block; }}
    .inspector {{ min-height: 72vh; min-width: 0; }}
    .stack, .section, .list {{ display: grid; gap: 10px; min-width: 0; }}
    .badge {{ display: inline-flex; padding: 6px 10px; border: 1px solid var(--line); border-radius: 999px; background: #f2f6fb; font-size: .82rem; font-weight: 700; min-width: 0; max-width: 100%; overflow-wrap: anywhere; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; min-width: 0; }}
    .grid > * {{ min-width: 0; }}
    .card {{ border: 1px solid var(--line); border-radius: 14px; padding: 12px; background: #fbfcfe; min-width: 0; overflow-wrap: anywhere; word-break: break-word; }}
    .label {{ display: block; font-size: .8rem; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; font-weight: 700; margin-bottom: 4px; }}
    .link-button {{ width: 100%; text-align: left; }}
    .prop, details {{ border: 1px solid var(--line); border-radius: 14px; background: #fbfcfe; }}
    .prop {{ padding: 12px; }}
    .group {{ border-top: 1px solid #ebf0f6; padding-top: 10px; margin-top: 10px; }}
    .group:first-of-type {{ border-top: 0; padding-top: 0; margin-top: 0; }}
    .param {{ display: grid; grid-template-columns: minmax(120px, 160px) minmax(0, 1fr); gap: 10px; font-size: .86rem; }}
    .param-name {{ color: var(--muted); font-weight: 700; }}
    .table-wrap {{ overflow: auto; max-width: 100%; border: 1px solid var(--line); border-radius: 14px; background: #fff; }}
    table {{ width: 100%; border-collapse: collapse; }}
    .inspector .table-wrap table {{ width: max-content; min-width: 100%; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; font-size: .9rem; }}
    th {{ background: #f7f9fc; color: var(--muted); font-size: .82rem; text-transform: uppercase; letter-spacing: .05em; }}
    tr:last-child td {{ border-bottom: 0; }}
    .row {{ cursor: pointer; }}
    .row:hover {{ background: #f9fbff; }}
    .row.selected {{ background: #eef4ff; }}
    details summary {{ cursor: pointer; padding: 12px 14px; font-weight: 700; list-style: none; }}
    details summary::-webkit-details-marker {{ display: none; }}
    .details-body {{ padding: 0 14px 14px; }}
    pre {{ margin: 0; padding: 12px; border-radius: 12px; background: #f7f9fc; border: 1px solid #e4ebf4; white-space: pre-wrap; overflow-wrap: anywhere; font-family: "Cascadia Code", Consolas, monospace; font-size: .8rem; }}
    .empty {{ color: var(--muted); font-style: italic; }}
    .inspector h2, .inspector h3, .inspector .small, .inspector .muted {{ overflow-wrap: anywhere; word-break: break-word; min-width: 0; }}
    .inspector th, .inspector td {{ white-space: normal; overflow-wrap: normal; word-break: normal; }}
    .inspector .table-wrap th, .inspector .table-wrap td {{ max-width: 26rem; overflow-wrap: anywhere; word-break: break-word; }}
    .node {{ cursor: pointer; transition: opacity .12s ease; }}
    .node.dragging {{ cursor: grabbing; }}
    .node.dim, .edge.dim {{ opacity: .18; }}
    .node.selected .node-shape {{ stroke: var(--accent); stroke-width: 3; }}
    .edge {{ fill: none; stroke: rgba(95,111,133,.5); stroke-width: 2.5; stroke-linecap: round; stroke-linejoin: round; cursor: pointer; }}
    .edge.connected {{ stroke: rgba(36,88,166,.62); stroke-width: 3; opacity: 1; }}
    .edge.selected {{ stroke: rgba(36,88,166,.95); stroke-width: 3.4; opacity: 1; }}
    .node-shape {{ stroke: #b8c6d7; stroke-width: 1.5; filter: drop-shadow(0 5px 12px rgba(20,32,51,.08)); }}
    .node-label {{ fill: #132132; font-size: 14px; font-weight: 700; pointer-events: none; }}
    .node-meta {{ fill: rgba(20,32,51,.7); font-size: 12px; font-weight: 600; pointer-events: none; }}
    mark {{ background: #fff2a8; color: inherit; padding: 0 2px; border-radius: 3px; }}
    @media (max-width: 1300px) {{ .workspace {{ grid-template-columns: 1fr; }} .inspector {{ min-height: auto; }} }}
  </style>
</head>
<body>
  <main class="page">
    <div class="sticky">
      <section class="header">
        <h1>{escape(title)}</h1>
        <p class="subtitle">Workflow blocks use their stored canvas coordinates. Click a block or connection on the canvas to inspect its metadata.</p>
        <div class="meta">
          <span class="chip"><strong>Template</strong><span>{escape(document_name)}</span></span>
          <span class="chip"><strong>Workflow</strong><span>{escape(workflow_name)}</span></span>
          <span class="chip"><strong>Generated</strong><span id="generated-at">{escape(timestamp_iso)}</span></span>
        </div>
      </section>
      <section class="toolbar">
        <div class="toolbar-row">
          <input id="search" class="search" type="search" placeholder="Search block id, title, type, or property text" autocomplete="off" spellcheck="false">
          <button id="reset-layout" type="button">Reset layout</button>
          <button id="clear-selection" type="button">Clear selection</button>
        </div>
        <div class="toolbar-row"><div id="summary" class="muted"></div></div>
      </section>
    </div>
    <section id="stats" class="stats"></section>
    <section id="legend" class="legend"></section>
    <section class="workspace">
      <article class="panel">
        <div class="panel-header"><h2>Canvas</h2><div class="small"></div></div>
        <div id="canvas-wrap" class="canvas-wrap"><div id="canvas-stage" class="canvas-stage"></div></div>
      </article>
      <aside class="panel inspector">
        <div class="panel-header"><h2>Selected Block</h2><div class="small">Metadata, connections and grouped properties.</div></div>
        <div id="inspector" class="panel-body"></div>
      </aside>
    </section>
  </main>
  <script id="workflow-report-data" type="application/json">
{payload}
  </script>
  <script>
"""
        + _HTML_SCRIPT
        + """
  </script>
</body>
</html>
"""
    )


_HTML_SCRIPT = """
    const data = JSON.parse(document.getElementById("workflow-report-data").textContent);
    const searchInput = document.getElementById("search");
    const resetLayoutButton = document.getElementById("reset-layout");
    const clearSelectionButton = document.getElementById("clear-selection");
    const summaryElement = document.getElementById("summary");
    const statsElement = document.getElementById("stats");
    const legendElement = document.getElementById("legend");
    const canvasWrap = document.getElementById("canvas-wrap");
    const canvasStage = document.getElementById("canvas-stage");
    const inspectorElement = document.getElementById("inspector");
    const nodeMap = new Map(data.graph.nodes.map((node) => [node.block_id, node]));
    const quickActionMap = new Map(data.quick_actions.map((item) => [String(item.id || "").toLowerCase(), item]));
    function edgeKey(edge) {
      return [
        edge.source_block_id || "",
        edge.target_block_id || "",
        edge.source_exit_id || "",
        edge.source_exit_title || "",
        edge.source_exit_condition || "",
      ].join("|");
    }
    const edgeMap = new Map(data.graph.edges.map((edge) => [edgeKey(edge), edge]));
    const incomingMap = new Map();
    const outgoingMap = new Map();
    for (const edge of data.graph.edges) {
      if (!incomingMap.has(edge.target_block_id)) incomingMap.set(edge.target_block_id, []);
      if (!outgoingMap.has(edge.source_block_id)) outgoingMap.set(edge.source_block_id, []);
      incomingMap.get(edge.target_block_id).push(edge);
      outgoingMap.get(edge.source_block_id).push(edge);
    }
    let selectedBlockId = data.initial_selected_block_id || null;
    let selectedEdgeKey = null;
    const layoutOverrides = new Map();
    let isDraggingCanvas = false;
    let draggedBlockId = null;
    let dragBlockStartX = 0;
    let dragBlockStartY = 0;
    let dragBlockOriginX = 0;
    let dragBlockOriginY = 0;
    let dragBlockMoved = false;
    let dragRenderFrameRequested = false;
    let suppressBlockClick = false;
    let dragStartX = 0;
    let dragStartY = 0;
    let dragScrollLeft = 0;
    let dragScrollTop = 0;
    let canvasZoom = 1;
    let canvasSpacer = null;
    let canvasContent = null;
    let zoomFrameRequested = false;
    let zoomingClassTimer = 0;
    let pendingZoom = 1;
    let pendingZoomClientX = 0;
    let pendingZoomClientY = 0;
    function escapeHtml(value) {
      return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }
    function formatGeneratedTimestamp(value) {
      if (!value) return "";
      const moment = new Date(value);
      if (Number.isNaN(moment.getTime())) return value;
      return new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(moment);
    }
    function query() { return searchInput.value.trim().toLowerCase(); }
    function shortLabel(node) { return node.title || node.block_id; }
    function effectiveDisplayX(node) {
      const override = layoutOverrides.get(node.block_id);
      return override ? override.x : node.display_x;
    }
    function effectiveDisplayY(node) {
      const override = layoutOverrides.get(node.block_id);
      return override ? override.y : node.display_y;
    }
    function effectiveCanvasWidth() {
      let width = 0;
      for (const node of data.graph.nodes) {
        width = Math.max(width, effectiveDisplayX(node) + node.width);
      }
      return Math.max(data.graph.canvas_width, width);
    }
    function effectiveCanvasHeight() {
      let height = 0;
      for (const node of data.graph.nodes) {
        height = Math.max(height, effectiveDisplayY(node) + node.height);
      }
      return Math.max(data.graph.canvas_height, height);
    }
    function highlightText(value) {
      const text = String(value);
      const q = query();
      if (!q) return escapeHtml(text);
      const lower = text.toLowerCase();
      let index = 0;
      let result = "";
      while (index < text.length) {
        const matchIndex = lower.indexOf(q, index);
        if (matchIndex === -1) {
          result += escapeHtml(text.slice(index));
          break;
        }
        result += escapeHtml(text.slice(index, matchIndex));
        result += `<mark>${escapeHtml(text.slice(matchIndex, matchIndex + q.length))}</mark>`;
        index = matchIndex + q.length;
      }
      return result;
    }
    function formatValue(value) { return value == null || value === "" ? '<span class="empty">None</span>' : highlightText(value); }
    function nodeColor(type) {
      const normalized = (type || "").toLowerCase();
      if (normalized === "start") return "#dff3e6";
      if (normalized === "stop") return "#fde4e1";
      if (normalized === "if" || normalized === "switch") return "#fff3d7";
      if (["task","advancedtask","runforchild","invokeforchild","invokeworkflow","multichild"].includes(normalized)) return "#e9eefc";
      if (normalized === "notification") return "#efe6fb";
      if (["update","searchandlink","archiveforsearch","runforsearch"].includes(normalized)) return "#e3f3f5";
      if (["quickaction","create","createnew0002","remotescript","wscall","template"].includes(normalized)) return "#fce9d7";
      if (["wait","waitforchild","waitforevent"].includes(normalized)) return "#ececf7";
      if (normalized.startsWith("vote")) return "#f7eadf";
      if (normalized === "join") return "#edf1f5";
      return "#f8fbff";
    }
    function nodeShapeMarkup(node) {
      if (node.shape === "circle") {
        const radius = Math.min(node.width, node.height) / 2;
        return `<circle class="node-shape" cx="${radius}" cy="${radius}" r="${radius - 3}" fill="${nodeColor(node.block_type)}"></circle>`;
      }
      if (node.shape === "diamond") {
        const halfWidth = node.width / 2;
        const halfHeight = node.height / 2;
        const points = `${halfWidth},0 ${node.width},${halfHeight} ${halfWidth},${node.height} 0,${halfHeight}`;
        return `<polygon class="node-shape" points="${points}" fill="${nodeColor(node.block_type)}"></polygon>`;
      }
      return `<rect class="node-shape" width="${node.width}" height="${node.height}" rx="10" ry="10" fill="${nodeColor(node.block_type)}"></rect>`;
    }
    function isTruthyExit(edge) {
      const text = `${edge.source_exit_title || ""} ${edge.source_exit_condition || ""}`.toLowerCase();
      return text.includes("true");
    }
    function isFalseyExit(edge) {
      const text = `${edge.source_exit_title || ""} ${edge.source_exit_condition || ""}`.toLowerCase();
      return text.includes("false");
    }
    function uniqueExitLabels(blockId) {
      const node = nodeMap.get(blockId);
      const seen = new Set();
      const labels = [];
      const exits = node && Array.isArray(node.exits) ? node.exits : [];
      for (const exit of exits) {
        const label = (exit.title || exit.condition || "").trim();
        if (!label) continue;
        const key = label.toLowerCase();
        if (seen.has(key)) continue;
        seen.add(key);
        labels.push(label);
      }
      if (labels.length) return labels;
      for (const edge of outgoingMap.get(blockId) || []) {
        const label = (edge.source_exit_title || edge.source_exit_condition || "").trim();
        if (!label) continue;
        const key = label.toLowerCase();
        if (seen.has(key)) continue;
        seen.add(key);
        labels.push(label);
      }
      return labels;
    }
    function exitLabelForEdge(edge) {
      return (edge.source_exit_title || edge.source_exit_condition || "").trim();
    }
    function rectExitAnchorY(source, edge) {
      const exitLabels = uniqueExitLabels(source.block_id);
      const label = exitLabelForEdge(edge);
      if (!label || !exitLabels.length) {
        return effectiveDisplayY(source) + source.height / 2;
      }
      const index = exitLabels.findIndex((item) => item.toLowerCase() === label.toLowerCase());
      if (index === -1) {
        return effectiveDisplayY(source) + source.height / 2;
      }
      const localY = source.height - 18 - (exitLabels.length - 1 - index) * 24;
      return effectiveDisplayY(source) + localY - 5;
    }
    function connectionPoints(source, target, edge) {
      const sourceX = effectiveDisplayX(source);
      const sourceY = effectiveDisplayY(source);
      const targetX = effectiveDisplayX(target);
      const targetY = effectiveDisplayY(target);
      const sourceCenterX = sourceX + source.width / 2;
      const sourceCenterY = sourceY + source.height / 2;
      const targetCenterX = targetX + target.width / 2;
      const targetCenterY = targetY + target.height / 2;
      const sourceType = (source.block_type || "").toLowerCase();
      const horizontalDistance = Math.abs(targetCenterX - sourceCenterX);
      const verticalGapToTop = targetY - sourceCenterY;
      const verticalOffset = targetCenterY - sourceCenterY;
      const targetUpperLeftY = targetY + Math.max(18, Math.min(target.height * 0.24, 30));

      let startX = sourceX + source.width;
      let startY = sourceCenterY;
      if (source.shape === "rect") {
        startY = rectExitAnchorY(source, edge);
      }
      if (sourceType === "if" && isFalseyExit(edge)) {
        startX = sourceX;
        startY = sourceCenterY;
      }

      const sourceClearlyAbove = sourceCenterY <= targetY - target.height * 0.2;
      const falseExit = sourceType === "if" && isFalseyExit(edge);
      const ifTopEntry = sourceType === "if"
        && (
          (!falseExit && verticalGapToTop > Math.max(120, horizontalDistance * 0.35))
          || (falseExit && verticalGapToTop > Math.max(48, horizontalDistance * 0.2))
        );
      const switchTopEntry = sourceType === "switch"
        && Math.abs(verticalOffset) > Math.max(56, target.height * 0.6);
      const movingLeft = startX > targetCenterX;
      const leftwardTopEntry = movingLeft
        && target.shape !== "rect"
        && sourceCenterY <= targetY - 12;
      let endX = targetX;
      let endY = targetCenterY;
      let endSide = "left";
      if (
        (sourceType === "if" && ifTopEntry)
        || switchTopEntry
        || (sourceType !== "if" && sourceClearlyAbove)
        || leftwardTopEntry
      ) {
        endX = targetCenterX;
        endY = targetY;
        endSide = "top";
      } else {
        endY = targetUpperLeftY;
        if (target.shape === "circle") {
          const radius = target.width / 2;
          const yOffset = endY - targetCenterY;
          const xOffset = Math.sqrt(Math.max(0, radius * radius - yOffset * yOffset));
          endX = targetCenterX - xOffset;
        } else if (target.shape === "diamond") {
          const halfWidth = target.width / 2;
          const halfHeight = target.height / 2;
          const yOffset = Math.abs(endY - targetCenterY);
          const normalizedYOffset = Math.min(1, yOffset / halfHeight);
          endX = targetCenterX - halfWidth * (1 - normalizedYOffset);
        }
      }

      return {
        startX,
        startY,
        endX,
        endY,
        endSide,
      };
    }
    function relationshipSet(blockId) {
      const related = new Set();
      if (!blockId) return related;
      related.add(blockId);
      for (const edge of incomingMap.get(blockId) || []) related.add(edge.source_block_id);
      for (const edge of outgoingMap.get(blockId) || []) related.add(edge.target_block_id);
      return related;
    }
    function edgeRelationshipSet(edgeKeyValue) {
      const related = new Set();
      const edge = edgeMap.get(edgeKeyValue);
      if (!edge) return related;
      related.add(edge.source_block_id);
      related.add(edge.target_block_id);
      return related;
    }
    function edgeSearchText(edge) {
      const parts = [edge.source_exit_title || "", edge.source_exit_condition || ""];
      if (Array.isArray(edge.source_exit_properties)) {
        for (const property of edge.source_exit_properties) {
          parts.push(property.name || "");
          for (const group of property.groups || []) {
            for (const [name, value] of Object.entries(group || {})) {
              parts.push(name);
              if (value) parts.push(String(value));
            }
          }
        }
      }
      return parts.join(" ").toLowerCase();
    }
    function edgeMatchesQuery(edge, q) {
      if (!q) return true;
      const source = nodeMap.get(edge.source_block_id);
      const target = nodeMap.get(edge.target_block_id);
      return Boolean(
        (source && source.search_text.includes(q))
        || (target && target.search_text.includes(q))
        || edgeSearchText(edge).includes(q)
      );
    }
    function groupEntries(group) {
      const params = group && typeof group === "object" && "params" in group ? group.params : group;
      if (!params || typeof params !== "object") return [];
      return Object.entries(params);
    }
    function wrapLines(value, maxChars, maxLines) {
      const text = String(value || "").trim();
      if (!text) return [];
      const words = text.split(/\\s+/);
      const lines = [];
      let current = "";
      for (const word of words) {
        if (word.length > maxChars) {
          if (current) {
            lines.push(current);
            current = "";
            if (lines.length === maxLines) break;
          }
          const truncated = `${word.slice(0, Math.max(0, maxChars - 3))}...`;
          lines.push(truncated);
          if (lines.length === maxLines) break;
          continue;
        }
        const candidate = current ? `${current} ${word}` : word;
        if (candidate.length <= maxChars) {
          current = candidate;
        } else {
          if (current) lines.push(current);
          current = word;
          if (lines.length === maxLines - 1) break;
        }
      }
      if (lines.length < maxLines && current) lines.push(current);
      if (lines.length === maxLines && text.length > lines.join(" ").length) {
        lines[maxLines - 1] = `${lines[maxLines - 1].slice(0, Math.max(0, maxChars - 4)).trimEnd()} ...`;
      }
      return lines;
    }
    function truncateText(value, maxChars) {
      const text = String(value || "").trim();
      if (!text) return "";
      if (text.length <= maxChars) return text;
      return `${text.slice(0, Math.max(0, maxChars - 3)).trimEnd()}...`;
    }
    function findProperty(node, name) {
      return (node.properties || []).find((property) => (property.name || "").toLowerCase() === name.toLowerCase()) || null;
    }
    function firstGroupParams(property) {
      if (!property || !property.groups || !property.groups.length) return null;
      const first = property.groups[0];
      if (!first || typeof first !== "object") return null;
      return "params" in first ? first.params : first;
    }
    function findQuickAction(node) {
      const quickActionProperty = findProperty(node, "QuickAction");
      const params = firstGroupParams(quickActionProperty);
      const qaid = params && params.QAID ? String(params.QAID).toLowerCase() : "";
      return qaid ? (quickActionMap.get(qaid) || null) : null;
    }
    function renderIfSummary(node) {
      const logical = firstGroupParams(findProperty(node, "logicaloperator"));
      const conditionsProperty = findProperty(node, "conditions");
      const groups = conditionsProperty && conditionsProperty.groups ? conditionsProperty.groups : [];
      const rows = groups.map((group) => {
        const params = group && typeof group === "object"
          ? ("params" in group ? group.params : group)
          : {};
        return `
          <tr>
            <td>${formatValue(params.field)}</td>
            <td>${formatValue(params.operator)}</td>
            <td>${formatValue(params.value)}</td>
          </tr>
        `;
      }).join("");
      return `
        <section class="section">
          <h3>Condition Logic</h3>
          <div class="grid">
            <div class="card"><span class="label">Operator</span><div>${formatValue(logical ? logical.cond : null)}</div></div>
            <div class="card"><span class="label">Conditions</span><div>${groups.length}</div></div>
          </div>
          ${groups.length ? `<div class="table-wrap"><table><thead><tr><th>Field</th><th>Operator</th><th>Value</th></tr></thead><tbody>${rows}</tbody></table></div>` : '<p class="empty">No conditions were parsed.</p>'}
        </section>
      `;
    }
    function formatDurationParts(params) {
      if (!params) return null;
      const parts = [];
      const days = firstMeaningfulValue(params, ["timeoutdays"]);
      const hours = firstMeaningfulValue(params, ["timeouthours"]);
      const minutes = firstMeaningfulValue(params, ["timeoutminutes"]);
      const seconds = firstMeaningfulValue(params, ["timeoutseconds"]);
      if (days) parts.push(`${days} day(s)`);
      if (hours) parts.push(`${hours} hour(s)`);
      if (minutes) parts.push(`${minutes} minute(s)`);
      if (seconds) parts.push(`${seconds} second(s)`);
      return parts.length ? parts.join(", ") : null;
    }
    function renderWaitSummary(node) {
      const timeoutProperty = findProperty(node, "timeout");
      const timeoutGroups = timeoutProperty && timeoutProperty.groups ? timeoutProperty.groups.map((group) => ("params" in group ? group.params : group)) : [];
      const fieldGroups = timeoutGroups.filter((params) => firstMeaningfulValue(params, ["timeoutfield"]));
      const durationGroups = timeoutGroups.filter((params) => formatDurationParts(params));
      const logical = firstGroupParams(findProperty(node, "logicaloperator"));
      const conditionsProperty = findProperty(node, "conditions");
      const conditionGroups = conditionsProperty && conditionsProperty.groups ? conditionsProperty.groups : [];
      const conditionRows = conditionGroups.map((group) => {
        const params = group && typeof group === "object"
          ? ("params" in group ? group.params : group)
          : {};
        return `
          <tr>
            <td>${formatValue(params.field)}</td>
            <td>${formatValue(params.operator)}</td>
            <td>${formatValue(params.value)}</td>
          </tr>
        `;
      }).join("");
      return `
        <section class="section">
          <h3>Wait Summary</h3>
          <div class="grid">
            <div class="card"><span class="label">Wait Fields</span><div>${fieldGroups.length}</div></div>
            <div class="card"><span class="label">Durations</span><div>${durationGroups.length}</div></div>
            <div class="card"><span class="label">Condition Operator</span><div>${formatValue(logical ? logical.cond : null)}</div></div>
            <div class="card"><span class="label">Conditions</span><div>${conditionGroups.length}</div></div>
          </div>
          <section class="section">
            <h3>Wait Timing</h3>
            ${timeoutGroups.length ? `<div class="table-wrap"><table><thead><tr><th>Mode</th><th>Field</th><th>Duration</th></tr></thead><tbody>
              ${timeoutGroups.map((params) => `
                <tr>
                  <td>${formatValue(firstMeaningfulValue(params, ["isfield"]))}</td>
                  <td>${formatValue(firstMeaningfulValue(params, ["timeoutfield"]))}</td>
                  <td>${formatValue(formatDurationParts(params))}</td>
                </tr>
              `).join("")}
            </tbody></table></div>` : '<p class="empty">No wait timing data was parsed.</p>'}
          </section>
          <section class="section">
            <h3>Wait Conditions</h3>
            ${conditionGroups.length ? `<div class="table-wrap"><table><thead><tr><th>Field</th><th>Operator</th><th>Value</th></tr></thead><tbody>${conditionRows}</tbody></table></div>` : '<p class="empty">No wait conditions were parsed.</p>'}
          </section>
        </section>
      `;
    }
    function renderVoteSummary(node) {
      const summaryProperty = findProperty(node, "summaryblock");
      const summaryGroups = summaryProperty && summaryProperty.groups ? summaryProperty.groups.map((group) => ("params" in group ? group.params : group)) : [];
      const approversProperty = findProperty(node, "approvers");
      const approverSourceGroups = approversProperty && approversProperty.groups ? approversProperty.groups.map((group) => ("params" in group ? group.params : group)) : [];
      const groupFromFieldProperty = findProperty(node, "isgroupfromfield");
      const groupFromFieldGroups = groupFromFieldProperty && groupFromFieldProperty.groups ? groupFromFieldProperty.groups.map((group) => ("params" in group ? group.params : group)) : [];
      const groupFromProfileProperty = findProperty(node, "isgroupfromprofile");
      const groupFromProfileGroups = groupFromProfileProperty && groupFromProfileProperty.groups ? groupFromProfileProperty.groups.map((group) => ("params" in group ? group.params : group)) : [];
      const approverBlockProperty = findProperty(node, "approver_block");
      const approverBlockGroups = approverBlockProperty && approverBlockProperty.groups ? approverBlockProperty.groups.map((group) => ("params" in group ? group.params : group)) : [];
      const requestorProperty = findProperty(node, "requestor_block");
      const requestorGroups = requestorProperty && requestorProperty.groups ? requestorProperty.groups.map((group) => ("params" in group ? group.params : group)) : [];
      const soleApproverProperty = findProperty(node, "soleapproverblock");
      const soleApproverGroups = soleApproverProperty && soleApproverProperty.groups ? soleApproverProperty.groups.map((group) => ("params" in group ? group.params : group)) : [];
      const noRuleProperty = findProperty(node, "noapproverrules");
      const noRuleGroups = noRuleProperty && noRuleProperty.groups ? noRuleProperty.groups.map((group) => ("params" in group ? group.params : group)) : [];
      const dueDateProperty = findProperty(node, "duedate");
      const dueDateGroups = dueDateProperty && dueDateProperty.groups ? dueDateProperty.groups.map((group) => ("params" in group ? group.params : group)) : [];
      const hopProperty = findProperty(node, "hop");
      const hopGroups = hopProperty && hopProperty.groups ? hopProperty.groups.map((group) => ("params" in group ? group.params : group)) : [];
      const approvalRulesProperty = findProperty(node, "approverules");
      const approvalRuleGroups = approvalRulesProperty && approvalRulesProperty.groups ? approvalRulesProperty.groups.map((group) => ("params" in group ? group.params : group)) : [];
      const notificationProperty = findProperty(node, "notificationblock");
      const notificationGroups = notificationProperty && notificationProperty.groups ? notificationProperty.groups.map((group) => ("params" in group ? group.params : group)) : [];

      const summaryRows = summaryGroups.filter((params) => hasMeaningfulValue(params.summary) || hasMeaningfulValue(params.relationtoapproval)).map((params) => `
        <tr>
          <td>${formatValue(params.summary)}</td>
          <td>${formatValue(params.relationtoapproval)}</td>
        </tr>
      `).join("");
      const approverSources = [
        ...approverSourceGroups.map((params) => ({
          source: "Contact Group",
          selector: params.is,
          value: params.contactgroup,
        })),
        ...groupFromFieldGroups.map((params) => ({
          source: "Group From Field",
          selector: params.is,
          value: params.groupfromfield,
        })),
        ...groupFromProfileGroups.map((params) => ({
          source: "Group From Profile",
          selector: params.is,
          value: params.groupfromprofile,
        })),
        ...approverBlockGroups.map((params) => ({
          source: "Approver Block",
          selector: params.is,
          value: params.approver || params.approverfilter,
        })),
      ].filter((item) => hasMeaningfulValue(item.value) || hasMeaningfulValue(item.selector));
      const activeApproverSources = approverSources.filter((item) => isActiveSelection(item.selector));
      const approverRows = activeApproverSources.map((item) => `
        <tr><td>${formatValue(item.source)}</td><td>${formatValue(item.selector)}</td><td>${formatValue(item.value)}</td></tr>
      `).join("");
      const requestorSources = requestorGroups.map((params) => ({
        selector: params.is,
        value: params.requestor,
      })).filter((item) => hasMeaningfulValue(item.value) || hasMeaningfulValue(item.selector));
      const activeRequestorSources = requestorSources.filter((item) => isActiveSelection(item.selector));
      const requestorRows = activeRequestorSources.map((item) => `
        <tr>
          <td>${formatValue(item.selector)}</td>
          <td>${formatValue(item.value)}</td>
        </tr>
      `).join("");
      const ruleRows = approvalRuleGroups.filter((params) => Object.values(params || {}).some((value) => hasMeaningfulValue(value))).map((params) => `
        <tr>
          <td>${formatValue(params.approvalcheck)}</td>
          <td>${formatValue(params.approvalselect)}</td>
          <td>${formatValue(params.approvalnumber)}</td>
          <td>${formatValue(params.denialcheck)}</td>
          <td>${formatValue(params.denialselect)}</td>
          <td>${formatValue(params.denialnumber)}</td>
        </tr>
      `).join("");
      const notificationRows = notificationGroups.filter((params) => Object.values(params || {}).some((value) => hasMeaningfulValue(value))).map((params) => `
        <tr>
          <td>${formatValue(params.notificationqa)}</td>
          <td>${formatValue(params.approvalqa)}</td>
          <td>${formatValue(params.denialqa)}</td>
          <td>${formatValue(params.timeoutqa)}</td>
        </tr>
      `).join("");

      const dueDateSummary = dueDateGroups.map((params) => {
        const parts = [];
        if (hasMeaningfulValue(params.duedatedays)) parts.push(`${params.duedatedays} day(s)`);
        if (hasMeaningfulValue(params.duedatehours)) parts.push(`${params.duedatehours} hour(s)`);
        if (hasMeaningfulValue(params.duedateminutes)) parts.push(`${params.duedateminutes} minute(s)`);
        return parts.join(", ");
      }).filter((value) => hasMeaningfulValue(value));

      return `
        <section class="section">
          <h3>Approval Summary</h3>
          <div class="grid">
            <div class="card"><span class="label">Summary Entries</span><div>${summaryGroups.length}</div></div>
            <div class="card"><span class="label">Approver Sources</span><div>${activeApproverSources.length}</div></div>
            <div class="card"><span class="label">Requestor Sources</span><div>${activeRequestorSources.length}</div></div>
            <div class="card"><span class="label">Due Date</span><div>${formatValue(dueDateSummary.join("; "))}</div></div>
            <div class="card"><span class="label">Hop</span><div>${formatValue(hopGroups.map((params) => params.hopselect).filter((value) => hasMeaningfulValue(value)).join(", "))}</div></div>
            <div class="card"><span class="label">No Approver Rule</span><div>${formatValue(noRuleGroups.map((params) => params.norule).filter((value) => hasMeaningfulValue(value)).join(", "))}</div></div>
            <div class="card"><span class="label">Sole Approver</span><div>${formatValue(soleApproverGroups.map((params) => params.soleapprover || params.requestorfield).filter((value) => hasMeaningfulValue(value)).join(", "))}</div></div>
            <div class="card"><span class="label">Notification References</span><div>${notificationGroups.filter((params) => Object.values(params || {}).some((value) => hasMeaningfulValue(value))).length}</div></div>
          </div>
          <section class="section">
            <h3>Summary</h3>
            ${summaryRows ? `<div class="table-wrap"><table><thead><tr><th>Summary</th><th>Relation To Approval</th></tr></thead><tbody>${summaryRows}</tbody></table></div>` : '<p class="empty">No approval summary values were parsed.</p>'}
          </section>
          <section class="section">
            <h3>Approver Sources</h3>
            ${approverRows ? `<div class="table-wrap"><table><thead><tr><th>Source</th><th>Selected</th><th>Value</th></tr></thead><tbody>${approverRows}</tbody></table></div>` : '<p class="empty">No active approver source was parsed.</p>'}
          </section>
          <section class="section">
            <h3>Requestor Sources</h3>
            ${requestorRows ? `<div class="table-wrap"><table><thead><tr><th>Selected</th><th>Value</th></tr></thead><tbody>${requestorRows}</tbody></table></div>` : '<p class="empty">No active requestor source was parsed.</p>'}
          </section>
          <section class="section">
            <h3>Approval Rules</h3>
            ${ruleRows ? `<div class="table-wrap"><table><thead><tr><th>Approval Check</th><th>Approval Select</th><th>Approval Number</th><th>Denial Check</th><th>Denial Select</th><th>Denial Number</th></tr></thead><tbody>${ruleRows}</tbody></table></div>` : '<p class="empty">No approval rules were parsed.</p>'}
          </section>
          <section class="section">
            <h3>Notification References</h3>
            ${notificationRows ? `<div class="table-wrap"><table><thead><tr><th>Notification QA</th><th>Approval QA</th><th>Denial QA</th><th>Timeout QA</th></tr></thead><tbody>${notificationRows}</tbody></table></div>` : '<p class="empty">No notification references were parsed.</p>'}
          </section>
        </section>
      `;
    }
    function activeGroup(groups, selectorKey = "is") {
      return (groups || []).find((params) => isActiveSelection(params && params[selectorKey])) || null;
    }
    function renderArchiveForSearchSummary(node) {
      const searchGroups = (findProperty(node, "search_prop")?.groups || []).map((group) => ("params" in group ? group.params : group));
      const rows = searchGroups.filter((params) => hasMeaningfulValue(params.BOType) || hasMeaningfulValue(params.search)).map((params) => `
        <tr><td>${formatValue(params.BOType)}</td><td>${formatValue(params.search)}</td></tr>
      `).join("");
      return `
        <section class="section">
          <h3>Archive Search Summary</h3>
          ${rows ? `<div class="table-wrap"><table><thead><tr><th>Business Object</th><th>Search Id</th></tr></thead><tbody>${rows}</tbody></table></div>` : '<p class="empty">No archive search settings were parsed.</p>'}
        </section>
      `;
    }
    function renderInvokeForChildSummary(node) {
      const relationship = firstGroupParams(findProperty(node, "object_prop"));
      const workflow = firstGroupParams(findProperty(node, "workflow_prop"));
      const logical = firstGroupParams(findProperty(node, "logicaloperator"));
      const conditionGroups = findProperty(node, "conditions")?.groups || [];
      const conditionRows = conditionGroups.map((group) => {
        const params = "params" in group ? group.params : group;
        return `<tr><td>${formatValue(params.field)}</td><td>${formatValue(params.operator)}</td><td>${formatValue(params.value)}</td></tr>`;
      }).join("");
      return `
        <section class="section">
          <h3>Invoke Child Workflow</h3>
          <div class="grid">
            <div class="card"><span class="label">Relationship</span><div>${formatValue(relationship ? relationship.relationship : null)}</div></div>
            <div class="card"><span class="label">Workflow</span><div>${formatValue(workflow ? workflow.workflow : null)}</div></div>
            <div class="card"><span class="label">Condition Operator</span><div>${formatValue(logical ? logical.cond : null)}</div></div>
            <div class="card"><span class="label">Conditions</span><div>${conditionGroups.length}</div></div>
          </div>
          ${conditionRows ? `<div class="table-wrap"><table><thead><tr><th>Field</th><th>Operator</th><th>Value</th></tr></thead><tbody>${conditionRows}</tbody></table></div>` : '<p class="empty">No invoke conditions were parsed.</p>'}
        </section>
      `;
    }
    function renderInvokeWorkflowSummary(node) {
      const objectGroups = (findProperty(node, "object_prop")?.groups || []).map((group) => ("params" in group ? group.params : group));
      const activeObject = activeGroup(objectGroups) || objectGroups.find((params) => hasMeaningfulValue(params.contextobject) || hasMeaningfulValue(params.relationship)) || null;
      const workflow = firstGroupParams(findProperty(node, "workflow_prop"));
      return `
        <section class="section">
          <h3>Invoke Workflow</h3>
          <div class="grid">
            <div class="card"><span class="label">Context Object</span><div>${formatValue(activeObject ? activeObject.contextobject : null)}</div></div>
            <div class="card"><span class="label">Relationship</span><div>${formatValue(activeObject ? activeObject.relationship : null)}</div></div>
            <div class="card"><span class="label">Workflow</span><div>${formatValue(workflow ? workflow.workflow : null)}</div></div>
            <div class="card"><span class="label">Wait For Completion</span><div>${formatValue(workflow ? workflow.waitforcompletion : null)}</div></div>
          </div>
        </section>
      `;
    }
    function renderMultichildSummary(node) {
      const selectionGroups = (findProperty(node, "selection")?.groups || []).map((group) => ("params" in group ? group.params : group));
      const activeSelection = activeGroup(selectionGroups, "selected") || selectionGroups.find((params) => hasMeaningfulValue(params.SRTParamField) || hasMeaningfulValue(params.ObjRelationField)) || null;
      return `
        <section class="section">
          <h3>Multi Child Selection</h3>
          <div class="grid">
            <div class="card"><span class="label">Selected Mode</span><div>${formatValue(activeSelection ? activeSelection.selected : null)}</div></div>
            <div class="card"><span class="label">SRT Param Field</span><div>${formatValue(activeSelection ? activeSelection.SRTParamField : null)}</div></div>
            <div class="card"><span class="label">Object Relation Field</span><div>${formatValue(activeSelection ? activeSelection.ObjRelationField : null)}</div></div>
          </div>
        </section>
      `;
    }
    function renderRunForChildSummary(node) {
      const relationship = firstGroupParams(findProperty(node, "relationship_prop"));
      const action = firstGroupParams(findProperty(node, "action"));
      const logical = firstGroupParams(findProperty(node, "logicaloperator"));
      const conditionGroups = findProperty(node, "conditions")?.groups || [];
      const conditionRows = conditionGroups.map((group) => {
        const params = "params" in group ? group.params : group;
        return `<tr><td>${formatValue(params.field)}</td><td>${formatValue(params.operator)}</td><td>${formatValue(params.value)}</td></tr>`;
      }).join("");
      return `
        <section class="section">
          <h3>Run For Child</h3>
          <div class="grid">
            <div class="card"><span class="label">Relationship</span><div>${formatValue(relationship ? relationship.relationship : null)}</div></div>
            <div class="card"><span class="label">Action Quick Action</span><div>${formatValue(action ? action.quickaction : null)}</div></div>
            <div class="card"><span class="label">Condition Operator</span><div>${formatValue(logical ? logical.cond : null)}</div></div>
            <div class="card"><span class="label">Conditions</span><div>${conditionGroups.length}</div></div>
          </div>
          ${conditionRows ? `<div class="table-wrap"><table><thead><tr><th>Field</th><th>Operator</th><th>Value</th></tr></thead><tbody>${conditionRows}</tbody></table></div>` : '<p class="empty">No run conditions were parsed.</p>'}
        </section>
      `;
    }
    function renderRunForSearchSummary(node) {
      const search = firstGroupParams(findProperty(node, "search_prop"));
      const actionGroups = (findProperty(node, "action")?.groups || []).map((group) => ("params" in group ? group.params : group));
      const activeAction = activeGroup(actionGroups, "run") || actionGroups.find((params) => hasMeaningfulValue(params.quickaction) || hasMeaningfulValue(params.workflow)) || null;
      return `
        <section class="section">
          <h3>Run For Search</h3>
          <div class="grid">
            <div class="card"><span class="label">Search Id</span><div>${formatValue(search ? search.search : null)}</div></div>
            <div class="card"><span class="label">Selected Action</span><div>${formatValue(activeAction ? activeAction.run : null)}</div></div>
            <div class="card"><span class="label">Quick Action</span><div>${formatValue(activeAction ? activeAction.quickaction : null)}</div></div>
            <div class="card"><span class="label">Workflow</span><div>${formatValue(activeAction ? activeAction.workflow : null)}</div></div>
          </div>
        </section>
      `;
    }
    function renderWaitForChildSummary(node) {
      const relationship = firstGroupParams(findProperty(node, "relationship_prop"));
      const count = firstGroupParams(findProperty(node, "children_count_block"));
      const timeoutProperty = findProperty(node, "timeout");
      const timeoutGroups = timeoutProperty && timeoutProperty.groups ? timeoutProperty.groups.map((group) => ("params" in group ? group.params : group)) : [];
      const logical = firstGroupParams(findProperty(node, "logicaloperator"));
      const conditionGroups = findProperty(node, "conditions")?.groups || [];
      const conditionRows = conditionGroups.map((group) => {
        const params = "params" in group ? group.params : group;
        return `<tr><td>${formatValue(params.field)}</td><td>${formatValue(params.operator)}</td><td>${formatValue(params.value)}</td></tr>`;
      }).join("");
      return `
        <section class="section">
          <h3>Wait For Child</h3>
          <div class="grid">
            <div class="card"><span class="label">Relationship</span><div>${formatValue(relationship ? relationship.relationship : null)}</div></div>
            <div class="card"><span class="label">Children Count Mode</span><div>${formatValue(count ? count.children_count_switch : null)}</div></div>
            <div class="card"><span class="label">Children Count</span><div>${formatValue(count ? count.children_count : null)}</div></div>
            <div class="card"><span class="label">Condition Operator</span><div>${formatValue(logical ? logical.cond : null)}</div></div>
          </div>
          <section class="section">
            <h3>Wait Timing</h3>
            ${timeoutGroups.length ? `<div class="table-wrap"><table><thead><tr><th>Mode</th><th>Field</th><th>Duration</th></tr></thead><tbody>
              ${timeoutGroups.map((params) => `
                <tr>
                  <td>${formatValue(firstMeaningfulValue(params, ["isfield"]))}</td>
                  <td>${formatValue(firstMeaningfulValue(params, ["timeoutfield"]))}</td>
                  <td>${formatValue(formatDurationParts(params))}</td>
                </tr>
              `).join("")}
            </tbody></table></div>` : '<p class="empty">No wait timing data was parsed.</p>'}
          </section>
          <section class="section">
            <h3>Wait Conditions</h3>
            ${conditionRows ? `<div class="table-wrap"><table><thead><tr><th>Field</th><th>Operator</th><th>Value</th></tr></thead><tbody>${conditionRows}</tbody></table></div>` : '<p class="empty">No wait conditions were parsed.</p>'}
          </section>
        </section>
      `;
    }
    function renderWaitForEventSummary(node) {
      const timeoutGroups = (findProperty(node, "timeout")?.groups || []).map((group) => ("params" in group ? group.params : group));
      const activeTimeout = activeGroup(timeoutGroups, "isfield") || timeoutGroups.find((params) => Object.values(params || {}).some((value) => hasMeaningfulValue(value))) || null;
      const objectEvent = firstGroupParams(findProperty(node, "ObjectEvent"));
      const fieldEventGroups = (findProperty(node, "fieldEvent")?.groups || []).map((group) => ("params" in group ? group.params : group));
      const relationshipEventGroups = (findProperty(node, "relationshipEvent")?.groups || []).map((group) => ("params" in group ? group.params : group));
      const activeFieldEvent = activeGroup(fieldEventGroups, "isChanged") || fieldEventGroups.find((params) => hasMeaningfulValue(params.fieldEvent) || hasMeaningfulValue(params.field)) || null;
      const activeRelationshipEvent = activeGroup(relationshipEventGroups, "onlinkRelEvent") || relationshipEventGroups.find((params) => hasMeaningfulValue(params.onlinkRelEvent) || hasMeaningfulValue(params.relField)) || null;
      return `
        <section class="section">
          <h3>Wait For Event</h3>
          <div class="grid">
            <div class="card"><span class="label">Timeout Mode</span><div>${formatValue(activeTimeout ? (activeTimeout.isfield || activeTimeout.type) : null)}</div></div>
            <div class="card"><span class="label">Timeout Field</span><div>${formatValue(activeTimeout ? (activeTimeout.timeoutfield || activeTimeout.field1) : null)}</div></div>
            <div class="card"><span class="label">Timeout Duration</span><div>${formatValue(formatDurationParts(activeTimeout) || (activeTimeout && activeTimeout.timedays ? `${activeTimeout.timedays} ${activeTimeout.type || ""}` : null))}</div></div>
            <div class="card"><span class="label">Object Event</span><div>${formatValue(objectEvent ? objectEvent.objectEventRadio : null)}</div></div>
            <div class="card"><span class="label">Field Event</span><div>${formatValue(activeFieldEvent ? (activeFieldEvent.fieldEvent || activeFieldEvent.isChanged) : null)}</div></div>
            <div class="card"><span class="label">Field</span><div>${formatValue(activeFieldEvent ? (activeFieldEvent.field || activeFieldEvent.fields || activeFieldEvent.isChangedfromto) : null)}</div></div>
            <div class="card"><span class="label">Relationship Event</span><div>${formatValue(activeRelationshipEvent ? activeRelationshipEvent.onlinkRelEvent : null)}</div></div>
            <div class="card"><span class="label">Relationship</span><div>${formatValue(activeRelationshipEvent ? activeRelationshipEvent.relField : null)}</div></div>
          </div>
        </section>
      `;
    }
    function renderTemplateSummary(node) {
      const templateLink = firstGroupParams(findProperty(node, "TemplateLink"));
      const templateLinkId = firstGroupParams(findProperty(node, "TemplateLinkId"));
      const templateLinkRelations = firstGroupParams(findProperty(node, "TemplateLinkRelations"));
      const objRelations = firstGroupParams(findProperty(node, "ObjRelations"));
      const ciComputer = firstGroupParams(findProperty(node, "CIComputer"));
      const mappingGroups = (findProperty(node, "TemplateMapping")?.groups || []).map((group) => ("params" in group ? group.params : group));
      const mappingRows = mappingGroups.filter((params) => Object.values(params || {}).some((value) => hasMeaningfulValue(value))).map((params) => `
        <tr><td>${formatValue(Object.keys(params).join(", "))}</td><td>${formatValue(Object.values(params).filter((value) => hasMeaningfulValue(value)).join(", "))}</td></tr>
      `).join("");
      return `
        <section class="section">
          <h3>Template Summary</h3>
          <div class="grid">
            <div class="card"><span class="label">Link Field</span><div>${formatValue(templateLink ? templateLink.linkField : null)}</div></div>
            <div class="card"><span class="label">Link Id Field</span><div>${formatValue(templateLinkId ? templateLinkId.idField : null)}</div></div>
            <div class="card"><span class="label">Link Relations Field</span><div>${formatValue(templateLinkRelations ? templateLinkRelations.relField : null)}</div></div>
            <div class="card"><span class="label">Object Relation</span><div>${formatValue(objRelations ? objRelations.objRelField : null)}</div></div>
            <div class="card"><span class="label">CI Field</span><div>${formatValue(ciComputer ? ciComputer.ciField : null)}</div></div>
            <div class="card"><span class="label">Mapping Groups</span><div>${mappingGroups.length}</div></div>
          </div>
          ${mappingRows ? `<div class="table-wrap"><table><thead><tr><th>Mapping Keys</th><th>Values</th></tr></thead><tbody>${mappingRows}</tbody></table></div>` : '<p class="empty">No template mappings were parsed.</p>'}
        </section>
      `;
    }
    function renderSwitchSummary(node) {
      const descriptionProperty = firstGroupParams(findProperty(node, "description"));
      const descriptionText = descriptionProperty ? descriptionProperty.descriptionText : null;
      const exits = Array.isArray(node.exits) ? node.exits : [];
      const exitSections = exits.map((exitItem) => {
        const exitLabel = exitItem.title || exitItem.condition || "(unlabelled)";
        const targets = Array.isArray(exitItem.target_block_ids) ? exitItem.target_block_ids.map((blockId) => nodeMap.get(blockId)).filter(Boolean) : [];
        const destinationSummary = targets.length
          ? targets.map((target) => shortLabel(target)).join(", ")
          : null;
        const destinationTypeSummary = targets.length
          ? targets.map((target) => target.block_type || "-").join(", ")
          : null;
        const exitProperties = Array.isArray(exitItem.properties) ? exitItem.properties : [];
        const logicalProperty = exitProperties.find((property) => (property.name || "").toLowerCase() === "logicaloperator");
        const conditionProperty = exitProperties.find((property) => (property.name || "").toLowerCase() === "conditions");
        const logicalGroups = logicalProperty && Array.isArray(logicalProperty.groups) ? logicalProperty.groups : [];
        const logicalValue = logicalGroups.map((group) => firstMeaningfulValue(group, Object.keys(group || {}))).find((value) => hasMeaningfulValue(value)) || null;
        const conditionGroups = conditionProperty && Array.isArray(conditionProperty.groups) ? conditionProperty.groups.filter((group) => Object.values(group || {}).some((value) => hasMeaningfulValue(value))) : [];
        const conditionRows = conditionGroups.map((group) => `
          <tr>
            <td>${formatValue(group.field)}</td>
            <td>${formatValue(group.operator)}</td>
            <td>${formatValue(group.value)}</td>
          </tr>
        `).join("");
        return `
          <section class="section">
            <h3>${highlightText(exitLabel)}</h3>
            <div class="grid">
              <div class="card"><span class="label">Destination</span><div>${formatValue(destinationSummary)}</div></div>
              <div class="card"><span class="label">Destination Type</span><div>${formatValue(destinationTypeSummary)}</div></div>
              <div class="card"><span class="label">Condition Logic</span><div>${formatValue(logicalValue)}</div></div>
              <div class="card"><span class="label">Conditions</span><div>${conditionGroups.length}</div></div>
            </div>
            ${conditionRows ? `<div class="table-wrap"><table><thead><tr><th>Field</th><th>Operator</th><th>Value</th></tr></thead><tbody>${conditionRows}</tbody></table></div>` : '<p class="empty">No exit conditions were parsed.</p>'}
          </section>
        `;
      }).join("");
      return `
        <section class="section">
          <h3>Switch Summary</h3>
          <div class="grid">
            <div class="card"><span class="label">Exit Options</span><div>${exits.length}</div></div>
            <div class="card"><span class="label">Description</span><div>${formatValue(descriptionText)}</div></div>
          </div>
          ${exitSections || '<p class="empty">No switch routes were parsed.</p>'}
        </section>
      `;
    }
    function renderExternalQuickActionReference(node) {
      const quickActionProperty = findProperty(node, "QuickAction");
      const params = firstGroupParams(quickActionProperty);
      const qaid = params && params.QAID ? params.QAID : null;
      if (!hasMeaningfulValue(qaid) || findQuickAction(node)) return "";
      return `
        <section class="section">
          <h3>Configured Action</h3>
          <div class="grid">
            <div class="card"><span class="label">Quick Action Reference</span><div>${formatValue(qaid)}</div></div>
            <div class="card"><span class="label">Definition</span><div><span class="empty">Not available in this workflow document</span></div></div>
          </div>
        </section>
      `;
    }
    function firstMeaningfulValue(params, keys) {
      if (!params) return null;
      for (const key of keys) {
        const value = params[key];
        if (value != null && value !== "") return value;
      }
      return null;
    }
    function formatDueDate(property) {
      if (!property || !property.groups || !property.groups.length) return null;
      const groups = property.groups.map((group) => ("params" in group ? group.params : group));
      for (const params of groups) {
        const field = firstMeaningfulValue(params, ["duedatefield"]);
        if (field) return `Field: ${field}`;
      }
      for (const params of groups) {
        const days = firstMeaningfulValue(params, ["duedatedays"]);
        const hours = firstMeaningfulValue(params, ["duedatehours"]);
        const minutes = firstMeaningfulValue(params, ["duedateminutes"]);
        if (days || hours || minutes) {
          const parts = [];
          if (days) parts.push(`${days} day(s)`);
          if (hours) parts.push(`${hours} hour(s)`);
          if (minutes) parts.push(`${minutes} minute(s)`);
          return parts.join(", ");
        }
      }
      return null;
    }
    function renderTaskSummary(node) {
      const summary = firstGroupParams(findProperty(node, "summaryblock"));
      const details = firstGroupParams(findProperty(node, "detailsblock"));
      const team = firstGroupParams(findProperty(node, "teamblock"));
      const assignee = firstGroupParams(findProperty(node, "assigneeblock"));
      const type = firstGroupParams(findProperty(node, "typeblock"));
      const priority = firstGroupParams(findProperty(node, "priorityblock"));
      const dueDate = formatDueDate(findProperty(node, "duedate"));
      return `
        <section class="section">
          <h3>Task Summary</h3>
          <div class="grid">
            <div class="card"><span class="label">Summary</span><div>${formatValue(summary ? summary.summary : null)}</div></div>
            <div class="card"><span class="label">Details</span><div>${formatValue(details ? details.details : null)}</div></div>
            <div class="card"><span class="label">Team</span><div>${formatValue(team ? team.team : null)}</div></div>
            <div class="card"><span class="label">Assignee</span><div>${formatValue(assignee ? assignee.assignee : null)}</div></div>
            <div class="card"><span class="label">Type</span><div>${formatValue(type ? type.type : null)}</div></div>
            <div class="card"><span class="label">Priority</span><div>${formatValue(priority ? firstMeaningfulValue(priority, ["priority", "priorityfield"]) : null)}</div></div>
            <div class="card"><span class="label">Due Date</span><div>${formatValue(dueDate)}</div></div>
          </div>
        </section>
      `;
    }
    function configuredFieldValues(quickAction) {
      const definition = quickAction && quickAction.definition_json;
      const fieldValues = definition && Array.isArray(definition.FieldValues) ? definition.FieldValues : [];
      return fieldValues.filter((item) => {
        const expressionText = item.ExpressionText;
        return Boolean(expressionText) || Boolean(item.Overwrite);
      });
    }
    function hasMeaningfulValue(value) {
      if (value == null) return false;
      if (typeof value === "string") return value.trim() !== "";
      if (Array.isArray(value)) return value.length > 0;
      if (typeof value === "object") return Object.values(value).some((item) => hasMeaningfulValue(item));
      return true;
    }
    function isActiveSelection(value) {
      if (!hasMeaningfulValue(value)) return false;
      const normalized = String(value).trim().toLowerCase();
      return !["_unchecked", "false", "no", "none", "0"].includes(normalized);
    }
    function renderRecipientValue(value) {
      if (!value || typeof value !== "object") return null;
      const parts = [];
      const pushPart = (label, items) => {
        if (Array.isArray(items) && items.length) {
          parts.push(`<div><strong>${highlightText(label)}:</strong> ${highlightText(items.join(", "))}</div>`);
        }
      };
      pushPart("Fields", value.Fields);
      pushPart("Users", value.Users);
      pushPart("Teams", value.Teams);
      pushPart("Groups", value.Groups);
      pushPart("Expressions", value.Expressions);
      return parts.length ? parts.join("") : null;
    }
    function collectPlaceholderRefs(value) {
      const refs = [];
      const pattern = /\\$\\((\\d+)\\)/g;
      const text = String(value || "");
      let match;
      while ((match = pattern.exec(text)) !== null) {
        refs.push(Number(match[1]));
      }
      return refs;
    }
    function collectSendEmailExpressionUses(definition) {
      const uses = new Map();
      const addUse = (ref, label) => {
        if (!uses.has(ref)) uses.set(ref, []);
        const labels = uses.get(ref);
        if (!labels.includes(label)) labels.push(label);
      };
      for (const ref of collectPlaceholderRefs(definition.Subject)) addUse(ref, "Subject");
      for (const ref of collectPlaceholderRefs(definition.BodyText)) addUse(ref, "Body");
      for (const [label, recipient] of [["From", definition.From], ["To", definition.To], ["Cc", definition.Cc], ["Bcc", definition.Bcc]]) {
        const expressions = recipient && Array.isArray(recipient.Expressions) ? recipient.Expressions : [];
        for (const expression of expressions) {
          for (const ref of collectPlaceholderRefs(expression)) addUse(ref, label);
        }
      }
      return uses;
    }
    function renderSendEmailSummary(quickAction) {
      const definition = quickAction && quickAction.definition_json ? quickAction.definition_json : {};
      const expressionUses = collectSendEmailExpressionUses(definition);
      const expressionTexts = Array.isArray(definition.ExpressionsText)
        ? definition.ExpressionsText
            .filter((item) => hasMeaningfulValue(item))
            .map((item, index) => ({
              value: item,
              ref: `$(${index})`,
            }))
        : [];
      const bodyText = hasMeaningfulValue(definition.BodyText) ? definition.BodyText : null;
      const subject = hasMeaningfulValue(definition.Subject) ? definition.Subject : null;
      const rows = expressionTexts.map((item) => `
        <tr>
          <td>${formatValue(item.ref)}</td>
          <td>${formatValue((expressionUses.get(Number(item.ref.slice(2, -1))) || []).join(", "))}</td>
          <td>${formatValue(item.value)}</td>
        </tr>
      `).join("");
      return `
        <section class="section">
          <h3>Email Action</h3>
          <div class="grid">
            <div class="card"><span class="label">From</span><div>${renderRecipientValue(definition.From) || '<span class="empty">None</span>'}</div></div>
            <div class="card"><span class="label">To</span><div>${renderRecipientValue(definition.To) || '<span class="empty">None</span>'}</div></div>
            <div class="card"><span class="label">Cc</span><div>${renderRecipientValue(definition.Cc) || '<span class="empty">None</span>'}</div></div>
            <div class="card"><span class="label">Bcc</span><div>${renderRecipientValue(definition.Bcc) || '<span class="empty">None</span>'}</div></div>
            <div class="card"><span class="label">Subject</span><div>${formatValue(subject)}</div></div>
            <div class="card"><span class="label">Body</span><div>${formatValue(bodyText)}</div></div>
            <div class="card"><span class="label">Log Rule</span><div>${formatValue(definition.LogInJournalType)}</div></div>
            <div class="card"><span class="label">Include Attachments</span><div>${definition.IncludeAttachments ? "Yes" : "No"}</div></div>
          </div>
          ${expressionTexts.length ? `<div class="table-wrap"><table><thead><tr><th>Reference</th><th>Used In</th><th>Expression</th></tr></thead><tbody>${rows}</tbody></table></div>` : ""}
        </section>
      `;
    }
    function renderSearchAndLinkSummary(quickAction) {
      const definition = quickAction && quickAction.definition_json ? quickAction.definition_json : {};
      const searchQuery = Array.isArray(definition.SearchQuery)
        ? definition.SearchQuery.filter((item) => item && typeof item === "object")
        : [];
      const rows = searchQuery.map((item) => {
        const objectName = item.ObjectDisplay || item.ObjectId || null;
        const fieldName = item.FieldDisplay || item.FieldName || null;
        const condition = item.Condition || item.ConditionType || null;
        const value = item.FieldValueDisplay || item.FieldValue || null;
        const joinRule = item.JoinRule || null;
        return `
          <tr>
            <td>${formatValue(objectName)}</td>
            <td>${formatValue(fieldName)}</td>
            <td>${formatValue(condition)}</td>
            <td>${formatValue(value)}</td>
            <td>${formatValue(joinRule)}</td>
          </tr>
        `;
      }).join("");
      return `
        <section class="section">
          <h3>Search And Link Action</h3>
          <div class="grid">
            <div class="card"><span class="label">Table</span><div>${formatValue(definition.TableRef)}</div></div>
            <div class="card"><span class="label">Child Table</span><div>${formatValue(definition.ChildTableRef)}</div></div>
            <div class="card"><span class="label">Relationship Tag</span><div>${formatValue(definition.RelationshipTag)}</div></div>
            <div class="card"><span class="label">Conditions</span><div>${searchQuery.length}</div></div>
          </div>
          ${searchQuery.length ? `<div class="table-wrap"><table><thead><tr><th>Object</th><th>Field</th><th>Condition</th><th>Value</th><th>Join</th></tr></thead><tbody>${rows}</tbody></table></div>` : '<p class="empty">No search conditions were found.</p>'}
        </section>
      `;
    }
    function renderQuickActionSummary(node) {
      const quickAction = findQuickAction(node);
      if (!quickAction) return "";
      const actionType = String(quickAction.action_type || "").toLowerCase();
      if (actionType === "sendemail") {
        return `
          <section class="section">
            <h3>Configured Action</h3>
            <div class="grid">
              <div class="card"><span class="label">Quick Action</span><div>${formatValue(quickAction.name)}</div></div>
              <div class="card"><span class="label">Action Type</span><div>${formatValue(quickAction.action_type)}</div></div>
              <div class="card"><span class="label">Group</span><div>${formatValue(quickAction.group_name)}</div></div>
            </div>
          </section>
          ${renderSendEmailSummary(quickAction)}
        `;
      }
      if (actionType === "searchandlink") {
        return `
          <section class="section">
            <h3>Configured Action</h3>
            <div class="grid">
              <div class="card"><span class="label">Quick Action</span><div>${formatValue(quickAction.name)}</div></div>
              <div class="card"><span class="label">Action Type</span><div>${formatValue(quickAction.action_type)}</div></div>
              <div class="card"><span class="label">Group</span><div>${formatValue(quickAction.group_name)}</div></div>
            </div>
          </section>
          ${renderSearchAndLinkSummary(quickAction)}
        `;
      }
      const configured = configuredFieldValues(quickAction);
      const rows = configured.map((item) => `
        <tr>
          <td>${formatValue(item.FieldName)}</td>
          <td>${formatValue(item.ExpressionText || null)}</td>
          <td>${item.Overwrite ? "Yes" : "No"}</td>
        </tr>
      `).join("");
      return `
        <section class="section">
          <h3>Configured Action</h3>
          <div class="grid">
            <div class="card"><span class="label">Quick Action</span><div>${formatValue(quickAction.name)}</div></div>
            <div class="card"><span class="label">Action Type</span><div>${formatValue(quickAction.action_type)}</div></div>
            <div class="card"><span class="label">Group</span><div>${formatValue(quickAction.group_name)}</div></div>
            <div class="card"><span class="label">Configured Fields</span><div>${configured.length}</div></div>
          </div>
          ${configured.length ? `<div class="table-wrap"><table><thead><tr><th>Field</th><th>Value / Expression</th><th>Overwrite</th></tr></thead><tbody>${rows}</tbody></table></div>` : '<p class="empty">No configured field values were found for this quick action.</p>'}
        </section>
      `;
    }
    function renderAdvancedTaskSummary(node) {
      const taskItem = firstGroupParams(findProperty(node, "taskitemblock"));
      const taskCatalog = firstGroupParams(findProperty(node, "taskcatalogblock"));
      const service = firstGroupParams(findProperty(node, "serviceblock"));
      const team = firstGroupParams(findProperty(node, "teamblock"));
      const owner = firstGroupParams(findProperty(node, "ownerblock"));
      const relation = firstGroupParams(findProperty(node, "reltotaskblock"));
      const notification = firstGroupParams(findProperty(node, "notificationblock"));
      const dueDate = formatDueDate(findProperty(node, "duedate"));
      const quickActionMarkup = renderQuickActionSummary(node);
      return `
        <section class="section">
          <h3>Advanced Task Summary</h3>
          <div class="grid">
            <div class="card"><span class="label">Task Item</span><div>${formatValue(taskItem ? taskItem.taskitem : null)}</div></div>
            <div class="card"><span class="label">Task Catalog</span><div>${formatValue(taskCatalog ? taskCatalog.TaskCatalog : null)}</div></div>
            <div class="card"><span class="label">Service</span><div>${formatValue(service ? service.service : null)}</div></div>
            <div class="card"><span class="label">Team</span><div>${formatValue(team ? firstMeaningfulValue(team, ["team", "teamEx", "teamExc"]) : null)}</div></div>
            <div class="card"><span class="label">Owner</span><div>${formatValue(owner ? owner.owner : null)}</div></div>
            <div class="card"><span class="label">Relation to Task</span><div>${formatValue(relation ? firstMeaningfulValue(relation, ["relationtotask", "relationtotaskc"]) : null)}</div></div>
            <div class="card"><span class="label">Notification QA</span><div>${formatValue(notification ? firstMeaningfulValue(notification, ["notificationqa", "notificationqac"]) : null)}</div></div>
            <div class="card"><span class="label">Due Date</span><div>${formatValue(dueDate)}</div></div>
          </div>
        </section>
      `;
    }
    function renderRawProperties(node) {
      return node.properties.length ? `<div class="list">${node.properties.map((property) => `
        <article class="prop">
          <h3>${escapeHtml(property.name)}</h3>
          ${property.groups.length ? property.groups.map((group, index) => `
            <div class="group">
              <div class="small"><strong>Group ${index + 1}</strong></div>
              <div class="list">${groupEntries(group).map(([name, value]) => `
                <div class="param"><div class="param-name">${escapeHtml(name)}</div><div>${formatValue(value)}</div></div>
              `).join("")}</div>
            </div>
          `).join("") : '<p class="empty">No grouped parameters.</p>'}
        </article>
      `).join("")}</div>` : '<p class="empty">No block properties were parsed.</p>';
    }
    function renderPropertiesSection(node) {
      const type = (node.block_type || "").toLowerCase();
      let primaryMarkup = "";
      if (type === "if") {
        primaryMarkup = renderIfSummary(node);
      } else if (type === "wait") {
        primaryMarkup = renderWaitSummary(node);
      } else if (type === "archiveforsearch") {
        primaryMarkup = renderArchiveForSearchSummary(node);
      } else if (type === "invokeforchild") {
        primaryMarkup = renderInvokeForChildSummary(node);
      } else if (type === "invokeworkflow") {
        primaryMarkup = renderInvokeWorkflowSummary(node);
      } else if (type === "multichild") {
        primaryMarkup = renderMultichildSummary(node);
      } else if (type === "runforchild") {
        primaryMarkup = renderRunForChildSummary(node);
      } else if (type === "runforsearch") {
        primaryMarkup = renderRunForSearchSummary(node);
      } else if (type.startsWith("vote")) {
        primaryMarkup = renderVoteSummary(node);
      } else if (type === "waitforchild") {
        primaryMarkup = renderWaitForChildSummary(node);
      } else if (type === "waitforevent") {
        primaryMarkup = renderWaitForEventSummary(node);
      } else if (type === "template") {
        primaryMarkup = renderTemplateSummary(node);
      } else if (type === "switch") {
        primaryMarkup = renderSwitchSummary(node);
      } else if (type === "task") {
        primaryMarkup = renderTaskSummary(node);
      } else if (type === "advancedtask") {
        primaryMarkup = renderAdvancedTaskSummary(node);
      }
      const quickActionMarkup = renderQuickActionSummary(node) || renderExternalQuickActionReference(node);
      const rawMarkup = renderRawProperties(node);
      return `
        ${primaryMarkup}
        ${quickActionMarkup}
        <section class="section">
          <h3>Raw Properties</h3>
          <details>
            <summary>Show raw property groups</summary>
            <div class="details-body">${rawMarkup}</div>
          </details>
        </section>
      `;
    }
    function selectBlock(blockId) {
      selectedBlockId = blockId;
      selectedEdgeKey = null;
      render();
      centerOnSelection();
    }
    function selectEdge(edgeKeyValue) {
      selectedBlockId = null;
      selectedEdgeKey = edgeKeyValue;
      render();
      centerOnEdgeSelection();
    }
    function canvasContentOffsetX() {
      return canvasContent ? canvasContent.offsetLeft : 24;
    }
    function canvasContentOffsetY() {
      return canvasContent ? canvasContent.offsetTop : 24;
    }
    function toViewportBox(left, top, right, bottom) {
      const offsetX = canvasContentOffsetX();
      const offsetY = canvasContentOffsetY();
      return {
        left: left * canvasZoom + offsetX,
        top: top * canvasZoom + offsetY,
        right: right * canvasZoom + offsetX,
        bottom: bottom * canvasZoom + offsetY,
      };
    }
    function isBoxVisible(left, top, right, bottom, margin = 48) {
      const box = toViewportBox(left, top, right, bottom);
      const viewportLeft = canvasWrap.scrollLeft;
      const viewportTop = canvasWrap.scrollTop;
      const viewportRight = viewportLeft + canvasWrap.clientWidth;
      const viewportBottom = viewportTop + canvasWrap.clientHeight;
      return (
        box.left >= viewportLeft + margin
        && box.top >= viewportTop + margin
        && box.right <= viewportRight - margin
        && box.bottom <= viewportBottom - margin
      );
    }
    function scrollBoxToCenter(left, top, right, bottom) {
      const box = toViewportBox(left, top, right, bottom);
      canvasWrap.scrollTo({
        left: Math.max(0, box.left - canvasWrap.clientWidth / 2 + (box.right - box.left) / 2),
        top: Math.max(0, box.top - canvasWrap.clientHeight / 2 + (box.bottom - box.top) / 2),
        behavior: "smooth",
      });
    }
    function centerOnSelection() {
      if (!selectedBlockId) return;
      const node = nodeMap.get(selectedBlockId);
      if (!node) return;
      const left = effectiveDisplayX(node);
      const top = effectiveDisplayY(node);
      const right = left + node.width;
      const bottom = top + node.height;
      if (isBoxVisible(left, top, right, bottom)) return;
      scrollBoxToCenter(left, top, right, bottom);
    }
    function centerOnEdgeSelection() {
      if (!selectedEdgeKey) return;
      const edge = edgeMap.get(selectedEdgeKey);
      if (!edge) return;
      const source = nodeMap.get(edge.source_block_id);
      const target = nodeMap.get(edge.target_block_id);
      if (!source || !target) return;
      const sourceX = effectiveDisplayX(source);
      const sourceY = effectiveDisplayY(source);
      const targetX = effectiveDisplayX(target);
      const targetY = effectiveDisplayY(target);
      const left = Math.min(sourceX, targetX);
      const top = Math.min(sourceY, targetY);
      const right = Math.max(sourceX + source.width, targetX + target.width);
      const bottom = Math.max(sourceY + source.height, targetY + target.height);
      if (isBoxVisible(left, top, right, bottom)) return;
      scrollBoxToCenter(left, top, right, bottom);
    }
    function renderStats() {
      statsElement.innerHTML = data.summary.cards.map((card) => `
        <div class="stat"><span class="stat-label">${escapeHtml(card.label)}</span><div class="stat-value">${escapeHtml(card.value)}</div></div>
      `).join("");
      legendElement.innerHTML = data.summary.block_type_counts.map((item) => `
        <span class="chip"><span style="width:12px;height:12px;border-radius:999px;display:inline-block;background:${nodeColor(item.type)};border:1px solid rgba(20,32,51,.12)"></span><span>${escapeHtml(item.type || "(unknown)")} (${item.count})</span></span>
      `).join("");
    }
    function applyCanvasZoom() {
      if (!canvasSpacer || !canvasContent) return;
      canvasContent.style.transform = `translateZ(0) scale(${canvasZoom})`;
      const scaledWidth = Math.max(canvasWrap.clientWidth, effectiveCanvasWidth() * canvasZoom + 48);
      const scaledHeight = Math.max(canvasWrap.clientHeight, effectiveCanvasHeight() * canvasZoom + 48);
      canvasSpacer.style.width = `${scaledWidth}px`;
      canvasSpacer.style.height = `${scaledHeight}px`;
    }
    function scheduleDragRender() {
      if (dragRenderFrameRequested) return;
      dragRenderFrameRequested = true;
      window.requestAnimationFrame(() => {
        dragRenderFrameRequested = false;
        renderCanvas();
      });
    }
    function markCanvasZooming() {
      canvasWrap.classList.add("zooming");
      if (zoomingClassTimer) window.clearTimeout(zoomingClassTimer);
      zoomingClassTimer = window.setTimeout(() => {
        canvasWrap.classList.remove("zooming");
        zoomingClassTimer = 0;
      }, 140);
    }
    function scheduleCanvasZoom(nextZoom, clientX, clientY) {
      pendingZoom = nextZoom;
      pendingZoomClientX = clientX;
      pendingZoomClientY = clientY;
      markCanvasZooming();
      if (zoomFrameRequested) return;
      zoomFrameRequested = true;
      window.requestAnimationFrame(() => {
        zoomFrameRequested = false;
        const rect = canvasWrap.getBoundingClientRect();
        const pointerX = pendingZoomClientX - rect.left + canvasWrap.scrollLeft;
        const pointerY = pendingZoomClientY - rect.top + canvasWrap.scrollTop;
        const contentX = pointerX / canvasZoom;
        const contentY = pointerY / canvasZoom;
        canvasZoom = pendingZoom;
        applyCanvasZoom();
        canvasWrap.scrollLeft = contentX * canvasZoom - (pendingZoomClientX - rect.left);
        canvasWrap.scrollTop = contentY * canvasZoom - (pendingZoomClientY - rect.top);
      });
    }
    function enableCanvasNavigation() {
      canvasWrap.addEventListener("mousedown", (event) => {
        if (event.button !== 0) return;
        if (event.target && typeof event.target.closest === "function" && (event.target.closest("[data-block-id]") || event.target.closest("[data-edge-key]"))) return;
        isDraggingCanvas = true;
        dragStartX = event.clientX;
        dragStartY = event.clientY;
        dragScrollLeft = canvasWrap.scrollLeft;
        dragScrollTop = canvasWrap.scrollTop;
        canvasWrap.classList.add("dragging");
        event.preventDefault();
      });
      window.addEventListener("mousemove", (event) => {
        if (draggedBlockId) {
          const deltaX = (event.clientX - dragBlockStartX) / canvasZoom;
          const deltaY = (event.clientY - dragBlockStartY) / canvasZoom;
          if (!dragBlockMoved && Math.hypot(deltaX, deltaY) >= 4) {
            dragBlockMoved = true;
            suppressBlockClick = true;
            canvasWrap.classList.add("block-dragging");
          }
          if (!dragBlockMoved) return;
          layoutOverrides.set(draggedBlockId, {
            x: Math.max(0, Math.round(dragBlockOriginX + deltaX)),
            y: Math.max(0, Math.round(dragBlockOriginY + deltaY)),
          });
          scheduleDragRender();
          return;
        }
        if (!isDraggingCanvas) return;
        const deltaX = event.clientX - dragStartX;
        const deltaY = event.clientY - dragStartY;
        canvasWrap.scrollLeft = dragScrollLeft - deltaX;
        canvasWrap.scrollTop = dragScrollTop - deltaY;
      });
      window.addEventListener("mouseup", () => {
        if (draggedBlockId) {
          const blockId = draggedBlockId;
          const moved = dragBlockMoved;
          draggedBlockId = null;
          dragBlockMoved = false;
          canvasWrap.classList.remove("block-dragging");
          if (!moved) {
            selectBlock(blockId);
          } else {
            renderCanvas();
            window.setTimeout(() => {
              suppressBlockClick = false;
            }, 0);
          }
          return;
        }
        if (!isDraggingCanvas) return;
        isDraggingCanvas = false;
        canvasWrap.classList.remove("dragging");
      });
      canvasWrap.addEventListener("mouseleave", () => {
        if (draggedBlockId) return;
        if (!isDraggingCanvas) return;
        isDraggingCanvas = false;
        canvasWrap.classList.remove("dragging");
      });
      canvasWrap.addEventListener("wheel", (event) => {
        event.preventDefault();
        const currentZoom = zoomFrameRequested ? pendingZoom : canvasZoom;
        const zoomFactor = Math.exp(-event.deltaY * 0.0015);
        const nextZoom = Math.min(3, Math.max(0.5, currentZoom * zoomFactor));
        if (Math.abs(nextZoom - currentZoom) < 0.001) return;
        scheduleCanvasZoom(nextZoom, event.clientX, event.clientY);
      }, { passive: false });
    }
"""

_HTML_SCRIPT += """
    function renderCanvas() {
      if (!data.graph.nodes.length) {
        canvasStage.innerHTML = '<p class="empty">No workflow scenario blocks were parsed.</p>';
        summaryElement.innerHTML = 'No workflow nodes are available for canvas inspection.';
        return;
      }
      const q = query();
      const related = selectedBlockId
        ? relationshipSet(selectedBlockId)
        : selectedEdgeKey
          ? edgeRelationshipSet(selectedEdgeKey)
          : new Set();
      const canvasWidth = effectiveCanvasWidth();
      const canvasHeight = effectiveCanvasHeight();
      const matched = data.graph.nodes.filter((node) => !q || node.search_text.includes(q));
      summaryElement.innerHTML = `<strong>${matched.length}</strong> of <strong>${data.graph.nodes.length}</strong> block(s) shown in search`;
      const edgesMarkup = data.graph.edges.map((edge) => {
        const source = nodeMap.get(edge.source_block_id);
        const target = nodeMap.get(edge.target_block_id);
        if (!source || !target) return "";
        const currentEdgeKey = edgeKey(edge);
        const points = connectionPoints(source, target, edge);
        const sourceType = (source.block_type || "").toLowerCase();
        const falseExit = sourceType === "if" && isFalseyExit(edge);
        const sx = points.startX;
        const sy = points.startY;
        const tx = points.endX;
        const ty = points.endY;
        const edgeSelected = selectedEdgeKey === currentEdgeKey;
        const edgeRelated = selectedBlockId
          ? related.has(edge.source_block_id) && related.has(edge.target_block_id)
          : false;
        const cls = edgeSelected
          ? "edge selected"
          : selectedBlockId && (edge.source_block_id === selectedBlockId || edge.target_block_id === selectedBlockId)
            ? "edge selected"
            : edgeRelated
              ? "edge connected"
              : (selectedBlockId || selectedEdgeKey || (q && !edgeMatchesQuery(edge, q))) ? "edge dim" : "edge";
        const title = [edge.source_exit_title, edge.source_exit_condition].filter(Boolean).join(" | ") || `${edge.source_block_id} -> ${edge.target_block_id}`;
        let polylinePoints = "";
        const exitStub = falseExit ? -24 : 24;
        const stubX = sx + exitStub;
        if (falseExit && points.endSide === "top") {
          if (tx <= stubX - 12) {
            polylinePoints = `${sx},${sy} ${stubX},${sy} ${tx},${sy} ${tx},${ty}`;
          } else {
            const elbowX = sx - 42;
            polylinePoints = `${sx},${sy} ${stubX},${sy} ${elbowX},${sy} ${elbowX},${ty} ${tx},${ty}`;
          }
        } else if (falseExit) {
          const elbowX = Math.min(sx - 42, tx - 18);
          polylinePoints = `${sx},${sy} ${stubX},${sy} ${elbowX},${sy} ${elbowX},${ty} ${tx},${ty}`;
        } else if (sourceType === "switch" && points.endSide === "top") {
          const approachY = Math.max(12, ty - 18);
          polylinePoints = `${sx},${sy} ${stubX},${sy} ${stubX},${approachY} ${tx},${approachY} ${tx},${ty}`;
        } else if (sourceType === "if" && points.endSide === "left") {
          const elbowX = Math.max(stubX, sx + (tx - sx) * 0.45);
          polylinePoints = `${sx},${sy} ${stubX},${sy} ${elbowX},${sy} ${elbowX},${ty} ${tx},${ty}`;
        } else if (sourceType === "if" || points.endSide === "top") {
          if (tx >= stubX) {
            polylinePoints = `${sx},${sy} ${stubX},${sy} ${tx},${sy} ${tx},${ty}`;
          } else {
            polylinePoints = `${sx},${sy} ${stubX},${sy} ${stubX},${ty} ${tx},${ty}`;
          }
        } else {
          const midX = Math.max(stubX, sx + (tx - sx) / 2);
          polylinePoints = `${sx},${sy} ${stubX},${sy} ${midX},${sy} ${midX},${ty} ${tx},${ty}`;
        }
        return `<polyline class="${cls}" data-edge-key="${escapeHtml(currentEdgeKey)}" points="${polylinePoints}" marker-end="url(#arrowhead)"><title>${escapeHtml(title)}</title></polyline>`;
      }).join("");
      const nodesMarkup = data.graph.nodes.map((node) => {
        const selected = selectedBlockId === node.block_id || (selectedEdgeKey && related.has(node.block_id));
        const dim = (q && !node.search_text.includes(q)) || ((selectedBlockId || selectedEdgeKey) && !selected && !related.has(node.block_id));
        const displayX = effectiveDisplayX(node);
        const displayY = effectiveDisplayY(node);
        const centerX = node.width / 2;
        const centerY = node.height / 2;
        let labelMarkup = "";
        let metaMarkup = "";
        if (node.shape === "circle") {
          labelMarkup = `<text class="node-label" x="${centerX}" y="${centerY + 6}" text-anchor="middle">${escapeHtml((node.block_type || shortLabel(node)).toUpperCase())}</text>`;
        } else if (node.shape === "diamond") {
          const typeText = (node.block_type || "if").toUpperCase();
          const diamondLabelChars = Math.max(8, Math.floor((node.width - 24) / 8));
          const diamondLabelLines = wrapLines(shortLabel(node), diamondLabelChars, 2);
          labelMarkup = `
            <text class="node-meta" x="${centerX}" y="${centerY + 4}" text-anchor="middle">${escapeHtml(typeText)}</text>
            <text class="node-label" x="${centerX}" y="${node.height + 22}" text-anchor="middle">${diamondLabelLines.map((line, index) => `<tspan x="${centerX}" dy="${index === 0 ? 0 : 18}">${escapeHtml(line)}</tspan>`).join("")}</text>
          `;
        } else {
          const exitLabels = uniqueExitLabels(node.block_id);
          const typeText = (node.block_type || "Unknown").replace(/_/g, " ");
          const typeZoneWidth = Math.max(72, Math.min(112, Math.floor(node.width * 0.44)));
          const typeChars = Math.max(6, Math.floor((typeZoneWidth - 4) / 7));
          const titleChars = Math.max(8, Math.floor((node.width - typeZoneWidth - 28) / 7.2));
          const titleLines = wrapLines(shortLabel(node), titleChars, 2);
          const exitChars = Math.max(8, Math.floor((node.width - 30) / 7.2));
          const exitMarkup = exitLabels.map((label, index) => {
            const y = node.height - 18 - (exitLabels.length - 1 - index) * 24;
            return `<text class="node-meta" x="${node.width - 12}" y="${y}" text-anchor="end">${escapeHtml(truncateText(label.toUpperCase(), exitChars))} ></text>`;
          }).join("");
          labelMarkup = `<text class="node-label" x="16" y="24">${titleLines.map((line, index) => `<tspan x="16" dy="${index === 0 ? 0 : 15}">${escapeHtml(line)}</tspan>`).join("")}</text>`;
          metaMarkup = `
            <text class="node-meta" x="${node.width - 10}" y="18" text-anchor="end">${escapeHtml(truncateText(typeText, typeChars))}</text>
            ${exitMarkup}
          `;
        }
        return `
          <g class="node${draggedBlockId === node.block_id ? " dragging" : ""}${selected ? " selected" : dim ? " dim" : ""}" data-block-id="${node.block_id}" transform="translate(${displayX}, ${displayY})">
            <title>${escapeHtml(node.block_id)}${node.title ? `\\n${escapeHtml(node.title)}` : ""}</title>
            ${nodeShapeMarkup(node)}
            ${labelMarkup}
            ${metaMarkup}
          </g>
        `;
      }).join("");
      canvasStage.innerHTML = `
        <div class="canvas-spacer"></div>
        <div class="canvas-content">
          <svg width="${canvasWidth}" height="${canvasHeight}" viewBox="0 0 ${canvasWidth} ${canvasHeight}">
            <defs><marker id="arrowhead" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto" markerUnits="strokeWidth"><path d="M 0 0 L 10 4 L 0 8 z" fill="rgba(95,111,133,.7)"></path></marker></defs>
            ${edgesMarkup}
            ${nodesMarkup}
          </svg>
        </div>
      `;
      canvasSpacer = canvasStage.querySelector(".canvas-spacer");
      canvasContent = canvasStage.querySelector(".canvas-content");
      applyCanvasZoom();
      for (const element of canvasStage.querySelectorAll("[data-block-id]")) {
        element.addEventListener("mousedown", (event) => {
          if (event.button !== 0) return;
          draggedBlockId = element.getAttribute("data-block-id");
          dragBlockStartX = event.clientX;
          dragBlockStartY = event.clientY;
          const node = nodeMap.get(draggedBlockId);
          dragBlockOriginX = node ? effectiveDisplayX(node) : 0;
          dragBlockOriginY = node ? effectiveDisplayY(node) : 0;
          dragBlockMoved = false;
          event.preventDefault();
          event.stopPropagation();
        });
        element.addEventListener("click", () => {
          if (suppressBlockClick) {
            suppressBlockClick = false;
            return;
          }
          selectBlock(element.getAttribute("data-block-id"));
        });
      }
      for (const element of canvasStage.querySelectorAll("[data-edge-key]")) {
        element.addEventListener("click", () => selectEdge(element.getAttribute("data-edge-key")));
      }
    }
    function renderEdgeInspector(edge) {
      const source = nodeMap.get(edge.source_block_id);
      const target = nodeMap.get(edge.target_block_id);
      const exitProperties = Array.isArray(edge.source_exit_properties) ? edge.source_exit_properties : [];
      const rawMarkup = exitProperties.length ? `<div class="list">${exitProperties.map((property) => `
        <article class="prop">
          <h3>${escapeHtml(property.name)}</h3>
          ${property.groups.length ? property.groups.map((group, index) => `
            <div class="group">
              <div class="small"><strong>Group ${index + 1}</strong></div>
              <div class="list">${groupEntries(group).map(([name, value]) => `
                <div class="param"><div class="param-name">${escapeHtml(name)}</div><div>${formatValue(value)}</div></div>
              `).join("")}</div>
            </div>
          `).join("") : '<p class="empty">No grouped parameters.</p>'}
        </article>
      `).join("")}</div>` : '<p class="empty">No exit properties were parsed.</p>';
      inspectorElement.innerHTML = `
        <div class="stack">
          <div>
            <h2>${highlightText(edge.source_exit_title || edge.source_exit_condition || "Connection")}</h2>
            <div class="badges">
              <span class="badge">${highlightText(source ? shortLabel(source) : edge.source_block_id)}</span>
              <span class="badge">${highlightText(target ? shortLabel(target) : edge.target_block_id)}</span>
            </div>
          </div>
          <section class="section">
            <h3>Overview</h3>
            <div class="grid">
              <div class="card"><span class="label">From</span><div>${formatValue(source ? shortLabel(source) : edge.source_block_id)}</div></div>
              <div class="card"><span class="label">To</span><div>${formatValue(target ? shortLabel(target) : edge.target_block_id)}</div></div>
              <div class="card"><span class="label">Exit</span><div>${formatValue(edge.source_exit_title)}</div></div>
              <div class="card"><span class="label">Condition</span><div>${formatValue(edge.source_exit_condition)}</div></div>
            </div>
          </section>
          <section class="section">
            <h3>Exit Properties</h3>
            ${rawMarkup}
          </section>
        </div>
      `;
    }
    function renderInspector() {
      if (!selectedBlockId && !selectedEdgeKey) {
        inspectorElement.innerHTML = '<p class="empty">Select a block or connection on the canvas to inspect its metadata.</p>';
        return;
      }
      if (selectedEdgeKey) {
        const edge = edgeMap.get(selectedEdgeKey);
        if (!edge) {
          inspectorElement.innerHTML = '<p class="empty">The selected connection could not be found.</p>';
          return;
        }
        renderEdgeInspector(edge);
        return;
      }
      const node = nodeMap.get(selectedBlockId);
      if (!node) {
        inspectorElement.innerHTML = '<p class="empty">The selected block could not be found.</p>';
        return;
      }
      const incoming = incomingMap.get(selectedBlockId) || [];
      const outgoing = outgoingMap.get(selectedBlockId) || [];
      const propertiesMarkup = renderPropertiesSection(node);
      inspectorElement.innerHTML = `
        <div class="stack">
          <div>
            <h2>${highlightText(shortLabel(node))}</h2>
            <div class="badges"><span class="badge">${highlightText(node.block_type || "Unknown type")}</span><span class="badge">${highlightText(node.block_id)}</span></div>
          </div>
          <section class="section">
            <h3>Overview</h3>
            <div class="grid">
              <div class="card"><span class="label">Position</span><div>${escapeHtml(`${node.x != null ? node.x : "?"}, ${node.y != null ? node.y : "?"}`)}</div></div>
              <div class="card"><span class="label">Incoming</span><div>${incoming.length}</div></div>
              <div class="card"><span class="label">Outgoing</span><div>${outgoing.length}</div></div>
              <div class="card"><span class="label">Property Groups</span><div>${node.properties.reduce((count, property) => count + property.groups.length, 0)}</div></div>
            </div>
          </section>
          <section class="section"><h3>Properties</h3>${propertiesMarkup}</section>
        </div>
      `;
    }
"""

_HTML_SCRIPT += """
    function matchedNodes() {
      const q = query();
      return data.graph.nodes.filter((node) => !q || node.search_text.includes(q));
    }
    function syncSelectionToSearch() {
      const q = query();
      if (!q) return;
      const matched = matchedNodes();
      const selectedNode = selectedBlockId ? nodeMap.get(selectedBlockId) : null;
      const selectedMatches = selectedNode ? selectedNode.search_text.includes(q) : false;
      const selectedEdge = selectedEdgeKey ? edgeMap.get(selectedEdgeKey) : null;
      const selectedEdgeMatches = selectedEdge ? edgeMatchesQuery(selectedEdge, q) : false;
      if (matched.length === 1) {
        selectedBlockId = matched[0].block_id;
        selectedEdgeKey = null;
        return;
      }
      if (selectedBlockId && !selectedMatches) {
        selectedBlockId = null;
      }
      if (selectedEdgeKey && !selectedEdgeMatches) {
        selectedEdgeKey = null;
      }
    }
    function render() {
      renderStats();
      renderCanvas();
      renderInspector();
    }
    searchInput.addEventListener("input", () => {
      syncSelectionToSearch();
      render();
    });
    resetLayoutButton.addEventListener("click", () => {
      layoutOverrides.clear();
      renderCanvas();
      if (selectedBlockId) {
        centerOnSelection();
      } else if (selectedEdgeKey) {
        centerOnEdgeSelection();
      }
    });
    clearSelectionButton.addEventListener("click", () => {
      selectedBlockId = null;
      selectedEdgeKey = null;
      searchInput.value = "";
      render();
    });
    const generatedAtElement = document.getElementById("generated-at");
    if (generatedAtElement) {
      generatedAtElement.textContent = formatGeneratedTimestamp(generatedAtElement.textContent);
    }
    enableCanvasNavigation();
    render();
"""
