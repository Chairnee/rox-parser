"""Core parsing primitives for ROX files."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import TypeAlias
from xml.etree import ElementTree as ET

ScalarValue: TypeAlias = str | int | bool | Decimal | None
XmlValue: TypeAlias = ScalarValue | dict[str, "XmlValue"] | list["XmlValue"]


@dataclass(slots=True, frozen=True)
class Parameter:
    """A single parameter extracted from a ROX document."""

    sequence_number: int
    metadata: dict[str, XmlValue]

    @property
    def name(self) -> str | None:
        value = self.metadata.get("Name")
        return value if isinstance(value, str) else None

    @property
    def display_name(self) -> str | None:
        value = self.metadata.get("DisplayName")
        return value if isinstance(value, str) else None

    @property
    def display_type(self) -> str | None:
        value = self.metadata.get("DisplayType")
        return value if isinstance(value, str) else None

    def to_dict(self) -> dict[str, XmlValue]:
        """Return a shallow copy of the parsed metadata."""

        return dict(self.metadata)


@dataclass(slots=True)
class RoxDocument:
    """Parsed ROX document."""

    source: str
    name: str | None
    isRO: bool | None
    parameters: dict[int, Parameter]


def parse_text(source: str) -> RoxDocument:
    """Parse a ROX XML document from text."""

    root = ET.fromstring(source)
    name = _parse_template_name(root)
    is_ro = _parse_template_is_ro(root)
    parameters = _parse_parameters(root)
    return RoxDocument(source=source, name=name, isRO=is_ro, parameters=parameters)


def parse_file(path: str | Path) -> RoxDocument:
    """Parse a ROX XML document from disk."""

    source = Path(path).read_text(encoding="utf-8")
    return parse_text(source)


def parse_parameters(source: str) -> dict[int, Parameter]:
    """Return parameters keyed by sequence number in ascending order."""

    return parse_text(source).parameters


def _parse_parameters(root: ET.Element) -> dict[int, Parameter]:
    parameters_element = _find_first_descendant(root, "Parameters")
    if parameters_element is None:
        return {}

    parameters: dict[int, Parameter] = {}
    for parameter_element in parameters_element:
        if _local_name(parameter_element.tag) != "ServiceRequestTemplateParameter":
            continue

        metadata = _element_to_mapping(parameter_element)
        sequence_number = metadata.get("SequenceNumber")
        if not isinstance(sequence_number, int):
            raise ValueError("Each parameter must include an integer SequenceNumber.")
        if sequence_number in parameters:
            raise ValueError(f"Duplicate SequenceNumber found: {sequence_number}")

        parameters[sequence_number] = Parameter(
            sequence_number=sequence_number,
            metadata=metadata,
        )

    return dict(sorted(parameters.items()))


def _parse_template_name(root: ET.Element) -> str | None:
    template_element = _find_first_descendant(root, "ServiceRequestTemplate")
    if template_element is None:
        return None

    name_element = _find_first_child(template_element, "Name")
    if name_element is None:
        return None

    value = _element_to_value(name_element)
    return value if isinstance(value, str) else None


def _parse_template_is_ro(root: ET.Element) -> bool | None:
    template_element = _find_first_descendant(root, "ServiceRequestTemplate")
    if template_element is None:
        return None

    is_form_offering_element = _find_first_child(template_element, "IsFormOffering")
    if is_form_offering_element is None:
        return None

    value = _element_to_value(is_form_offering_element)
    if isinstance(value, bool):
        return not value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "false"}:
            return lowered == "false"
    return None


def _element_to_value(element: ET.Element) -> XmlValue:
    children = list(element)
    if not children:
        return _coerce_scalar(element)

    if element.attrib.get("IsList") == "True":
        return [_element_to_value(child) for child in children]

    return _element_to_mapping(element)


def _element_to_mapping(element: ET.Element) -> dict[str, XmlValue]:
    values: dict[str, XmlValue] = {}
    for child in element:
        key = _local_name(child.tag)
        value = _element_to_value(child)

        existing = values.get(key)
        if existing is None:
            values[key] = value
            continue

        if isinstance(existing, list):
            existing.append(value)
            continue

        values[key] = [existing, value]

    return values


def _coerce_scalar(element: ET.Element) -> ScalarValue:
    text = (element.text or "").strip()
    if text == "":
        return None

    type_code = element.attrib.get("TypeCode")
    if type_code == "Boolean":
        return text.lower() == "true"
    if type_code == "Int32":
        return int(text)
    if type_code == "Decimal":
        return Decimal(text)
    return text


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
