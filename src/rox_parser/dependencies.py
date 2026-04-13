"""Dependency extraction for ROX parameter expressions."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from .core import Parameter

DEFAULT_EXPRESSION_FIELDS = (
    "TriggerFields",
    "AutoFillExpression",
    "ValueExpression",
    "VisibilityExpression",
    "RequiredExpression",
    "ReadOnlyExpression",
)

_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(slots=True, frozen=True)
class DependencyEdge:
    """A directed dependency edge between two parameters.

    An edge from source to target means the target parameter references the
    source parameter inside one of its expression fields.
    """

    source_sequence_number: int
    source_name: str
    target_sequence_number: int
    target_name: str
    expression_field: str
    expression_text: str
    matched_name: str

    def to_dict(self) -> dict[str, int | str]:
        """Return the dependency edge as a plain dictionary."""

        return asdict(self)


def extract_dependencies(
    parameters: dict[int, Parameter],
    *,
    expression_fields: Sequence[str] | None = None,
    ignore_self_references: bool = True,
) -> list[DependencyEdge]:
    """Extract rough dependency edges from parameter expression fields."""

    active_expression_fields = tuple(expression_fields or DEFAULT_EXPRESSION_FIELDS)
    parameters_by_name = _parameters_by_name(parameters)
    edges: list[DependencyEdge] = []
    seen_edges: set[tuple[int, int, str, str]] = set()

    for target_sequence_number, target_parameter in parameters.items():
        target_name = target_parameter.name
        if target_name is None:
            continue

        for expression_field in active_expression_fields:
            expression_text = _expression_text(target_parameter, expression_field)
            if expression_text is None:
                continue

            for matched_name in find_parameter_references(
                expression_text,
                parameters_by_name,
            ):
                source_sequence_number, _source_parameter = parameters_by_name[
                    matched_name
                ]
                if (
                    ignore_self_references
                    and source_sequence_number == target_sequence_number
                ):
                    continue

                edge_key = (
                    source_sequence_number,
                    target_sequence_number,
                    expression_field,
                    matched_name,
                )
                if edge_key in seen_edges:
                    continue

                seen_edges.add(edge_key)
                edges.append(
                    DependencyEdge(
                        source_sequence_number=source_sequence_number,
                        source_name=matched_name,
                        target_sequence_number=target_sequence_number,
                        target_name=target_name,
                        expression_field=expression_field,
                        expression_text=expression_text,
                        matched_name=matched_name,
                    )
                )

    return edges


def build_dependency_rows(
    parameters: dict[int, Parameter],
    *,
    expression_fields: Sequence[str] | None = None,
    ignore_self_references: bool = True,
) -> list[dict[str, int | str]]:
    """Return dependency edges as dictionaries for tabular workflows."""

    return [
        edge.to_dict()
        for edge in extract_dependencies(
            parameters,
            expression_fields=expression_fields,
            ignore_self_references=ignore_self_references,
        )
    ]


def find_parameter_references(
    expression_text: str,
    parameters_by_name: dict[str, tuple[int, Parameter]],
) -> list[str]:
    """Return unique parameter names referenced in the expression text."""

    matches: list[str] = []
    seen: set[str] = set()

    for token in extract_identifiers(expression_text):
        if token not in parameters_by_name or token in seen:
            continue
        seen.add(token)
        matches.append(token)

    return matches


def extract_identifiers(expression_text: str) -> list[str]:
    """Extract identifier-like tokens from an expression."""

    return _IDENTIFIER_PATTERN.findall(expression_text)


def _parameters_by_name(
    parameters: dict[int, Parameter],
) -> dict[str, tuple[int, Parameter]]:
    parameters_by_name: dict[str, tuple[int, Parameter]] = {}

    for sequence_number, parameter in parameters.items():
        name = parameter.name
        if name is None:
            continue
        if name in parameters_by_name:
            raise ValueError(f"Duplicate parameter Name found: {name}")
        parameters_by_name[name] = (sequence_number, parameter)

    return parameters_by_name


def _expression_text(parameter: Parameter, field_name: str) -> str | None:
    value = parameter.metadata.get(field_name)
    if not isinstance(value, str):
        return None

    stripped = value.strip()
    return stripped or None
