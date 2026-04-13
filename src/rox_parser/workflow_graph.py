"""Normalized graph views for ROX workflow scenario definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree as ET

from .workflow import WorkflowDocument


@dataclass(slots=True, frozen=True)
class WorkflowPropertyGroup:
    """A single parameter group within a workflow block property."""

    params: dict[str, str | None]

    def to_dict(self) -> dict[str, str | None]:
        """Return the group as serializable data."""

        return dict(self.params)


@dataclass(slots=True, frozen=True)
class WorkflowBlockProperty:
    """A named property attached to a workflow block."""

    name: str
    groups: tuple[WorkflowPropertyGroup, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return the property as serializable data."""

        return {
            "name": self.name,
            "groups": [group.to_dict() for group in self.groups],
        }


@dataclass(slots=True, frozen=True)
class WorkflowGraphNode:
    """A normalized workflow block node."""

    block_id: str
    block_type: str | None
    title: str | None
    x: int | None
    y: int | None
    properties: tuple[WorkflowBlockProperty, ...]
    exits: tuple[WorkflowBlockExit, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return the node as serializable data."""

        return {
            "block_id": self.block_id,
            "block_type": self.block_type,
            "title": self.title,
            "x": self.x,
            "y": self.y,
            "properties": [item.to_dict() for item in self.properties],
            "exits": [item.to_dict() for item in self.exits],
        }


@dataclass(slots=True, frozen=True)
class WorkflowGraphEdge:
    """A directed edge between workflow blocks."""

    link_id: str | None
    source_block_id: str
    source_exit_id: str | None
    source_exit_title: str | None
    source_exit_condition: str | None
    source_exit_properties: tuple[WorkflowBlockProperty, ...]
    target_block_id: str

    def to_dict(self) -> dict[str, Any]:
        """Return the edge as serializable data."""

        return {
            "link_id": self.link_id,
            "source_block_id": self.source_block_id,
            "source_exit_id": self.source_exit_id,
            "source_exit_title": self.source_exit_title,
            "source_exit_condition": self.source_exit_condition,
            "source_exit_properties": [
                item.to_dict() for item in self.source_exit_properties
            ],
            "target_block_id": self.target_block_id,
        }


@dataclass(slots=True, frozen=True)
class WorkflowBlockExit:
    """A named exit attached to a workflow block."""

    exit_id: str | None
    title: str | None
    condition: str | None
    properties: tuple[WorkflowBlockProperty, ...]
    target_block_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return the exit as serializable data."""

        return {
            "exit_id": self.exit_id,
            "title": self.title,
            "condition": self.condition,
            "properties": [item.to_dict() for item in self.properties],
            "target_block_ids": list(self.target_block_ids),
        }


@dataclass(slots=True, frozen=True)
class WorkflowGraph:
    """A normalized graph built from workflow scenario Details."""

    nodes: dict[str, WorkflowGraphNode]
    edges: tuple[WorkflowGraphEdge, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return the graph as serializable data."""

        return {
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": [edge.to_dict() for edge in self.edges],
        }


def build_workflow_graph(workflow: WorkflowDocument) -> WorkflowGraph | None:
    """Build a normalized graph from a parsed workflow Details section."""

    details_text = workflow.details.repaired_text or workflow.details.decoded_text
    if not details_text or workflow.details.root_tag != "scenario":
        return None

    scenario_root = ET.fromstring(details_text)
    blocks_element = _find_first_child(scenario_root, "blocks")
    if blocks_element is None:
        return WorkflowGraph(nodes={}, edges=())

    nodes: dict[str, WorkflowGraphNode] = {}
    edges: list[WorkflowGraphEdge] = []

    for block_element in blocks_element:
        if _local_name(block_element.tag) != "block":
            continue

        block_id = _child_text(block_element, "id")
        if not block_id:
            continue

        block_exits = _parse_block_exits(block_element)
        nodes[block_id] = WorkflowGraphNode(
            block_id=block_id,
            block_type=_child_text(block_element, "type"),
            title=_child_text(block_element, "title"),
            x=_layout_coordinate(block_element, "x"),
            y=_layout_coordinate(block_element, "y"),
            properties=_parse_block_properties(block_element),
            exits=block_exits,
        )
        edges.extend(_parse_block_edges(block_id, block_exits))

    return WorkflowGraph(nodes=nodes, edges=tuple(edges))


def _parse_block_properties(
    block_element: ET.Element,
) -> tuple[WorkflowBlockProperty, ...]:
    block_properties_element = _find_first_child(block_element, "blockProperties")
    if block_properties_element is None:
        return ()

    return _parse_property_elements(block_properties_element)


def _parse_property_elements(
    container_element: ET.Element,
) -> tuple[WorkflowBlockProperty, ...]:
    """Parse workflow property elements from a container element."""

    properties: list[WorkflowBlockProperty] = []
    for property_element in container_element:
        if _local_name(property_element.tag) != "property":
            continue

        name = _child_text(property_element, "name") or "(unnamed)"
        groups_element = _find_first_child(property_element, "groups")
        groups: list[WorkflowPropertyGroup] = []
        if groups_element is not None:
            for group_element in groups_element:
                if _local_name(group_element.tag) != "group":
                    continue
                params: dict[str, str | None] = {}
                for param_element in group_element:
                    if _local_name(param_element.tag) != "param":
                        continue
                    param_name = _child_text(param_element, "name")
                    if not param_name:
                        continue
                    params[param_name] = _child_text(param_element, "value")
                groups.append(WorkflowPropertyGroup(params=params))

        properties.append(
            WorkflowBlockProperty(
                name=name,
                groups=tuple(groups),
            )
        )

    return tuple(properties)


def _parse_block_exits(block_element: ET.Element) -> tuple[WorkflowBlockExit, ...]:
    exits_element = _find_first_child(block_element, "exits")
    if exits_element is None:
        return ()

    exits: list[WorkflowBlockExit] = []
    for exit_element in exits_element:
        if _local_name(exit_element.tag) != "exit":
            continue

        exit_id = _child_text(exit_element, "id")
        exit_title = _child_text(exit_element, "title")
        exit_condition = _child_text(exit_element, "condition")
        condition_element = _find_first_child(exit_element, "condition")
        exit_properties = (
            _parse_property_elements(condition_element)
            if condition_element is not None
            else ()
        )
        links_element = _find_first_child(exit_element, "links")
        target_block_ids: list[str] = []
        if links_element is not None:
            for link_element in links_element:
                if _local_name(link_element.tag) != "link":
                    continue
                target_block_id = _child_text(link_element, "blockId")
                if target_block_id:
                    target_block_ids.append(target_block_id)

        exits.append(
            WorkflowBlockExit(
                exit_id=exit_id,
                title=exit_title,
                condition=exit_condition,
                properties=exit_properties,
                target_block_ids=tuple(target_block_ids),
            )
        )

    return tuple(exits)


def _parse_block_edges(
    block_id: str,
    block_exits: tuple[WorkflowBlockExit, ...],
) -> list[WorkflowGraphEdge]:
    edges: list[WorkflowGraphEdge] = []
    for block_exit in block_exits:
        for target_block_id in block_exit.target_block_ids:
            edges.append(
                WorkflowGraphEdge(
                    link_id=None,
                    source_block_id=block_id,
                    source_exit_id=block_exit.exit_id,
                    source_exit_title=block_exit.title,
                    source_exit_condition=block_exit.condition,
                    source_exit_properties=block_exit.properties,
                    target_block_id=target_block_id,
                )
            )

    return edges


def _layout_coordinate(block_element: ET.Element, coordinate_name: str) -> int | None:
    layout_element = _find_first_child(block_element, "layout")
    if layout_element is None:
        return None
    value = _child_text(layout_element, coordinate_name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _child_text(element: ET.Element | None, tag_name: str) -> str | None:
    if element is None:
        return None
    child = _find_first_child(element, tag_name)
    if child is None or child.text is None:
        return None
    stripped = child.text.strip()
    return stripped or None


def _find_first_child(element: ET.Element, tag_name: str) -> ET.Element | None:
    for child in element:
        if _local_name(child.tag) == tag_name:
            return child
    return None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
