"""Standalone HTML reporting for ROX parameter inspection."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from html import escape
from typing import Any

from .core import Parameter
from .graph import (
    DependencyGraph,
    GraphEdge,
    build_dependency_graph,
    reduce_dependency_graph,
)

REPORT_EXPRESSION_FIELDS = (
    "Description",
    "TriggerFields",
    "AutoFillExpression",
    "ValueExpression",
    "VisibilityExpression",
    "RequiredExpression",
    "AdHocValues",
    "ValidationListRecId",
    "ValidationConstraints",
    "ReadOnlyExpression",
    "HelpText",
    "HelpLink",
    "ConfigOptions",
)


@dataclass(slots=True, frozen=True)
class ReportEvidenceItem:
    """A single expression snippet supporting a dependency relationship."""

    field_name: str
    expression_text: str

    def to_dict(self) -> dict[str, str]:
        """Return the evidence item as serializable data."""

        return {
            "field_name": self.field_name,
            "expression_text": self.expression_text,
        }


@dataclass(slots=True, frozen=True)
class ReportRelationship:
    """A navigable parent/child relationship in the HTML inspector report."""

    sequence_number: int
    label: str
    detail: str
    evidence_items: list[ReportEvidenceItem]

    def to_dict(self) -> dict[str, Any]:
        """Return the relationship as serializable data."""

        return {
            "sequence_number": self.sequence_number,
            "label": self.label,
            "detail": self.detail,
            "evidence_items": [item.to_dict() for item in self.evidence_items],
        }


@dataclass(slots=True, frozen=True)
class ReportRow:
    """A table row in the HTML inspector report."""

    sequence_number: int
    name: str | None
    display_name: str | None
    display_type: str | None
    category: str | None
    parents: list[str]
    children: list[str]
    parent_links: list[ReportRelationship]
    child_links: list[ReportRelationship]
    parent_details: list[str]
    child_details: list[str]
    expressions: dict[str, str | None]
    search_text: str

    def to_dict(self) -> dict[str, Any]:
        """Return the row as serializable data."""

        return {
            "sequence_number": self.sequence_number,
            "name": self.name,
            "display_name": self.display_name,
            "display_type": self.display_type,
            "category": self.category,
            "parents": list(self.parents),
            "children": list(self.children),
            "parent_links": [item.to_dict() for item in self.parent_links],
            "child_links": [item.to_dict() for item in self.child_links],
            "parent_details": list(self.parent_details),
            "child_details": list(self.child_details),
            "expressions": dict(self.expressions),
            "search_text": self.search_text,
        }


def build_report_rows(
    parameters: dict[int, Parameter],
    *,
    reduced: bool = False,
) -> list[ReportRow]:
    """Build report rows ordered by sequence number."""

    graph = build_dependency_graph(parameters)
    if reduced:
        graph = reduce_dependency_graph(graph)
    parent_map, child_map = _relationship_maps(graph)
    rows: list[ReportRow] = []

    for sequence_number, parameter in parameters.items():
        category = _category_label(graph, sequence_number)
        parents = parent_map.get(sequence_number, [])
        children = child_map.get(sequence_number, [])
        expressions = {
            field_name: _expression_text(parameter, field_name)
            for field_name in REPORT_EXPRESSION_FIELDS
        }
        search_parts = _report_search_parts(
            sequence_number=sequence_number,
            parameter=parameter,
            category=category,
            parents=parents,
            children=children,
            expressions=expressions,
        )

        rows.append(
            ReportRow(
                sequence_number=sequence_number,
                name=parameter.name,
                display_name=parameter.display_name,
                display_type=parameter.display_type,
                category=category,
                parents=[item["label"] for item in parents],
                children=[item["label"] for item in children],
                parent_links=[
                    ReportRelationship(
                        sequence_number=int(item["sequence_number"]),
                        label=item["label"],
                        detail=item["detail"],
                        evidence_items=[
                            ReportEvidenceItem(
                                field_name=evidence["field_name"],
                                expression_text=evidence["expression_text"],
                            )
                            for evidence in item["evidence_items"]
                        ],
                    )
                    for item in parents
                ],
                child_links=[
                    ReportRelationship(
                        sequence_number=int(item["sequence_number"]),
                        label=item["label"],
                        detail=item["detail"],
                        evidence_items=[
                            ReportEvidenceItem(
                                field_name=evidence["field_name"],
                                expression_text=evidence["expression_text"],
                            )
                            for evidence in item["evidence_items"]
                        ],
                    )
                    for item in children
                ],
                parent_details=[item["detail"] for item in parents],
                child_details=[item["detail"] for item in children],
                expressions=expressions,
                search_text=" ".join(part.casefold() for part in search_parts if part),
            )
        )

    return rows


def build_report_html(
    parameters: dict[int, Parameter],
    *,
    document_name: str,
    title: str = "ROX Parameter Inspector",
    reduced: bool = False,
    generated_at: datetime | None = None,
) -> str:
    """Build a standalone HTML inspector report."""

    rows = build_report_rows(parameters, reduced=reduced)
    payload = _safe_json_for_html_script(
        {"title": title, "rows": [row.to_dict() for row in rows]}
    )
    escaped_title = escape(title)
    escaped_document_name = escape(document_name)
    timestamp_iso = _report_timestamp_iso(generated_at)
    mode_label = "Reduced View" if reduced else "Full dependency view"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #eef3f8;
      --panel: #ffffff;
      --line: #d7e0eb;
      --line-strong: #b8c6d7;
      --text: #142033;
      --muted: #5f6f85;
      --accent: #2458a6;
      --accent-soft: #e8f0ff;
      --chip: #edf2f8;
      --shadow: 0 14px 34px rgba(20, 32, 51, 0.09);
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      font-family: "Segoe UI", "Helvetica Neue", sans-serif;
      background: linear-gradient(180deg, #f4f7fb 0%, #edf2f8 100%);
      color: var(--text);
    }}

    .page {{
      width: 100%;
      max-width: none;
      margin: 0;
      padding: 24px 24px 40px;
    }}

    .sticky {{
      position: sticky;
      top: 0;
      z-index: 4;
      padding-bottom: 14px;
      background: linear-gradient(180deg, rgba(244,247,251,.98), rgba(237,242,248,.95));
    }}

    .header {{
      display: block;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: var(--shadow);
      padding: 18px;
      margin-bottom: 14px;
    }}

    h1 {{
      margin: 0;
      font-size: 1.85rem;
      font-weight: 700;
    }}

    .subtitle {{
      margin: 10px 0 0;
      color: var(--muted);
      max-width: 70ch;
    }}

    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 10px;
      font-size: 0.92rem;
    }}

    .chip {{
      display: inline-flex;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: #fbfcfe;
    }}

    .toolbar {{
      display: grid;
      gap: 14px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 14px 18px;
      box-shadow: var(--shadow);
      margin-bottom: 14px;
    }}

    .toolbar-row {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 12px;
    }}

    .toolbar-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}

    .search {{
      flex: 1 1 420px;
      min-width: 260px;
      padding: 12px 14px;
      border: 1px solid var(--line-strong);
      border-radius: 12px;
      font: inherit;
      color: var(--text);
      background: #fbfcfe;
    }}

    .toolbar-button,
    .row-toggle {{
      appearance: none;
      border: 1px solid var(--line-strong);
      border-radius: 12px;
      background: #fbfcfe;
      color: var(--text);
      font: inherit;
      font-size: 0.88rem;
      font-weight: 650;
      cursor: pointer;
      transition: background-color 120ms ease, border-color 120ms ease;
    }}

    .toolbar-button {{
      padding: 10px 12px;
    }}

    .toolbar-button:hover,
    .row-toggle:hover {{
      background: #f1f5fb;
      border-color: var(--accent);
    }}

    .summary {{
      color: var(--muted);
      font-size: 0.95rem;
    }}

    .summary strong {{
      color: var(--text);
    }}

    .table-wrap {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      overflow: hidden;
      box-shadow: var(--shadow);
    }}

    table {{
      table-layout: fixed;
      width: 100%;
      border-collapse: collapse;
    }}

    thead {{
      background: #f7f9fc;
    }}

    th,
    td {{
      padding: 14px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      font-size: 0.93rem;
    }}

    th {{
      color: var(--muted);
      font-weight: 600;
      letter-spacing: 0.01em;
      white-space: nowrap;
    }}

    tbody tr:hover {{
      background: #fbfcff;
    }}

    tbody tr:last-child td {{
      border-bottom: 0;
    }}

    .col-seq {{
      width: 5%;
    }}

    .col-name {{
      width: 10%;
    }}

    .col-display-name {{
      width: 10%;
    }}

    .col-display-type {{
      width: 10%;
    }}

    .col-category {{
      width: 10%;
    }}

    .col-parents {{
      width: 10%;
    }}

    .col-children {{
      width: 10%;
    }}

    .col-expressions {{
      width: 35%;
    }}

    .seq {{
      font-variant-numeric: tabular-nums;
      font-weight: 700;
      white-space: nowrap;
    }}

    .seq-cell {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    .row-toggle {{
      min-width: 2.2rem;
      padding: 6px 8px;
      line-height: 1;
    }}

    .row-toggle-text {{
      display: inline-block;
      width: 1ch;
      text-align: center;
    }}

    .stack,
    .relationship-list,
    .expression-list,
    .expression {{
      width: 100%;
    }}

    .stack {{
      display: grid;
      gap: 4px;
    }}

    .primary {{
      word-break: break-word;
      font-weight: 600;
      color: var(--text);
    }}

    .secondary {{
      color: var(--muted);
      font-size: 0.88rem;
      overflow-wrap: anywhere;
    }}

    .relationship-list {{
      display: grid;
      gap: 6px;
    }}

    .relationship-item {{
      display: block;
      width: 100%;
      padding: 6px 8px;
      border-radius: 10px;
      background: var(--chip);
      color: var(--text);
      font-size: 0.84rem;
      line-height: 1.35;
      overflow-wrap: anywhere;
    }}

    button.relationship-item {{
      appearance: none;
      border: 1px solid transparent;
      text-align: left;
      cursor: pointer;
    }}

    button.relationship-item:hover {{
      border-color: var(--accent);
      background: #e7eefb;
    }}

    .row-highlight td {{
      background: #fff7d6;
      transition: background-color 200ms ease;
    }}

    mark {{
      background: #ffe58f;
      color: inherit;
      padding: 0 1px;
      border-radius: 3px;
    }}

    .expression-list {{
      display: grid;
      gap: 8px;
    }}

    .expression {{
      padding: 8px 10px;
      border-radius: 12px;
      background: #f7f9fc;
      border: 1px solid #e4eaf2;
    }}

    .expression-name {{
      display: block;
      font-size: 0.8rem;
      font-weight: 700;
      color: var(--accent);
      margin-bottom: 4px;
    }}

    .expression-value {{
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-family: "Cascadia Code", "Consolas", monospace;
      font-size: 0.82rem;
      color: var(--text);
    }}

    .empty {{
      color: var(--muted);
      font-style: italic;
    }}

    .collapsed-cell {{
      color: var(--muted);
      font-size: 0.85rem;
      font-style: italic;
    }}

    th,
    td {{
      border-right: 1px solid var(--line);
    }}

    th:last-child,
    td:last-child {{
      border-right: 0;
    }}

    .hidden-row {{
      display: none;
    }}

    .relationship-preview {{
      position: fixed;
      z-index: 10;
      max-width: 440px;
      min-width: 280px;
      padding: 12px 14px;
      border: 1px solid var(--line-strong);
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.98);
      box-shadow: var(--shadow);
      color: var(--text);
    }}

    .relationship-preview[hidden] {{
      display: none;
    }}

    .relationship-preview-title {{
      margin: 0 0 6px;
      font-size: 0.92rem;
      font-weight: 700;
    }}

    .relationship-preview-detail {{
      margin: 0 0 10px;
      color: var(--muted);
      font-size: 0.84rem;
    }}

    .relationship-preview-list {{
      display: grid;
      gap: 8px;
    }}

    .relationship-preview-item {{
      padding: 8px 10px;
      border-radius: 10px;
      background: #f7f9fc;
      border: 1px solid #e4eaf2;
    }}

    .relationship-preview-field {{
      display: block;
      margin-bottom: 4px;
      font-size: 0.8rem;
      font-weight: 700;
      color: var(--accent);
    }}

    .relationship-preview-expression {{
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-family: "Cascadia Code", "Consolas", monospace;
      font-size: 0.8rem;
      color: var(--text);
    }}

    @media (max-width: 1100px) {{
      .table-wrap {{
        overflow-x: auto;
      }}

      table {{
        min-width: 1180px;
      }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <div class="sticky">
      <section class="header">
        <h1>{escaped_title}</h1>
        <p class="subtitle">
          Parent/child relationships are hoverable and clickable.
        </p>
        <div class="meta">
          <span class="chip"><strong>Template</strong><span>{escaped_document_name}</span></span>
          <span class="chip"><strong>Generated</strong><span id="generated-at">{escape(timestamp_iso)}</span></span>
          <span class="chip"><strong>Mode</strong><span>{escape(mode_label)}</span></span>
        </div>
      </section>

      <section class="toolbar">
        <div class="toolbar-row">
          <input
            id="search"
            class="search"
            type="search"
            placeholder="Search sequence, names, types, relationships, or expressions"
            autocomplete="off"
            spellcheck="false"
          >
          <div class="toolbar-actions">
            <button id="expand-all" class="toolbar-button" type="button">Expand all</button>
            <button id="collapse-all" class="toolbar-button" type="button">Collapse all</button>
          </div>
        </div>
        <div class="toolbar-row">
          <div id="summary" class="summary"></div>
        </div>
      </section>
    </div>

    <section class="table-wrap">
      <table>
        <thead>
          <tr>
            <th class="col-seq">Sequence</th>
            <th class="col-name">Name</th>
            <th class="col-display-name">Display Name</th>
            <th class="col-display-type">Display Type</th>
            <th class="col-category">Category</th>
            <th class="col-parents">Parents</th>
            <th class="col-children">Children</th>
            <th class="col-expressions">Expressions</th>
          </tr>
        </thead>
        <tbody id="rows"></tbody>
      </table>
    </section>
  </main>

  <script id="report-data" type="application/json">
{payload}
  </script>
  <div id="relationship-preview" class="relationship-preview" hidden></div>
  <script>
    const data = JSON.parse(document.getElementById("report-data").textContent);
    const rowsElement = document.getElementById("rows");
    const summaryElement = document.getElementById("summary");
    const searchInput = document.getElementById("search");
    const expandAllButton = document.getElementById("expand-all");
    const collapseAllButton = document.getElementById("collapse-all");
    const relationshipPreview = document.getElementById("relationship-preview");
    const expandedRows = new Set();

    function formatGeneratedTimestamp(value) {{
      if (!value) {{
        return "";
      }}

      const moment = new Date(value);
      if (Number.isNaN(moment.getTime())) {{
        return value;
      }}

      return new Intl.DateTimeFormat(undefined, {{
        dateStyle: "medium",
        timeStyle: "short",
      }}).format(moment);
    }}

    function relationshipList(items) {{
      if (!items.length) {{
        return '<span class="empty">None</span>';
      }}

      return `<div class="relationship-list">${{items
        .map((item) => `
          <button
            class="relationship-item"
            type="button"
            data-target-sequence="${{item.sequence_number}}"
            data-relationship="${{encodeRelationship(item)}}"
          >${{highlightText(item.label, searchInput.value.trim())}}</button>
        `)
        .join("")}}</div>`;
    }}

    function expressionList(expressions) {{
      const entries = Object.entries(expressions).filter(([, value]) => value);
      if (!entries.length) {{
        return '<span class="empty">None</span>';
      }}

      return `<div class="expression-list">${{entries
        .map(([name, value]) => `
          <div class="expression">
            <span class="expression-name">${{highlightText(shortExpressionName(name), searchInput.value.trim())}}</span>
            <pre class="expression-value">${{highlightText(value, searchInput.value.trim())}}</pre>
          </div>
        `)
        .join("")}}</div>`;
    }}

    function shortExpressionName(name) {{
      return name.replace(/Expression$/, "");
    }}

    function escapeHtml(value) {{
      return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }}

    function escapeRegExp(value) {{
      return String(value).replace(/[|\\\\{{}}()[\\]^$+*?.]/g, "\\\\$&");
    }}

    function highlightText(value, query) {{
      const text = value == null ? "" : String(value);
      if (!query) {{
        return escapeHtml(text);
      }}

      const pattern = new RegExp(`(${{escapeRegExp(query)}})`, "ig");
      return escapeHtml(text).replace(
        pattern,
        (match) => `<mark>${{match}}</mark>`,
      );
    }}

    function encodeRelationship(item) {{
      return encodeURIComponent(JSON.stringify(item));
    }}

    function decodeRelationship(value) {{
      return JSON.parse(decodeURIComponent(value));
    }}

    function collapsedSummary(items) {{
      if (!items.length) {{
        return '<span class="empty">None</span>';
      }}

      const countLabel = items.length === 1 ? "item" : "items";
      return `<span class="collapsed-cell">${{items.length}} ${{countLabel}} hidden</span>`;
    }}

    function isRowExpanded(sequenceNumber) {{
      return expandedRows.has(sequenceNumber);
    }}

    function hideRelationshipPreview() {{
      relationshipPreview.hidden = true;
      relationshipPreview.innerHTML = "";
    }}

    function positionRelationshipPreview(target) {{
      const rect = target.getBoundingClientRect();
      const previewRect = relationshipPreview.getBoundingClientRect();
      const margin = 12;
      let top = rect.bottom + margin;
      let left = rect.left;

      if (left + previewRect.width + margin > window.innerWidth) {{
        left = window.innerWidth - previewRect.width - margin;
      }}
      if (left < margin) {{
        left = margin;
      }}

      if (top + previewRect.height + margin > window.innerHeight) {{
        top = rect.top - previewRect.height - margin;
      }}
      if (top < margin) {{
        top = margin;
      }}

      relationshipPreview.style.top = `${{top}}px`;
      relationshipPreview.style.left = `${{left}}px`;
    }}

    function showRelationshipPreview(target) {{
      const encoded = target.getAttribute("data-relationship");
      if (!encoded) {{
        hideRelationshipPreview();
        return;
      }}

      const relationship = decodeRelationship(encoded);
      const evidence = relationship.evidence_items || [];
      const evidenceMarkup = evidence.length
        ? `<div class="relationship-preview-list">${{evidence
            .map((item) => `
              <div class="relationship-preview-item">
                <span class="relationship-preview-field">${{highlightText(shortExpressionName(item.field_name), searchInput.value.trim())}}</span>
                <pre class="relationship-preview-expression">${{highlightText(item.expression_text, searchInput.value.trim())}}</pre>
              </div>
            `)
            .join("")}}</div>`
        : '<span class="empty">No evidence available.</span>';

      relationshipPreview.innerHTML = `
        <p class="relationship-preview-title">${{highlightText(relationship.label, searchInput.value.trim())}}</p>
        <p class="relationship-preview-detail">${{highlightText(relationship.detail, searchInput.value.trim())}}</p>
        ${{evidenceMarkup}}
      `;
      relationshipPreview.hidden = false;
      positionRelationshipPreview(target);
    }}

    function highlightRow(sequenceNumber) {{
      const rowElement = rowsElement.querySelector(`[data-row-sequence="${{sequenceNumber}}"]`);
      if (!rowElement) {{
        return;
      }}

      rowElement.classList.add("row-highlight");
      window.setTimeout(() => {{
        rowElement.classList.remove("row-highlight");
      }}, 1800);
    }}

    function navigateToRow(sequenceNumber) {{
      searchInput.value = "";
      expandedRows.add(sequenceNumber);
      renderRows("");

      const rowElement = rowsElement.querySelector(`[data-row-sequence="${{sequenceNumber}}"]`);
      if (!rowElement) {{
        return;
      }}

      rowElement.scrollIntoView({{ behavior: "smooth", block: "center" }});
      highlightRow(sequenceNumber);
    }}

    function renderRows(filterText) {{
      const query = filterText.trim().toLowerCase();
      let visibleCount = 0;

      rowsElement.innerHTML = data.rows
        .map((row) => {{
          const visible = !query || row.search_text.includes(query);
          const expanded = isRowExpanded(row.sequence_number);
          if (visible) {{
            visibleCount += 1;
          }}

          return `
            <tr class="${{visible ? "" : "hidden-row"}}" data-row-sequence="${{row.sequence_number}}">
              <td class="col-seq seq">
                <div class="seq-cell">
                  <button
                    class="row-toggle"
                    type="button"
                    data-row-toggle="${{row.sequence_number}}"
                    aria-expanded="${{expanded ? "true" : "false"}}"
                    title="${{expanded ? "Collapse row" : "Expand row"}}"
                  >
                    <span class="row-toggle-text">${{expanded ? "-" : "+"}}</span>
                  </button>
                  <span>${{row.sequence_number}}</span>
                </div>
              </td>
              <td class="col-name">
                <div class="stack">
                  <span class="primary">${{highlightText(row.name || "-", filterText.trim())}}</span>
                </div>
              </td>
              <td class="col-display-name">
                <div class="stack">
                  <span class="primary">${{highlightText(row.display_name || "-", filterText.trim())}}</span>
                </div>
              </td>
              <td class="col-display-type">
                <div class="stack">
                  <span class="secondary">${{highlightText(row.display_type || "-", filterText.trim())}}</span>
                </div>
              </td>
              <td class="col-category">
                <div class="stack">
                  <span class="secondary">${{highlightText(row.category || "-", filterText.trim())}}</span>
                </div>
              </td>
              <td class="col-parents">
                ${{expanded ? relationshipList(row.parent_links) : collapsedSummary(row.parent_links)}}
              </td>
              <td class="col-children">
                ${{expanded ? relationshipList(row.child_links) : collapsedSummary(row.child_links)}}
              </td>
              <td class="col-expressions">${{expanded ? expressionList(row.expressions) : collapsedSummary(Object.values(row.expressions).filter(Boolean))}}</td>
            </tr>
          `;
        }})
        .join("");

      summaryElement.innerHTML = `<strong>${{visibleCount}}</strong> of <strong>${{data.rows.length}}</strong> parameter(s) shown`;
    }}

    searchInput.addEventListener("input", (event) => {{
      renderRows(event.target.value);
    }});

    rowsElement.addEventListener("click", (event) => {{
      const relationshipTarget = event.target.closest("[data-target-sequence]");
      if (relationshipTarget) {{
        navigateToRow(Number(relationshipTarget.getAttribute("data-target-sequence")));
        return;
      }}

      const toggle = event.target.closest("[data-row-toggle]");
      if (!toggle) {{
        return;
      }}

      const sequenceNumber = Number(toggle.getAttribute("data-row-toggle"));
      if (expandedRows.has(sequenceNumber)) {{
        expandedRows.delete(sequenceNumber);
      }} else {{
        expandedRows.add(sequenceNumber);
      }}
      renderRows(searchInput.value);
    }});

    rowsElement.addEventListener("mouseover", (event) => {{
      const relationshipTarget = event.target.closest("[data-relationship]");
      if (!relationshipTarget) {{
        return;
      }}
      showRelationshipPreview(relationshipTarget);
    }});

    rowsElement.addEventListener("focusin", (event) => {{
      const relationshipTarget = event.target.closest("[data-relationship]");
      if (!relationshipTarget) {{
        return;
      }}
      showRelationshipPreview(relationshipTarget);
    }});

    rowsElement.addEventListener("mouseout", (event) => {{
      const relationshipTarget = event.target.closest("[data-relationship]");
      if (!relationshipTarget) {{
        return;
      }}

      const relatedTarget = event.relatedTarget;
      if (relatedTarget && relationshipTarget.contains(relatedTarget)) {{
        return;
      }}
      hideRelationshipPreview();
    }});

    rowsElement.addEventListener("focusout", (event) => {{
      const relationshipTarget = event.target.closest("[data-relationship]");
      if (!relationshipTarget) {{
        return;
      }}
      hideRelationshipPreview();
    }});

    document.addEventListener("scroll", hideRelationshipPreview, true);

    expandAllButton.addEventListener("click", () => {{
      data.rows.forEach((row) => expandedRows.add(row.sequence_number));
      renderRows(searchInput.value);
    }});

    collapseAllButton.addEventListener("click", () => {{
      expandedRows.clear();
      renderRows(searchInput.value);
    }});

    const generatedAtElement = document.getElementById("generated-at");
    if (generatedAtElement) {{
      generatedAtElement.textContent = formatGeneratedTimestamp(generatedAtElement.textContent);
    }}

    renderRows("");
  </script>
</body>
</html>
"""


def _safe_json_for_html_script(payload: dict[str, Any]) -> str:
    """Serialize JSON safely for embedding inside a script tag."""

    return (
        json.dumps(payload, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _report_timestamp_iso(generated_at: datetime | None) -> str:
    """Return the report timestamp as an ISO 8601 UTC string."""

    moment = generated_at or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    else:
        moment = moment.astimezone(UTC)
    return moment.isoformat().replace("+00:00", "Z")


def _relationship_maps(
    graph: DependencyGraph,
) -> tuple[dict[int, list[dict[str, Any]]], dict[int, list[dict[str, Any]]]]:
    parents: dict[int, list[dict[str, Any]]] = {}
    children: dict[int, list[dict[str, Any]]] = {}

    for edge in graph.edges:
        parent_label = _relationship_label(
            edge.source_name, edge.source_sequence_number, edge
        )
        child_label = _relationship_label(
            edge.target_name, edge.target_sequence_number, edge
        )

        parent_detail = _relationship_detail(
            edge.source_name, edge.source_sequence_number, edge
        )
        child_detail = _relationship_detail(
            edge.target_name, edge.target_sequence_number, edge
        )

        parents.setdefault(edge.target_sequence_number, []).append(
            {
                "label": parent_label,
                "detail": parent_detail,
                "sequence_number": str(edge.source_sequence_number),
                "evidence_items": _relationship_evidence_items(edge),
            }
        )
        children.setdefault(edge.source_sequence_number, []).append(
            {
                "label": child_label,
                "detail": child_detail,
                "sequence_number": str(edge.target_sequence_number),
                "evidence_items": _relationship_evidence_items(edge),
            }
        )

    for relationship_list in parents.values():
        relationship_list.sort(
            key=lambda item: (int(item["sequence_number"]), item["label"])
        )
    for relationship_list in children.values():
        relationship_list.sort(
            key=lambda item: (int(item["sequence_number"]), item["label"])
        )

    return parents, children


def _relationship_label(name: str, sequence_number: int, edge: GraphEdge) -> str:
    labels = "/".join(edge.dependency_labels)
    return f"{name} ({labels}) #{sequence_number}"


def _relationship_detail(name: str, sequence_number: int, edge: GraphEdge) -> str:
    labels = "/".join(edge.dependency_labels)
    return f"{name} #{sequence_number} via {labels}"


def _relationship_evidence_items(edge: GraphEdge) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for field_name, expressions in edge.evidence.items():
        for expression_text in expressions:
            items.append(
                {
                    "field_name": field_name,
                    "expression_text": expression_text,
                }
            )
    return items


def _report_search_parts(
    *,
    sequence_number: int,
    parameter: Parameter,
    category: str | None,
    parents: list[dict[str, Any]],
    children: list[dict[str, Any]],
    expressions: dict[str, str | None],
) -> list[str]:
    parts = [
        str(sequence_number),
        parameter.name or "",
        parameter.display_name or "",
        parameter.display_type or "",
        category or "",
    ]

    for relationship in (*parents, *children):
        parts.append(str(relationship.get("label", "")))
        parts.append(str(relationship.get("detail", "")))
        for evidence_item in relationship.get("evidence_items", []):
            parts.append(str(evidence_item.get("field_name", "")))
            parts.append(str(evidence_item.get("expression_text", "")))

    for field_name, value in expressions.items():
        if value:
            parts.append(field_name)
            parts.append(value)

    return parts


def _category_label(graph: DependencyGraph, sequence_number: int) -> str | None:
    node = graph.nodes[sequence_number]
    if node.category_display_name is not None:
        return node.category_display_name
    if node.category_name is not None:
        return node.category_name
    return None


def _expression_text(parameter: Parameter, field_name: str) -> str | None:
    value = parameter.metadata.get(field_name)
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, list | dict):
        if not value:
            return None
        if field_name == "AdHocValues":
            return _format_ad_hoc_values(value)
        return json.dumps(
            _json_safe_expression_value(value),
            separators=(",", ":"),
            sort_keys=True,
        )
    return None


def _format_ad_hoc_values(value: list[Any] | dict[str, Any]) -> str | None:
    if not isinstance(value, list) or not value:
        return None

    sorted_items = sorted(value, key=_ad_hoc_sort_key)
    formatted_items = []
    for item in sorted_items:
        if not isinstance(item, dict):
            continue
        formatted_items.append(
            {
                "SortOrder": _json_safe_expression_value(item.get("SortOrder")),
                "ParameterValue": _json_safe_expression_value(
                    item.get("ParameterValue")
                ),
                "Price": _json_safe_expression_value(item.get("Price")),
                "AttachmentRecId": _json_safe_expression_value(
                    item.get("AttachmentRecId")
                ),
            }
        )

    if not formatted_items:
        return None

    return json.dumps(formatted_items, separators=(",", ":"))


def _ad_hoc_sort_key(item: Any) -> tuple[int, str]:
    if not isinstance(item, dict):
        return (1, "")

    sort_order = item.get("SortOrder")
    if isinstance(sort_order, Decimal):
        return (0, int(sort_order))
    if isinstance(sort_order, int):
        return (0, sort_order)
    if isinstance(sort_order, str):
        try:
            return (0, int(sort_order))
        except ValueError:
            return (1, sort_order)
    return (1, 0)


def _json_safe_expression_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return [_json_safe_expression_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe_expression_value(item) for key, item in value.items()}
    return value
