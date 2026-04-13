import unittest

from rox_parser import (
    build_dependency_graph,
    build_graph_nodes,
    build_graph_rows,
    parse_text,
    reduce_dependency_graph,
)


class GraphTests(unittest.TestCase):
    def test_build_graph_nodes_assigns_sections_from_category_parameters(self) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <Name>PRELUDE</Name>
              <DisplayName>Prelude</DisplayName>
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
              <Name>CATEGORY_B</Name>
              <DisplayName>Category B</DisplayName>
              <SequenceNumber TypeCode="Int32">4</SequenceNumber>
              <DisplayType>category</DisplayType>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_2</Name>
              <DisplayName>Field 2</DisplayName>
              <SequenceNumber TypeCode="Int32">5</SequenceNumber>
              <DisplayType>text</DisplayType>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        nodes = build_graph_nodes(parse_text(source).parameters)

        self.assertIsNone(nodes[1].category_sequence_number)
        self.assertTrue(nodes[2].is_category)
        self.assertEqual(nodes[2].category_sequence_number, 2)
        self.assertEqual(nodes[2].category_name, "CATEGORY_A")
        self.assertEqual(nodes[3].category_sequence_number, 2)
        self.assertEqual(nodes[3].category_display_name, "Category A")
        self.assertEqual(nodes[4].category_sequence_number, 4)
        self.assertEqual(nodes[5].category_name, "CATEGORY_B")

    def test_build_dependency_graph_merges_relationships_between_same_nodes(
        self,
    ) -> None:
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
              <VisibilityExpression>FIELD_1</VisibilityExpression>
              <ReadOnlyExpression>FIELD_1</ReadOnlyExpression>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        graph = build_dependency_graph(parse_text(source).parameters)

        self.assertEqual(len(graph.edges), 1)
        edge = graph.edges[0]
        self.assertEqual(edge.source_name, "FIELD_1")
        self.assertEqual(edge.target_name, "FIELD_2")
        self.assertEqual(
            edge.dependency_kinds,
            ("ReadOnlyExpression", "RequiredExpression", "VisibilityExpression"),
        )
        self.assertEqual(edge.dependency_labels, ("Read", "Req", "Vis"))
        self.assertEqual(edge.evidence["RequiredExpression"], ("FIELD_1",))

    def test_build_graph_rows_returns_plain_serializable_data(self) -> None:
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
              <ValueExpression>FIELD_1</ValueExpression>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        rows = build_graph_rows(parse_text(source).parameters)

        self.assertEqual(len(rows["nodes"]), 3)
        self.assertEqual(len(rows["edges"]), 1)
        self.assertEqual(rows["nodes"][1]["category_name"], "CATEGORY_A")
        self.assertEqual(rows["edges"][0]["dependency_labels"], ["Val"])

    def test_reduce_dependency_graph_removes_transitive_edges(self) -> None:
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
        reduced_graph = reduce_dependency_graph(graph)

        edge_pairs = {
            (edge.source_sequence_number, edge.target_sequence_number)
            for edge in reduced_graph.edges
        }
        self.assertEqual(edge_pairs, {(1, 2), (2, 3)})

    def test_reduce_dependency_graph_preserves_cycle_edges(self) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_1</Name>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
              <ValueExpression>FIELD_2</ValueExpression>
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
        reduced_graph = reduce_dependency_graph(graph)

        edge_pairs = {
            (edge.source_sequence_number, edge.target_sequence_number)
            for edge in reduced_graph.edges
        }
        self.assertEqual(edge_pairs, {(1, 2), (2, 1), (1, 3), (2, 3)})


if __name__ == "__main__":
    unittest.main()
