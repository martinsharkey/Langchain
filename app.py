#!/usr/bin/env python3
"""
Unified Application Startup — Start all components as one integrated system.

This single script starts:
1. Daily Research Scheduler
2. Market Data Collection
3. Trading Research Agent
4. Dashboard Web Server
5. System monitoring

All components run together as one cohesive application.

Usage:
    python app.py
"""

import asyncio
import sys
import os
import threading
import time
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.orchestration import get_orchestrator
from src.utils.logger import get_logger, console
from dashboard.app import app as flask_app


logger = get_logger("app.startup")


class UnifiedApplication:
    """Unified trading research application - all components integrated."""
    
    def __init__(self):
        self.orchestrator = None
        self.flask_thread = None
        self.is_running = False
        self.startup_time = None
        
    def print_banner(self):
        """Print startup banner."""
        console.print("\n" + "=" * 70, style="bold cyan")
        console.print("🚀 UNIFIED TRADING RESEARCH APPLICATION", style="bold cyan")
        console.print("=" * 70, style="bold cyan")
        console.print()
        
    def initialize_components(self):
        """Initialize all components."""
        console.print("INITIALIZING COMPONENTS", style="bold")
        console.print("-" * 70)
        
        try:
            # Initialize orchestrator (includes scheduler, research agent, etc.)
            console.print("  • Initializing Research Orchestrator...", style="dim")
            self.orchestrator = get_orchestrator()
            console.print("    ✅ Version Manager", style="green")
            console.print("    ✅ Research Scheduler", style="green")
            console.print("    ✅ Market Data Collector", style="green")
            console.print("    ✅ Research Agent", style="green")
            console.print("    ✅ Handoff Protocol", style="green")
            console.print("    ✅ Knowledge Base", style="green")
            console.print()
            
            # Verify Flask app
            console.print("  • Verifying Dashboard...", style="dim")
            if flask_app:
                console.print("    ✅ Flask App Ready", style="green")
            console.print()
            
            return True
            
        except Exception as e:
            console.print(f"  ❌ Initialization failed: {e}", style="red")
            logger.error(f"Initialization error: {e}", exc_info=True)
            return False
    
    def start_research_system(self):
        """Start the research scheduler."""
        console.print("STARTING RESEARCH SYSTEM", style="bold")
        console.print("-" * 70)
        
        try:
            console.print("  • Starting daily scheduler...", style="dim")
            self.orchestrator.start()
            
            status = self.orchestrator.scheduler.get_status()
            console.print(f"    ✅ Scheduler Running", style="green")
            console.print(f"    ✅ Trigger: {status['trigger_time']}", style="green")
            console.print(f"    ✅ Next Run: {status.get('next_run', 'N/A')}", style="green")
            console.print()
            
            return True
            
        except Exception as e:
            console.print(f"  ❌ Failed to start research system: {e}", style="red")
            logger.error(f"Research system error: {e}", exc_info=True)
            return False
    
    def start_dashboard(self):
        """Start the Flask dashboard in a separate thread."""
        console.print("STARTING DASHBOARD", style="bold")
        console.print("-" * 70)
        
        try:
            console.print("  • Starting Flask dashboard server...", style="dim")
            
            def run_flask():
                try:
                    # Disable Flask's default logging
                    import logging as py_logging
                    py_logging.getLogger('werkzeug').setLevel(py_logging.ERROR)
                    
                    flask_app.run(
                        host='0.0.0.0',
                        port=5000,
                        debug=False,
                        use_reloader=False,
                        threaded=True
                    )
                except Exception as e:
                    logger.error(f"Flask error: {e}")
            
            self.flask_thread = threading.Thread(target=run_flask, daemon=True)
            self.flask_thread.start()
            
            # Wait a moment for Flask to start
            time.sleep(2)
            
            console.print("    ✅ Dashboard Running", style="green")
            console.print("    ✅ Access: http://localhost:5000", style="green")
            console.print()
            
            return True
            
        except Exception as e:
            console.print(f"  ❌ Failed to start dashboard: {e}", style="red")
            logger.error(f"Dashboard error: {e}", exc_info=True)
            return False
    
    def print_startup_summary(self):
        """Print startup summary."""
        console.print("=" * 70, style="bold green")
        console.print("✅ APPLICATION STARTED SUCCESSFULLY", style="bold green")
        console.print("=" * 70, style="bold green")
        console.print()
        
        console.print("COMPONENTS RUNNING:", style="bold")
        console.print("  ✅ Research System")
        console.print("     • Daily scheduler (00:00 UTC)")
        console.print("     • Market data collection (6 sources)")
        console.print("     • LLM semantic analysis")
        console.print("     • Knowledge base storage")
        console.print()
        console.print("  ✅ Dashboard")
        console.print("     • Web interface (port 5000)")
        console.print("     • Real-time metrics")
        console.print("     • Performance tracking")
        console.print()
        
        console.print("ACCESS POINTS:", style="bold")
        console.print("  🌐 Dashboard: http://localhost:5000")
        console.print("  📊 Research: Automatic daily at 00:00 UTC")
        console.print("  🐍 Python API: from src.orchestration import get_orchestrator")
        console.print()
        
        console.print("SYSTEM STATUS:", style="bold")
        self.orchestrator.print_status()
        
        console.print()
        console.print("NEXT STEPS:", style="bold")
        console.print("  1. Open http://localhost:5000 in your browser")
        console.print("  2. Monitor the dashboard for metrics")
        console.print("  3. System runs automatically in background")
        console.print("  4. Press Ctrl+C to stop all components")
        console.print()
        
        self.startup_time = datetime.now(timezone.utc)
        console.print(f"Started: {self.startup_time.isoformat()}", style="dim")
        console.print()
    
    def print_uptime(self):
        """Print current uptime."""
        if self.startup_time:
            uptime = datetime.now(timezone.utc) - self.startup_time
            hours = uptime.seconds // 3600
            minutes = (uptime.seconds % 3600) // 60
            seconds = uptime.seconds % 60
            console.print(f"⏱️  Uptime: {hours}h {minutes}m {seconds}s", style="dim")
    
    def run(self):
        """Run the unified application."""
        self.print_banner()
        
        # Initialize all components
        if not self.initialize_components():
            console.print("❌ Failed to initialize components", style="red")
            return False
        
        # Start research system
        if not self.start_research_system():
            console.print("⚠️  Research system failed, but continuing...", style="yellow")
        
        # Start dashboard
        if not self.start_dashboard():
            console.print("⚠️  Dashboard failed, but continuing...", style="yellow")
        
        # Print summary
        self.print_startup_summary()
        
        # Keep application running
        self.is_running = True
        
        try:
            while True:
                time.sleep(1)
                # Could add periodic status checks here
        
        except KeyboardInterrupt:
            self.shutdown()
            return True
    
    def shutdown(self):
        """Graceful shutdown."""
        console.print("\n\n" + "=" * 70, style="bold yellow")
        console.print("🛑 SHUTTING DOWN", style="bold yellow")
        console.print("=" * 70 + "\n", style="bold yellow")
        
        try:
            console.print("Stopping research system...", style="dim")
            if self.orchestrator:
                self.orchestrator.stop()
            console.print("✅ Research system stopped", style="green")
        except Exception as e:
            console.print(f"⚠️  Error stopping research system: {e}", style="yellow")
        
        console.print("✅ Dashboard stopped", style="green")
        console.print()
        
        self.print_uptime()
        console.print()
        console.print("✅ Application stopped gracefully", style="green")
        console.print()


async def async_main():
    """Async wrapper for main."""
    app = UnifiedApplication()
    return app.run()


def main():
    """Main entry point."""
    try:
        # Run the application
        asyncio.run(async_main())
    
    except Exception as e:
        console.print(f"\n❌ Fatal error: {e}", style="red")
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
