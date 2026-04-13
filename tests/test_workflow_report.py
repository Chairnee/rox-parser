import json
import unittest
from datetime import UTC, datetime

from rox_parser import build_workflow_report_html, parse_workflow_text


class WorkflowReportTests(unittest.TestCase):
    def test_build_workflow_report_html_embeds_canvas_payload_and_inspector(
        self,
    ) -> None:
        workflow_text = """
        <WorkflowVersionInformation>
          <WorkflowDefinition>
            <Name>Workflow A</Name>
            <Details>
              &lt;scenario&gt;
                &lt;blocks&gt;
                  &lt;block&gt;
                    &lt;id&gt;BLOCK_START&lt;/id&gt;
                    &lt;type&gt;start&lt;/type&gt;
                    &lt;title&gt;Start&lt;/title&gt;
                    &lt;layout&gt;&lt;x&gt;10&lt;/x&gt;&lt;y&gt;20&lt;/y&gt;&lt;/layout&gt;
                    &lt;blockProperties /&gt;
                    &lt;exits&gt;
                      &lt;exit&gt;
                        &lt;title&gt;ok&lt;/title&gt;
                        &lt;links&gt;
                          &lt;link&gt;&lt;id&gt;LINK_1&lt;/id&gt;&lt;blockId&gt;BLOCK_TASK&lt;/blockId&gt;&lt;/link&gt;
                        &lt;/links&gt;
                      &lt;/exit&gt;
                    &lt;/exits&gt;
                  &lt;/block&gt;
                  &lt;block&gt;
                    &lt;id&gt;BLOCK_TASK&lt;/id&gt;
                    &lt;type&gt;task&lt;/type&gt;
                    &lt;title&gt;Task&lt;/title&gt;
                    &lt;layout&gt;&lt;x&gt;200&lt;/x&gt;&lt;y&gt;20&lt;/y&gt;&lt;/layout&gt;
                    &lt;blockProperties&gt;
                      &lt;property&gt;
                        &lt;name&gt;config&lt;/name&gt;
                        &lt;groups&gt;
                          &lt;group&gt;
                            &lt;param&gt;&lt;name&gt;enabled&lt;/name&gt;&lt;value&gt;yes&lt;/value&gt;&lt;/param&gt;
                          &lt;/group&gt;
                        &lt;/groups&gt;
                      &lt;/property&gt;
                    &lt;/blockProperties&gt;
                    &lt;exits /&gt;
                  &lt;/block&gt;
                &lt;/blocks&gt;
              &lt;/scenario&gt;
            </Details>
            <TriggerDetails>
              &lt;BPETrigger&gt;
                &lt;id&gt;TRIGGER_1&lt;/id&gt;
                &lt;type&gt;trigger&lt;/type&gt;
                &lt;layout&gt;&lt;x&gt;5&lt;/x&gt;&lt;y&gt;5&lt;/y&gt;&lt;/layout&gt;
                &lt;blockProperties&gt;
                  &lt;property&gt;
                    &lt;name&gt;starttype_block&lt;/name&gt;
                    &lt;groups&gt;
                      &lt;group&gt;&lt;param&gt;&lt;name&gt;starttype&lt;/name&gt;&lt;value&gt;Condition&lt;/value&gt;&lt;/param&gt;&lt;/group&gt;
                    &lt;/groups&gt;
                  &lt;/property&gt;
                  &lt;property&gt;
                    &lt;name&gt;contextblock&lt;/name&gt;
                    &lt;groups&gt;
                      &lt;group&gt;
                        &lt;param&gt;&lt;name&gt;created&lt;/name&gt;&lt;value&gt;yes&lt;/value&gt;&lt;/param&gt;
                        &lt;param&gt;&lt;name&gt;updated&lt;/name&gt;&lt;value&gt;yes&lt;/value&gt;&lt;/param&gt;
                      &lt;/group&gt;
                    &lt;/groups&gt;
                  &lt;/property&gt;
                  &lt;property&gt;
                    &lt;name&gt;trigger&lt;/name&gt;
                    &lt;groups&gt;
                      &lt;group&gt;
                        &lt;param&gt;&lt;name&gt;field&lt;/name&gt;&lt;value&gt;Status&lt;/value&gt;&lt;/param&gt;
                        &lt;param&gt;&lt;name&gt;operator&lt;/name&gt;&lt;value&gt;Equal to&lt;/value&gt;&lt;/param&gt;
                        &lt;param&gt;&lt;name&gt;value&lt;/name&gt;&lt;value&gt;Ready&lt;/value&gt;&lt;/param&gt;
                      &lt;/group&gt;
                    &lt;/groups&gt;
                  &lt;/property&gt;
                &lt;/blockProperties&gt;
                &lt;exits /&gt;
              &lt;/BPETrigger&gt;
            </TriggerDetails>
          </WorkflowDefinition>
          <QuickActions>
            <QuickAction>
              <Id>qa-1</Id>
              <Name>Insert</Name>
              <Definition>{"enabled": true}</Definition>
              <ActionType>insert</ActionType>
              <GroupName>default</GroupName>
            </QuickAction>
          </QuickActions>
        </WorkflowVersionInformation>
        """

        html = build_workflow_report_html(
            parse_workflow_text(workflow_text),
            document_name="Example Template",
            title="Workflow Inspector",
            generated_at=datetime(2026, 3, 25, 15, 45, tzinfo=UTC),
        )

        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("<title>Workflow Inspector</title>", html)
        self.assertIn("Example Template", html)
        self.assertIn("Workflow A", html)
        self.assertIn('id="canvas-stage"', html)
        self.assertIn('id="inspector"', html)
        self.assertIn('"block_id":"BLOCK_START"', html)
        self.assertIn("Trigger Conditions", html)
        self.assertIn('"name":"Insert"', html)
        self.assertIn('id="generated-at"', html)
        self.assertIn("2026-03-25T15:45:00Z", html)
        self.assertIn("function formatGeneratedTimestamp(value)", html)

    def test_build_workflow_report_html_preserves_literal_relative_positions(
        self,
    ) -> None:
        workflow_text = """
        <WorkflowVersionInformation>
          <WorkflowDefinition>
            <Name>Workflow A</Name>
            <Details>
              &lt;scenario&gt;
                &lt;blocks&gt;
                  &lt;block&gt;
                    &lt;id&gt;BLOCK_A&lt;/id&gt;
                    &lt;type&gt;task&lt;/type&gt;
                    &lt;title&gt;A&lt;/title&gt;
                    &lt;layout&gt;&lt;x&gt;100&lt;/x&gt;&lt;y&gt;100&lt;/y&gt;&lt;/layout&gt;
                    &lt;blockProperties /&gt;
                    &lt;exits /&gt;
                  &lt;/block&gt;
                  &lt;block&gt;
                    &lt;id&gt;BLOCK_B&lt;/id&gt;
                    &lt;type&gt;task&lt;/type&gt;
                    &lt;title&gt;B&lt;/title&gt;
                    &lt;layout&gt;&lt;x&gt;110&lt;/x&gt;&lt;y&gt;105&lt;/y&gt;&lt;/layout&gt;
                    &lt;blockProperties /&gt;
                    &lt;exits /&gt;
                  &lt;/block&gt;
                &lt;/blocks&gt;
              &lt;/scenario&gt;
            </Details>
            <TriggerDetails />
          </WorkflowDefinition>
        </WorkflowVersionInformation>
        """

        html = build_workflow_report_html(
            parse_workflow_text(workflow_text),
            document_name="Example Template",
        )

        marker = '<script id="workflow-report-data" type="application/json">\n'
        start = html.index(marker) + len(marker)
        end = html.index("\n  </script>", start)
        payload = json.loads(html[start:end])
        nodes = {node["block_id"]: node for node in payload["graph"]["nodes"]}

        self.assertEqual(
            nodes["BLOCK_B"]["display_x"] - nodes["BLOCK_A"]["display_x"],
            16,
        )
        self.assertEqual(
            nodes["BLOCK_B"]["display_y"] - nodes["BLOCK_A"]["display_y"],
            8,
        )

    def test_build_workflow_report_html_defaults_missing_y_to_lowest_known_y(
        self,
    ) -> None:
        workflow_text = """
        <WorkflowVersionInformation>
          <WorkflowDefinition>
            <Name>Workflow A</Name>
            <Details>
              &lt;scenario&gt;
                &lt;blocks&gt;
                  &lt;block&gt;
                    &lt;id&gt;BLOCK_TOP&lt;/id&gt;
                    &lt;type&gt;task&lt;/type&gt;
                    &lt;title&gt;Top&lt;/title&gt;
                    &lt;layout&gt;&lt;x&gt;100&lt;/x&gt;&lt;y&gt;100&lt;/y&gt;&lt;/layout&gt;
                    &lt;blockProperties /&gt;
                    &lt;exits /&gt;
                  &lt;/block&gt;
                  &lt;block&gt;
                    &lt;id&gt;BLOCK_BOTTOM&lt;/id&gt;
                    &lt;type&gt;task&lt;/type&gt;
                    &lt;title&gt;Bottom&lt;/title&gt;
                    &lt;layout&gt;&lt;x&gt;100&lt;/x&gt;&lt;y&gt;300&lt;/y&gt;&lt;/layout&gt;
                    &lt;blockProperties /&gt;
                    &lt;exits /&gt;
                  &lt;/block&gt;
                  &lt;block&gt;
                    &lt;id&gt;BLOCK_MISSING&lt;/id&gt;
                    &lt;type&gt;task&lt;/type&gt;
                    &lt;title&gt;Missing&lt;/title&gt;
                    &lt;blockProperties /&gt;
                    &lt;exits /&gt;
                  &lt;/block&gt;
                &lt;/blocks&gt;
              &lt;/scenario&gt;
            </Details>
            <TriggerDetails />
          </WorkflowDefinition>
        </WorkflowVersionInformation>
        """

        html = build_workflow_report_html(
            parse_workflow_text(workflow_text),
            document_name="Example Template",
        )

        marker = '<script id="workflow-report-data" type="application/json">\n'
        start = html.index(marker) + len(marker)
        end = html.index("\n  </script>", start)
        payload = json.loads(html[start:end])
        nodes = {node["block_id"]: node for node in payload["graph"]["nodes"]}

        self.assertEqual(nodes["BLOCK_MISSING"]["y"], 300)

    def test_build_workflow_report_html_expands_rect_block_for_many_exits(self) -> None:
        workflow_text = """
        <WorkflowVersionInformation>
          <WorkflowDefinition>
            <Name>Workflow A</Name>
            <Details>
              &lt;scenario&gt;
                &lt;blocks&gt;
                  &lt;block&gt;
                    &lt;id&gt;BLOCK_WAIT&lt;/id&gt;
                    &lt;type&gt;wait&lt;/type&gt;
                    &lt;title&gt;Wait&lt;/title&gt;
                    &lt;layout&gt;&lt;x&gt;100&lt;/x&gt;&lt;y&gt;100&lt;/y&gt;&lt;/layout&gt;
                    &lt;blockProperties /&gt;
                    &lt;exits&gt;
                      &lt;exit&gt;&lt;title&gt;one&lt;/title&gt;&lt;links&gt;&lt;link&gt;&lt;id&gt;L1&lt;/id&gt;&lt;blockId&gt;A&lt;/blockId&gt;&lt;/link&gt;&lt;/links&gt;&lt;/exit&gt;
                      &lt;exit&gt;&lt;title&gt;two&lt;/title&gt;&lt;links&gt;&lt;link&gt;&lt;id&gt;L2&lt;/id&gt;&lt;blockId&gt;B&lt;/blockId&gt;&lt;/link&gt;&lt;/links&gt;&lt;/exit&gt;
                      &lt;exit&gt;&lt;title&gt;three&lt;/title&gt;&lt;links&gt;&lt;link&gt;&lt;id&gt;L3&lt;/id&gt;&lt;blockId&gt;C&lt;/blockId&gt;&lt;/link&gt;&lt;/links&gt;&lt;/exit&gt;
                      &lt;exit&gt;&lt;title&gt;four&lt;/title&gt;&lt;links&gt;&lt;link&gt;&lt;id&gt;L4&lt;/id&gt;&lt;blockId&gt;D&lt;/blockId&gt;&lt;/link&gt;&lt;/links&gt;&lt;/exit&gt;
                    &lt;/exits&gt;
                  &lt;/block&gt;
                  &lt;block&gt;&lt;id&gt;A&lt;/id&gt;&lt;type&gt;task&lt;/type&gt;&lt;title&gt;A&lt;/title&gt;&lt;layout&gt;&lt;x&gt;300&lt;/x&gt;&lt;y&gt;50&lt;/y&gt;&lt;/layout&gt;&lt;blockProperties /&gt;&lt;exits /&gt;&lt;/block&gt;
                  &lt;block&gt;&lt;id&gt;B&lt;/id&gt;&lt;type&gt;task&lt;/type&gt;&lt;title&gt;B&lt;/title&gt;&lt;layout&gt;&lt;x&gt;300&lt;/x&gt;&lt;y&gt;100&lt;/y&gt;&lt;/layout&gt;&lt;blockProperties /&gt;&lt;exits /&gt;&lt;/block&gt;
                  &lt;block&gt;&lt;id&gt;C&lt;/id&gt;&lt;type&gt;task&lt;/type&gt;&lt;title&gt;C&lt;/title&gt;&lt;layout&gt;&lt;x&gt;300&lt;/x&gt;&lt;y&gt;150&lt;/y&gt;&lt;/layout&gt;&lt;blockProperties /&gt;&lt;exits /&gt;&lt;/block&gt;
                  &lt;block&gt;&lt;id&gt;D&lt;/id&gt;&lt;type&gt;task&lt;/type&gt;&lt;title&gt;D&lt;/title&gt;&lt;layout&gt;&lt;x&gt;300&lt;/x&gt;&lt;y&gt;200&lt;/y&gt;&lt;/layout&gt;&lt;blockProperties /&gt;&lt;exits /&gt;&lt;/block&gt;
                &lt;/blocks&gt;
              &lt;/scenario&gt;
            </Details>
            <TriggerDetails />
          </WorkflowDefinition>
        </WorkflowVersionInformation>
        """

        html = build_workflow_report_html(
            parse_workflow_text(workflow_text),
            document_name="Example Template",
        )

        marker = '<script id="workflow-report-data" type="application/json">\n'
        start = html.index(marker) + len(marker)
        end = html.index("\n  </script>", start)
        payload = json.loads(html[start:end])
        nodes = {node["block_id"]: node for node in payload["graph"]["nodes"]}

        self.assertGreater(nodes["BLOCK_WAIT"]["height"], 82)


if __name__ == "__main__":
    unittest.main()
