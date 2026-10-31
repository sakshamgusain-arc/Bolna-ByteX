import json
import time
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from services.phone_pairing import (
    pairing_session_manager,
    secure_phone_manager,
    BYTEX_PHONE_PROTOCOL
)

router = APIRouter()

class CreatePairingResponse(BaseModel):
    session_id: str
    secret: str
    pc_name: str
    pc_id: str
    host: str
    port: int
    expires_at: int
    expires_in_seconds: int
    protocol_version: int
    qr_payload: Dict[str, Any]

class ApprovePairingRequest(BaseModel):
    session_id: str
    approved: bool

# --- REST ENDPOINTS FOR PC UI ---

@router.post("/phone/pairing/create", response_model=CreatePairingResponse)
async def create_pairing_session():
    """Generates a temporary 60-second pairing session and QR payload."""
    print("[PHONE_PAIRING] Pairing endpoint received")
    print("[PHONE_PAIRING] Creating session")
    session = pairing_session_manager.create_session()
    print(f"[PHONE_PAIRING] Session created: {session.session_id}")
    print("[PHONE_PAIRING] Expiry: 60s")
    return CreatePairingResponse(
        session_id=session.session_id,
        secret=session.secret,
        pc_name=session.pc_name,
        pc_id=session.pc_id,
        host=session.host,
        port=session.port,
        expires_at=int(session.expires_at),
        expires_in_seconds=int(max(0, session.expires_at - time.time())),
        protocol_version=session.protocol_version,
        qr_payload=session.to_qr_payload()
    )

@router.post("/phone/pairing/cancel")
async def cancel_pairing_session(session_id: str):
    """Cancels an active pairing session."""
    pairing_session_manager.cancel_session(session_id)
    return {"status": "cancelled", "session_id": session_id}

@router.get("/phone/pairing/status")
async def get_pairing_status(session_id: Optional[str] = None):
    """Returns the current status of an active or pending pairing session."""
    session = pairing_session_manager.get_session(session_id)
    if not session:
        return {"has_active_session": False, "status": "NONE"}
    
    return {
        "has_active_session": True,
        "session_id": session.session_id,
        "status": session.status,
        "expires_in_seconds": int(max(0, session.expires_at - time.time())),
        "pending_device": session.pending_device
    }

@router.post("/phone/pairing/approve")
async def approve_pairing_endpoint(req: ApprovePairingRequest):
    """PC user explicitly approves or rejects the pending phone pairing."""
    print(f"[PHONE_PAIRING] PC user action on session {req.session_id}: approved={req.approved}")
    ok, dev_info, msg, raw_token = pairing_session_manager.approve_session(req.session_id, req.approved)
    if not ok and req.approved:
        raise HTTPException(status_code=400, detail=msg)
    
    if req.approved and dev_info:
        dev = secure_phone_manager.get_device(dev_info["device_id"])
        return {
            "status": "approved",
            "message": msg,
            "device": dev.to_dict() if dev else None,
            "raw_token": "[REDACTED]"
        }
    
    return {"status": "rejected", "message": msg}

@router.get("/phone/devices")
async def list_phone_devices():
    """Lists all trusted paired Android devices and their live status."""
    return secure_phone_manager.list_trusted_devices()

@router.post("/phone/devices/{device_id}/revoke")
async def revoke_phone_device(device_id: str):
    """Permanently revokes and removes a trusted phone."""
    ok = secure_phone_manager.remove_device(device_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"status": "revoked", "device_id": device_id}

@router.post("/phone/devices/{device_id}/disconnect")
async def disconnect_phone_device(device_id: str):
    """Disconnects an active phone session."""
    secure_phone_manager.disconnect_device(device_id)
    return {"status": "disconnected", "device_id": device_id}

# --- WEBSOCKET HANDLER FOR ANDROID PHONE ---

@router.websocket("/ws/phone")
async def phone_websocket_endpoint(websocket: WebSocket):
    """Dedicated authenticated WebSocket channel for ByteX Android Companion."""
    await websocket.accept()
    print("[PhoneWS] WebSocket connection opened")
    authenticated_device_id: Optional[str] = None
    
    try:
        # Initial greeting
        await websocket.send_text(json.dumps({
            "type": "HELLO_ACK",
            "protocol_version": BYTEX_PHONE_PROTOCOL,
            "pc_name": pairing_session_manager.pc_name,
            "pc_id": pairing_session_manager.pc_id
        }))

        while True:
            raw_data = await websocket.receive_text()
            try:
                msg = json.loads(raw_data)
                msg_type = msg.get("type", "").upper()
                proto_ver = msg.get("protocol_version", BYTEX_PHONE_PROTOCOL)

                if proto_ver != BYTEX_PHONE_PROTOCOL:
                    await websocket.send_text(json.dumps({
                        "type": "ERROR",
                        "code": "UNSUPPORTED_PROTOCOL",
                        "message": f"Supported protocol version is {BYTEX_PHONE_PROTOCOL}"
                    }))
                    continue

                # 1. Pairing Request Handshake
                if msg_type == "PAIRING_REQUEST":
                    sid = msg.get("session_id", "")
                    secret = msg.get("secret", "")
                    dev_id = msg.get("device_id", "")
                    dev_name = msg.get("device_name", "Android Phone")
                    platform = msg.get("platform", "Android")
                    print(f"[PhoneWS] PAIRING_REQUEST received: session={sid}, device='{dev_name}' ({dev_id}), secret=[REDACTED]")

                    valid, reason = pairing_session_manager.validate_pairing_request(
                        session_id=sid,
                        secret=secret,
                        device_id=dev_id,
                        device_name=dev_name,
                        platform=platform
                    )
                    if not valid:
                        print(f"[PhoneWS] PAIRING_REQUEST invalid: {reason}")
                        await websocket.send_text(json.dumps({
                            "type": "PAIRING_ERROR",
                            "message": reason
                        }))
                        continue

                    # Send waiting acknowledgment to phone
                    print(f"[PhoneWS] Sending PAIRING_WAITING_APPROVAL to phone (session={sid})")
                    await websocket.send_text(json.dumps({
                        "type": "PAIRING_WAITING_APPROVAL",
                        "message": "Approval requested on ByteX PC. Please approve on your PC."
                    }))

                    # Wait for PC approval (poll session status up to 45s)
                    approved = False
                    raw_token = None
                    for _ in range(90):
                        await asyncio.sleep(0.5)
                        sess = pairing_session_manager.active_sessions.get(sid)
                        if not sess:
                            break
                        if sess.status == "APPROVED":
                            approved = True
                            raw_token = getattr(sess, "approved_token", None)
                            pairing_session_manager.active_sessions.pop(sid, None)
                            break
                        if sess.status == "REJECTED":
                            approved = False
                            pairing_session_manager.active_sessions.pop(sid, None)
                            break

                    if approved and raw_token:
                        authenticated_device_id = dev_id
                        secure_phone_manager.set_connected(dev_id, websocket)
                        print(f"[PhoneWS] PAIRING_APPROVED: Delivering credentials to '{dev_name}' ({dev_id})")
                        await websocket.send_text(json.dumps({
                            "type": "PAIRING_APPROVED",
                            "status": "CONNECTED",
                            "device_id": dev_id,
                            "device_token": raw_token,
                            "pc_name": pairing_session_manager.pc_name,
                            "permissions": ["PHONE_CONNECTION"]
                        }))
                    else:
                        print(f"[PhoneWS] PAIRING_REJECTED: Session {sid} rejected or expired")
                        await websocket.send_text(json.dumps({
                            "type": "PAIRING_REJECTED",
                            "message": "Pairing request was rejected or expired."
                        }))

                # 2. Cryptographic Reconnect Authentication
                elif msg_type == "AUTHENTICATE":
                    dev_id = msg.get("device_id", "")
                    token = msg.get("device_token", "")
                    print(f"[PhoneWS] AUTHENTICATE received for device='{dev_id}', token=[REDACTED]")

                    if secure_phone_manager.authenticate_device(dev_id, token):
                        authenticated_device_id = dev_id
                        secure_phone_manager.set_connected(dev_id, websocket)
                        print(f"[PhoneWS] AUTH_SUCCESS: Device '{dev_id}' authenticated and connected")
                        await websocket.send_text(json.dumps({
                            "type": "AUTH_SUCCESS",
                            "status": "CONNECTED",
                            "device_id": dev_id,
                            "pc_name": pairing_session_manager.pc_name,
                            "permissions": ["PHONE_CONNECTION"]
                        }))
                    else:
                        print(f"[PhoneWS] AUTH_FAILED: Authentication failed for device '{dev_id}'")
                        await websocket.send_text(json.dumps({
                            "type": "AUTH_FAILED",
                            "message": "Authentication failed. Device revoked or invalid credential."
                        }))
                        await websocket.close(code=4001)
                        break

                # 3. Heartbeat Ping / Pong
                elif msg_type == "PING":
                    if authenticated_device_id:
                        secure_phone_manager.record_heartbeat(authenticated_device_id)
                    await websocket.send_text(json.dumps({
                        "type": "PONG",
                        "timestamp": time.time()
                    }))

                elif msg_type == "PONG":
                    if authenticated_device_id:
                        secure_phone_manager.record_heartbeat(authenticated_device_id)

                # 4. Disconnect Request
                elif msg_type == "DISCONNECT":
                    if authenticated_device_id:
                        secure_phone_manager.disconnect_device(authenticated_device_id)
                    break

            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "ERROR", "message": "Invalid JSON"}))

    except WebSocketDisconnect:
        if authenticated_device_id:
            secure_phone_manager.disconnect_device(authenticated_device_id)
    except Exception as e:
        print(f"[PhoneWS] Exception: {e}")
        if authenticated_device_id:
            secure_phone_manager.disconnect_device(authenticated_device_id)
