import time
import uuid
import secrets
import hashlib
import json
import socket
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict

BYTEX_PHONE_PROTOCOL = 1
PAIRING_EXPIRATION_SECONDS = 60
HEARTBEAT_INTERVAL_SECONDS = 10
HEARTBEAT_TIMEOUT_SECONDS = 30

def get_local_ip() -> str:
    """Gets primary local network IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        # Connect to non-routable IP to determine best local interface
        s.connect(("10.254.254.254", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

@dataclass
class PairingSession:
    session_id: str
    secret: str
    created_at: float
    expires_at: float
    pc_name: str
    pc_id: str
    host: str
    port: int
    protocol_version: int = BYTEX_PHONE_PROTOCOL
    status: str = "ACTIVE"  # ACTIVE, PENDING_APPROVAL, APPROVED, REJECTED, EXPIRED
    pending_device: Optional[Dict[str, Any]] = None
    approved_token: Optional[str] = None

    def is_expired(self) -> bool:
        return time.time() > self.expires_at or self.status == "EXPIRED"

    def to_qr_payload(self) -> Dict[str, Any]:
        """Compact pairing payload for QR code rendering (strictly no sensitive credentials)."""
        return {
            "v": self.protocol_version,
            "sid": self.session_id,
            "sec": self.secret,
            "pc": self.pc_name,
            "host": self.host,
            "port": self.port,
            "exp": int(self.expires_at),
        }

class PairingSessionManager:
    """Manages ephemeral 60-second single-use phone pairing sessions."""

    def __init__(self):
        self.active_sessions: Dict[str, PairingSession] = {}
        self.pc_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, socket.gethostname() + "_bytex_pc"))
        self.pc_name = socket.gethostname()

    def create_session(self, port: int = 8000) -> PairingSession:
        # Expire any previous active sessions
        self._cleanup_expired()
        
        session_id = str(uuid.uuid4())
        secret = secrets.token_hex(16)  # 32 hex chars
        now = time.time()
        
        session = PairingSession(
            session_id=session_id,
            secret=secret,
            created_at=now,
            expires_at=now + PAIRING_EXPIRATION_SECONDS,
            pc_name=self.pc_name,
            pc_id=self.pc_id,
            host=get_local_ip(),
            port=port,
            protocol_version=BYTEX_PHONE_PROTOCOL,
            status="ACTIVE"
        )
        self.active_sessions[session_id] = session
        print(f"[PhonePairing] Created pairing session {session_id} (Expires in {PAIRING_EXPIRATION_SECONDS}s, secret=[REDACTED])")
        return session

    def get_session(self, session_id: Optional[str] = None) -> Optional[PairingSession]:
        if session_id:
            session = self.active_sessions.get(session_id)
            if session:
                if session.status not in ["PENDING_APPROVAL", "APPROVED"] and session.is_expired():
                    session.status = "EXPIRED"
                    return None
                return session
            return None
        
        # If session_id not given, search for any pending or active session
        for sess in reversed(list(self.active_sessions.values())):
            if sess.status == "PENDING_APPROVAL" or (sess.status == "ACTIVE" and not sess.is_expired()):
                return sess
        return None

    def validate_pairing_request(
        self, session_id: str, secret: str, device_id: str, device_name: str, platform: str = "Android"
    ) -> Tuple[bool, str]:
        """
        Validates incoming pairing request from Android app scan.
        Enforces single-use token and 60-second expiration.
        """
        session = self.active_sessions.get(session_id)
        if not session:
            print(f"[PhonePairing] Validation failed: Session {session_id} not found in active_sessions")
            return False, "Pairing session not found"
        
        if session.is_expired() and session.status not in ["PENDING_APPROVAL", "APPROVED"]:
            session.status = "EXPIRED"
            print(f"[PhonePairing] Validation failed: Session {session_id} has expired")
            return False, "Pairing code expired"

        if session.status != "ACTIVE":
            print(f"[PhonePairing] Validation failed: Session {session_id} is in status '{session.status}'")
            return False, "Pairing code already used or invalid"

        if not secrets.compare_digest(session.secret, secret):
            print(f"[PhonePairing] Validation failed: Secret mismatch for session {session_id}")
            return False, "Invalid pairing secret token"

        if not device_id or not device_name:
            print(f"[PhonePairing] Validation failed: Missing device identification")
            return False, "Invalid device identification"

        # Mark single-use session as pending approval
        session.status = "PENDING_APPROVAL"
        session.pending_device = {
            "device_id": device_id.strip(),
            "device_name": device_name.strip(),
            "platform": platform,
            "requested_at": time.time()
        }
        print(f"[PhonePairing] Session {session_id} pending approval for device: '{device_name}' ({device_id})")
        return True, "Pending user approval on PC"

    def approve_session(self, session_id: str, approved: bool) -> Tuple[bool, Optional[Dict[str, Any]], str, Optional[str]]:
        """Approves or rejects the pending phone pairing session."""
        session = self.active_sessions.get(session_id)
        if not session:
            # Check if there is any pending session
            for s in self.active_sessions.values():
                if s.status == "PENDING_APPROVAL":
                    session = s
                    break
        
        if not session:
            print(f"[PhonePairing] Approve error: Session {session_id} not found")
            return False, None, "Session not found", None

        if session.is_expired() and session.status != "PENDING_APPROVAL":
            session.status = "EXPIRED"
            return False, None, "Session expired", None

        if session.status != "PENDING_APPROVAL" or not session.pending_device:
            print(f"[PhonePairing] Approve error: Session {session.session_id} has status '{session.status}'")
            return False, None, "No pending device approval", None

        if not approved:
            session.status = "REJECTED"
            dev = session.pending_device
            print(f"[PhonePairing] Session {session.session_id} REJECTED by user for device '{dev.get('device_name')}'")
            return False, dev, "Pairing rejected by user", None

        dev_info = session.pending_device
        trusted_dev, raw_token = secure_phone_manager.register_trusted_device(
            device_id=dev_info["device_id"],
            device_name=dev_info["device_name"],
            platform=dev_info.get("platform", "Android")
        )
        session.status = "APPROVED"
        session.approved_token = raw_token
        print(f"[PhonePairing] Session {session.session_id} APPROVED by user for device '{dev_info.get('device_name')}'. Device registered as TRUSTED.")
        return True, dev_info, "Pairing approved", raw_token

    def cancel_session(self, session_id: str):
        if session_id in self.active_sessions:
            self.active_sessions[session_id].status = "EXPIRED"
            self.active_sessions.pop(session_id, None)

    def _cleanup_expired(self):
        now = time.time()
        expired_ids = [
            sid for sid, s in self.active_sessions.items()
            if (now > s.expires_at and s.status not in ["PENDING_APPROVAL", "APPROVED"]) or s.status in ["EXPIRED", "REJECTED"]
        ]
        for sid in expired_ids:
            self.active_sessions.pop(sid, None)

@dataclass
class TrustedDevice:
    device_id: str
    device_name: str
    platform: str
    paired_at: float
    token_hash: str
    status: str = "TRUSTED"  # TRUSTED, REVOKED
    permissions: List[str] = None
    last_connected_at: Optional[float] = None

    def __post_init__(self):
        if self.permissions is None:
            self.permissions = ["PHONE_CONNECTION"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "device_name": self.device_name,
            "platform": self.platform,
            "paired_at": self.paired_at,
            "status": self.status,
            "permissions": self.permissions,
            "last_connected_at": self.last_connected_at,
        }

class SecurePhoneConnectionManager:
    """Manages trusted device registry, long-term authentication, and live connection states."""

    def __init__(self, storage_dir: Optional[str] = None):
        if storage_dir is None:
            base_dir = Path(__file__).resolve().parent.parent / "storage"
        else:
            base_dir = Path(storage_dir)
        
        base_dir.mkdir(parents=True, exist_ok=True)
        self.storage_file = base_dir / "trusted_phone_devices.json"
        self.trusted_devices: Dict[str, TrustedDevice] = {}
        self.live_connections: Dict[str, Any] = {}  # device_id -> connection object
        self.last_heartbeats: Dict[str, float] = {}
        self._load_devices()

    def register_trusted_device(
        self, device_id: str, device_name: str, platform: str = "Android"
    ) -> Tuple[TrustedDevice, str]:
        """
        Creates and stores a trusted device relationship with cryptographically hashed token.
        Returns the TrustedDevice record and the raw auth_token (sent once to Android during handshake).
        """
        raw_token = secrets.token_hex(32)  # 64 hex chars
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        device = TrustedDevice(
            device_id=device_id,
            device_name=device_name,
            platform=platform,
            paired_at=time.time(),
            token_hash=token_hash,
            status="TRUSTED",
            permissions=["PHONE_CONNECTION"],
            last_connected_at=time.time()
        )
        self.trusted_devices[device_id] = device
        self._save_devices()
        print(f"[PhonePairing] Device '{device_name}' ({device_id}) registered as TRUSTED")
        return device, raw_token

    def authenticate_device(self, device_id: str, raw_token: str) -> bool:
        """Cryptographically verifies device credentials."""
        device = self.trusted_devices.get(device_id)
        if not device:
            print(f"[PhonePairing] Auth failed: Unknown device '{device_id}'")
            return False

        if device.status != "TRUSTED":
            print(f"[PhonePairing] Auth failed: Device '{device_id}' is {device.status}")
            return False

        expected_hash = device.token_hash
        candidate_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        if secrets.compare_digest(expected_hash, candidate_hash):
            device.last_connected_at = time.time()
            self._save_devices()
            return True

        print(f"[PhonePairing] Auth failed: Invalid token for device '{device_id}'")
        return False

    def revoke_device(self, device_id: str) -> bool:
        """Revokes a trusted device permanently. Invalidate credentials."""
        device = self.trusted_devices.get(device_id)
        if not device:
            return False

        device.status = "REVOKED"
        self._save_devices()
        
        # Disconnect live connection if any
        self.disconnect_device(device_id)
        print(f"[PhonePairing] Device '{device.device_name}' ({device_id}) REVOKED")
        return True

    def remove_device(self, device_id: str) -> bool:
        """Completely deletes a device from the trusted store."""
        if device_id in self.trusted_devices:
            self.disconnect_device(device_id)
            del self.trusted_devices[device_id]
            self._save_devices()
            print(f"[PhonePairing] Device '{device_id}' completely removed from trusted store")
            return True
        return False

    def list_trusted_devices(self) -> List[Dict[str, Any]]:
        result = []
        for dev_id, dev in self.trusted_devices.items():
            item = dev.to_dict()
            item["is_connected"] = dev_id in self.live_connections
            result.append(item)
        return result

    def get_device(self, device_id: str) -> Optional[TrustedDevice]:
        return self.trusted_devices.get(device_id)

    def set_connected(self, device_id: str, ws_connection: Any):
        self.live_connections[device_id] = ws_connection
        self.last_heartbeats[device_id] = time.time()
        if device_id in self.trusted_devices:
            self.trusted_devices[device_id].last_connected_at = time.time()

    def record_heartbeat(self, device_id: str):
        if device_id in self.live_connections:
            self.last_heartbeats[device_id] = time.time()

    def is_connected(self, device_id: str) -> bool:
        if device_id not in self.live_connections:
            return False
        last_hb = self.last_heartbeats.get(device_id, 0)
        if time.time() - last_hb > HEARTBEAT_TIMEOUT_SECONDS:
            self.disconnect_device(device_id)
            return False
        return True

    def disconnect_device(self, device_id: str):
        if device_id in self.live_connections:
            del self.live_connections[device_id]
        if device_id in self.last_heartbeats:
            del self.last_heartbeats[device_id]

    def _save_devices(self):
        try:
            data = {
                dev_id: {
                    "device_id": d.device_id,
                    "device_name": d.device_name,
                    "platform": d.platform,
                    "paired_at": d.paired_at,
                    "token_hash": d.token_hash,
                    "status": d.status,
                    "permissions": d.permissions,
                    "last_connected_at": d.last_connected_at
                }
                for dev_id, d in self.trusted_devices.items()
            }
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[PhonePairing] Error saving trusted devices: {e}")

    def _load_devices(self):
        if not self.storage_file.exists():
            return
        try:
            with open(self.storage_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for dev_id, item in data.items():
                    self.trusted_devices[dev_id] = TrustedDevice(
                        device_id=item["device_id"],
                        device_name=item["device_name"],
                        platform=item.get("platform", "Android"),
                        paired_at=item["paired_at"],
                        token_hash=item["token_hash"],
                        status=item.get("status", "TRUSTED"),
                        permissions=item.get("permissions", ["PHONE_CONNECTION"]),
                        last_connected_at=item.get("last_connected_at")
                    )
        except Exception as e:
            print(f"[PhonePairing] Error loading trusted devices: {e}")

# Global singleton managers
pairing_session_manager = PairingSessionManager()
secure_phone_manager = SecurePhoneConnectionManager()
