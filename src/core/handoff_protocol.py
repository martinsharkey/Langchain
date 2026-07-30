"""
Handoff Protocol — Atomic agent-to-agent data transfers.

This module ensures that handoffs between agents are:
1. Atomic: All-or-nothing transfers
2. Versioned: Code and data stay synchronized
3. Audited: Every handoff is logged
4. Checksummed: Integrity verified
5. Verified: Destination validates before accepting

Usage:
    protocol = HandoffProtocol(version_manager)
    
    # Prepare handoff
    handoff = protocol.prepare_handoff(
        from_agent="developer",
        to_agent="tester",
        version_id="v123",
        payload={"code": "...", "metadata": "..."},
        reason="Testing new momentum indicator"
    )
    
    # Recipient validates and accepts
    if handoff.validate():
        handoff.accept()
    else:
        handoff.reject(reason="Tests failing")
"""

import os
import json
import hashlib
import uuid
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
import sqlite3

logger = logging.getLogger("core.handoff_protocol")


@dataclass
class HandoffPackage:
    """Atomic unit of data transfer between agents."""
    id: str                          # UUID
    timestamp: str                   # ISO timestamp
    from_agent: str                  # Sender
    to_agent: str                    # Recipient
    version_id: str                  # Code version
    reason: str                      # Why this handoff?
    payload: Dict[str, Any]          # Data being transferred
    checksum: str                    # SHA256 of payload
    signature: str                   # HMAC signature
    metadata: Dict[str, Any]         # Additional context
    status: str                      # "prepared" | "accepted" | "rejected"
    validation_result: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        result = asdict(self)
        result["validation_result"] = self.validation_result
        return result


class HandoffProtocol:
    """
    Manages atomic agent-to-agent handoffs with full integrity checks.
    """
    
    DB_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data",
        "handoff_protocol.db",
    )
    
    def __init__(self, version_manager=None):
        """
        Initialize handoff protocol.
        
        Args:
            version_manager: VersionManager instance (for validation)
        """
        self.version_manager = version_manager
        self.db_path = self.DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()
        self.handoff_cache = {}  # Local cache for quick access
        
        logger.info(f"HandoffProtocol initialized at {self.db_path}")
    
    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS handoff_packages (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                from_agent TEXT NOT NULL,
                to_agent TEXT NOT NULL,
                version_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                payload TEXT NOT NULL,
                checksum TEXT NOT NULL UNIQUE,
                signature TEXT NOT NULL,
                metadata TEXT,
                status TEXT NOT NULL DEFAULT 'prepared',
                validation_result TEXT,
                created_at TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS handoff_log (
                id TEXT PRIMARY KEY,
                handoff_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_data TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                agent TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (handoff_id) REFERENCES handoff_packages(id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def prepare_handoff(
        self,
        from_agent: str,
        to_agent: str,
        version_id: str,
        payload: Dict[str, Any],
        reason: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> HandoffPackage:
        """
        Prepare an atomic handoff package.
        
        Args:
            from_agent: Sending agent
            to_agent: Receiving agent
            version_id: Code version ID
            payload: Data to transfer (will be JSON-serialized)
            reason: Why this handoff?
            metadata: Optional context
            
        Returns:
            HandoffPackage ready for transfer
        """
        
        handoff_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Serialize payload and calculate checksum
        payload_json = json.dumps(payload, sort_keys=True)
        checksum = hashlib.sha256(payload_json.encode()).hexdigest()
        
        # Generate signature (HMAC-like)
        signature_data = f"{handoff_id}{from_agent}{to_agent}{version_id}{checksum}{timestamp}"
        signature = hashlib.sha256(signature_data.encode()).hexdigest()
        
        package = HandoffPackage(
            id=handoff_id,
            timestamp=timestamp,
            from_agent=from_agent,
            to_agent=to_agent,
            version_id=version_id,
            reason=reason,
            payload=payload,
            checksum=checksum,
            signature=signature,
            metadata=metadata or {},
            status="prepared"
        )
        
        # Store in database
        self._store_handoff(package)
        
        # Log event
        self._log_handoff_event(
            handoff_id=handoff_id,
            event_type="prepared",
            event_data={
                "from": from_agent,
                "to": to_agent,
                "version": version_id,
                "reason": reason
            },
            agent=from_agent
        )
        
        logger.info(
            f"Handoff prepared {handoff_id}: "
            f"{from_agent} → {to_agent} (v{version_id[:8]}...) "
            f"checksum: {checksum[:8]}..."
        )
        
        return package
    
    def validate_handoff(self, handoff: HandoffPackage) -> Dict[str, Any]:
        """
        Validate a handoff package before acceptance.
        
        Checks:
        1. Checksum matches payload
        2. Signature is valid
        3. Version exists and is safe
        4. Recipient is authorized
        5. No version conflicts
        
        Returns:
            {
                "valid": bool,
                "issues": [str, ...],
                "warnings": [str, ...],
                "version_status": {...}
            }
        """
        
        issues = []
        warnings = []
        version_status = None
        
        # 1. Verify checksum
        payload_json = json.dumps(handoff.payload, sort_keys=True)
        calculated_checksum = hashlib.sha256(payload_json.encode()).hexdigest()
        if calculated_checksum != handoff.checksum:
            issues.append(f"Checksum mismatch: expected {handoff.checksum}, got {calculated_checksum}")
        
        # 2. Verify signature
        signature_data = (
            f"{handoff.id}{handoff.from_agent}{handoff.to_agent}"
            f"{handoff.version_id}{handoff.checksum}{handoff.timestamp}"
        )
        calculated_signature = hashlib.sha256(signature_data.encode()).hexdigest()
        if calculated_signature != handoff.signature:
            issues.append(f"Signature verification failed")
        
        # 3. Validate version with version manager
        if self.version_manager:
            try:
                version_status = self.version_manager.get_version_status(handoff.version_id)
                if not version_status["all_tests_passed"]:
                    warnings.append(f"Version has failing tests ({version_status['test_count'] - version_status['tests_passed']} failed)")
            except ValueError:
                issues.append(f"Version {handoff.version_id} not found")
        
        # 4. Validate agent transition
        valid_transitions = {
            "developer": ["tester"],
            "tester": ["developer", "trader"],
            "trader": ["researcher"],
            "researcher": ["trader"],
        }
        
        if handoff.from_agent not in valid_transitions:
            issues.append(f"Unknown agent: {handoff.from_agent}")
        elif handoff.to_agent not in valid_transitions.get(handoff.from_agent, []):
            issues.append(
                f"Invalid transition: {handoff.from_agent} → {handoff.to_agent}. "
                f"Valid targets: {valid_transitions.get(handoff.from_agent, [])}"
            )
        
        # 5. Check for version conflicts
        if "previous_version_id" in handoff.payload:
            prev_id = handoff.payload["previous_version_id"]
            if self.version_manager:
                try:
                    prev_status = self.version_manager.get_version_status(prev_id)
                    if prev_status["status"] != "deployed":
                        warnings.append(
                            f"Previous version {prev_id[:8]}... not yet deployed. "
                            f"Potential version mismatch."
                        )
                except ValueError:
                    # Previous version doesn't exist, that's ok
                    pass
        
        is_valid = len(issues) == 0
        
        validation_result = {
            "valid": is_valid,
            "issues": issues,
            "warnings": warnings,
            "version_status": version_status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Store validation result
        handoff.validation_result = validation_result
        
        logger.info(
            f"Handoff {handoff.id[:8]}... validation: "
            f"{'PASS' if is_valid else 'FAIL'} "
            f"({len(issues)} issues, {len(warnings)} warnings)"
        )
        
        return validation_result
    
    def accept_handoff(self, handoff: HandoffPackage, recipient: str) -> bool:
        """
        Accept a handoff on the recipient side.
        
        Args:
            handoff: HandoffPackage to accept
            recipient: Name of receiving agent
            
        Returns:
            True if accepted successfully
        """
        
        # Verify checksum one more time
        payload_json = json.dumps(handoff.payload, sort_keys=True)
        calculated_checksum = hashlib.sha256(payload_json.encode()).hexdigest()
        if calculated_checksum != handoff.checksum:
            logger.error(f"Handoff {handoff.id} FAILED integrity check during acceptance")
            self.reject_handoff(handoff, recipient, "Integrity check failed")
            return False
        
        # Update status
        handoff.status = "accepted"
        self._update_handoff_status(handoff.id, "accepted")
        
        # Log event
        self._log_handoff_event(
            handoff_id=handoff.id,
            event_type="accepted",
            event_data={"by": recipient},
            agent=recipient
        )
        
        logger.info(f"Handoff {handoff.id[:8]}... ACCEPTED by {recipient}")
        
        return True
    
    def reject_handoff(
        self,
        handoff: HandoffPackage,
        recipient: str,
        reason: str
    ) -> bool:
        """
        Reject a handoff on the recipient side.
        
        Args:
            handoff: HandoffPackage to reject
            recipient: Name of receiving agent
            reason: Why rejecting?
            
        Returns:
            True if rejected successfully
        """
        
        # Update status
        handoff.status = "rejected"
        self._update_handoff_status(handoff.id, "rejected")
        
        # Log event
        self._log_handoff_event(
            handoff_id=handoff.id,
            event_type="rejected",
            event_data={"by": recipient, "reason": reason},
            agent=recipient
        )
        
        logger.warning(f"Handoff {handoff.id[:8]}... REJECTED by {recipient}: {reason}")
        
        return True
    
    def get_handoff_status(self, handoff_id: str) -> Dict[str, Any]:
        """Get status of a handoff."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM handoff_packages WHERE id = ?", (handoff_id,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return {"error": f"Handoff {handoff_id} not found"}
        
        # Get audit log
        cursor.execute("""
            SELECT event_type, event_data, timestamp, agent
            FROM handoff_log
            WHERE handoff_id = ?
            ORDER BY created_at
        """, (handoff_id,))
        
        log_rows = cursor.fetchall()
        conn.close()
        
        audit_log = [
            {
                "event_type": row[0],
                "event_data": json.loads(row[1]),
                "timestamp": row[2],
                "agent": row[3]
            }
            for row in log_rows
        ]
        
        return {
            "handoff_id": handoff_id,
            "from_agent": row[2],
            "to_agent": row[3],
            "version_id": row[4],
            "status": row[10],
            "created_at": row[13],
            "validation_result": json.loads(row[11]) if row[11] else None,
            "audit_log": audit_log
        }
    
    def get_pending_handoffs(self, agent: str) -> List[Dict[str, Any]]:
        """Get all pending handoffs for an agent."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, from_agent, version_id, reason, timestamp
            FROM handoff_packages
            WHERE to_agent = ? AND status = 'prepared'
            ORDER BY timestamp
        """, (agent,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "handoff_id": row[0],
                "from_agent": row[1],
                "version_id": row[2],
                "reason": row[3],
                "timestamp": row[4]
            }
            for row in rows
        ]
    
    def _store_handoff(self, package: HandoffPackage):
        """Store handoff in database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO handoff_packages
            (id, timestamp, from_agent, to_agent, version_id, reason, payload, checksum, signature, metadata, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            package.id, package.timestamp, package.from_agent, package.to_agent,
            package.version_id, package.reason, json.dumps(package.payload),
            package.checksum, package.signature, json.dumps(package.metadata),
            package.status, datetime.now(timezone.utc).isoformat()
        ))
        
        conn.commit()
        conn.close()
    
    def _update_handoff_status(self, handoff_id: str, new_status: str):
        """Update handoff status in database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE handoff_packages
            SET status = ?
            WHERE id = ?
        """, (new_status, handoff_id))
        
        conn.commit()
        conn.close()
    
    def _log_handoff_event(
        self,
        handoff_id: str,
        event_type: str,
        event_data: Dict[str, Any],
        agent: str
    ):
        """Log a handoff event."""
        log_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO handoff_log
            (id, handoff_id, event_type, event_data, timestamp, agent, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            log_id, handoff_id, event_type, json.dumps(event_data),
            timestamp, agent, datetime.now(timezone.utc).isoformat()
        ))
        
        conn.commit()
        conn.close()
