import unittest
from unittest.mock import patch

from rox_parser import (
    GraphvizNotInstalledError,
    GraphvizRenderError,
    build_dependency_graph,
    build_graph_dot,
    build_graph_svg,
    export_graph_to_dot,
    parse_text,
    render_dot_to_svg,
)


class DotTests(unittest.TestCase):
    def test_export_graph_to_dot_groups_category_nodes_in_clusters(self) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <Name>INTRO</Name>
              <DisplayName>Intro</DisplayName>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
              <DisplayType>text</DisplayType>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <Name>CATEGORY_A</Name>
              <DisplayName>Category A</DisplayName>
              <SequenceNumber TypeCode="Int32">2</SequenceNumber>
              <DisplayType>category</DisplayType>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_1</Name>
              <DisplayName>Field 1</DisplayName>
              <SequenceNumber TypeCode="Int32">3</SequenceNumber>
              <DisplayType>text</DisplayType>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_2</Name>
              <DisplayName>Field 2</DisplayName>
              <SequenceNumber TypeCode="Int32">4</SequenceNumber>
              <DisplayType>text</DisplayType>
              <VisibilityExpression>FIELD_1</VisibilityExpression>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        graph = build_dependency_graph(parse_text(source).parameters)
        dot = export_graph_to_dot(graph)

        self.assertIn('digraph "rox_form" {', dot)
        self.assertIn('n_1 [label="Intro\\nINTRO\\n#1"', dot)
        self.assertIn("subgraph cluster_2 {", dot)
        self.assertIn('label="Category A";', dot)
        self.assertIn('n_2 [label="Category A\\nCATEGORY_A\\n#2"', dot)
        self.assertIn('n_4 [label="Field 2\\nFIELD_2\\n#4"', dot)
        self.assertIn('n_3 -> n_4 [label="Vis"];', dot)

    def test_build_graph_dot_supports_custom_graph_name_and_escaping(self) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_QUOTE</Name>
              <DisplayName>Field "Quoted"</DisplayName>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
              <DisplayType>text</DisplayType>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        dot = build_graph_dot(
            parse_text(source).parameters,
            graph_name="quoted graph",
            rankdir="TB",
        )

        self.assertIn('digraph "quoted graph" {', dot)
        self.assertIn('graph [rankdir="TB"', dot)
        self.assertIn('label="Field \\"Quoted\\"\\nFIELD_QUOTE\\n#1"', dot)

    def test_export_graph_to_dot_reverses_cluster_emission_order(self) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <Name>CATEGORY_A</Name>
              <DisplayName>Category A</DisplayName>
              <SequenceNumber TypeCode="Int32">2</SequenceNumber>
              <DisplayType>category</DisplayType>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_1</Name>
              <SequenceNumber TypeCode="Int32">3</SequenceNumber>
              <DisplayType>text</DisplayType>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <Name>CATEGORY_B</Name>
              <DisplayName>Category B</DisplayName>
              <SequenceNumber TypeCode="Int32">4</SequenceNumber>
              <DisplayType>category</DisplayType>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_2</Name>
              <SequenceNumber TypeCode="Int32">5</SequenceNumber>
              <DisplayType>text</DisplayType>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        graph = build_dependency_graph(parse_text(source).parameters)
        dot = export_graph_to_dot(graph)

        self.assertLess(
            dot.index("subgraph cluster_4 {"), dot.index("subgraph cluster_2 {")
        )

    def test_export_graph_to_dot_omits_rowaligner_nodes(self) -> None:
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
              <Name>ROW_ALIGNER_1</Name>
              <DisplayName>Row Aligner 1</DisplayName>
              <SequenceNumber TypeCode="Int32">2</SequenceNumber>
              <DisplayType>rowaligner</DisplayType>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_1</Name>
              <DisplayName>Field 1</DisplayName>
              <SequenceNumber TypeCode="Int32">3</SequenceNumber>
              <DisplayType>text</DisplayType>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_2</Name>
              <DisplayName>Field 2</DisplayName>
              <SequenceNumber TypeCode="Int32">4</SequenceNumber>
              <VisibilityExpression>ROW_ALIGNER_1 || FIELD_1</VisibilityExpression>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        graph = build_dependency_graph(parse_text(source).parameters)
        dot = export_graph_to_dot(graph)

        self.assertNotIn("ROW_ALIGNER_1", dot)
        self.assertNotIn('n_2 [label="Row Aligner 1\\nROW_ALIGNER_1\\n#2"', dot)
        self.assertNotIn("n_2 -> n_4", dot)
        self.assertIn('n_3 -> n_4 [label="Vis"];', dot)

    def test_export_graph_to_dot_supports_reduced_view(self) -> None:
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

        graph = build_dependency_graph(parse_text(source).parameters)
        dot = export_graph_to_dot(graph, reduced=True)

        self.assertIn('n_1 -> n_2 [label="Val"];', dot)
        self.assertIn('n_2 -> n_3 [label="Val"];', dot)
        self.assertNotIn('n_1 -> n_3 [label="Val"];', dot)

    @patch("rox_parser.dot.subprocess.run")
    @patch("rox_parser.dot.shutil.which")
    def test_render_dot_to_svg_returns_svg_output(
        self,
        mock_which,
        mock_run,
    ) -> None:
        mock_which.return_value = "dot"
        mock_run.return_value = type(
            "CompletedProcess",
            (),
            {"returncode": 0, "stdout": "<svg>ok</svg>", "stderr": ""},
        )()

        svg = render_dot_to_svg('digraph "x" {}')

        self.assertEqual(svg, "<svg>ok</svg>")
        mock_run.assert_called_once()

    @patch("rox_parser.dot.shutil.which", return_value=None)
    def test_render_dot_to_svg_raises_when_graphviz_is_missing(
        self, mock_which
    ) -> None:
        with self.assertRaisesRegex(GraphvizNotInstalledError, "Graphviz 'dot'"):
            render_dot_to_svg('digraph "x" {}')

    @patch("rox_parser.dot.subprocess.run")
    @patch("rox_parser.dot.shutil.which")
    def test_render_dot_to_svg_raises_when_graphviz_fails(
        self,
        mock_which,
        mock_run,
    ) -> None:
        mock_which.return_value = "dot"
        mock_run.return_value = type(
            "CompletedProcess",
            (),
            {"returncode": 1, "stdout": "", "stderr": "render failed"},
        )()

        with self.assertRaisesRegex(GraphvizRenderError, "render failed"):
            render_dot_to_svg('digraph "x" {}')

    @patch("rox_parser.dot.render_dot_to_svg", return_value="<svg>graph</svg>")
    def test_build_graph_svg_uses_dot_renderer(self, mock_render_dot_to_svg) -> None:
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

        svg = build_graph_svg(parse_text(source).parameters)

        self.assertEqual(svg, "<svg>graph</svg>")
        mock_render_dot_to_svg.assert_called_once()


if __name__ == "__main__":
    unittest.main()
