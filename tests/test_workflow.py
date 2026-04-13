import unittest

from rox_parser import (
    build_workflow_graph,
    build_workflow_trigger_model,
    extract_workflow_definition_text,
    parse_text,
    parse_workflow_from_document,
    parse_workflow_from_text,
    parse_workflow_text,
)


class WorkflowTests(unittest.TestCase):
    def test_extract_workflow_definition_text_from_rox_source(self) -> None:
        source = """
        <Offerings>
          <WorkflowDefinition>&lt;WorkflowVersionInformation /&gt;</WorkflowDefinition>
        </Offerings>
        """

        workflow_text = extract_workflow_definition_text(source)

        self.assertEqual(workflow_text, "<WorkflowVersionInformation />")

    def test_parse_workflow_text_decodes_nested_sections_and_quick_actions(
        self,
    ) -> None:
        workflow_text = """
        <WorkflowVersionInformation>
          <WorkflowDefinition>
            <Name>Workflow A</Name>
            <Details>&lt;scenario&gt;&lt;id&gt;1&lt;/id&gt;&lt;title&gt;Simple&lt;/title&gt;&lt;/scenario&gt;</Details>
            <TriggerDetails>&lt;BPETrigger&gt;&lt;id&gt;T1&lt;/id&gt;&lt;/BPETrigger&gt;</TriggerDetails>
            <ExceptionHandling>ignore</ExceptionHandling>
          </WorkflowDefinition>
          <WorkflowType>manual</WorkflowType>
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

        workflow = parse_workflow_text(workflow_text)

        self.assertEqual(workflow.definition_name, "Workflow A")
        self.assertEqual(workflow.workflow_type, "manual")
        self.assertEqual(workflow.details.root_tag, "scenario")
        self.assertEqual(workflow.trigger_details.root_tag, "BPETrigger")
        self.assertEqual(workflow.exception_handling_text, "ignore")
        self.assertEqual(len(workflow.quick_actions), 1)
        self.assertEqual(workflow.quick_actions[0].name, "Insert")
        self.assertEqual(workflow.quick_actions[0].definition_json, {"enabled": True})
        self.assertEqual(workflow.warnings, ())

    def test_parse_workflow_text_normalizes_javascript_dates_to_aest_strings(
        self,
    ) -> None:
        workflow_text = """
        <WorkflowVersionInformation>
          <WorkflowDefinition>
            <Name>Workflow A</Name>
            <Details>&lt;scenario /&gt;</Details>
            <TriggerDetails />
            <ExceptionHandling />
          </WorkflowDefinition>
          <QuickActions>
            <QuickAction>
              <Id>qa-1</Id>
              <Name>Insert</Name>
              <Definition>{"CreatedDateTime":new Date(1774405020000)}</Definition>
              <ActionType>insert</ActionType>
              <GroupName>default</GroupName>
            </QuickAction>
          </QuickActions>
        </WorkflowVersionInformation>
        """

        workflow = parse_workflow_text(workflow_text)

        self.assertEqual(
            workflow.quick_actions[0].definition_json,
            {"CreatedDateTime": "25/03/2026 12:17 PM"},
        )
        self.assertTrue(
            any(
                warning.code == "normalized_quick_action_dates"
                for warning in workflow.warnings
            )
        )

    def test_parse_workflow_text_repairs_bare_ampersands_in_nested_xml(self) -> None:
        workflow_text = """
        <WorkflowVersionInformation>
          <WorkflowDefinition>
            <Name>Workflow A</Name>
            <Details>&lt;scenario&gt;&lt;title&gt;Task &amp; Events&lt;/title&gt;&lt;/scenario&gt;</Details>
            <TriggerDetails />
            <ExceptionHandling />
          </WorkflowDefinition>
        </WorkflowVersionInformation>
        """

        workflow = parse_workflow_text(workflow_text)

        self.assertEqual(workflow.details.root_tag, "scenario")
        self.assertTrue(
            any(
                warning.code == "repaired_bare_ampersands"
                for warning in workflow.warnings
            )
        )
        self.assertIn("&amp;", workflow.details.repaired_text or "")

    def test_parse_workflow_from_text_returns_none_when_workflow_is_missing(
        self,
    ) -> None:
        self.assertIsNone(parse_workflow_from_text("<Offerings />"))

    def test_parse_workflow_from_document_uses_document_source(self) -> None:
        source = """
        <Offerings>
          <WorkflowDefinition>
            &lt;WorkflowVersionInformation&gt;
              &lt;WorkflowDefinition&gt;
                &lt;Name&gt;Workflow A&lt;/Name&gt;
                &lt;Details&gt;&amp;lt;scenario /&amp;gt;&lt;/Details&gt;
              &lt;/WorkflowDefinition&gt;
            &lt;/WorkflowVersionInformation&gt;
          </WorkflowDefinition>
        </Offerings>
        """

        document = parse_text(source)
        workflow = parse_workflow_from_document(document)

        self.assertIsNotNone(workflow)
        assert workflow is not None
        self.assertEqual(workflow.definition_name, "Workflow A")
        self.assertEqual(workflow.details.root_tag, "scenario")

    def test_build_workflow_graph_extracts_nodes_edges_and_properties(self) -> None:
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
                    &lt;exits&gt;
                      &lt;exit&gt;
                        &lt;title&gt;ok&lt;/title&gt;
                        &lt;id&gt;EXIT_1&lt;/id&gt;
                        &lt;links&gt;
                          &lt;link&gt;
                            &lt;id&gt;LINK_1&lt;/id&gt;
                            &lt;blockId&gt;BLOCK_TASK&lt;/blockId&gt;
                          &lt;/link&gt;
                        &lt;/links&gt;
                        &lt;condition&gt;passed&lt;/condition&gt;
                      &lt;/exit&gt;
                    &lt;/exits&gt;
                  &lt;/block&gt;
                  &lt;block&gt;
                    &lt;id&gt;BLOCK_TASK&lt;/id&gt;
                    &lt;type&gt;task&lt;/type&gt;
                    &lt;title&gt;Task&lt;/title&gt;
                    &lt;layout&gt;&lt;x&gt;30&lt;/x&gt;&lt;y&gt;40&lt;/y&gt;&lt;/layout&gt;
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

        workflow = parse_workflow_text(workflow_text)
        graph = build_workflow_graph(workflow)

        self.assertIsNotNone(graph)
        assert graph is not None
        self.assertEqual(set(graph.nodes), {"BLOCK_START", "BLOCK_TASK"})
        self.assertEqual(graph.nodes["BLOCK_START"].block_type, "start")
        self.assertEqual(graph.nodes["BLOCK_START"].title, "Start")
        self.assertEqual(graph.nodes["BLOCK_START"].x, 10)
        self.assertEqual(graph.nodes["BLOCK_START"].y, 20)
        self.assertEqual(graph.nodes["BLOCK_START"].properties[0].name, "config")
        self.assertEqual(
            graph.nodes["BLOCK_START"].properties[0].groups[0].params,
            {"enabled": "yes"},
        )
        self.assertEqual(len(graph.nodes["BLOCK_START"].exits), 1)
        self.assertEqual(graph.nodes["BLOCK_START"].exits[0].title, "ok")
        self.assertEqual(
            graph.nodes["BLOCK_START"].exits[0].target_block_ids, ("BLOCK_TASK",)
        )
        self.assertEqual(len(graph.edges), 1)
        self.assertEqual(graph.edges[0].source_block_id, "BLOCK_START")
        self.assertEqual(graph.edges[0].target_block_id, "BLOCK_TASK")
        self.assertEqual(graph.edges[0].source_exit_title, "ok")
        self.assertEqual(graph.edges[0].source_exit_condition, "passed")
        self.assertEqual(graph.edges[0].source_exit_properties, ())

    def test_build_workflow_graph_extracts_structured_exit_condition_properties(
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
                    &lt;id&gt;BLOCK_SWITCH&lt;/id&gt;
                    &lt;type&gt;switch&lt;/type&gt;
                    &lt;title&gt;&lt;/title&gt;
                    &lt;layout&gt;&lt;x&gt;10&lt;/x&gt;&lt;y&gt;20&lt;/y&gt;&lt;/layout&gt;
                    &lt;blockProperties /&gt;
                    &lt;exits&gt;
                      &lt;exit&gt;
                        &lt;title&gt;exit 1&lt;/title&gt;
                        &lt;id&gt;EXIT_1&lt;/id&gt;
                        &lt;links&gt;
                          &lt;link&gt;
                            &lt;id&gt;LINK_1&lt;/id&gt;
                            &lt;blockId&gt;BLOCK_TASK&lt;/blockId&gt;
                          &lt;/link&gt;
                        &lt;/links&gt;
                        &lt;condition&gt;
                          &lt;property&gt;
                            &lt;name&gt;logicaloperator&lt;/name&gt;
                            &lt;groups&gt;
                              &lt;group&gt;
                                &lt;param&gt;&lt;name&gt;cond_EXIT_1&lt;/name&gt;&lt;value&gt;AND&lt;/value&gt;&lt;/param&gt;
                              &lt;/group&gt;
                            &lt;/groups&gt;
                          &lt;/property&gt;
                          &lt;property&gt;
                            &lt;name&gt;conditions&lt;/name&gt;
                            &lt;groups&gt;
                              &lt;group&gt;
                                &lt;param&gt;&lt;name&gt;field&lt;/name&gt;&lt;value&gt;AlternateContactLink&lt;/value&gt;&lt;/param&gt;
                                &lt;param&gt;&lt;name&gt;operator&lt;/name&gt;&lt;value&gt;Contains&lt;/value&gt;&lt;/param&gt;
                                &lt;param&gt;&lt;name&gt;value&lt;/name&gt;&lt;value&gt;test&lt;/value&gt;&lt;/param&gt;
                              &lt;/group&gt;
                            &lt;/groups&gt;
                          &lt;/property&gt;
                        &lt;/condition&gt;
                      &lt;/exit&gt;
                    &lt;/exits&gt;
                  &lt;/block&gt;
                  &lt;block&gt;
                    &lt;id&gt;BLOCK_TASK&lt;/id&gt;
                    &lt;type&gt;task&lt;/type&gt;
                    &lt;title&gt;Task&lt;/title&gt;
                    &lt;layout&gt;&lt;x&gt;30&lt;/x&gt;&lt;y&gt;40&lt;/y&gt;&lt;/layout&gt;
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

        workflow = parse_workflow_text(workflow_text)
        graph = build_workflow_graph(workflow)

        self.assertIsNotNone(graph)
        assert graph is not None
        self.assertEqual(len(graph.nodes["BLOCK_SWITCH"].exits), 1)
        self.assertEqual(graph.nodes["BLOCK_SWITCH"].exits[0].title, "exit 1")
        self.assertEqual(len(graph.edges), 1)
        self.assertIsNone(graph.edges[0].source_exit_condition)
        self.assertEqual(
            graph.edges[0].source_exit_properties[0].groups[0].params,
            {"cond_EXIT_1": "AND"},
        )
        self.assertEqual(
            graph.edges[0].source_exit_properties[1].groups[0].params,
            {
                "field": "AlternateContactLink",
                "operator": "Contains",
                "value": "test",
            },
        )

    def test_build_workflow_graph_returns_none_without_scenario_details(self) -> None:
        workflow_text = """
        <WorkflowVersionInformation>
          <WorkflowDefinition>
            <Name>Workflow A</Name>
            <Details />
            <TriggerDetails />
          </WorkflowDefinition>
        </WorkflowVersionInformation>
        """

        workflow = parse_workflow_text(workflow_text)

        self.assertIsNone(build_workflow_graph(workflow))

    def test_build_workflow_trigger_model_extracts_conditions_and_event_flags(
        self,
    ) -> None:
        workflow_text = """
        <WorkflowVersionInformation>
          <WorkflowDefinition>
            <Name>Workflow A</Name>
            <Details>&lt;scenario /&gt;</Details>
            <TriggerDetails>
              &lt;BPETrigger&gt;
                &lt;id&gt;TRIGGER_1&lt;/id&gt;
                &lt;type&gt;trigger&lt;/type&gt;
                &lt;title&gt;When Ready&lt;/title&gt;
                &lt;layout&gt;&lt;x&gt;15&lt;/x&gt;&lt;y&gt;25&lt;/y&gt;&lt;/layout&gt;
                &lt;blockProperties&gt;
                  &lt;property&gt;
                    &lt;name&gt;starttype_block&lt;/name&gt;
                    &lt;groups&gt;
                      &lt;group&gt;
                        &lt;param&gt;&lt;name&gt;starttype&lt;/name&gt;&lt;value&gt;Condition&lt;/value&gt;&lt;/param&gt;
                      &lt;/group&gt;
                    &lt;/groups&gt;
                  &lt;/property&gt;
                  &lt;property&gt;
                    &lt;name&gt;contextblock&lt;/name&gt;
                    &lt;groups&gt;
                      &lt;group&gt;
                        &lt;param&gt;&lt;name&gt;created&lt;/name&gt;&lt;value&gt;yes&lt;/value&gt;&lt;/param&gt;
                        &lt;param&gt;&lt;name&gt;updated&lt;/name&gt;&lt;value&gt;yes&lt;/value&gt;&lt;/param&gt;
                        &lt;param&gt;&lt;name&gt;deleted&lt;/name&gt;&lt;value&gt;&lt;/value&gt;&lt;/param&gt;
                      &lt;/group&gt;
                    &lt;/groups&gt;
                  &lt;/property&gt;
                  &lt;property&gt;
                    &lt;name&gt;logical&lt;/name&gt;
                    &lt;groups&gt;
                      &lt;group&gt;
                        &lt;param&gt;&lt;name&gt;cond&lt;/name&gt;&lt;value&gt;AND&lt;/value&gt;&lt;/param&gt;
                      &lt;/group&gt;
                    &lt;/groups&gt;
                  &lt;/property&gt;
                  &lt;property&gt;
                    &lt;name&gt;trigger&lt;/name&gt;
                    &lt;groups&gt;
                      &lt;group&gt;
                        &lt;param&gt;&lt;name&gt;childObjectName&lt;/name&gt;&lt;value&gt;ChildObject&lt;/value&gt;&lt;/param&gt;
                        &lt;param&gt;&lt;name&gt;relationshipName&lt;/name&gt;&lt;value&gt;ChildToParent&lt;/value&gt;&lt;/param&gt;
                        &lt;param&gt;&lt;name&gt;field&lt;/name&gt;&lt;value&gt;Status&lt;/value&gt;&lt;/param&gt;
                        &lt;param&gt;&lt;name&gt;operator&lt;/name&gt;&lt;value&gt;Equal to&lt;/value&gt;&lt;/param&gt;
                        &lt;param&gt;&lt;name&gt;value&lt;/name&gt;&lt;value&gt;Ready&lt;/value&gt;&lt;/param&gt;
                      &lt;/group&gt;
                      &lt;group&gt;
                        &lt;param&gt;&lt;name&gt;field&lt;/name&gt;&lt;value&gt;Priority&lt;/value&gt;&lt;/param&gt;
                        &lt;param&gt;&lt;name&gt;operator&lt;/name&gt;&lt;value&gt;Equal to&lt;/value&gt;&lt;/param&gt;
                        &lt;param&gt;&lt;name&gt;value&lt;/name&gt;&lt;value&gt;High&lt;/value&gt;&lt;/param&gt;
                      &lt;/group&gt;
                    &lt;/groups&gt;
                  &lt;/property&gt;
                &lt;/blockProperties&gt;
                &lt;exits /&gt;
              &lt;/BPETrigger&gt;
            </TriggerDetails>
          </WorkflowDefinition>
        </WorkflowVersionInformation>
        """

        workflow = parse_workflow_text(workflow_text)
        trigger = build_workflow_trigger_model(workflow)

        self.assertIsNotNone(trigger)
        assert trigger is not None
        self.assertEqual(trigger.trigger_id, "TRIGGER_1")
        self.assertEqual(trigger.block_type, "trigger")
        self.assertEqual(trigger.title, "When Ready")
        self.assertEqual(trigger.x, 15)
        self.assertEqual(trigger.y, 25)
        self.assertEqual(trigger.start_type, "Condition")
        self.assertTrue(trigger.events.created)
        self.assertTrue(trigger.events.updated)
        self.assertFalse(trigger.events.deleted)
        self.assertEqual(trigger.logic, "AND")
        self.assertEqual(len(trigger.conditions), 2)
        self.assertEqual(trigger.conditions[0].child_object_name, "ChildObject")
        self.assertEqual(trigger.conditions[0].relationship_name, "ChildToParent")
        self.assertEqual(trigger.conditions[0].field, "Status")
        self.assertEqual(trigger.conditions[0].operator, "Equal to")
        self.assertEqual(trigger.conditions[0].value, "Ready")
        self.assertEqual(trigger.conditions[1].field, "Priority")
        self.assertEqual(trigger.conditions[1].value, "High")
        self.assertEqual(trigger.properties[0].name, "starttype_block")

    def test_build_workflow_trigger_model_returns_none_without_trigger_details(
        self,
    ) -> None:
        workflow_text = """
        <WorkflowVersionInformation>
          <WorkflowDefinition>
            <Name>Workflow A</Name>
            <Details>&lt;scenario /&gt;</Details>
            <TriggerDetails />
          </WorkflowDefinition>
        </WorkflowVersionInformation>
        """

        workflow = parse_workflow_text(workflow_text)

        self.assertIsNone(build_workflow_trigger_model(workflow))


if __name__ == "__main__":
    unittest.main()
