"""Graphviz DOT export for ROX dependency graphs."""

from __future__ import annotations

import shutil
import subprocess
from collections import defaultdict
from collections.abc import Sequence

from .core import Parameter
from .graph import (
    DependencyGraph,
    GraphNode,
    build_dependency_graph,
    reduce_dependency_graph,
)


class GraphvizError(RuntimeError):
    """Base class for Graphviz rendering errors."""


class GraphvizNotInstalledError(GraphvizError):
    """Raised when the Graphviz `dot` executable is unavailable."""


class GraphvizRenderError(GraphvizError):
    """Raised when Graphviz fails to render output."""


def export_graph_to_dot(
    graph: DependencyGraph,
    *,
    graph_name: str = "rox_form",
    rankdir: str = "LR",
    reduced: bool = False,
) -> str:
    """Export a dependency graph as Graphviz DOT."""

    graph = _visible_graph(graph)
    if reduced:
        graph = reduce_dependency_graph(graph)

    lines = [
        f"digraph {_quote_id(graph_name)} {{",
        f"  graph [rankdir={_quote(rankdir)}, splines={_quote('polyline')}, overlap=false];",
        '  node [shape=box, style="rounded", fontname="Helvetica"];',
        '  edge [fontname="Helvetica"];',
    ]

    ungrouped_nodes, grouped_nodes = _group_nodes(graph.nodes)

    for node in ungrouped_nodes:
        lines.append(f"  {_node_statement(node)}")

    for category_sequence_number, nodes in grouped_nodes:
        category_node = graph.nodes[category_sequence_number]
        cluster_label = (
            category_node.display_name
            or category_node.name
            or (f"Category {category_sequence_number}")
        )
        lines.append(f"  subgraph cluster_{category_sequence_number} {{")
        lines.append(f"    label={_quote(cluster_label)};")
        lines.append('    color="#b8c4d6";')
        lines.append('    style="rounded";')
        for node in nodes:
            lines.append(f"    {_node_statement(node)}")
        lines.append("  }")

    for edge in graph.edges:
        lines.append(
            "  "
            f"{_node_id(edge.source_sequence_number)} -> {_node_id(edge.target_sequence_number)} "
            f"[label={_quote('/'.join(edge.dependency_labels))}];"
        )

    lines.append("}")
    return "\n".join(lines)


def build_graph_dot(
    parameters: dict[int, Parameter],
    *,
    graph_name: str = "rox_form",
    rankdir: str = "LR",
    expression_fields: Sequence[str] | None = None,
    ignore_self_references: bool = True,
    reduced: bool = False,
) -> str:
    """Build a dependency graph from parameters and export it as DOT."""

    graph = build_dependency_graph(
        parameters,
        expression_fields=expression_fields,
        ignore_self_references=ignore_self_references,
    )
    return export_graph_to_dot(
        graph,
        graph_name=graph_name,
        rankdir=rankdir,
        reduced=reduced,
    )


def render_dot_to_svg(dot_source: str) -> str:
    """Render Graphviz DOT source to SVG using the `dot` executable."""

    dot_executable = shutil.which("dot")
    if dot_executable is None:
        raise GraphvizNotInstalledError(
            "Graphviz 'dot' was not found. Install Graphviz to use --param-graph-svg."
        )

    result = subprocess.run(
        [dot_executable, "-Tsvg"],
        input=dot_source,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or "Graphviz failed to render SVG."
        raise GraphvizRenderError(message)

    return result.stdout


def export_graph_to_svg(
    graph: DependencyGraph,
    *,
    graph_name: str = "rox_form",
    rankdir: str = "LR",
    reduced: bool = False,
) -> str:
    """Export a dependency graph as rendered SVG."""

    dot_source = export_graph_to_dot(
        graph,
        graph_name=graph_name,
        rankdir=rankdir,
        reduced=reduced,
    )
    return render_dot_to_svg(dot_source)


def build_graph_svg(
    parameters: dict[int, Parameter],
    *,
    graph_name: str = "rox_form",
    rankdir: str = "LR",
    expression_fields: Sequence[str] | None = None,
    ignore_self_references: bool = True,
    reduced: bool = False,
) -> str:
    """Build a dependency graph from parameters and render it as SVG."""

    dot_source = build_graph_dot(
        parameters,
        graph_name=graph_name,
        rankdir=rankdir,
        expression_fields=expression_fields,
        ignore_self_references=ignore_self_references,
        reduced=reduced,
    )
    return render_dot_to_svg(dot_source)


def _group_nodes(
    nodes_by_sequence_number: dict[int, GraphNode],
) -> tuple[list[GraphNode], list[tuple[int, list[GraphNode]]]]:
    ungrouped_nodes: list[GraphNode] = []
    grouped_nodes_map: dict[int, list[GraphNode]] = defaultdict(list)

    for node in nodes_by_sequence_number.values():
        if node.category_sequence_number is None:
            ungrouped_nodes.append(node)
            continue
        grouped_nodes_map[node.category_sequence_number].append(node)

    # Reverse emission order so lower sequence numbers tend to render higher.
    ungrouped_nodes.sort(key=lambda node: node.sequence_number, reverse=True)
    for nodes in grouped_nodes_map.values():
        nodes.sort(key=lambda node: node.sequence_number, reverse=True)

    # Reverse cluster emission order so earlier categories tend to render higher.
    grouped_nodes = sorted(grouped_nodes_map.items(), reverse=True)
    return ungrouped_nodes, grouped_nodes


def _visible_graph(graph: DependencyGraph) -> DependencyGraph:
    visible_nodes = {
        sequence_number: node
        for sequence_number, node in graph.nodes.items()
        if _include_node(node)
    }
    visible_edges = [
        edge
        for edge in graph.edges
        if edge.source_sequence_number in visible_nodes
        and edge.target_sequence_number in visible_nodes
    ]
    return DependencyGraph(nodes=visible_nodes, edges=visible_edges)


def _node_statement(node: GraphNode) -> str:
    attributes = {
        "label": _node_label(node),
        "tooltip": _node_tooltip(node),
    }

    if node.is_category:
        attributes["shape"] = "folder"
        attributes["style"] = "filled,rounded"
        attributes["fillcolor"] = "#e7edf5"

    parts = [f"{key}={_quote(value)}" for key, value in attributes.items()]
    return f"{_node_id(node.sequence_number)} [{', '.join(parts)}];"


def _node_label(node: GraphNode) -> str:
    title = node.display_name or node.name or f"Parameter {node.sequence_number}"
    subtitle = node.name or "-"
    if title == subtitle:
        return f"{title}\\n#{node.sequence_number}"
    return f"{title}\\n{subtitle}\\n#{node.sequence_number}"


def _node_tooltip(node: GraphNode) -> str:
    parts = [f"Sequence {node.sequence_number}"]
    if node.display_type is not None:
        parts.append(f"DisplayType: {node.display_type}")
    if node.category_display_name is not None and not node.is_category:
        parts.append(f"Category: {node.category_display_name}")
    return " | ".join(parts)


def _node_id(sequence_number: int) -> str:
    return f"n_{sequence_number}"


def _include_node(node: GraphNode) -> bool:
    return node.display_type != "rowaligner"


def _quote_id(value: str) -> str:
    return _quote(value)


def _quote(value: str) -> str:
    escaped = value.replace('"', '\\"')
    return f'"{escaped}"'
