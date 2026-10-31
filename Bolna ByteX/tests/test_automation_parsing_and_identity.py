import os
import sys
import asyncio
import unittest

# Ensure project roots in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from agent.automation import (
    NaturalLanguageAutomationParser,
    AutomationScheduleType,
    AutomationTriggerType,
    automation_manager
)
from core.command_router import CommandRouter
from core.confirmation import confirmation_manager
from ai.prompts.system import get_system_prompt
from config.settings import settings


class TestAutomationParsingAndIdentity(unittest.IsolatedAsyncioTestCase):
    """
    Focused test suite verifying:
    1. Compound natural-language automation step-parsing and preview confirmation.
    2. Zero-step parsing bug resolution on named automations.
    3. Multi-step automation parsing (code creation, system status, application launch).
    4. Malformed and empty automation requests handling.
    5. Identity and Creator Attribution ("What is your name?", "Who made you?", "Who created you?").
    """

    async def asyncSetUp(self):
        automation_manager.clear_all_automations()
        confirmation_manager.clear()

    async def asyncTearDown(self):
        automation_manager.clear_all_automations()
        confirmation_manager.clear()

    # =========================================================================
    # PART 1: AUTOMATION STEP PARSING
    # =========================================================================

    def test_parse_bytex_dev_that_opens_notepad(self):
        """Verify 'Create an automation called ByteX Dev that opens Notepad' produces a 1-step automation."""
        is_auto, auto_obj, feedback = NaturalLanguageAutomationParser.parse_creation_request(
            "Create an automation called ByteX Dev that opens Notepad"
        )
        self.assertTrue(is_auto)
        self.assertIsNotNone(auto_obj)
        self.assertIsNone(feedback)
        self.assertEqual(auto_obj.name, "ByteX Dev")
        self.assertEqual(len(auto_obj.steps), 1)
        self.assertEqual(auto_obj.steps[0].skill, "open_application")
        self.assertEqual(auto_obj.steps[0].arguments.get("application"), "Notepad")
        self.assertEqual(auto_obj.steps[0].description, "Open Notepad")

    def test_parse_bytex_dev_with_period(self):
        """Verify request with trailing punctuation works identically."""
        is_auto, auto_obj, feedback = NaturalLanguageAutomationParser.parse_creation_request(
            "Create an automation called ByteX Dev that opens Notepad."
        )
        self.assertTrue(is_auto)
        self.assertIsNotNone(auto_obj)
        self.assertEqual(auto_obj.name, "ByteX Dev")
        self.assertEqual(len(auto_obj.steps), 1)

    def test_parse_code_routine_with_code_file_creation(self):
        """Verify 'Create an automation called Code Routine that opens Edge and creates main.py' generates 2 steps."""
        is_auto, auto_obj, feedback = NaturalLanguageAutomationParser.parse_creation_request(
            "Create an automation called Code Routine that opens Edge and creates main.py"
        )
        self.assertTrue(is_auto)
        self.assertIsNotNone(auto_obj)
        self.assertEqual(auto_obj.name, "Code Routine")
        self.assertEqual(len(auto_obj.steps), 2)
        self.assertEqual(auto_obj.steps[0].skill, "browser_control")
        self.assertEqual(auto_obj.steps[1].skill, "coding_workspace")
        self.assertEqual(auto_obj.steps[1].action, "create_code_file")
        self.assertEqual(auto_obj.steps[1].arguments.get("filename"), "main.py")

    def test_parse_full_stack_with_system_status_and_command_trigger(self):
        """Verify command trigger phrase and system status action parsing."""
        is_auto, auto_obj, feedback = NaturalLanguageAutomationParser.parse_creation_request(
            "Create an automation called Full Stack that opens Notepad and checks system status whenever I say launch stack."
        )
        self.assertTrue(is_auto)
        self.assertIsNotNone(auto_obj)
        self.assertEqual(auto_obj.name, "Full Stack")
        self.assertEqual(len(auto_obj.steps), 2)
        self.assertEqual(auto_obj.steps[0].skill, "open_application")
        self.assertEqual(auto_obj.steps[1].skill, "system_status")
        self.assertEqual(auto_obj.schedule_details.get("command_trigger"), "launch stack")

    def test_parse_empty_and_malformed_requests(self):
        """Verify malformed, empty, or incomplete automation requests fail gracefully."""
        # Non-automation command
        is_auto, auto_obj, _ = NaturalLanguageAutomationParser.parse_creation_request("Hello ByteX")
        self.assertFalse(is_auto)
        self.assertIsNone(auto_obj)

        # Automation creation without any actions
        is_auto, auto_obj, feedback = NaturalLanguageAutomationParser.parse_creation_request(
            "Create an automation called EmptyRoutine"
        )
        self.assertTrue(is_auto)
        self.assertIsNone(auto_obj)
        self.assertIn("Please specify what actions", feedback)

        # Bare creation command
        is_auto, auto_obj, feedback = NaturalLanguageAutomationParser.parse_creation_request(
            "Create an automation"
        )
        self.assertTrue(is_auto)
        self.assertIsNone(auto_obj)
        self.assertIn("Please specify the name and actions", feedback)

        # Unsupported skill requested
        is_auto, auto_obj, feedback = NaturalLanguageAutomationParser.parse_creation_request(
            "Create an automation called Space that flies to Jupiter"
        )
        self.assertTrue(is_auto)
        self.assertIsNone(auto_obj)
        self.assertIn("don't currently have a supported skill", feedback)

    async def test_route_command_automation_preview_and_confirmation(self):
        """Verify full end-to-end routing: generates preview, requires confirmation, then persists on 'Yes.'"""
        handled, resp, state, data = await CommandRouter.route_command(
            "Create an automation called ByteX Dev that opens Notepad."
        )
        self.assertTrue(handled)
        self.assertEqual(state, "waiting_confirmation")
        self.assertIn("Create automation 'ByteX Dev'?", resp)
        self.assertIn("Open Notepad", resp)
        self.assertTrue(confirmation_manager.has_pending())

        # Confirm
        c_handled, c_resp, c_state, c_data = await CommandRouter.route_command("Yes.")
        self.assertTrue(c_handled)
        self.assertEqual(c_state, "speaking")
        self.assertIn("created and enabled", c_resp.lower())

        saved = automation_manager.get_automation_by_name("ByteX Dev")
        self.assertIsNotNone(saved)
        self.assertEqual(saved.name, "ByteX Dev")
        self.assertEqual(len(saved.steps), 1)

    # =========================================================================
    # PART 2: IDENTITY AND CREATOR ATTRIBUTION
    # =========================================================================

    async def test_identity_name_queries(self):
        """Verify ByteX identifies itself as 'ByteX Core' when asked its name."""
        name_queries = [
            "What is your name?",
            "what is your name",
            "What's your name?",
            "Who are you?",
            "Tell me your name",
            "What are you called?"
        ]
        for query in name_queries:
            with self.subTest(query=query):
                handled, resp, state, data = await CommandRouter.route_command(query)
                self.assertTrue(handled, f"Query '{query}' was not handled.")
                self.assertEqual(resp, "I am ByteX Core.", f"Expected 'I am ByteX Core.' for '{query}', got '{resp}'.")
                self.assertEqual(state, "speaking")
                self.assertEqual(data.get("name"), "ByteX Core")

    async def test_creator_attribution_queries(self):
        """Verify ByteX answers that its creator identity is not configured and does NOT claim ByteX AI."""
        creator_queries = [
            "Who made you?",
            "who made you",
            "Who created you?",
            "who created you",
            "Who developed you?",
            "Who built you?",
            "Who is your creator?",
            "Who is your developer?"
        ]
        for query in creator_queries:
            with self.subTest(query=query):
                handled, resp, state, data = await CommandRouter.route_command(query)
                self.assertTrue(handled, f"Query '{query}' was not handled.")
                self.assertEqual(
                    resp,
                    "My creator identity is not configured.",
                    f"Expected 'My creator identity is not configured.' for '{query}', got '{resp}'."
                )
                self.assertEqual(state, "speaking")
                self.assertEqual(data.get("creator"), "not_configured")

    def test_system_prompt_identity(self):
        """Verify system prompt enforces ByteX Core name and not-configured creator guideline."""
        prompt = get_system_prompt()
        self.assertIn("You are ByteX Core", prompt)
        self.assertIn("Name: ByteX Core", prompt)
        self.assertIn("The creator identity for ByteX Core is not configured", prompt)
        self.assertNotIn("You are ByteX AI", prompt)

    def test_settings_project_name(self):
        """Verify project name in settings is ByteX Core."""
        self.assertEqual(settings.PROJECT_NAME, "ByteX Core")


if __name__ == "__main__":
    unittest.main()
