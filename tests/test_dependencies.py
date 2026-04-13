import unittest

from rox_parser import build_dependency_rows, extract_dependencies, parse_text


class DependencyTests(unittest.TestCase):
    def test_extract_dependencies_from_expression_fields(self) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <Name>EMPLOYEE</Name>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <Name>EMPLOYEE_2</Name>
              <SequenceNumber TypeCode="Int32">2</SequenceNumber>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <Name>TARGET_A</Name>
              <SequenceNumber TypeCode="Int32">3</SequenceNumber>
              <VisibilityExpression>IsNull(EMPLOYEE) = false</VisibilityExpression>
              <RequiredExpression>EMPLOYEE_2 &gt; 0</RequiredExpression>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        parameters = parse_text(source).parameters
        edges = extract_dependencies(parameters)

        self.assertEqual(len(edges), 2)
        edge_tuples = {
            (edge.source_name, edge.target_name, edge.expression_field)
            for edge in edges
        }
        self.assertEqual(
            edge_tuples,
            {
                ("EMPLOYEE", "TARGET_A", "VisibilityExpression"),
                ("EMPLOYEE_2", "TARGET_A", "RequiredExpression"),
            },
        )

    def test_extract_dependencies_uses_identifier_matches_not_substrings(self) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <Name>EMPLOYEE</Name>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <Name>TARGET_A</Name>
              <SequenceNumber TypeCode="Int32">2</SequenceNumber>
              <VisibilityExpression>MYEMPLOYEE = true</VisibilityExpression>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        parameters = parse_text(source).parameters

        self.assertEqual(extract_dependencies(parameters), [])

    def test_extract_dependencies_ignores_self_references_by_default(self) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <Name>SELF_1</Name>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
              <ValueExpression>SELF_1</ValueExpression>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        parameters = parse_text(source).parameters

        self.assertEqual(extract_dependencies(parameters), [])
        self.assertEqual(
            len(extract_dependencies(parameters, ignore_self_references=False)),
            1,
        )

    def test_build_dependency_rows_returns_plain_records(self) -> None:
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

        rows = build_dependency_rows(parse_text(source).parameters)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_name"], "FIELD_1")
        self.assertEqual(rows[0]["target_name"], "FIELD_2")
        self.assertEqual(rows[0]["expression_field"], "RequiredExpression")

    def test_duplicate_parameter_names_are_rejected(self) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_1</Name>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <Name>FIELD_1</Name>
              <SequenceNumber TypeCode="Int32">2</SequenceNumber>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        parameters = parse_text(source).parameters

        with self.assertRaisesRegex(ValueError, "Duplicate parameter Name"):
            extract_dependencies(parameters)


if __name__ == "__main__":
    unittest.main()
