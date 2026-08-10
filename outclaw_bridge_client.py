#!/usr/bin/env python3
"""
outclaw_bridge_client.py
Python client for OutClaw sync bridge
"""

import json
import os
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List


class OutClawBridge:
    """Client for the OutClaw sync bridge"""
    
    def __init__(self, base_path: Optional[str] = None):
        self.base = Path(base_path or os.path.expanduser("~/.outclaw"))
        self.bus = self.base / "sync_bus"
        self.logs = self.base / "logs"
        
        # Ensure directories exist
        self.bus.mkdir(parents=True, exist_ok=True)
        self.logs.mkdir(parents=True, exist_ok=True)
        
        self.device = "penguin"
        
    def send(self, recipient: str, msg_type: str, payload: Dict[str, Any]) -> str:
        """Send a message through the bridge"""
        import uuid
        msg_id = f"msg_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        envelope = {
            "id": msg_id,
            "sender": self.device,
            "recipient": recipient,
            "type": msg_type,
            "timestamp": datetime.now().isoformat(),
            "payload": payload
        }
        
        # Write to recipient's incoming (will be picked up by bridge)
        out_file = self.bus / recipient / "incoming" / f"{msg_id}.json"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(out_file, 'w') as f:
            json.dump(envelope, f, indent=2)
        
        # Also archive for logging
        archive_file = self.bus / "archive" / f"{msg_id}.json"
        archive_file.parent.mkdir(parents=True, exist_ok=True)
        with open(archive_file, 'w') as f:
            json.dump(envelope, f, indent=2)
        
        print(f"📤 [{self.device}] → [{recipient}] {msg_type} ({msg_id})")
        return msg_id
    
    def receive(self, sender: str) -> List[Dict[str, Any]]:
        """Receive messages from a specific sender"""
        incoming_dir = self.bus / sender / "incoming"
        if not incoming_dir.exists():
            return []
        
        messages = []
        for msg_file in incoming_dir.glob("*.json"):
            with open(msg_file, 'r') as f:
                msg = json.load(f)
            messages.append(msg)
            # Move to archive after reading
            archive_file = self.bus / sender / "archive" / msg_file.name
            archive_file.parent.mkdir(parents=True, exist_ok=True)
            msg_file.rename(archive_file)
        
        return messages
    
    def broadcast(self, msg_type: str, payload: Dict[str, Any]) -> Dict[str, str]:
        """Broadcast to all devices"""
        ids = {}
        for device in ["moto4", "a9"]:
            ids[device] = self.send(device, msg_type, payload)
        return ids
    
    def wait_for_response(self, sender: str, timeout: int = 60) -> Optional[Dict[str, Any]]:
        """Wait for a response from a device"""
        start = time.time()
        while time.time() - start < timeout:
            messages = self.receive(sender)
            if messages:
                return messages[-1]  # Return most recent
            time.sleep(2)
        return None
    
    def log_message(self, message: str, log_file: str = "bridge.log"):
        """Log a message"""
        log_path = self.logs / log_file
        with open(log_path, 'a') as f:
            f.write(f"[{datetime.now().isoformat()}] {message}\n")


# Example usage
if __name__ == "__main__":
    bridge = OutClawBridge()
    
    # Test message to both devices
    bridge.broadcast("ping", {
        "message": "Testing sync bridge",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    })
    
    print("\n✅ Test messages sent to moto4 and a9")
    print("Run the bash bridge to sync them across devices:")
    print("  ./outclaw_sync_bridge.sh sync")
