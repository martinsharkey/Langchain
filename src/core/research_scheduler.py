"""
Daily Research Scheduler — Triggers research cycle at 00:00 UTC.

This module handles:
1. Scheduling research to run at 00:00 UTC daily
2. Running research asynchronously (non-blocking)
3. Managing scheduler state and logging
4. Handling errors gracefully

Usage:
    scheduler = ResearchScheduler()
    scheduler.start()  # Starts the scheduler thread
    scheduler.stop()   # Stops the scheduler
"""

import os
import logging
from typing import Optional, Callable
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio
import threading

logger = logging.getLogger("core.research_scheduler")


class ResearchScheduler:
    """
    Manages daily research trigger at 00:00 UTC.
    
    Non-blocking: Research runs in background without stopping trading.
    """
    
    def __init__(self, research_callback: Optional[Callable] = None):
        """
        Initialize scheduler.
        
        Args:
            research_callback: Async function to call at trigger time.
                              If not provided, must be set via set_callback()
        """
        self.scheduler = BackgroundScheduler(daemon=True)
        self.research_callback = research_callback
        self.is_running = False
        self.last_run_timestamp = None
        self.run_count = 0
        
        # Configuration
        self.trigger_hour = int(os.getenv("RESEARCH_TRIGGER_HOUR", "0"))
        self.trigger_minute = int(os.getenv("RESEARCH_TRIGGER_MINUTE", "0"))
        self.timezone = "UTC"
        
        logger.info(
            f"ResearchScheduler initialized: "
            f"trigger at {self.trigger_hour:02d}:{self.trigger_minute:02d} {self.timezone}"
        )
    
    def set_callback(self, callback: Callable):
        """Set or update the research callback function."""
        self.research_callback = callback
        logger.info("Research callback set")
    
    def start(self):
        """Start the scheduler."""
        if self.is_running:
            logger.warning("Scheduler already running")
            return
        
        if not self.research_callback:
            raise ValueError("Research callback not set. Use set_callback() first.")
        
        # Add job with cron trigger
        self.scheduler.add_job(
            func=self._run_research_cycle,
            trigger=CronTrigger(
                hour=self.trigger_hour,
                minute=self.trigger_minute,
                timezone=self.timezone
            ),
            id="daily_research",
            name="Daily Market Research Cycle",
            replace_existing=True,
            max_instances=1  # Prevent overlapping runs
        )
        
        self.scheduler.start()
        self.is_running = True
        
        logger.info(f"Research scheduler started (next run at {self.trigger_hour:02d}:{self.trigger_minute:02d} UTC)")
    
    def stop(self):
        """Stop the scheduler."""
        if not self.is_running:
            logger.warning("Scheduler not running")
            return
        
        self.scheduler.shutdown(wait=True)
        self.is_running = False
        
        logger.info("Research scheduler stopped")
    
    def _run_research_cycle(self):
        """
        Internal method called by scheduler.
        Handles the research execution in a thread-safe way.
        """
        logger.info("=" * 60)
        logger.info("RESEARCH CYCLE TRIGGERED")
        logger.info("=" * 60)
        
        try:
            self.last_run_timestamp = datetime.now(timezone.utc).isoformat()
            self.run_count += 1
            
            # If callback is async, run it in event loop
            if asyncio.iscoroutinefunction(self.research_callback):
                # Run async callback in new event loop
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self.research_callback())
                finally:
                    loop.close()
            else:
                # Sync callback
                self.research_callback()
            
            logger.info(f"Research cycle completed successfully (run #{self.run_count})")
            
        except Exception as e:
            logger.error(f"Error during research cycle: {e}", exc_info=True)
            # Don't re-raise - scheduler should continue
    
    def get_status(self) -> dict:
        """Get current scheduler status."""
        next_run = None
        if self.scheduler.get_job("daily_research"):
            next_job = self.scheduler.get_job("daily_research")
            next_run = next_job.next_run_time.isoformat() if next_job.next_run_time else None
        
        return {
            "is_running": self.is_running,
            "trigger_time": f"{self.trigger_hour:02d}:{self.trigger_minute:02d} {self.timezone}",
            "last_run": self.last_run_timestamp,
            "run_count": self.run_count,
            "next_run": next_run
        }
    
    def force_run(self):
        """Force an immediate research run (for testing)."""
        logger.info("Force-running research cycle")
        self._run_research_cycle()
    
    def pause(self):
        """Pause the scheduler without stopping it."""
        if self.scheduler.running:
            self.scheduler.pause()
            logger.info("Scheduler paused")
    
    def resume(self):
        """Resume the scheduler."""
        if self.scheduler.running:
            self.scheduler.resume()
            logger.info("Scheduler resumed")
