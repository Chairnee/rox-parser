"""Tolerant extraction helpers for embedded ROX workflow definitions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Any
from xml.etree import ElementTree as ET

from .core import RoxDocument

_BARE_AMPERSAND_PATTERN = re.compile(r"&(?!#?[A-Za-z0-9]+;)")
_JS_NEW_DATE_PATTERN = re.compile(r"new Date\((\d+)\)")
_JS_UNDEFINED_PATTERN = re.compile(r"\bundefined\b")
_WORKFLOW_TIMEZONE = timezone(timedelta(hours=10))


@dataclass(slots=True, frozen=True)
class WorkflowWarning:
    """A non-fatal issue encountered while decoding workflow content."""

    code: str
    message: str
    section: str

    def to_dict(self) -> dict[str, str]:
        """Return the warning as serializable data."""

        return {
            "code": self.code,
            "message": self.message,
            "section": self.section,
        }


@dataclass(slots=True, frozen=True)
class WorkflowXmlSection:
    """A decoded embedded workflow XML section."""

    name: str
    raw_text: str | None
    decoded_text: str | None
    repaired_text: str | None
    root_tag: str | None
    parse_error: str | None
    warnings: tuple[WorkflowWarning, ...]

    @property
    def parsed(self) -> bool:
        """Return whether the section was parsed successfully."""

        return self.root_tag is not None

    def to_dict(self) -> dict[str, Any]:
        """Return the section as serializable data."""

        return {
            "name": self.name,
            "raw_text": self.raw_text,
            "decoded_text": self.decoded_text,
            "repaired_text": self.repaired_text,
            "root_tag": self.root_tag,
            "parse_error": self.parse_error,
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


@dataclass(slots=True, frozen=True)
class WorkflowQuickAction:
    """A quick action declared alongside the workflow definition."""

    id: str | None
    object_id: str | None
    name: str | None
    action_type: str | None
    group_name: str | None
    definition_text: str | None
    definition_json: dict[str, Any] | list[Any] | None

    def to_dict(self) -> dict[str, Any]:
        """Return the quick action as serializable data."""

        return {
            "id": self.id,
            "object_id": self.object_id,
            "name": self.name,
            "action_type": self.action_type,
            "group_name": self.group_name,
            "definition_text": self.definition_text,
            "definition_json": self.definition_json,
        }


@dataclass(slots=True, frozen=True)
class WorkflowDocument:
    """A tolerant first-pass decode of a ROX workflow definition."""

    raw_text: str
    definition_name: str | None
    workflow_type: str | None
    details: WorkflowXmlSection
    trigger_details: WorkflowXmlSection
    exception_handling_text: str | None
    quick_actions: tuple[WorkflowQuickAction, ...]
    warnings: tuple[WorkflowWarning, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return the workflow document as serializable data."""

        return {
            "raw_text": self.raw_text,
            "definition_name": self.definition_name,
            "workflow_type": self.workflow_type,
            "details": self.details.to_dict(),
            "trigger_details": self.trigger_details.to_dict(),
            "exception_handling_text": self.exception_handling_text,
            "quick_actions": [item.to_dict() for item in self.quick_actions],
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


def extract_workflow_definition_text(source: str) -> str | None:
    """Extract the raw WorkflowDefinition XML string from a ROX document."""

    root = ET.fromstring(source)
    workflow_element = _find_first_descendant(root, "WorkflowDefinition")
    if workflow_element is None:
        return None

    text = workflow_element.text or ""
    stripped = text.strip()
    return stripped or None


def parse_workflow_from_document(document: RoxDocument) -> WorkflowDocument | None:
    """Extract and parse workflow content from a parsed ROX document."""

    return parse_workflow_from_text(document.source)


def parse_workflow_from_text(source: str) -> WorkflowDocument | None:
    """Extract and parse workflow content from a ROX XML document."""

    workflow_text = extract_workflow_definition_text(source)
    if workflow_text is None:
        return None
    return parse_workflow_text(workflow_text)


def parse_workflow_text(workflow_text: str) -> WorkflowDocument:
    """Parse a raw WorkflowDefinition XML payload."""

    outer_root = ET.fromstring(workflow_text)
    warnings: list[WorkflowWarning] = []

    definition_element = _find_first_child(outer_root, "WorkflowDefinition")
    workflow_type_element = _find_first_child(outer_root, "WorkflowType")
    quick_actions_element = _find_first_child(outer_root, "QuickActions")

    definition_name = _child_text(definition_element, "Name")
    workflow_type = _text_or_none(
        workflow_type_element.text if workflow_type_element is not None else None
    )
    details = _parse_embedded_xml_section(
        "Details",
        _child_text(definition_element, "Details"),
    )
    trigger_details = _parse_embedded_xml_section(
        "TriggerDetails",
        _child_text(definition_element, "TriggerDetails"),
    )
    warnings.extend(details.warnings)
    warnings.extend(trigger_details.warnings)

    return WorkflowDocument(
        raw_text=workflow_text,
        definition_name=definition_name,
        workflow_type=workflow_type,
        details=details,
        trigger_details=trigger_details,
        exception_handling_text=_child_text(definition_element, "ExceptionHandling"),
        quick_actions=_parse_quick_actions(quick_actions_element, warnings),
        warnings=tuple(warnings),
    )


def _parse_embedded_xml_section(
    section_name: str,
    raw_text: str | None,
) -> WorkflowXmlSection:
    stripped = _text_or_none(raw_text)
    if stripped is None:
        return WorkflowXmlSection(
            name=section_name,
            raw_text=None,
            decoded_text=None,
            repaired_text=None,
            root_tag=None,
            parse_error=None,
            warnings=(),
        )

    decoded_text = _decode_embedded_text(stripped)
    warnings: list[WorkflowWarning] = []

    try:
        root = ET.fromstring(decoded_text)
        return WorkflowXmlSection(
            name=section_name,
            raw_text=stripped,
            decoded_text=decoded_text,
            repaired_text=decoded_text,
            root_tag=_local_name(root.tag),
            parse_error=None,
            warnings=(),
        )
    except ET.ParseError as error:
        repaired_text, repair_count = _repair_embedded_xml_text(decoded_text)
        if repair_count:
            warnings.append(
                WorkflowWarning(
                    code="repaired_bare_ampersands",
                    message=(
                        f"Escaped {repair_count} bare ampersand(s) before parsing."
                    ),
                    section=section_name,
                )
            )
            try:
                root = ET.fromstring(repaired_text)
                return WorkflowXmlSection(
                    name=section_name,
                    raw_text=stripped,
                    decoded_text=decoded_text,
                    repaired_text=repaired_text,
                    root_tag=_local_name(root.tag),
                    parse_error=None,
                    warnings=tuple(warnings),
                )
            except ET.ParseError as repaired_error:
                warnings.append(
                    WorkflowWarning(
                        code="xml_parse_error",
                        message=str(repaired_error),
                        section=section_name,
                    )
                )
                return WorkflowXmlSection(
                    name=section_name,
                    raw_text=stripped,
                    decoded_text=decoded_text,
                    repaired_text=repaired_text,
                    root_tag=None,
                    parse_error=str(repaired_error),
                    warnings=tuple(warnings),
                )

        warnings.append(
            WorkflowWarning(
                code="xml_parse_error",
                message=str(error),
                section=section_name,
            )
        )
        return WorkflowXmlSection(
            name=section_name,
            raw_text=stripped,
            decoded_text=decoded_text,
            repaired_text=decoded_text,
            root_tag=None,
            parse_error=str(error),
            warnings=tuple(warnings),
        )


def _parse_quick_actions(
    quick_actions_element: ET.Element | None,
    warnings: list[WorkflowWarning],
) -> tuple[WorkflowQuickAction, ...]:
    if quick_actions_element is None:
        return ()

    quick_actions: list[WorkflowQuickAction] = []
    for quick_action_element in quick_actions_element:
        if _local_name(quick_action_element.tag) != "QuickAction":
            continue

        definition_text = _child_text(quick_action_element, "Definition")
        definition_json = _parse_quick_action_definition(definition_text, warnings)

        quick_actions.append(
            WorkflowQuickAction(
                id=_child_text(quick_action_element, "Id"),
                object_id=_child_text(quick_action_element, "ObjectId"),
                name=_child_text(quick_action_element, "Name"),
                action_type=_child_text(quick_action_element, "ActionType"),
                group_name=_child_text(quick_action_element, "GroupName"),
                definition_text=definition_text,
                definition_json=definition_json,
            )
        )

    return tuple(quick_actions)


def _parse_quick_action_definition(
    definition_text: str | None,
    warnings: list[WorkflowWarning],
) -> dict[str, Any] | list[Any] | None:
    if not definition_text:
        return None

    normalized_text = _normalize_quick_action_definition_text(definition_text, warnings)
    try:
        return json.loads(normalized_text)
    except json.JSONDecodeError as error:
        warnings.append(
            WorkflowWarning(
                code="quick_action_definition_json_error",
                message=str(error),
                section="QuickActions",
            )
        )
        return None


def _normalize_quick_action_definition_text(
    definition_text: str,
    warnings: list[WorkflowWarning],
) -> str:
    normalized_text, date_count = _JS_NEW_DATE_PATTERN.subn(
        lambda match: json.dumps(_format_epoch_milliseconds_as_aest(match.group(1))),
        definition_text,
    )
    if date_count:
        warnings.append(
            WorkflowWarning(
                code="normalized_quick_action_dates",
                message=f"Normalized {date_count} JavaScript date value(s) to AEST.",
                section="QuickActions",
            )
        )

    normalized_text, undefined_count = _JS_UNDEFINED_PATTERN.subn(
        "null",
        normalized_text,
    )
    if undefined_count:
        warnings.append(
            WorkflowWarning(
                code="normalized_quick_action_undefined",
                message=f"Replaced {undefined_count} undefined value(s) with null.",
                section="QuickActions",
            )
        )

    return normalized_text


def _format_epoch_milliseconds_as_aest(epoch_milliseconds: str) -> str:
    moment = datetime.fromtimestamp(
        int(epoch_milliseconds) / 1000,
        tz=_WORKFLOW_TIMEZONE,
    )
    return moment.strftime("%d/%m/%Y %I:%M %p")


def _decode_embedded_text(text: str) -> str:
    decoded = text
    for _ in range(5):
        next_value = unescape(decoded)
        if next_value == decoded:
            return decoded
        decoded = next_value
    return decoded


def _repair_embedded_xml_text(text: str) -> tuple[str, int]:
    repaired_text, count = _BARE_AMPERSAND_PATTERN.subn("&amp;", text)
    return repaired_text, count


def _child_text(element: ET.Element | None, tag_name: str) -> str | None:
    if element is None:
        return None
    child = _find_first_child(element, tag_name)
    if child is None:
        return None
    return _text_or_none(child.text)


def _text_or_none(text: str | None) -> str | None:
    if text is None:
        return None
    stripped = text.strip()
    return stripped or None


def _find_first_descendant(element: ET.Element, tag_name: str) -> ET.Element | None:
    for descendant in element.iter():
        if _local_name(descendant.tag) == tag_name:
            return descendant
    return None


def _find_first_child(element: ET.Element, tag_name: str) -> ET.Element | None:
    for child in element:
        if _local_name(child.tag) == tag_name:
            return child
    return None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
