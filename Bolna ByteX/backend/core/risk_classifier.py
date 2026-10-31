import json
import logging
from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel
from skills.registry import skill_registry

logger = logging.getLogger("bytex.risk_classifier")

class RiskLevel(str, Enum):
    SAFE = "SAFE"
    SENSITIVE = "SENSITIVE"
    DANGEROUS = "DANGEROUS"
    BLOCKED = "BLOCKED"

class RiskAssessment(BaseModel):
    risk_level: RiskLevel
    requires_confirmation: bool
    reason: str
    is_blocked: bool = False

class ActionRiskClassifier:
    """
    ByteX Action Risk Classifier.
    
    Determines the authoritative minimum risk level and confirmation requirement
    for an action BEFORE execution.
    
    Invariants & Security Rules:
    1. Single Source of Truth: Registered skills are verified against skill_registry.
    2. Non-Overridable: The Agent/LLM/Plan CANNOT lower a skill's assigned risk level.
    3. Block Unknowns: Any unregistered or hallucinated skill is strictly marked BLOCKED.
    4. Zero Tool Execution: Purely analytical inspection; executes no tools or commands.
    5. Zero LLM Overhead: Fast, deterministic rule-based evaluation.
    """

    SAFE_SKILLS = {
        "system_status",
        "get_system_stats",
        "file_search",
        "search_files",
        "list_files",
        "list_directory",
        "open_application",
        "open_website",
        "browser_control",
        "browser",
        "web_search",
        "search_web",
        "read_webpage",
        "read_page",
        "read_website",
        "fill_form",
        "form_filler",
        "form_filling",
        "download_file",
        "download",
        "downloader",
        "website_automation",
        "web_automation",
        "automate_website",
        "research_mode",
        "research",
        "deep_research",
        "investigate",
        "summarize",
        "summarizer",
        "summary",
        "play_media",
        "play_song",
        "play_video",
        "media_player",
        "play",
        "take_screenshot",
        "screenshot",
        "screen_vision",
        "vision",
        "coding_workspace",
        "coding",
        "code_workspace",
        "code",
        "project",
    }

    SENSITIVE_SKILLS = {
        "create_folder",
        "create_file",
        "copy_file",
        "rename_file",
        "move_file",
        "close_application",
        "modify_settings",
    }

    DANGEROUS_SKILLS = {
        "delete_file",
        "delete",
        "shutdown",
        "restart",
        "send_message",
        "risky_test",
    }

    @classmethod
    def classify_action(cls, skill_name: str, arguments: Optional[Dict[str, Any]] = None) -> RiskAssessment:
        """
        Classifies an action and returns an authoritative RiskAssessment.
        """
        clean_name = (skill_name or "").strip().lower()
        args = arguments or {}

        # 1. Unregistered / Unknown Skill Check
        skill = skill_registry.get_skill(clean_name)
        if not skill:
            return RiskAssessment(
                risk_level=RiskLevel.BLOCKED,
                requires_confirmation=True,
                reason=f"Skill '{skill_name}' is not registered in ByteX Skill Registry. Execution blocked.",
                is_blocked=True
            )

        # 2. Granular File Operations Sub-Classification
        if clean_name == "file_operations":
            operation = str(args.get("operation", "")).strip().lower()
            if operation in ["delete", "delete_file", "remove"]:
                return RiskAssessment(
                    risk_level=RiskLevel.DANGEROUS,
                    requires_confirmation=True,
                    reason=f"File operation '{operation}' is destructive and permanently modifies filesystem state."
                )
            elif operation in ["rename", "move", "rename_file", "move_file"]:
                return RiskAssessment(
                    risk_level=RiskLevel.SENSITIVE,
                    requires_confirmation=True,
                    reason=f"File operation '{operation}' modifies existing file paths/structures."
                )
            elif operation in ["create_folder", "create_file", "copy", "copy_file", "mkdir"]:
                return RiskAssessment(
                    risk_level=RiskLevel.SENSITIVE,
                    requires_confirmation=False,
                    reason=f"File operation '{operation}' creates or copies resources safely without destructive overwrite."
                )

        # 2b. Granular Coding Workspace Sub-Classification
        if clean_name in ["coding_workspace", "coding", "code_workspace", "code", "project"]:
            action = str(args.get("action", "")).strip().lower()
            overwrite = bool(args.get("overwrite", False))
            if action in ["execute_code", "run_code", "compile_and_run", "execute", "run"]:
                target_fname = args.get("filename") or args.get("file_path") or args.get("name") or "source file"
                return RiskAssessment(
                    risk_level=RiskLevel.SENSITIVE,
                    requires_confirmation=True,
                    reason=f"Executing source code file '{target_fname}' is a sensitive operation requiring user confirmation."
                )
            elif action in ["edit_code_file", "edit_file", "modify_code", "edit_code"] or (action == "generate_code" and overwrite):
                target_fname = args.get("filename") or args.get("name") or "file"
                return RiskAssessment(
                    risk_level=RiskLevel.SENSITIVE,
                    requires_confirmation=True,
                    reason=f"Modifying/replacing existing source code file '{target_fname}' requires user confirmation."
                )
            elif action in ["fix_code_error", "fix_error", "fix_code", "auto_fix", "fix"]:
                target_fname = args.get("filename") or args.get("file_path") or args.get("name") or "source file"
                fix_mode = str(args.get("fix_mode", "automatic")).strip().lower()
                req_conf = bool(args.get("require_confirmation", False))
                is_conf_required = req_conf or (fix_mode == "confirm")
                return RiskAssessment(
                    risk_level=RiskLevel.SENSITIVE,
                    requires_confirmation=is_conf_required,
                    reason=f"Fixing code error in '{target_fname}' is a sensitive operation{' requiring user confirmation' if is_conf_required else ' with automated verification'}."
                )
            else:
                # create_project, open_project, inspect_project, create_code_file, read_code_file, project_structure, detect_language, generate_code (safe), explain_code (safe), diagnose_code_error (safe)
                return RiskAssessment(
                    risk_level=RiskLevel.SAFE,
                    requires_confirmation=False,
                    reason=f"Coding workspace operation '{action}' performs safe code diagnosis, explanation, generation, inspection, creation, or analysis."
                )

        # 2c. Granular Controlled Terminal Agent Sub-Classification (Feature #33.6)
        if clean_name in ["terminal_agent", "terminal", "controlled_terminal"]:
            op = str(args.get("operation") or args.get("action", "")).strip().lower()
            
            # Check for forbidden metacharacters or dangerous commands
            raw_arg_str = json.dumps(args)
            if any(k in raw_arg_str for k in ["&&", "||", ";", "|", "`", "$(", "%COMSPEC%", "powershell", "cmd.exe", "del ", "rm ", "format "]):
                return RiskAssessment(
                    risk_level=RiskLevel.BLOCKED,
                    requires_confirmation=True,
                    reason="Command contains forbidden shell metacharacters or unsafe system command syntax."
                )

            sensitive_ops = {
                "npm_install", "pip_install_requirements", "create_virtual_environment",
                "build_project", "run_project_tests", "start_dev_server", "run_pytest",
                "npm_test", "npm_run_script"
            }
            if op in sensitive_ops:
                return RiskAssessment(
                    risk_level=RiskLevel.SENSITIVE,
                    requires_confirmation=True,
                    reason=f"Controlled terminal operation '{op}' modifies dependencies or executes test/build scripts, requiring confirmation."
                )
            else:
                # list_files, list_directory, print_working_directory, python_version, pip_version, node_version, npm_version, show_package_scripts, show_project_metadata
                return RiskAssessment(
                    risk_level=RiskLevel.SAFE,
                    requires_confirmation=False,
                    reason=f"Terminal operation '{op}' performs safe inspection and version queries."
                )

        # 2d. Granular Advanced Screen Vision Sub-Classification (Feature #34 & Feature #40)
        vision_aliases = {
            "screen_vision", "vision", "screen_understanding", "analyze_screen", "understand_screen",
            "screen_diagnosis", "diagnose_screen", "find_ui_element", "detect_element", "find_element",
            "locate_element", "locate", "visual_click", "click_coordinates", "click_point",
            "visual_double_click", "double_click", "visual_type", "type_text", "visual_scroll",
            "scroll", "visual_select", "explain_region", "examine_region", "read_screen",
            "read_text", "screen_ocr", "ocr", "click", "vision_click", "left_click"
        }
        if clean_name in vision_aliases:
            action = str(args.get("action") or clean_name).strip().lower()
            target_str = str(args.get("target") or args.get("element") or args.get("raw_text") or "").strip().lower()

            destructive_keywords = ["delete", "remove", "uninstall", "format", "shutdown", "erase", "drop", "destroy", "purge", "close without saving"]
            is_destructive = any(k in target_str for k in destructive_keywords)

            if is_destructive and action in ["visual_click", "click", "vision_click", "left_click", "visual_double_click", "double_click", "visual_type", "type", "visual_select", "select"]:
                return RiskAssessment(
                    risk_level=RiskLevel.DANGEROUS,
                    requires_confirmation=True,
                    reason=f"Visual UI action '{action}' on destructive target '{target_str}' requires explicit user confirmation."
                )
            elif action in ["visual_click", "click", "vision_click", "left_click", "click_coordinates", "click_point", "visual_double_click", "double_click", "visual_type", "type", "vision_type", "type_text", "visual_select", "select", "visual_scroll", "scroll"]:
                return RiskAssessment(
                    risk_level=RiskLevel.SENSITIVE,
                    requires_confirmation=True,
                    reason=f"Visual UI interaction '{action}' sends physical input to the focused window and requires confirmation."
                )
            else:
                # analyze_screen, screen_analyze, describe, read_screen, read_text, ocr, find_ui_element, detect_element, find_element, locate, screen_diagnosis, diagnose_screen, explain_region, etc.
                return RiskAssessment(
                    risk_level=RiskLevel.SAFE,
                    requires_confirmation=False,
                    reason=f"Screen vision operation '{action}' performs safe read-only visual analysis, OCR, or element detection."
                )

        # 3. Direct Dangerous Classification
        if clean_name in cls.DANGEROUS_SKILLS:
            return RiskAssessment(
                risk_level=RiskLevel.DANGEROUS,
                requires_confirmation=True,
                reason=f"Skill '{clean_name}' performs destructive or externally consequential actions."
            )

        # 4. Direct Sensitive Classification
        if clean_name in cls.SENSITIVE_SKILLS:
            return RiskAssessment(
                risk_level=RiskLevel.SENSITIVE,
                requires_confirmation=True,
                reason=f"Skill '{clean_name}' modifies application state or user file metadata."
            )

        # 5. Direct Safe Classification
        if clean_name in cls.SAFE_SKILLS:
            return RiskAssessment(
                risk_level=RiskLevel.SAFE,
                requires_confirmation=False,
                reason=f"Skill '{clean_name}' performs read-only inspection or safe resource creation."
            )

        # 6. Default Fallback for custom registered tools (Conservative Sensitive Default)
        return RiskAssessment(
            risk_level=RiskLevel.SENSITIVE,
            requires_confirmation=True,
            reason=f"Skill '{clean_name}' requires confirmation under conservative safety policy."
        )

risk_classifier = ActionRiskClassifier()
