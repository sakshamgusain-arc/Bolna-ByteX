import time
import re
from typing import Optional, Dict, Any, Tuple
from pydantic import BaseModel

class PendingConfirmation(BaseModel):
    tool: str
    action: str
    description: str
    arguments: Dict[str, Any]
    created_at: float

class ConfirmationManager:
    """Manages pending confirmation requests for sensitive/risky ByteX PC actions."""

    _instance: Optional["ConfirmationManager"] = None
    _pending: Optional[PendingConfirmation] = None

    # Positive and negative affirmation regex patterns
    CONFIRM_POSITIVE_PATTERN = r"^(?:yes|y|confirm|do\s+it|proceed|sure|okay|ok|approve|go\s+ahead|yes,?\s+(?:delete|do|proceed)\s+it|yes\s+please)$"
    CONFIRM_NEGATIVE_PATTERN = r"^(?:no|n|cancel|stop|abort|don\'?t\s+do\s+it|reject|deny|don\'?t\s+delete|no\s+don\'?t)$"

    @classmethod
    def get_instance(cls) -> "ConfirmationManager":
        if cls._instance is None:
            cls._instance = ConfirmationManager()
        return cls._instance

    def set_pending(self, tool: str, action: str, description: str, arguments: Dict[str, Any]) -> str:
        """Stores a pending action requiring user approval."""
        self._pending = PendingConfirmation(
            tool=tool,
            action=action,
            description=description,
            arguments=arguments,
            created_at=time.time()
        )
        print(f"[ByteX Confirmation] Pending action stored: {action} ({description})")
        if action == "delete_file":
            return f"{description}\n\nPlease confirm: (Yes, delete it / No)"
        return f"[Confirmation Required]: {description}\nDo you want to proceed? (yes/no)"

    def has_pending(self) -> bool:
        """Checks if an unexpired pending action is awaiting user confirmation."""
        if not self._pending:
            return False
        # Optional 5-minute expiry timeout
        if time.time() - self._pending.created_at > 300:
            print("[ByteX Confirmation] Pending action expired.")
            self._pending = None
            return False
        return True

    def get_pending(self) -> Optional[PendingConfirmation]:
        if self.has_pending():
            return self._pending
        return None

    def clear(self):
        """Clears any pending confirmation."""
        if self._pending:
            print(f"[ByteX Confirmation] Cleared pending action: {self._pending.action}")
        self._pending = None

    def evaluate_response(self, user_message: str) -> Optional[bool]:
        """
        Evaluates whether a user's prompt is an explicit confirmation response.
        Returns:
            True  -> User approved (yes, confirm, do it)
            False -> User rejected (no, cancel, abort)
            None  -> Unrelated prompt
        """
        clean = user_message.strip().lower()
        clean = re.sub(r"[.!?,\"\']+$", "", clean).strip()

        if re.match(self.CONFIRM_POSITIVE_PATTERN, clean):
            return True
        elif re.match(self.CONFIRM_NEGATIVE_PATTERN, clean):
            return False
        return None

confirmation_manager = ConfirmationManager.get_instance()
