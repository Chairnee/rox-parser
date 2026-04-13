"""Graph-oriented views built from ROX parameter dependencies."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from graphlib import TopologicalSorter

from .core import Parameter
from .dependencies import DependencyEdge, extract_dependencies

DEPENDENCY_LABELS = {
    "TriggerFields": "Trig",
    "AutoFillExpression": "Val",
    "ValueExpression": "Val",
    "VisibilityExpression": "Vis",
    "RequiredExpression": "Req",
    "ReadOnlyExpression": "Read",
}

_PREFERRED_DEPENDENCY_KIND_ORDER = (
    "ReadOnlyExpression",
    "RequiredExpression",
    "ValueExpression",
    "VisibilityExpression",
)

_DEPENDENCY_LABEL_ORDER = {
    field_name: index
    for index, field_name in enumerate(_PREFERRED_DEPENDENCY_KIND_ORDER)
}


@dataclass(slots=True, frozen=True)
class GraphNode:
    """A parameter node enriched with lightweight layout metadata."""

    sequence_number: int
    name: str | None
    display_name: str | None
    display_type: str | None
    is_category: bool
    category_sequence_number: int | None
    category_name: str | None
    category_display_name: str | None

    def to_dict(self) -> dict[str, int | str | bool | None]:
        """Return the graph node as a plain dictionary."""

        return {
            "sequence_number": self.sequence_number,
            "name": self.name,
            "display_name": self.display_name,
            "display_type": self.display_type,
            "is_category": self.is_category,
            "category_sequence_number": self.category_sequence_number,
            "category_name": self.category_name,
            "category_display_name": self.category_display_name,
        }


@dataclass(slots=True, frozen=True)
class GraphEdge:
    """A merged dependency edge between two parameters."""

    source_sequence_number: int
    source_name: str
    target_sequence_number: int
    target_name: str
    dependency_kinds: tuple[str, ...]
    dependency_labels: tuple[str, ...]
    evidence: dict[str, tuple[str, ...]]

    def to_dict(self) -> dict[str, int | str | list[str] | dict[str, list[str]]]:
        """Return the graph edge as a plain dictionary."""

        return {
            "source_sequence_number": self.source_sequence_number,
            "source_name": self.source_name,
            "target_sequence_number": self.target_sequence_number,
            "target_name": self.target_name,
            "dependency_kinds": list(self.dependency_kinds),
            "dependency_labels": list(self.dependency_labels),
            "evidence": {
                field_name: list(expressions)
                for field_name, expressions in self.evidence.items()
            },
        }


@dataclass(slots=True, frozen=True)
class DependencyGraph:
    """A visualization-friendly graph built from ROX parameters."""

    nodes: dict[int, GraphNode]
    edges: list[GraphEdge]

    def to_dict(self) -> dict[str, list[dict[str, object]]]:
        """Return the graph as plain serializable data."""

        return {
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": [edge.to_dict() for edge in self.edges],
        }


def reduce_dependency_graph(graph: DependencyGraph) -> DependencyGraph:
    """Return a reduced graph while preserving cycle edges.

    Cycle edges are retained as-is. Non-cycle edges are transitively reduced
    after cycle edges are temporarily excluded from the reduction pass.
    """

    cycle_edge_indexes = _cycle_edge_indexes(graph.edges)
    preserved_cycle_edges = [
        edge for index, edge in enumerate(graph.edges) if index in cycle_edge_indexes
    ]
    reducible_edges = [
        edge
        for index, edge in enumerate(graph.edges)
        if index not in cycle_edge_indexes
    ]
    reduced_edges = _transitively_reduce_acyclic_edges(reducible_edges)
    edge_order = {id(edge): index for index, edge in enumerate(graph.edges)}
    merged_edges = preserved_cycle_edges + reduced_edges
    merged_edges.sort(key=lambda edge: edge_order[id(edge)])
    return DependencyGraph(nodes=dict(graph.nodes), edges=merged_edges)


def build_dependency_graph(
    parameters: dict[int, Parameter],
    *,
    expression_fields: Sequence[str] | None = None,
    ignore_self_references: bool = True,
) -> DependencyGraph:
    """Build a merged graph view from raw parameters."""

    nodes = build_graph_nodes(parameters)
    raw_edges = extract_dependencies(
        parameters,
        expression_fields=expression_fields,
        ignore_self_references=ignore_self_references,
    )
    edges = _merge_dependency_edges(raw_edges)
    return DependencyGraph(nodes=nodes, edges=edges)


def build_graph_nodes(parameters: dict[int, Parameter]) -> dict[int, GraphNode]:
    """Build graph nodes with first-pass category assignment."""

    nodes: dict[int, GraphNode] = {}
    active_category: Parameter | None = None

    for sequence_number, parameter in parameters.items():
        is_category = parameter.display_type == "category"
        if is_category:
            active_category = parameter

        nodes[sequence_number] = GraphNode(
            sequence_number=sequence_number,
            name=parameter.name,
            display_name=parameter.display_name,
            display_type=parameter.display_type,
            is_category=is_category,
            category_sequence_number=(
                active_category.sequence_number if active_category is not None else None
            ),
            category_name=active_category.name if active_category is not None else None,
            category_display_name=(
                active_category.display_name if active_category is not None else None
            ),
        )

    return nodes


def build_graph_rows(
    parameters: dict[int, Parameter],
    *,
    expression_fields: Sequence[str] | None = None,
    ignore_self_references: bool = True,
    reduced: bool = False,
) -> dict[str, list[dict[str, object]]]:
    """Return graph nodes and edges as plain dictionaries."""

    graph = build_dependency_graph(
        parameters,
        expression_fields=expression_fields,
        ignore_self_references=ignore_self_references,
    )
    if reduced:
        graph = reduce_dependency_graph(graph)
    return graph.to_dict()


def _merge_dependency_edges(edges: list[DependencyEdge]) -> list[GraphEdge]:
    merged: dict[tuple[int, int], _MergedEdgeState] = {}
    edge_order: list[tuple[int, int]] = []

    for edge in edges:
        key = (edge.source_sequence_number, edge.target_sequence_number)
        state = merged.get(key)
        if state is None:
            state = _MergedEdgeState(
                source_sequence_number=edge.source_sequence_number,
                source_name=edge.source_name,
                target_sequence_number=edge.target_sequence_number,
                target_name=edge.target_name,
            )
            merged[key] = state
            edge_order.append(key)

        state.add(edge)

    return [merged[key].freeze() for key in edge_order]


def _cycle_edge_indexes(edges: list[GraphEdge]) -> set[int]:
    component_by_node = _strongly_connected_components(edges)
    component_sizes: dict[int, int] = {}
    for component_id in component_by_node.values():
        component_sizes[component_id] = component_sizes.get(component_id, 0) + 1

    cycle_edge_indexes: set[int] = set()
    for index, edge in enumerate(edges):
        source_component = component_by_node.get(edge.source_sequence_number)
        target_component = component_by_node.get(edge.target_sequence_number)
        if source_component is None or target_component is None:
            continue
        if source_component != target_component:
            continue
        if component_sizes[source_component] > 1 or (
            edge.source_sequence_number == edge.target_sequence_number
        ):
            cycle_edge_indexes.add(index)

    return cycle_edge_indexes


def _strongly_connected_components(edges: list[GraphEdge]) -> dict[int, int]:
    adjacency: dict[int, list[int]] = {}
    nodes: set[int] = set()
    for edge in edges:
        nodes.add(edge.source_sequence_number)
        nodes.add(edge.target_sequence_number)
        adjacency.setdefault(edge.source_sequence_number, []).append(
            edge.target_sequence_number
        )
        adjacency.setdefault(edge.target_sequence_number, [])

    index_by_node: dict[int, int] = {}
    lowlink_by_node: dict[int, int] = {}
    component_by_node: dict[int, int] = {}
    stack: list[int] = []
    stack_nodes: set[int] = set()
    next_index = 0
    next_component = 0

    def visit(node: int) -> None:
        nonlocal next_index, next_component

        index_by_node[node] = next_index
        lowlink_by_node[node] = next_index
        next_index += 1
        stack.append(node)
        stack_nodes.add(node)

        for neighbor in adjacency[node]:
            if neighbor not in index_by_node:
                visit(neighbor)
                lowlink_by_node[node] = min(
                    lowlink_by_node[node],
                    lowlink_by_node[neighbor],
                )
            elif neighbor in stack_nodes:
                lowlink_by_node[node] = min(
                    lowlink_by_node[node],
                    index_by_node[neighbor],
                )

        if lowlink_by_node[node] != index_by_node[node]:
            return

        while True:
            component_node = stack.pop()
            stack_nodes.remove(component_node)
            component_by_node[component_node] = next_component
            if component_node == node:
                break
        next_component += 1

    for node in nodes:
        if node not in index_by_node:
            visit(node)

    return component_by_node


def _transitively_reduce_acyclic_edges(edges: list[GraphEdge]) -> list[GraphEdge]:
    if len(edges) < 2:
        return list(edges)

    adjacency: dict[int, set[int]] = {}
    edge_by_pair: dict[tuple[int, int], GraphEdge] = {}
    predecessors: dict[int, set[int]] = {}
    nodes: set[int] = set()

    for edge in edges:
        nodes.add(edge.source_sequence_number)
        nodes.add(edge.target_sequence_number)
        adjacency.setdefault(edge.source_sequence_number, set()).add(
            edge.target_sequence_number
        )
        adjacency.setdefault(edge.target_sequence_number, set())
        predecessors.setdefault(edge.target_sequence_number, set()).add(
            edge.source_sequence_number
        )
        predecessors.setdefault(edge.source_sequence_number, set())
        edge_by_pair[(edge.source_sequence_number, edge.target_sequence_number)] = edge

    topological_sorter = TopologicalSorter()
    for node in nodes:
        topological_sorter.add(node, *predecessors[node])
    topological_order = list(topological_sorter.static_order())

    descendants: dict[int, set[int]] = {node: set() for node in nodes}
    for node in reversed(topological_order):
        for neighbor in adjacency[node]:
            descendants[node].add(neighbor)
            descendants[node].update(descendants[neighbor])

    reduced_pairs: list[tuple[int, int]] = []
    for edge in edges:
        alternate_targets: set[int] = set()
        for neighbor in adjacency[edge.source_sequence_number]:
            if neighbor == edge.target_sequence_number:
                continue
            alternate_targets.add(neighbor)
            alternate_targets.update(descendants[neighbor])

        if edge.target_sequence_number in alternate_targets:
            continue
        reduced_pairs.append((edge.source_sequence_number, edge.target_sequence_number))

    return [edge_by_pair[pair] for pair in reduced_pairs]


@dataclass(slots=True)
class _MergedEdgeState:
    source_sequence_number: int
    source_name: str
    target_sequence_number: int
    target_name: str
    dependency_kinds: list[str] | None = None
    evidence: dict[str, list[str]] | None = None

    def __post_init__(self) -> None:
        self.dependency_kinds = []
        self.evidence = {}

    def add(self, edge: DependencyEdge) -> None:
        if edge.expression_field not in self.dependency_kinds:
            self.dependency_kinds.append(edge.expression_field)

        expressions = self.evidence.setdefault(edge.expression_field, [])
        if edge.expression_text not in expressions:
            expressions.append(edge.expression_text)

    def freeze(self) -> GraphEdge:
        ordered_dependency_kinds = tuple(
            sorted(self.dependency_kinds, key=_expression_field_sort_key)
        )
        dependency_labels = tuple(
            _label_for_expression_field(field_name)
            for field_name in ordered_dependency_kinds
        )
        evidence = {
            field_name: tuple(expressions)
            for field_name, expressions in self.evidence.items()
        }
        return GraphEdge(
            source_sequence_number=self.source_sequence_number,
            source_name=self.source_name,
            target_sequence_number=self.target_sequence_number,
            target_name=self.target_name,
            dependency_kinds=ordered_dependency_kinds,
            dependency_labels=dependency_labels,
            evidence=evidence,
        )


def _label_for_expression_field(field_name: str) -> str:
    if field_name in DEPENDENCY_LABELS:
        return DEPENDENCY_LABELS[field_name]
    if field_name.endswith("Expression"):
        return field_name.removesuffix("Expression")
    return field_name


def _expression_field_sort_key(field_name: str) -> tuple[int, str]:
    if field_name in _DEPENDENCY_LABEL_ORDER:
        return (_DEPENDENCY_LABEL_ORDER[field_name], field_name)
    return (len(_DEPENDENCY_LABEL_ORDER), field_name)
