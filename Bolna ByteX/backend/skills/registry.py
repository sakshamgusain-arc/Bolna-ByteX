import logging
from typing import Dict, Any, Optional
from skills.base import BaseSkill, ToolResult
from skills.apps import OpenApplicationSkill, CloseApplicationSkill, ApplicationStatusSkill
from skills.browser import OpenWebsiteSkill
from skills.screenshot import TakeScreenshotSkill
from skills.system import SystemStatusSkill
from skills.search import WebSearchSkill
from skills.reader import ReadWebpageSkill
from skills.form_filler import FormFillingSkill
from skills.downloader import DownloadFileSkill
from skills.website_automation import WebsiteAutomationSkill
from skills.research import ResearchModeSkill
from skills.summarizer import SummarizeSkill
from skills.media import PlayMediaSkill
from skills.clipboard import DesktopClipboardSkill
from skills.vision import ScreenVisionSkill
from skills.coding import CodingWorkspaceSkill
from skills.terminal import TerminalAgentSkill
from skills.risky_test import RiskyTestActionSkill, MockVerificationFailureSkill
from skills.files import (
    ListFilesSkill,
    FileSearchSkill,
    FileOperationsSkill,
    CreateFolderSkill,
    CreateFileSkill,
    RenameFileSkill,
    MoveFileSkill,
    CopyFileSkill,
    DeleteFileSkill,
)

logger = logging.getLogger("bytex.skill_registry")

class SkillRegistry:
    """Central Registry for all ByteX PC Automation Skills."""

    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {}
        self._register_default_skills()

    def _register_default_skills(self):
        skills = [
            OpenApplicationSkill(),
            CloseApplicationSkill(),
            ApplicationStatusSkill(),
            OpenWebsiteSkill(),
            TakeScreenshotSkill(),
            SystemStatusSkill(),
            WebSearchSkill(),
            ReadWebpageSkill(),
            FormFillingSkill(),
            DownloadFileSkill(),
            WebsiteAutomationSkill(),
            ResearchModeSkill(),
            SummarizeSkill(),
            PlayMediaSkill(),
            DesktopClipboardSkill(),
            ScreenVisionSkill(),
            CodingWorkspaceSkill(),
            TerminalAgentSkill(),
            ListFilesSkill(),
            FileSearchSkill(),
            FileOperationsSkill(),
            CreateFolderSkill(),
            CreateFileSkill(),
            RenameFileSkill(),
            MoveFileSkill(),
            CopyFileSkill(),
            DeleteFileSkill(),
            RiskyTestActionSkill(),
            MockVerificationFailureSkill(),
        ]
        for skill in skills:
            self._skills[skill.name] = skill
            
        # Aliases for natural intent mapping
        self._skills["list_directory"] = self._skills["list_files"]
        self._skills["search_files"] = self._skills["file_search"]
        self._skills["smart_file_search"] = self._skills["file_search"]
        self._skills["coding"] = self._skills["coding_workspace"]
        self._skills["code_workspace"] = self._skills["coding_workspace"]
        self._skills["code"] = self._skills["coding_workspace"]
        self._skills["project"] = self._skills["coding_workspace"]
        self._skills["generate_code"] = self._skills["coding_workspace"]
        self._skills["edit_code_file"] = self._skills["coding_workspace"]
        self._skills["create_code_file"] = self._skills["coding_workspace"]
        self._skills["read_code_file"] = self._skills["coding_workspace"]
        self._skills["read_file"] = self._skills["coding_workspace"]
        self._skills["read_source_file"] = self._skills["coding_workspace"]
        self._skills["read"] = self._skills["coding_workspace"]
        self._skills["execute_code"] = self._skills["coding_workspace"]
        self._skills["run_code"] = self._skills["coding_workspace"]
        self._skills["compile_and_run"] = self._skills["coding_workspace"]
        self._skills["compile_code"] = self._skills["coding_workspace"]
        self._skills["compile"] = self._skills["coding_workspace"]
        self._skills["build_code"] = self._skills["coding_workspace"]
        self._skills["build"] = self._skills["coding_workspace"]
        self._skills["explain_code"] = self._skills["coding_workspace"]
        self._skills["diagnose_code_error"] = self._skills["coding_workspace"]
        self._skills["fix_code_error"] = self._skills["coding_workspace"]
        self._skills["review_code"] = self._skills["coding_workspace"]
        self._skills["review"] = self._skills["coding_workspace"]
        self._skills["teach_code"] = self._skills["coding_workspace"]
        self._skills["teach"] = self._skills["coding_workspace"]
        self._skills["hint"] = self._skills["coding_workspace"]
        self._skills["analyze_code"] = self._skills["coding_workspace"]
        self._skills["analyze"] = self._skills["coding_workspace"]
        self._skills["create_project"] = self._skills["coding_workspace"]
        self._skills["open_project"] = self._skills["coding_workspace"]
        self._skills["inspect_project"] = self._skills["coding_workspace"]
        self._skills["project_structure"] = self._skills["coding_workspace"]
        self._skills["detect_language"] = self._skills["coding_workspace"]
        self._skills["open_website"] = self._skills["browser_control"]
        self._skills["navigate"] = self._skills["browser_control"]
        self._skills["browser"] = self._skills["browser_control"]
        self._skills["read_page"] = self._skills["read_webpage"]
        self._skills["web_reader"] = self._skills["read_webpage"]
        self._skills["read_website"] = self._skills["read_webpage"]
        self._skills["form_filler"] = self._skills["fill_form"]
        self._skills["form_filling"] = self._skills["fill_form"]
        self._skills["download"] = self._skills["download_file"]
        self._skills["downloader"] = self._skills["download_file"]
        self._skills["web_automation"] = self._skills["website_automation"]
        self._skills["automate_website"] = self._skills["website_automation"]
        self._skills["research"] = self._skills["research_mode"]
        self._skills["deep_research"] = self._skills["research_mode"]
        self._skills["investigate"] = self._skills["research_mode"]
        self._skills["web_research"] = self._skills["research_mode"]
        self._skills["advanced_research"] = self._skills["research_mode"]
        self._skills["multi_source_research"] = self._skills["research_mode"]
        self._skills["verify_claim"] = self._skills["research_mode"]
        self._skills["summarizer"] = self._skills["summarize"]
        self._skills["summary"] = self._skills["summarize"]
        self._skills["play_song"] = self._skills["play_media"]
        self._skills["play_video"] = self._skills["play_media"]
        self._skills["media_player"] = self._skills["play_media"]
        self._skills["play"] = self._skills["play_media"]
        self._skills["screenshot"] = self._skills["take_screenshot"]
        self._skills["get_system_stats"] = self._skills["system_status"]
        self._skills["search_files"] = self._skills["file_search"]
        self._skills["search_web"] = self._skills["web_search"]
        self._skills["search"] = self._skills["web_search"]
        self._skills["delete"] = self._skills["delete_file"]
        self._skills["clipboard"] = self._skills["clipboard_control"]
        self._skills["get_clipboard"] = self._skills["clipboard_control"]
        self._skills["set_clipboard"] = self._skills["clipboard_control"]
        self._skills["clear_clipboard"] = self._skills["clipboard_control"]
        self._skills["paste_clipboard"] = self._skills["clipboard_control"]
        self._skills["paste"] = self._skills["clipboard_control"]
        # Screen Understanding 2.0 / Screen Vision commands & aliases (Feature #40)
        self._skills["screen_understanding"] = self._skills["screen_vision"]
        self._skills["analyze_screen"] = self._skills["screen_vision"]
        self._skills["understand_screen"] = self._skills["screen_vision"]
        self._skills["screen_diagnosis"] = self._skills["screen_vision"]
        self._skills["diagnose_screen"] = self._skills["screen_vision"]
        self._skills["find_ui_element"] = self._skills["screen_vision"]
        self._skills["detect_element"] = self._skills["screen_vision"]
        self._skills["find_element"] = self._skills["screen_vision"]
        self._skills["locate_element"] = self._skills["screen_vision"]
        self._skills["locate"] = self._skills["screen_vision"]
        self._skills["visual_click"] = self._skills["screen_vision"]
        self._skills["click_coordinates"] = self._skills["screen_vision"]
        self._skills["click_point"] = self._skills["screen_vision"]
        self._skills["visual_double_click"] = self._skills["screen_vision"]
        self._skills["double_click"] = self._skills["screen_vision"]
        self._skills["visual_type"] = self._skills["screen_vision"]
        self._skills["type_text"] = self._skills["screen_vision"]
        self._skills["visual_scroll"] = self._skills["screen_vision"]
        self._skills["scroll"] = self._skills["screen_vision"]
        self._skills["visual_select"] = self._skills["screen_vision"]
        self._skills["explain_region"] = self._skills["screen_vision"]
        self._skills["examine_region"] = self._skills["screen_vision"]
        self._skills["read_screen"] = self._skills["screen_vision"]
        self._skills["read_text"] = self._skills["screen_vision"]
        self._skills["screen_ocr"] = self._skills["screen_vision"]
        self._skills["ocr"] = self._skills["screen_vision"]
        self._skills["vision"] = self._skills["screen_vision"]
        self._skills["screen_analyze"] = self._skills["screen_vision"]
        self._skills["describe_screen"] = self._skills["screen_vision"]
        self._skills["click"] = self._skills["screen_vision"]
        self._skills["vision_click"] = self._skills["screen_vision"]
        self._skills["left_click"] = self._skills["screen_vision"]

        # Resume My Work Skill (Feature #42)
        from skills.work_resume_skill import work_resume_skill
        self._skills["resume_my_work"] = work_resume_skill
        self._skills["resume_work"] = work_resume_skill
        self._skills["resume_task"] = work_resume_skill
        self._skills["get_work_context"] = work_resume_skill
        self._skills["summarize_last_work"] = work_resume_skill
        self._skills["find_resumable_tasks"] = work_resume_skill
        self._skills["find_resumable_task"] = work_resume_skill

    def get_skill(self, name: str) -> Optional[BaseSkill]:
        return self._skills.get(name)

    def list_skills(self) -> Dict[str, str]:
        return {name: skill.description for name, skill in self._skills.items()}

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        skill = self.get_skill(name)
        if not skill:
            return ToolResult(
                success=False,
                tool=name,
                message=f"Skill '{name}' is not registered in ByteX Skill Registry."
            )

        args = dict(arguments) if arguments else {}
        if skill.name == "screen_vision" and "action" not in args:
            args["action"] = name
        elif skill.name == "coding_workspace" and "action" not in args:
            if name in ["generate_code", "edit_code_file", "create_code_file", "read_code_file", "execute_code", "run_code", "compile_and_run", "compile_code", "compile", "build_code", "build", "explain_code", "diagnose_code_error", "fix_code_error", "create_project", "open_project", "inspect_project", "project_structure", "detect_language"]:
                args["action"] = name
            elif name in ["read_file", "read_source_file", "read"]:
                args["action"] = "read_code_file"

        print(f"[ByteX SkillRegistry] Executing skill '{name}' with arguments: {args}")
        try:
            return await skill.execute(args)
        except Exception as e:
            logger.error(f"[ByteX SkillRegistry] Exception executing '{name}': {e}")
            return ToolResult(
                success=False,
                tool=name,
                message=f"Execution error for skill '{name}': {e}"
            )

skill_registry = SkillRegistry()
