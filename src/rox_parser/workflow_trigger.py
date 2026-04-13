"""Normalized trigger helpers for ROX workflow trigger details."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree as ET

from .workflow import WorkflowDocument


@dataclass(slots=True, frozen=True)
class WorkflowTriggerEvents:
    """Normalized workflow start-event flags."""

    created: bool
    updated: bool
    deleted: bool

    def to_dict(self) -> dict[str, bool]:
        """Return the event flags as serializable data."""

        return {
            "created": self.created,
            "updated": self.updated,
            "deleted": self.deleted,
        }


@dataclass(slots=True, frozen=True)
class WorkflowTriggerGroup:
    """One property group inside a trigger property."""

    params: dict[str, str | None]

    def to_dict(self) -> dict[str, str | None]:
        """Return the group as serializable data."""

        return dict(self.params)


@dataclass(slots=True, frozen=True)
class WorkflowTriggerProperty:
    """A trigger property with one or more grouped parameter sets."""

    name: str
    groups: tuple[WorkflowTriggerGroup, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return the property as serializable data."""

        return {
            "name": self.name,
            "groups": [group.to_dict() for group in self.groups],
        }


@dataclass(slots=True, frozen=True)
class WorkflowTriggerCondition:
    """One normalized workflow trigger condition."""

    child_object_name: str | None
    relationship_name: str | None
    field: str | None
    operator: str | None
    value: str | None

    def to_dict(self) -> dict[str, str | None]:
        """Return the condition as serializable data."""

        return {
            "child_object_name": self.child_object_name,
            "relationship_name": self.relationship_name,
            "field": self.field,
            "operator": self.operator,
            "value": self.value,
        }


@dataclass(slots=True, frozen=True)
class WorkflowTriggerModel:
    """A readable first-pass model of TriggerDetails."""

    trigger_id: str | None
    block_type: str | None
    title: str | None
    x: int | None
    y: int | None
    start_type: str | None
    events: WorkflowTriggerEvents
    logic: str | None
    conditions: tuple[WorkflowTriggerCondition, ...]
    properties: tuple[WorkflowTriggerProperty, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return the trigger model as serializable data."""

        return {
            "trigger_id": self.trigger_id,
            "block_type": self.block_type,
            "title": self.title,
            "x": self.x,
            "y": self.y,
            "start_type": self.start_type,
            "events": self.events.to_dict(),
            "logic": self.logic,
            "conditions": [condition.to_dict() for condition in self.conditions],
            "properties": [property_.to_dict() for property_ in self.properties],
        }


def build_workflow_trigger_model(
    workflow: WorkflowDocument,
) -> WorkflowTriggerModel | None:
    """Build a normalized trigger model from parsed workflow content."""

    if workflow.trigger_details.root_tag != "BPETrigger":
        return None

    trigger_text = (
        workflow.trigger_details.repaired_text or workflow.trigger_details.decoded_text
    )
    if not trigger_text:
        return None

    root = ET.fromstring(trigger_text)
    properties = _parse_trigger_properties(root)
    properties_by_name = {property_.name: property_ for property_ in properties}

    start_type = _property_param_value(
        properties_by_name.get("starttype_block"), "starttype"
    )
    events = WorkflowTriggerEvents(
        created=_property_param_flag(properties_by_name.get("contextblock"), "created"),
        updated=_property_param_flag(properties_by_name.get("contextblock"), "updated"),
        deleted=_property_param_flag(properties_by_name.get("contextblock"), "deleted"),
    )
    logic = _property_param_value(properties_by_name.get("logical"), "cond")
    conditions = _build_trigger_conditions(properties_by_name.get("trigger"))

    return WorkflowTriggerModel(
        trigger_id=_child_text(root, "id"),
        block_type=_child_text(root, "type"),
        title=_child_text(root, "title"),
        x=_layout_coordinate(root, "x"),
        y=_layout_coordinate(root, "y"),
        start_type=start_type,
        events=events,
        logic=logic,
        conditions=conditions,
        properties=properties,
    )


def _build_trigger_conditions(
    property_: WorkflowTriggerProperty | None,
) -> tuple[WorkflowTriggerCondition, ...]:
    if property_ is None:
        return ()

    conditions: list[WorkflowTriggerCondition] = []
    for group in property_.groups:
        condition = WorkflowTriggerCondition(
            child_object_name=group.params.get("childObjectName"),
            relationship_name=group.params.get("relationshipName"),
            field=group.params.get("field"),
            operator=group.params.get("operator"),
            value=group.params.get("value"),
        )
        if any(
            value is not None
            for value in (
                condition.child_object_name,
                condition.relationship_name,
                condition.field,
                condition.operator,
                condition.value,
            )
        ):
            conditions.append(condition)

    return tuple(conditions)


def _parse_trigger_properties(root: ET.Element) -> tuple[WorkflowTriggerProperty, ...]:
    block_properties = _find_first_child(root, "blockProperties")
    if block_properties is None:
        return ()

    properties: list[WorkflowTriggerProperty] = []
    for property_element in block_properties:
        if _local_name(property_element.tag) != "property":
            continue

        name = _child_text(property_element, "name")
        if name is None:
            continue

        groups_element = _find_first_child(property_element, "groups")
        groups: list[WorkflowTriggerGroup] = []
        if groups_element is not None:
            for group_element in groups_element:
                if _local_name(group_element.tag) != "group":
                    continue

                params: dict[str, str | None] = {}
                for param_element in group_element:
                    if _local_name(param_element.tag) != "param":
                        continue

                    param_name = _child_text(param_element, "name")
                    if param_name is None:
                        continue
                    params[param_name] = _child_text(param_element, "value")

                groups.append(WorkflowTriggerGroup(params=params))

        properties.append(WorkflowTriggerProperty(name=name, groups=tuple(groups)))

    return tuple(properties)


def _property_param_value(
    property_: WorkflowTriggerProperty | None,
    param_name: str,
) -> str | None:
    if property_ is None:
        return None
    for group in property_.groups:
        if param_name in group.params and group.params[param_name] is not None:
            return group.params[param_name]
    return None


def _property_param_flag(
    property_: WorkflowTriggerProperty | None,
    param_name: str,
) -> bool:
    value = _property_param_value(property_, param_name)
    return value in {"1", "true", "True", "yes", "Yes"}


def _layout_coordinate(root: ET.Element, axis: str) -> int | None:
    layout = _find_first_child(root, "layout")
    value = _child_text(layout, axis)
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
