import csv
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from rox_parser import GraphvizNotInstalledError, parse_parameters, parse_text
from rox_parser.__main__ import main


class ParseTextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.test_temp_root = Path(".test-temp")
        self.test_temp_root.mkdir(exist_ok=True)

    def _write_sample_file(self, source: str) -> Path:
        sample_dir = self.test_temp_root / uuid4().hex
        sample_dir.mkdir(parents=True, exist_ok=True)
        path = sample_dir / "sample.rox"
        path.write_text(source, encoding="utf-8")
        return path

    def _chdir(self, target: Path):
        class _ChangeDirectory:
            def __enter__(self_inner):
                self_inner._original = Path.cwd()
                os.chdir(target)
                return self_inner

            def __exit__(self_inner, exc_type, exc, tb):
                os.chdir(self_inner._original)
                return False

        return _ChangeDirectory()

    def test_parse_text_extracts_sorted_parameters(self) -> None:
        source = """
        <Offerings>
          <ServiceRequestTemplate>
            <Name>Example Template</Name>
            <IsFormOffering TypeCode="Boolean">False</IsFormOffering>
          </ServiceRequestTemplate>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <DisplayName>Second</DisplayName>
              <Name>second</Name>
              <SequenceNumber TypeCode="Int32">9</SequenceNumber>
              <DisplayType>datetime</DisplayType>
              <AutoFillOnlyWhenEmpty TypeCode="Boolean">False</AutoFillOnlyWhenEmpty>
              <Price TypeCode="Decimal">0.0000</Price>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <DisplayName>First</DisplayName>
              <Name>first</Name>
              <SequenceNumber TypeCode="Int32">5</SequenceNumber>
              <DisplayType>text</DisplayType>
              <AutoFillOnlyWhenEmpty TypeCode="Boolean">True</AutoFillOnlyWhenEmpty>
              <Price TypeCode="Decimal">10.5000</Price>
              <FieldTranslations TypeCode="Object" IsList="True">
                <FieldTranslation>
                  <FieldName>DisplayName</FieldName>
                </FieldTranslation>
              </FieldTranslations>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        document = parse_text(source)
        parameters = document.parameters

        self.assertEqual(document.name, "Example Template")
        self.assertIs(document.isRO, True)
        self.assertEqual(list(parameters), [5, 9])
        self.assertEqual(parameters[5].name, "first")
        self.assertEqual(parameters[5].display_name, "First")
        self.assertEqual(parameters[5].display_type, "text")
        self.assertIs(parameters[5].metadata["AutoFillOnlyWhenEmpty"], True)
        self.assertEqual(parameters[5].metadata["Price"], Decimal("10.5000"))
        self.assertEqual(
            parameters[5].metadata["FieldTranslations"],
            [{"FieldName": "DisplayName"}],
        )

    def test_parse_parameters_rejects_duplicate_sequence_numbers(self) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        with self.assertRaisesRegex(ValueError, "Duplicate SequenceNumber"):
            parse_parameters(source)

    def test_parse_text_returns_empty_mapping_when_parameters_are_missing(self) -> None:
        document = parse_text("<Offerings />")

        self.assertIsNone(document.name)
        self.assertIsNone(document.isRO)
        self.assertEqual(document.parameters, {})

    def test_parse_text_inverts_is_form_offering_for_is_ro(self) -> None:
        source = """
        <Offerings>
          <ServiceRequestTemplate>
            <Name>Form Offering</Name>
            <IsFormOffering TypeCode="Boolean">True</IsFormOffering>
          </ServiceRequestTemplate>
          <Parameters />
        </Offerings>
        """

        document = parse_text(source)

        self.assertEqual(document.name, "Form Offering")
        self.assertIs(document.isRO, False)

    def test_cli_prints_summary(self) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <DisplayName>First</DisplayName>
              <Name>first</Name>
              <SequenceNumber TypeCode="Int32">2</SequenceNumber>
              <DisplayType>text</DisplayType>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <DisplayName>Second</DisplayName>
              <Name>second</Name>
              <SequenceNumber TypeCode="Int32">5</SequenceNumber>
              <DisplayType>checkbox</DisplayType>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        path = self._write_sample_file(source).resolve()

        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main([str(path)])

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("sample.rox: 2 parameter(s)", output)
        self.assertIn("   2  first", output)
        self.assertIn("   5  second", output)

    def test_cli_prints_json_for_single_sequence(self) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <DisplayName>Only</DisplayName>
              <Name>only</Name>
              <SequenceNumber TypeCode="Int32">7</SequenceNumber>
              <DisplayType>text</DisplayType>
              <Price TypeCode="Decimal">10.5000</Price>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        path = self._write_sample_file(source).resolve()

        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main([str(path), "--param-sequence", "7", "--param-json"])

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn('"7"', output)
        self.assertIn('"Name": "only"', output)
        self.assertIn('"Price": "10.5000"', output)

    def test_cli_prints_csv(self) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <DisplayName>Only</DisplayName>
              <Name>only</Name>
              <SequenceNumber TypeCode="Int32">7</SequenceNumber>
              <DisplayType>text</DisplayType>
              <Price TypeCode="Decimal">10.5000</Price>
              <FieldTranslations TypeCode="Object" IsList="True">
                <FieldTranslation>
                  <FieldName>DisplayName</FieldName>
                </FieldTranslation>
              </FieldTranslations>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        path = self._write_sample_file(source).resolve()

        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main([str(path), "--param-csv"])

        output = stdout.getvalue()
        rows = list(csv.DictReader(StringIO(output)))

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["SequenceNumber"], "7")
        self.assertEqual(rows[0]["Name"], "only")
        self.assertEqual(rows[0]["Price"], "10.5000")
        self.assertEqual(
            rows[0]["FieldTranslations"],
            '[{"FieldName": "DisplayName"}]',
        )

    def test_cli_prints_dependencies_json(self) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_1</Name>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_2</Name>
              <SequenceNumber TypeCode="Int32">2</SequenceNumber>
              <RequiredExpression>FIELD_1</RequiredExpression>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        path = self._write_sample_file(source).resolve()

        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main([str(path), "--param-dependencies-json"])

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn('"source_name": "FIELD_1"', output)
        self.assertIn('"target_name": "FIELD_2"', output)
        self.assertIn('"expression_field": "RequiredExpression"', output)

    def test_cli_prints_dependencies_csv(self) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_1</Name>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_2</Name>
              <SequenceNumber TypeCode="Int32">2</SequenceNumber>
              <VisibilityExpression>FIELD_1</VisibilityExpression>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        path = self._write_sample_file(source).resolve()

        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main([str(path), "--param-dependencies-csv"])

        output = stdout.getvalue()
        rows = list(csv.DictReader(StringIO(output)))

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_name"], "FIELD_1")
        self.assertEqual(rows[0]["target_name"], "FIELD_2")
        self.assertEqual(rows[0]["expression_field"], "VisibilityExpression")

    def test_cli_prints_graph_dot(self) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <Name>CATEGORY_A</Name>
              <DisplayName>Category A</DisplayName>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
              <DisplayType>category</DisplayType>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_1</Name>
              <DisplayName>Field 1</DisplayName>
              <SequenceNumber TypeCode="Int32">2</SequenceNumber>
              <DisplayType>text</DisplayType>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_2</Name>
              <DisplayName>Field 2</DisplayName>
              <SequenceNumber TypeCode="Int32">3</SequenceNumber>
              <VisibilityExpression>FIELD_1</VisibilityExpression>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        path = self._write_sample_file(source).resolve()

        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main([str(path), "--param-graph-dot"])

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn('digraph "rox_form" {', output)
        self.assertIn("subgraph cluster_1 {", output)
        self.assertIn('n_2 -> n_3 [label="Vis"];', output)

    def test_cli_prints_reduced_graph_dot(self) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_1</Name>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_2</Name>
              <SequenceNumber TypeCode="Int32">2</SequenceNumber>
              <ValueExpression>FIELD_1</ValueExpression>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_3</Name>
              <SequenceNumber TypeCode="Int32">3</SequenceNumber>
              <ValueExpression>FIELD_1 || FIELD_2</ValueExpression>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        path = self._write_sample_file(source)

        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main([str(path), "--param-graph-dot", "--param-reduced"])

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn('n_1 -> n_2 [label="Val"];', output)
        self.assertIn('n_2 -> n_3 [label="Val"];', output)
        self.assertNotIn('n_1 -> n_3 [label="Val"];', output)

    def test_cli_prints_report_html(self) -> None:
        source = """
        <Offerings>
          <ServiceRequestTemplate>
            <Name>Example Template</Name>
            <IsFormOffering TypeCode="Boolean">False</IsFormOffering>
          </ServiceRequestTemplate>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <DisplayName>Only</DisplayName>
              <Name>FIELD_1</Name>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
              <DisplayType>text</DisplayType>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        path = self._write_sample_file(source)

        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main([str(path), "--param-report-html"])

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("<!DOCTYPE html>", output)
        self.assertIn('id="search"', output)
        self.assertIn("Example Template", output)
        self.assertIn('"display_name":"Only"', output)

    def test_cli_prints_reduced_report_html(self) -> None:
        source = """
        <Offerings>
          <ServiceRequestTemplate>
            <Name>Example Template</Name>
            <IsFormOffering TypeCode="Boolean">False</IsFormOffering>
          </ServiceRequestTemplate>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_1</Name>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_2</Name>
              <SequenceNumber TypeCode="Int32">2</SequenceNumber>
              <ValueExpression>FIELD_1</ValueExpression>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_3</Name>
              <SequenceNumber TypeCode="Int32">3</SequenceNumber>
              <ValueExpression>FIELD_1 || FIELD_2</ValueExpression>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        path = self._write_sample_file(source)

        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main([str(path), "--param-report-html", "--param-reduced"])

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn('"sequence_number":3', output)
        self.assertIn("Example Template", output)
        self.assertIn('"parents":["FIELD_2 (Val) #2"]', output)
        self.assertNotIn('"FIELD_1 (Val) #1","FIELD_2 (Val) #2"', output)

    def test_cli_prints_workflow_report_html(self) -> None:
        source = """
        <Offerings>
          <ServiceRequestTemplate>
            <Name>Example Template</Name>
            <IsFormOffering TypeCode="Boolean">False</IsFormOffering>
          </ServiceRequestTemplate>
          <WorkflowDefinition>
            &lt;WorkflowVersionInformation&gt;
              &lt;WorkflowDefinition&gt;
                &lt;Name&gt;Workflow A&lt;/Name&gt;
                &lt;Details&gt;
                  &amp;lt;scenario&amp;gt;
                    &amp;lt;blocks&amp;gt;
                      &amp;lt;block&amp;gt;
                        &amp;lt;id&amp;gt;BLOCK_START&amp;lt;/id&amp;gt;
                        &amp;lt;type&amp;gt;start&amp;lt;/type&amp;gt;
                        &amp;lt;title&amp;gt;Start&amp;lt;/title&amp;gt;
                        &amp;lt;layout&amp;gt;&amp;lt;x&amp;gt;10&amp;lt;/x&amp;gt;&amp;lt;y&amp;gt;20&amp;lt;/y&amp;gt;&amp;lt;/layout&amp;gt;
                        &amp;lt;blockProperties /&amp;gt;
                        &amp;lt;exits /&amp;gt;
                      &amp;lt;/block&amp;gt;
                    &amp;lt;/blocks&amp;gt;
                  &amp;lt;/scenario&amp;gt;
                &lt;/Details&gt;
                &lt;TriggerDetails&gt;
                  &amp;lt;BPETrigger&amp;gt;
                    &amp;lt;id&amp;gt;TRIGGER_1&amp;lt;/id&amp;gt;
                    &amp;lt;type&amp;gt;trigger&amp;lt;/type&amp;gt;
                    &amp;lt;layout&amp;gt;&amp;lt;x&amp;gt;5&amp;lt;/x&amp;gt;&amp;lt;y&amp;gt;5&amp;lt;/y&amp;gt;&amp;lt;/layout&amp;gt;
                    &amp;lt;blockProperties /&amp;gt;
                    &amp;lt;exits /&amp;gt;
                  &amp;lt;/BPETrigger&amp;gt;
                &lt;/TriggerDetails&gt;
              &lt;/WorkflowDefinition&gt;
            &lt;/WorkflowVersionInformation&gt;
          </WorkflowDefinition>
          <Parameters />
        </Offerings>
        """

        path = self._write_sample_file(source)

        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main([str(path), "--workflow-report-html"])

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("<!DOCTYPE html>", output)
        self.assertIn("Example Template", output)
        self.assertIn("Workflow A", output)
        self.assertIn('id="canvas-stage"', output)
        self.assertIn('"block_id":"BLOCK_START"', output)

    @patch("rox_parser.__main__.build_graph_svg", return_value="<svg>graph</svg>")
    def test_cli_exports_default_set(self, mock_build_graph_svg) -> None:
        source = """
        <Offerings>
          <ServiceRequestTemplate>
            <Name>Example Template</Name>
            <IsFormOffering TypeCode="Boolean">False</IsFormOffering>
          </ServiceRequestTemplate>
          <WorkflowDefinition>
            &lt;WorkflowVersionInformation&gt;
              &lt;WorkflowDefinition&gt;
                &lt;Name&gt;Workflow A&lt;/Name&gt;
                &lt;Details&gt;
                  &amp;lt;scenario&amp;gt;
                    &amp;lt;blocks&amp;gt;
                      &amp;lt;block&amp;gt;
                        &amp;lt;id&amp;gt;BLOCK_START&amp;lt;/id&amp;gt;
                        &amp;lt;type&amp;gt;start&amp;lt;/type&amp;gt;
                        &amp;lt;title&amp;gt;Start&amp;lt;/title&amp;gt;
                        &amp;lt;layout&amp;gt;&amp;lt;x&amp;gt;10&amp;lt;/x&amp;gt;&amp;lt;y&amp;gt;20&amp;lt;/y&amp;gt;&amp;lt;/layout&amp;gt;
                        &amp;lt;blockProperties /&amp;gt;
                        &amp;lt;exits /&amp;gt;
                      &amp;lt;/block&amp;gt;
                    &amp;lt;/blocks&amp;gt;
                  &amp;lt;/scenario&amp;gt;
                &lt;/Details&gt;
                &lt;TriggerDetails&gt;
                  &amp;lt;BPETrigger /&amp;gt;
                &lt;/TriggerDetails&gt;
              &lt;/WorkflowDefinition&gt;
            &lt;/WorkflowVersionInformation&gt;
          </WorkflowDefinition>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <DisplayName>Only</DisplayName>
              <Name>FIELD_1</Name>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
              <DisplayType>text</DisplayType>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        path = self._write_sample_file(source).resolve()
        stdout = StringIO()
        stderr = StringIO()
        with self._chdir(path.parent):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main([str(path), "--export-default-set"])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr.getvalue(), "")
            self.assertEqual(
                (path.parent / "graph.svg").read_text(encoding="utf-8"),
                "<svg>graph</svg>",
            )
            self.assertIn(
                "<!DOCTYPE html>",
                (path.parent / "param_report.html").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "<!DOCTYPE html>",
                (path.parent / "workflow_report.html").read_text(encoding="utf-8"),
            )
            self.assertIn("Wrote graph.svg", stdout.getvalue())
            self.assertIn("Wrote param_report.html", stdout.getvalue())
            self.assertIn("Wrote workflow_report.html", stdout.getvalue())

        mock_build_graph_svg.assert_called_once()

    @patch(
        "rox_parser.__main__.build_graph_svg",
        side_effect=GraphvizNotInstalledError("Graphviz 'dot' was not found."),
    )
    def test_cli_exports_default_set_with_warnings_and_continues(
        self,
        mock_build_graph_svg,
    ) -> None:
        source = """
        <Offerings>
          <ServiceRequestTemplate>
            <Name>Example Template</Name>
            <IsFormOffering TypeCode="Boolean">False</IsFormOffering>
          </ServiceRequestTemplate>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <DisplayName>Only</DisplayName>
              <Name>FIELD_1</Name>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
              <DisplayType>text</DisplayType>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        path = self._write_sample_file(source).resolve()
        stdout = StringIO()
        stderr = StringIO()
        with self._chdir(path.parent):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main([str(path), "--export-default-set"])

            self.assertEqual(exit_code, 0)
            self.assertFalse((path.parent / "graph.svg").exists())
            self.assertIn(
                "<!DOCTYPE html>",
                (path.parent / "param_report.html").read_text(encoding="utf-8"),
            )
            self.assertFalse((path.parent / "workflow_report.html").exists())
            self.assertIn("Wrote param_report.html", stdout.getvalue())
            self.assertIn("Warning: Graphviz 'dot' was not found.", stderr.getvalue())
            self.assertIn("Skipped graph.svg.", stderr.getvalue())
            self.assertIn("does not include a workflow definition", stderr.getvalue())

        mock_build_graph_svg.assert_called_once()

    def test_cli_rejects_non_ro_documents(self) -> None:
        source = """
        <Offerings>
          <ServiceRequestTemplate>
            <Name>Not RO</Name>
            <IsFormOffering TypeCode="Boolean">True</IsFormOffering>
          </ServiceRequestTemplate>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_1</Name>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        path = self._write_sample_file(source)

        stdout = StringIO()
        stderr = StringIO()
        with self.assertRaises(SystemExit) as error:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                main([str(path)])

        self.assertEqual(error.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("IsFormOffering is true", stderr.getvalue())

    @patch("rox_parser.__main__.build_graph_svg", return_value="<svg>graph</svg>")
    def test_cli_prints_graph_svg(self, mock_build_graph_svg) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_1</Name>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        path = self._write_sample_file(source)

        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main([str(path), "--param-graph-svg"])

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertEqual(output, "<svg>graph</svg>")
        mock_build_graph_svg.assert_called_once()

    @patch(
        "rox_parser.__main__.build_graph_svg",
        side_effect=GraphvizNotInstalledError("Graphviz 'dot' was not found."),
    )
    def test_cli_reports_graph_svg_fallback_error(self, mock_build_graph_svg) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_1</Name>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        path = self._write_sample_file(source)

        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main([str(path), "--param-graph-svg"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Graphviz 'dot' was not found.", stderr.getvalue())
        mock_build_graph_svg.assert_called_once()


if __name__ == "__main__":
    unittest.main()
