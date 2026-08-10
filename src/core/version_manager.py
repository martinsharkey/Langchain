"""
Version Management System — Ensures code and tests stay synchronized.

This module provides version tracking for the trading bot's code and tests.
It ensures that:
1. Each code change gets a unique version ID
2. Tests are tied to specific code versions
3. Handoffs only proceed when versions match (or conflict is approved)
4. Audit trail shows all version transitions

Usage:
    vm = VersionManager()
    
    # Record a new code version
    version = vm.record_code_change(
        module="strategies/xauusd_strategy.py",
        description="Added new momentum indicator",
        author="bot"
    )
    
    # Record test results
    vm.record_test_results(
        version_id=version.id,
        test_name="test_momentum_indicator",
        passed=True,
        details={...}
    )
    
    # Check version status
    status = vm.get_version_status(version.id)
    
    # Validate before handoff
    is_safe = vm.validate_handoff(from_agent="tester", to_agent="developer")
"""

import os
import json
import sqlite3
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger("core.version_manager")


@dataclass
class CodeVersion:
    """Represents a single code version snapshot."""
    id: str                          # UUID
    timestamp: str                   # ISO format timestamp
    module: str                      # File path relative to src/
    description: str                 # What changed
    author: str                      # Who made the change (agent name)
    code_hash: str                   # SHA256 of changed code
    parent_version_id: Optional[str] # Previous version
    status: str                      # "draft" | "tested" | "approved" | "deployed"
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class TestResult:
    """Represents test results for a code version."""
    id: str                          # UUID
    version_id: str                  # Which version this tests
    timestamp: str                   # ISO format timestamp
    test_name: str                   # Test identifier
    passed: bool                     # Did test pass?
    error_message: Optional[str]     # If failed, error details
    details: Dict[str, Any]          # Additional test data
    agent_run_by: str                # Which agent ran this
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class Handoff:
    """Represents an agent-to-agent handoff."""
    id: str                          # UUID
    timestamp: str                   # ISO format timestamp
    from_agent: str                  # Sender (e.g., "developer")
    to_agent: str                    # Receiver (e.g., "tester")
    version_id: str                  # Version being handed off
    status: str                      # "pending" | "accepted" | "rejected"
    payload: Dict[str, Any]          # Data being handed off
    reason: str                      # Why this handoff?
    signature: str                   # Hash for integrity check
    metadata: Dict[str, Any]         # Additional context
    
    def to_dict(self) -> Dict:
        return asdict(self)


class VersionManager:
    """
    Manages code versions and enforces synchronization between code and tests.
    """
    
    DB_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data",
        "version_management.db",
    )
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize version manager."""
        self.db_path = db_path or self.DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()
        logger.info(f"Version Manager initialized at {self.db_path}")
    
    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Code versions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS code_versions (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                module TEXT NOT NULL,
                description TEXT NOT NULL,
                author TEXT NOT NULL,
                code_hash TEXT NOT NULL UNIQUE,
                parent_version_id TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL
            )
        """)
        
        # Test results table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_results (
                id TEXT PRIMARY KEY,
                version_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                test_name TEXT NOT NULL,
                passed BOOLEAN NOT NULL,
                error_message TEXT,
                details TEXT,
                agent_run_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (version_id) REFERENCES code_versions(id)
            )
        """)
        
        # Handoffs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS handoffs (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                from_agent TEXT NOT NULL,
                to_agent TEXT NOT NULL,
                version_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                payload TEXT NOT NULL,
                reason TEXT NOT NULL,
                signature TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (version_id) REFERENCES code_versions(id)
            )
        """)
        
        # Version audit trail table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS version_audit (
                id TEXT PRIMARY KEY,
                version_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_data TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                agent TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (version_id) REFERENCES code_versions(id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def record_code_change(
        self,
        module: str,
        description: str,
        author: str,
        code_content: Optional[str] = None,
        parent_version_id: Optional[str] = None
    ) -> CodeVersion:
        """
        Record a new code version.
        
        Args:
            module: File path (e.g., "strategies/xauusd_strategy.py")
            description: What changed
            author: Agent making the change
            code_content: Actual code (for hashing)
            parent_version_id: Previous version ID for lineage
            
        Returns:
            CodeVersion object
        """
        version_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Generate code hash
        if code_content:
            code_hash = hashlib.sha256(code_content.encode()).hexdigest()
        else:
            # If no content provided, use module path + timestamp
            code_hash = hashlib.sha256(f"{module}{timestamp}".encode()).hexdigest()
        
        version = CodeVersion(
            id=version_id,
            timestamp=timestamp,
            module=module,
            description=description,
            author=author,
            code_hash=code_hash,
            parent_version_id=parent_version_id,
            status="draft"
        )
        
        # Store in database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO code_versions
            (id, timestamp, module, description, author, code_hash, parent_version_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            version.id, version.timestamp, version.module, version.description,
            version.author, version.code_hash, version.parent_version_id,
            version.status, datetime.now(timezone.utc).isoformat()
        ))
        
        # Audit trail
        self._audit_log(
            version_id=version_id,
            event_type="version_created",
            event_data={"module": module, "description": description},
            agent=author
        )
        
        conn.commit()
        conn.close()
        
        logger.info(f"Recorded code version {version_id} for {module}")
        return version
    
    def record_test_results(
        self,
        version_id: str,
        test_name: str,
        passed: bool,
        agent_run_by: str,
        error_message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> TestResult:
        """
        Record test results for a version.
        
        Args:
            version_id: Which version was tested
            test_name: Name of the test
            passed: Did it pass?
            agent_run_by: Which agent ran the test
            error_message: If failed
            details: Additional context
            
        Returns:
            TestResult object
        """
        test_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        result = TestResult(
            id=test_id,
            version_id=version_id,
            timestamp=timestamp,
            test_name=test_name,
            passed=passed,
            error_message=error_message,
            details=details or {},
            agent_run_by=agent_run_by
        )
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO test_results
            (id, version_id, timestamp, test_name, passed, error_message, details, agent_run_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result.id, result.version_id, result.timestamp, result.test_name,
            result.passed, result.error_message, json.dumps(result.details),
            result.agent_run_by, datetime.now(timezone.utc).isoformat()
        ))
        
        # Update version status if all tests pass
        self._update_version_status(version_id, conn)
        
        # Audit trail
        self._audit_log(
            version_id=version_id,
            event_type="test_executed",
            event_data={"test_name": test_name, "passed": passed},
            agent=agent_run_by
        )
        
        conn.commit()
        conn.close()
        
        status_str = "PASS" if passed else "FAIL"
        logger.info(f"Test {test_name} {status_str} for version {version_id}")
        
        return result
    
    def get_version_status(self, version_id: str) -> Dict[str, Any]:
        """
        Get current status of a version.
        
        Returns:
            {
                "version": CodeVersion,
                "test_results": [TestResult, ...],
                "all_tests_passed": bool,
                "is_safe_to_deploy": bool
            }
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get version
        cursor.execute("SELECT * FROM code_versions WHERE id = ?", (version_id,))
        version_row = cursor.fetchone()
        if not version_row:
            conn.close()
            raise ValueError(f"Version {version_id} not found")
        
        # Get test results
        cursor.execute("SELECT * FROM test_results WHERE version_id = ? ORDER BY created_at", (version_id,))
        test_rows = cursor.fetchall()
        
        conn.close()
        
        # Parse results
        tests = []
        all_passed = True
        for row in test_rows:
            test = TestResult(
                id=row[0], version_id=row[1], timestamp=row[2],
                test_name=row[3], passed=bool(row[4]),
                error_message=row[5], details=json.loads(row[6]),
                agent_run_by=row[7]
            )
            tests.append(test)
            if not test.passed:
                all_passed = False
        
        # Determine if safe to deploy
        is_safe = all_passed and len(tests) > 0
        
        return {
            "version_id": version_id,
            "module": version_row[2],
            "description": version_row[3],
            "status": version_row[7],
            "test_count": len(tests),
            "tests_passed": sum(1 for t in tests if t.passed),
            "all_tests_passed": all_passed,
            "test_results": [t.to_dict() for t in tests],
            "is_safe_to_deploy": is_safe
        }
    
    def create_handoff(
        self,
        from_agent: str,
        to_agent: str,
        version_id: str,
        payload: Dict[str, Any],
        reason: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Handoff:
        """
        Create an agent-to-agent handoff.
        
        Args:
            from_agent: Sending agent
            to_agent: Receiving agent
            version_id: Version being handed off
            payload: Data to transfer
            reason: Why this handoff?
            metadata: Optional context
            
        Returns:
            Handoff object
        """
        handoff_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Calculate signature for integrity
        signature = self._calculate_signature({
            "from_agent": from_agent,
            "to_agent": to_agent,
            "version_id": version_id,
            "payload": payload,
            "timestamp": timestamp
        })
        
        handoff = Handoff(
            id=handoff_id,
            timestamp=timestamp,
            from_agent=from_agent,
            to_agent=to_agent,
            version_id=version_id,
            status="pending",
            payload=payload,
            reason=reason,
            signature=signature,
            metadata=metadata or {}
        )
        
        # Validate before handoff
        validation = self.validate_handoff(from_agent, to_agent, version_id)
        if not validation["safe"]:
            logger.warning(f"Handoff validation failed: {validation['issues']}")
            # Still create handoff but mark it for review
            if not validation["approved"]:
                handoff.status = "pending_review"
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO handoffs
            (id, timestamp, from_agent, to_agent, version_id, status, payload, reason, signature, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            handoff.id, handoff.timestamp, handoff.from_agent, handoff.to_agent,
            handoff.version_id, handoff.status, json.dumps(handoff.payload),
            handoff.reason, handoff.signature, json.dumps(handoff.metadata),
            datetime.now(timezone.utc).isoformat()
        ))
        
        # Audit trail
        self._audit_log(
            version_id=version_id,
            event_type="handoff_created",
            event_data={"from": from_agent, "to": to_agent, "reason": reason},
            agent=from_agent
        )
        
        conn.commit()
        conn.close()
        
        logger.info(f"Created handoff {handoff_id}: {from_agent} → {to_agent} (v{version_id})")
        
        return handoff
    
    def validate_handoff(
        self,
        from_agent: str,
        to_agent: str,
        version_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate if a handoff is safe to proceed.
        
        Returns:
            {
                "safe": bool,  # All checks pass?
                "approved": bool,  # Safe AND approved?
                "issues": [str, ...],  # Any problems
                "version_status": {...}
            }
        """
        issues = []
        
        # Validate agent transition
        valid_transitions = {
            "developer": ["tester"],
            "tester": ["developer", "trader"],
            "trader": ["researcher"],
            "researcher": ["trader"],
        }
        
        if from_agent not in valid_transitions or to_agent not in valid_transitions.get(from_agent, []):
            issues.append(f"Invalid transition: {from_agent} → {to_agent}")
        
        # Check version status if provided
        version_status = None
        if version_id:
            try:
                version_status = self.get_version_status(version_id)
                if not version_status["all_tests_passed"]:
                    issues.append(f"Version {version_id} has failing tests")
            except ValueError:
                issues.append(f"Version {version_id} not found")
        
        is_safe = len(issues) == 0
        is_approved = is_safe  # TODO: could add approval workflow here
        
        return {
            "safe": is_safe,
            "approved": is_approved,
            "issues": issues,
            "version_status": version_status
        }
    
    def accept_handoff(self, handoff_id: str, receiving_agent: str):
        """Accept a handoff."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE handoffs
            SET status = 'accepted'
            WHERE id = ?
        """, (handoff_id,))
        
        # Get handoff details for audit
        cursor.execute("SELECT version_id, from_agent FROM handoffs WHERE id = ?", (handoff_id,))
        result = cursor.fetchone()
        version_id = result[0] if result else None
        from_agent = result[1] if result else None
        
        if version_id:
            self._audit_log(
                version_id=version_id,
                event_type="handoff_accepted",
                event_data={"handoff_id": handoff_id, "from": from_agent},
                agent=receiving_agent
            )
        
        conn.commit()
        conn.close()
        
        logger.info(f"Handoff {handoff_id} accepted by {receiving_agent}")
    
    def reject_handoff(self, handoff_id: str, receiving_agent: str, reason: str):
        """Reject a handoff."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE handoffs
            SET status = 'rejected'
            WHERE id = ?
        """, (handoff_id,))
        
        # Get handoff details for audit
        cursor.execute("SELECT version_id, from_agent FROM handoffs WHERE id = ?", (handoff_id,))
        result = cursor.fetchone()
        version_id = result[0] if result else None
        from_agent = result[1] if result else None
        
        if version_id:
            self._audit_log(
                version_id=version_id,
                event_type="handoff_rejected",
                event_data={"handoff_id": handoff_id, "from": from_agent, "reason": reason},
                agent=receiving_agent
            )
        
        conn.commit()
        conn.close()
        
        logger.warning(f"Handoff {handoff_id} rejected by {receiving_agent}: {reason}")
    
    def get_audit_trail(self, version_id: str) -> List[Dict[str, Any]]:
        """Get complete audit trail for a version."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT event_type, event_data, timestamp, agent
            FROM version_audit
            WHERE version_id = ?
            ORDER BY created_at
        """, (version_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "event_type": row[0],
                "event_data": json.loads(row[1]),
                "timestamp": row[2],
                "agent": row[3]
            }
            for row in rows
        ]
    
    def _update_version_status(self, version_id: str, conn: sqlite3.Connection):
        """Update version status based on test results."""
        cursor = conn.cursor()
        
        # Get all tests for this version
        cursor.execute("SELECT passed FROM test_results WHERE version_id = ?", (version_id,))
        test_rows = cursor.fetchall()
        
        if test_rows and all(row[0] for row in test_rows):
            # All tests passed
            cursor.execute("""
                UPDATE code_versions
                SET status = 'tested'
                WHERE id = ?
            """, (version_id,))
    
    def _calculate_signature(self, data: Dict[str, Any]) -> str:
        """Generate integrity signature for handoff."""
        json_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()
    
    def _audit_log(
        self,
        version_id: str,
        event_type: str,
        event_data: Dict[str, Any],
        agent: str
    ):
        """Create audit log entry."""
        log_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO version_audit
            (id, version_id, event_type, event_data, timestamp, agent, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            log_id, version_id, event_type, json.dumps(event_data),
            timestamp, agent, datetime.now(timezone.utc).isoformat()
        ))
        
        conn.commit()
        conn.close()
