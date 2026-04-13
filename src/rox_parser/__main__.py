"""Command line interface for inspecting ROX parameters."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Sequence
from decimal import Decimal
from io import StringIO
from pathlib import Path
from typing import Any

from .core import Parameter, XmlValue, parse_file
from .dependencies import DependencyEdge, extract_dependencies
from .dot import GraphvizError, build_graph_dot, build_graph_svg
from .report import build_report_html
from .workflow import parse_workflow_from_document
from .workflow_report import build_workflow_report_html

_DEPENDENCY_FIELDNAMES = [
    "source_sequence_number",
    "source_name",
    "target_sequence_number",
    "target_name",
    "expression_field",
    "expression_text",
    "matched_name",
]


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ROX parser CLI."""

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.param_reduced and not (
        args.param_graph_dot or args.param_graph_svg or args.param_report_html
    ):
        parser.error(
            "--param-reduced is only supported with --param-graph-dot, --param-graph-svg, or --param-report-html."
        )
    if args.export_default_set and args.param_sequence is not None:
        parser.error("--param-sequence is not supported with --export-default-set.")
    if args.export_default_set and args.param_reduced:
        parser.error(
            "--param-reduced is not supported with --export-default-set because that bundle already uses reduced parameter outputs."
        )

    document = parse_file(args.path)
    _validate_document(
        document,
        parser,
        requires_name=(
            args.param_report_html
            or args.workflow_report_html
            or args.export_default_set
        ),
    )
    if args.export_default_set:
        return _export_default_set(document)

    if args.param_report_html:
        if args.param_sequence is not None:
            parser.error(
                "--param-sequence is only supported with parameter output modes."
            )
        print(
            build_report_html(
                document.parameters,
                document_name=document.name,
                reduced=args.param_reduced,
            ),
            end="",
        )
        return 0

    if args.workflow_report_html:
        if args.param_sequence is not None:
            parser.error(
                "--param-sequence is only supported with parameter output modes."
            )

        workflow = parse_workflow_from_document(document)
        if workflow is None:
            parser.error("This ROX document does not include a workflow definition.")

        print(
            build_workflow_report_html(
                workflow,
                document_name=document.name,
            ),
            end="",
        )
        return 0

    if args.param_graph_dot or args.param_graph_svg:
        if args.param_sequence is not None:
            parser.error(
                "--param-sequence is only supported with parameter output modes."
            )

        if args.param_graph_dot:
            print(build_graph_dot(document.parameters, reduced=args.param_reduced))
            return 0

        try:
            print(
                build_graph_svg(document.parameters, reduced=args.param_reduced),
                end="",
            )
        except GraphvizError as error:
            print(str(error), file=sys.stderr)
            return 1
        return 0

    if _uses_dependency_output(args):
        if args.param_sequence is not None:
            parser.error(
                "--param-sequence is only supported with parameter output modes."
            )

        dependencies = extract_dependencies(document.parameters)
        if args.param_dependencies_json:
            print(_dependencies_as_json(dependencies))
            return 0
        if args.param_dependencies_csv:
            print(_dependencies_as_csv(dependencies), end="")
            return 0

    parameters = document.parameters
    if args.param_sequence is not None:
        parameters = _select_parameter(parameters, args.param_sequence, parser)

    if args.param_json:
        print(_parameters_as_json(parameters))
        return 0
    if args.param_csv:
        print(_parameters_as_csv(parameters), end="")
        return 0

    print(_format_summary(Path(args.path), parameters))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rox_parser",
        description="Inspect parameters from a ROX XML file.",
    )
    parser.add_argument("path", help="Path to the .rox file to inspect.")
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--param-json",
        action="store_true",
        help="Print parameter data as JSON.",
    )
    output_group.add_argument(
        "--param-csv",
        action="store_true",
        help="Print parameter data as CSV.",
    )
    output_group.add_argument(
        "--param-dependencies-json",
        action="store_true",
        help="Print extracted dependency edges as JSON.",
    )
    output_group.add_argument(
        "--param-dependencies-csv",
        action="store_true",
        help="Print extracted dependency edges as CSV.",
    )
    output_group.add_argument(
        "--param-graph-dot",
        action="store_true",
        help="Print the merged dependency graph as Graphviz DOT.",
    )
    output_group.add_argument(
        "--param-graph-svg",
        action="store_true",
        help="Render the merged dependency graph as SVG using Graphviz.",
    )
    output_group.add_argument(
        "--param-report-html",
        action="store_true",
        help="Print a standalone HTML inspector report.",
    )
    output_group.add_argument(
        "--workflow-report-html",
        action="store_true",
        help="Print a standalone HTML workflow inspector report.",
    )
    output_group.add_argument(
        "--export-default-set",
        action="store_true",
        help="Write graph.svg, param_report.html, and workflow_report.html to the current directory.",
    )
    parser.add_argument(
        "--param-sequence",
        type=int,
        help="Show only a single parameter by SequenceNumber.",
    )
    parser.add_argument(
        "--param-reduced",
        action="store_true",
        help="Use a transitively reduced graph view with graph or report output modes.",
    )
    return parser


def _uses_dependency_output(args: argparse.Namespace) -> bool:
    return args.param_dependencies_json or args.param_dependencies_csv


def _export_default_set(document: Any) -> int:
    graph_path = Path("graph.svg")
    param_report_path = Path("param_report.html")
    workflow_report_path = Path("workflow_report.html")

    try:
        graph_path.write_text(
            build_graph_svg(document.parameters, reduced=True),
            encoding="utf-8",
        )
        print(f"Wrote {graph_path.name}")
    except GraphvizError as error:
        print(
            f"Warning: {error} Skipped {graph_path.name}.",
            file=sys.stderr,
        )

    param_report_path.write_text(
        build_report_html(
            document.parameters,
            document_name=document.name,
            reduced=True,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {param_report_path.name}")

    workflow = parse_workflow_from_document(document)
    if workflow is None:
        print(
            f"Warning: This ROX document does not include a workflow definition. Skipped {workflow_report_path.name}.",
            file=sys.stderr,
        )
        return 0

    workflow_report_path.write_text(
        build_workflow_report_html(
            workflow,
            document_name=document.name,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {workflow_report_path.name}")
    return 0


def _validate_document(
    document: Any,
    parser: argparse.ArgumentParser,
    *,
    requires_name: bool,
) -> None:
    if document.isRO is False:
        parser.error(
            "This ROX document is not supported because IsFormOffering is true (isRO is false)."
        )
    if requires_name and not document.name:
        parser.error("This ROX document does not include a template name.")


def _select_parameter(
    parameters: dict[int, Parameter],
    sequence_number: int,
    parser: argparse.ArgumentParser,
) -> dict[int, Parameter]:
    parameter = parameters.get(sequence_number)
    if parameter is None:
        parser.error(f"SequenceNumber {sequence_number} was not found.")
    return {sequence_number: parameter}


def _parameters_as_json(parameters: dict[int, Parameter]) -> str:
    payload = {
        str(sequence_number): _json_safe(parameter.to_dict())
        for sequence_number, parameter in parameters.items()
    }
    return json.dumps(payload, indent=2, sort_keys=False)


def _parameters_as_csv(parameters: dict[int, Parameter]) -> str:
    fieldnames = _csv_fieldnames(parameters)
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()

    for sequence_number, parameter in parameters.items():
        row = {"SequenceNumber": sequence_number}
        for fieldname in fieldnames[1:]:
            row[fieldname] = _csv_safe(parameter.metadata.get(fieldname))
        writer.writerow(row)

    return output.getvalue()


def _dependencies_as_json(dependencies: list[DependencyEdge]) -> str:
    return json.dumps([dependency.to_dict() for dependency in dependencies], indent=2)


def _dependencies_as_csv(dependencies: list[DependencyEdge]) -> str:
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=_DEPENDENCY_FIELDNAMES,
        lineterminator="\n",
    )
    writer.writeheader()

    for dependency in dependencies:
        writer.writerow(dependency.to_dict())

    return output.getvalue()


def _csv_fieldnames(parameters: dict[int, Parameter]) -> list[str]:
    metadata_fields = sorted(
        {
            key
            for parameter in parameters.values()
            for key in parameter.metadata
            if key != "SequenceNumber"
        }
    )
    return ["SequenceNumber", *metadata_fields]


def _csv_safe(value: XmlValue) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list | dict):
        return json.dumps(_json_safe(value), sort_keys=True)
    return str(value)


def _json_safe(value: XmlValue) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value


def _format_summary(path: Path, parameters: dict[int, Parameter]) -> str:
    lines = [f"{path.name}: {len(parameters)} parameter(s)"]
    if not parameters:
        return "\n".join(lines)

    for sequence_number, parameter in parameters.items():
        name = parameter.name or "-"
        display_name = parameter.display_name or "-"
        display_type = parameter.display_type or "-"
        lines.append(
            f"{sequence_number:>4}  {name:<25}  {display_name:<30}  {display_type}"
        )

    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
