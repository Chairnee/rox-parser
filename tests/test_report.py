import unittest
from datetime import UTC, datetime

from rox_parser import build_report_html, build_report_rows, parse_text


class ReportTests(unittest.TestCase):
    def test_build_report_rows_includes_relationships_and_search_text(self) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <DisplayName>Source</DisplayName>
              <Name>FIELD_1</Name>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
              <DisplayType>text</DisplayType>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <DisplayName>Target</DisplayName>
              <Name>FIELD_2</Name>
              <SequenceNumber TypeCode="Int32">2</SequenceNumber>
              <DisplayType>combo</DisplayType>
              <ValueExpression>FIELD_1</ValueExpression>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        rows = build_report_rows(parse_text(source).parameters)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].sequence_number, 1)
        self.assertEqual(rows[0].children, ["FIELD_2 (Val) #2"])
        self.assertEqual(rows[0].child_links[0].sequence_number, 2)
        self.assertEqual(
            rows[0].child_links[0].evidence_items[0].field_name,
            "ValueExpression",
        )
        self.assertEqual(
            rows[0].child_links[0].evidence_items[0].expression_text,
            "FIELD_1",
        )
        self.assertEqual(rows[1].parents, ["FIELD_1 (Val) #1"])
        self.assertEqual(rows[1].parent_links[0].sequence_number, 1)
        self.assertEqual(rows[1].expressions["ValueExpression"], "FIELD_1")
        self.assertIn("2", rows[1].search_text)
        self.assertIn("field_2", rows[1].search_text)
        self.assertIn("target", rows[1].search_text)
        self.assertIn("combo", rows[1].search_text)
        self.assertIn("field_1", rows[1].search_text)

    def test_build_report_rows_orders_relationships_by_sequence_number(self) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <DisplayName>Target</DisplayName>
              <Name>FIELD_10</Name>
              <SequenceNumber TypeCode="Int32">10</SequenceNumber>
              <DisplayType>text</DisplayType>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <DisplayName>Source B</DisplayName>
              <Name>FIELD_2</Name>
              <SequenceNumber TypeCode="Int32">2</SequenceNumber>
              <DisplayType>text</DisplayType>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <DisplayName>Source A</DisplayName>
              <Name>FIELD_1</Name>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
              <DisplayType>text</DisplayType>
            </ServiceRequestTemplateParameter>
            <ServiceRequestTemplateParameter>
              <DisplayName>Dependent</DisplayName>
              <Name>FIELD_20</Name>
              <SequenceNumber TypeCode="Int32">20</SequenceNumber>
              <DisplayType>text</DisplayType>
              <ValueExpression>FIELD_10 || FIELD_2 || FIELD_1</ValueExpression>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        rows = build_report_rows(parse_text(source).parameters)
        target_row = next(row for row in rows if row.sequence_number == 20)

        self.assertEqual(
            target_row.parents,
            [
                "FIELD_1 (Val) #1",
                "FIELD_2 (Val) #2",
                "FIELD_10 (Val) #10",
            ],
        )

    def test_build_report_rows_search_text_includes_expression_content(self) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <DisplayName>Only</DisplayName>
              <Name>FIELD_1</Name>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
              <DisplayType>text</DisplayType>
              <ValueExpression>$('The Student')</ValueExpression>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        rows = build_report_rows(parse_text(source).parameters)

        self.assertIn("the student", rows[0].search_text)

    def test_build_report_rows_includes_non_string_expression_metadata(self) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <DisplayName>Only</DisplayName>
              <Name>FIELD_1</Name>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
              <DisplayType>text</DisplayType>
              <AdHocValues TypeCode="Object" IsList="True">
                <ServiceRequestTemplateParameterAdHocValue>
                  <SortOrder TypeCode="Int32">2</SortOrder>
                  <ParameterValue>Beta</ParameterValue>
                  <Price TypeCode="Decimal">10.5000</Price>
                  <AttachmentRecId>ATTACH_2</AttachmentRecId>
                </ServiceRequestTemplateParameterAdHocValue>
                <ServiceRequestTemplateParameterAdHocValue>
                  <SortOrder TypeCode="Int32">1</SortOrder>
                  <ParameterValue>Alpha</ParameterValue>
                  <Price TypeCode="Decimal">0.0000</Price>
                  <AttachmentRecId>ATTACH_1</AttachmentRecId>
                </ServiceRequestTemplateParameterAdHocValue>
              </AdHocValues>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        rows = build_report_rows(parse_text(source).parameters)

        self.assertEqual(
            rows[0].expressions["AdHocValues"],
            '[{"SortOrder":1,"ParameterValue":"Alpha","Price":"0.0000","AttachmentRecId":"ATTACH_1"},{"SortOrder":2,"ParameterValue":"Beta","Price":"10.5000","AttachmentRecId":"ATTACH_2"}]',
        )
        self.assertIn("alpha", rows[0].search_text)
        self.assertIn("beta", rows[0].search_text)
        self.assertIn("attach_1", rows[0].search_text)
        self.assertIn("10.5000", rows[0].search_text)

    def test_build_report_rows_does_not_index_empty_expression_field_names(
        self,
    ) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <DisplayName>Only</DisplayName>
              <Name>FIELD_1</Name>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
              <DisplayType>text</DisplayType>
              <Description></Description>
              <HelpText></HelpText>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        rows = build_report_rows(parse_text(source).parameters)

        self.assertNotIn("description", rows[0].search_text)
        self.assertNotIn("helptext", rows[0].search_text)

    def test_build_report_rows_can_use_reduced_graph(self) -> None:
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

        rows = build_report_rows(parse_text(source).parameters, reduced=True)
        reduced_row = next(row for row in rows if row.sequence_number == 3)

        self.assertEqual(reduced_row.parents, ["FIELD_2 (Val) #2"])

    def test_build_report_html_embeds_rows_and_search_ui(self) -> None:
        source = """
        <Offerings>
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

        html = build_report_html(
            parse_text(source).parameters,
            document_name="Example Template",
            title="Inspector",
            generated_at=datetime(2026, 3, 25, 15, 45, tzinfo=UTC),
        )

        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("<title>Inspector</title>", html)
        self.assertIn('id="search"', html)
        self.assertIn('id="expand-all"', html)
        self.assertIn('id="collapse-all"', html)
        self.assertIn("Example Template", html)
        self.assertIn(
            "Parent/child relationships are hoverable and clickable.",
            html,
        )
        self.assertIn('"sequence_number":1', html)
        self.assertIn('"display_name":"Only"', html)
        self.assertIn('id="generated-at"', html)
        self.assertIn("2026-03-25T15:45:00Z", html)
        self.assertIn("Full dependency view", html)
        self.assertIn('data-row-toggle="${row.sequence_number}"', html)
        self.assertIn('data-target-sequence="${item.sequence_number}"', html)
        self.assertIn('data-relationship="${encodeRelationship(item)}"', html)
        self.assertIn("collapsedSummary(row.parent_links)", html)
        self.assertIn('id="relationship-preview"', html)
        self.assertIn("function highlightText(value, query)", html)
        self.assertIn("function showRelationshipPreview(target)", html)
        self.assertIn("function formatGeneratedTimestamp(value)", html)

    def test_build_report_html_shows_reduced_view_badge(self) -> None:
        source = """
        <Offerings>
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

        html = build_report_html(
            parse_text(source).parameters,
            document_name="Example Template",
            reduced=True,
            generated_at=datetime(2026, 3, 25, 5, 0, tzinfo=UTC),
        )

        self.assertIn("2026-03-25T05:00:00Z", html)
        self.assertIn("Reduced View", html)

    def test_build_report_html_escapes_script_breaking_html_strings(self) -> None:
        source = """
        <Offerings>
          <Parameters>
            <ServiceRequestTemplateParameter>
              <DisplayName>&lt;/script&gt;&lt;div&gt;Injected&lt;/div&gt;</DisplayName>
              <Name>FIELD_1</Name>
              <SequenceNumber TypeCode="Int32">1</SequenceNumber>
              <DisplayType>text</DisplayType>
              <ValueExpression>&lt;b&gt;bold&lt;/b&gt; &amp; &lt;/script&gt;</ValueExpression>
            </ServiceRequestTemplateParameter>
          </Parameters>
        </Offerings>
        """

        html = build_report_html(
            parse_text(source).parameters,
            document_name="Example Template",
        )

        self.assertIn(
            "\\u003c/script\\u003e\\u003cdiv\\u003eInjected\\u003c/div\\u003e", html
        )
        self.assertIn(
            "\\u003cb\\u003ebold\\u003c/b\\u003e \\u0026 \\u003c/script\\u003e", html
        )
        self.assertNotIn("</script><div>Injected</div>", html)


if __name__ == "__main__":
    unittest.main()
