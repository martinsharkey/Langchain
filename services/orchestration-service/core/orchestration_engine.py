"""
Orchestration Service Core Engine

Manages workflow orchestration and job coordination across services.
"""

import json
import sqlite3
from enum import Enum
from typing import Dict, List, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)


class WorkflowStage(Enum):
    """Workflow stages."""
    DISCOVERY = "discovery"
    OPTIMIZATION = "optimization"
    VALIDATION = "validation"
    DEPLOYMENT = "deployment"
    EXECUTION = "execution"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class WorkflowJob:
    """Workflow job definition and tracking."""
    job_id: str
    symbol: str
    timeframe: str
    session: str
    workflow_id: str
    current_stage: str
    status: str  # pending, running, completed, failed
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    results: Dict
    error_message: Optional[str] = None


@dataclass
class WorkflowPipeline:
    """Complete workflow pipeline from discovery to deployment."""
    workflow_id: str
    symbol: str
    timeframe: str
    session: str
    created_at: str
    status: str  # active, paused, completed, failed
    stages_completed: List[str]
    current_stage: str
    discovered_strategies: List[Dict]
    optimized_strategies: List[Dict]
    validated_strategies: List[Dict]
    error_message: Optional[str] = None


class OrchestrationEngine:
    """Core orchestration engine for workflow management."""
    
    def __init__(self, db_path: str = "./orchestration.db"):
        """
        Initialize Orchestration Engine.
        
        Args:
            db_path: SQLite database path
        """
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Workflows table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    workflow_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    session TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stages_completed TEXT NOT NULL,
                    current_stage TEXT NOT NULL,
                    discovered_strategies TEXT NOT NULL,
                    optimized_strategies TEXT NOT NULL,
                    validated_strategies TEXT NOT NULL,
                    error_message TEXT
                )
            """)
            
            # Jobs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    session TEXT NOT NULL,
                    workflow_id TEXT NOT NULL,
                    current_stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    results TEXT NOT NULL,
                    error_message TEXT,
                    FOREIGN KEY (workflow_id) REFERENCES workflows(workflow_id)
                )
            """)
            
            conn.commit()
            conn.close()
            logger.info(f"Orchestration database initialized: {self.db_path}")
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
    
    async def create_workflow(
        self,
        workflow_id: str,
        symbol: str,
        timeframe: str,
        session: str
    ) -> WorkflowPipeline:
        """
        Create a new workflow pipeline.
        
        Args:
            workflow_id: Unique workflow identifier
            symbol: Trading symbol
            timeframe: Timeframe
            session: Trading session
        
        Returns:
            WorkflowPipeline
        """
        logger.info(f"Creating workflow: {workflow_id} ({symbol}/{session}/{timeframe})")
        
        workflow = WorkflowPipeline(
            workflow_id=workflow_id,
            symbol=symbol,
            timeframe=timeframe,
            session=session,
            created_at=datetime.now(timezone.utc).isoformat(),
            status="active",
            stages_completed=[],
            current_stage=WorkflowStage.DISCOVERY.value,
            discovered_strategies=[],
            optimized_strategies=[],
            validated_strategies=[]
        )
        
        self._save_workflow(workflow)
        logger.info(f"Workflow created: {workflow_id}")
        return workflow
    
    async def create_job(
        self,
        job_id: str,
        workflow_id: str,
        symbol: str,
        timeframe: str,
        session: str,
        stage: WorkflowStage
    ) -> WorkflowJob:
        """
        Create a job for a specific workflow stage.
        
        Args:
            job_id: Job identifier
            workflow_id: Parent workflow
            symbol: Trading symbol
            timeframe: Timeframe
            session: Session
            stage: Workflow stage
        
        Returns:
            WorkflowJob
        """
        logger.info(f"Creating job: {job_id} in workflow {workflow_id} (stage: {stage.value})")
        
        job = WorkflowJob(
            job_id=job_id,
            symbol=symbol,
            timeframe=timeframe,
            session=session,
            workflow_id=workflow_id,
            current_stage=stage.value,
            status="pending",
            created_at=datetime.now(timezone.utc).isoformat(),
            started_at=None,
            completed_at=None,
            results={}
        )
        
        self._save_job(job)
        logger.info(f"Job created: {job_id}")
        return job
    
    async def start_job(self, job_id: str) -> Optional[WorkflowJob]:
        """Start a job."""
        job = self._load_job(job_id)
        if not job:
            return None
        
        job.status = "running"
        job.started_at = datetime.now(timezone.utc).isoformat()
        self._save_job(job)
        
        logger.info(f"Job started: {job_id}")
        return job
    
    async def complete_job(
        self,
        job_id: str,
        results: Dict
    ) -> Optional[WorkflowJob]:
        """Complete a job."""
        job = self._load_job(job_id)
        if not job:
            return None
        
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc).isoformat()
        job.results = results
        self._save_job(job)
        
        # Update workflow
        workflow = self._load_workflow(job.workflow_id)
        if workflow:
            if job.current_stage not in workflow.stages_completed:
                workflow.stages_completed.append(job.current_stage)
            
            # Move to next stage
            stages = [s.value for s in WorkflowStage]
            current_idx = stages.index(job.current_stage)
            if current_idx + 1 < len(stages) - 2:  # Skip COMPLETED and FAILED
                workflow.current_stage = stages[current_idx + 1]
            
            self._save_workflow(workflow)
        
        logger.info(f"Job completed: {job_id}")
        return job
    
    async def fail_job(
        self,
        job_id: str,
        error_message: str
    ) -> Optional[WorkflowJob]:
        """Mark job as failed."""
        job = self._load_job(job_id)
        if not job:
            return None
        
        job.status = "failed"
        job.completed_at = datetime.now(timezone.utc).isoformat()
        job.error_message = error_message
        self._save_job(job)
        
        # Mark workflow as failed
        workflow = self._load_workflow(job.workflow_id)
        if workflow:
            workflow.status = "failed"
            workflow.error_message = error_message
            self._save_workflow(workflow)
        
        logger.error(f"Job failed: {job_id} - {error_message}")
        return job
    
    async def get_workflow_status(self, workflow_id: str) -> Optional[WorkflowPipeline]:
        """Get workflow status."""
        return self._load_workflow(workflow_id)
    
    async def list_workflows(self, symbol: Optional[str] = None) -> List[WorkflowPipeline]:
        """List workflows."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if symbol:
                cursor.execute("SELECT * FROM workflows WHERE symbol = ?", (symbol,))
            else:
                cursor.execute("SELECT * FROM workflows")
            
            rows = cursor.fetchall()
            conn.close()
            
            workflows = []
            for row in rows:
                workflow = WorkflowPipeline(*row)
                workflow.stages_completed = json.loads(workflow.stages_completed)
                workflow.discovered_strategies = json.loads(workflow.discovered_strategies)
                workflow.optimized_strategies = json.loads(workflow.optimized_strategies)
                workflow.validated_strategies = json.loads(workflow.validated_strategies)
                workflows.append(workflow)
            
            return workflows
        except Exception as e:
            logger.error(f"List workflows error: {e}")
            return []
    
    async def list_jobs(self, workflow_id: str) -> List[WorkflowJob]:
        """List jobs in workflow."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM jobs WHERE workflow_id = ?",
                (workflow_id,)
            )
            rows = cursor.fetchall()
            conn.close()
            
            jobs = []
            for row in rows:
                job = WorkflowJob(*row)
                job.results = json.loads(job.results)
                jobs.append(job)
            
            return jobs
        except Exception as e:
            logger.error(f"List jobs error: {e}")
            return []
    
    def _save_workflow(self, workflow: WorkflowPipeline):
        """Save workflow to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO workflows
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            workflow.workflow_id,
            workflow.symbol,
            workflow.timeframe,
            workflow.session,
            workflow.created_at,
            workflow.status,
            json.dumps(workflow.stages_completed),
            workflow.current_stage,
            json.dumps(workflow.discovered_strategies),
            json.dumps(workflow.optimized_strategies),
            json.dumps(workflow.validated_strategies),
            workflow.error_message
        ))
        
        conn.commit()
        conn.close()
    
    def _load_workflow(self, workflow_id: str) -> Optional[WorkflowPipeline]:
        """Load workflow from database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM workflows WHERE workflow_id = ?", (workflow_id,))
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return None
            
            workflow = WorkflowPipeline(*row)
            workflow.stages_completed = json.loads(workflow.stages_completed)
            workflow.discovered_strategies = json.loads(workflow.discovered_strategies)
            workflow.optimized_strategies = json.loads(workflow.optimized_strategies)
            workflow.validated_strategies = json.loads(workflow.validated_strategies)
            return workflow
        except Exception as e:
            logger.error(f"Load workflow error: {e}")
            return None
    
    def _save_job(self, job: WorkflowJob):
        """Save job to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO jobs
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job.job_id,
            job.symbol,
            job.timeframe,
            job.session,
            job.workflow_id,
            job.current_stage,
            job.status,
            job.created_at,
            job.started_at,
            job.completed_at,
            json.dumps(job.results),
            job.error_message
        ))
        
        conn.commit()
        conn.close()
    
    def _load_job(self, job_id: str) -> Optional[WorkflowJob]:
        """Load job from database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return None
            
            job = WorkflowJob(*row)
            job.results = json.loads(job.results)
            return job
        except Exception as e:
            logger.error(f"Load job error: {e}")
            return None


__all__ = ['OrchestrationEngine', 'WorkflowJob', 'WorkflowPipeline', 'WorkflowStage']
