"""
End-to-End Pipeline Orchestrator

Runs complete feedback loop: Discovery → Tuning → Validation → Deployment
Scheduled to run nightly at 10pm GMT (Mon-Fri)
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

try:
    from apscheduler.schedulers.background import BackgroundScheduler
except ImportError:
    BackgroundScheduler = None

from scripts.phase1_vectorbt_discovery import VectorbtDiscovery
from scripts.phase2_optuna_tuning import Phase2Tuner
from scripts.phase3_vectorbt_validation import Phase3Validator
from src.learning.learning_log import LearningLog
from src.utils.logger import get_logger

logger = get_logger("nightly_orchestrator")


class Phase4Deployer:
    """Phase 4: Deploy accepted params to live trading."""
    
    def __init__(self, learning_log: Optional[LearningLog] = None):
        self.learning_log = learning_log
    
    def deploy(self, symbol: str, validation_results: Dict) -> Dict:
        """
        Deploy accepted params to live trading.
        Keep baseline for rejected params.
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"PHASE 4: DEPLOYMENT - {symbol}")
        logger.info(f"{'='*80}")
        
        deployed_count = 0
        rejected_count = 0
        deployment_summary = {}
        
        try:
            for session, result in validation_results.items():
                indicator = result["indicator"]
                
                if result["accepted"]:
                    # DEPLOY tuned params
                    deployed_params = result["tuned_params"]
                    improvement = result["improvement_test"]
                    pf = result["tuned_pf_test"]
                    
                    logger.info(f"\n✅ DEPLOYING {session}/{indicator}")
                    logger.info(f"   Improvement: +{improvement*100:.2f}%")
                    logger.info(f"   New PF: {pf:.2f}")
                    logger.info(f"   Params: {deployed_params}")
                    
                    # Save to file
                    deploy_path = self._save_deployment(symbol, session, indicator, result)
                    
                    # Update live ParameterOptimizer (if available)
                    self._update_live_params(symbol, session, deployed_params)
                    
                    # Log to learning log
                    if self.learning_log:
                        self.learning_log.record(
                            kind="DEPLOYED",
                            symbol=symbol,
                            session=session,
                            indicator=indicator,
                            improvement=improvement,
                            message=f"Deployed {indicator} with {improvement*100:.2f}% improvement"
                        )
                    
                    deployment_summary[session] = {
                        "action": "DEPLOYED",
                        "indicator": indicator,
                        "improvement": improvement,
                        "pf": pf,
                        "file": str(deploy_path),
                    }
                    deployed_count += 1
                
                else:
                    # REJECT - keep baseline
                    logger.info(f"\n❌ REJECTING {session}/{indicator}")
                    logger.info(f"   Reason: {result['rejection_reason']}")
                    
                    if self.learning_log:
                        self.learning_log.record(
                            kind="REJECTED",
                            symbol=symbol,
                            session=session,
                            indicator=indicator,
                            reason=result["rejection_reason"],
                            message=f"Rejected {indicator}: {result['rejection_reason']}"
                        )
                    
                    deployment_summary[session] = {
                        "action": "REJECTED",
                        "indicator": indicator,
                        "reason": result["rejection_reason"],
                    }
                    rejected_count += 1
            
            # Summary
            logger.info(f"\n{'='*80}")
            logger.info(f"DEPLOYMENT COMPLETE - {symbol}")
            logger.info(f"{'='*80}")
            logger.info(f"Deployed: {deployed_count}")
            logger.info(f"Rejected: {rejected_count}")
            
            return {
                "symbol": symbol,
                "deployed": deployed_count,
                "rejected": rejected_count,
                "summary": deployment_summary,
            }
        
        except Exception as e:
            logger.error(f"Deployment failed: {e}", exc_info=True)
            return {
                "symbol": symbol,
                "deployed": deployed_count,
                "rejected": rejected_count,
                "error": str(e),
                "summary": deployment_summary,
            }
    
    def _save_deployment(self, symbol: str, session: str, indicator: str, 
                        result: Dict) -> Path:
        """Save deployed params to file."""
        deploy_dir = Path("data/qmmp") / symbol / "deployed"
        deploy_dir.mkdir(parents=True, exist_ok=True)
        
        deploy_file = deploy_dir / f"{session}_{indicator}_deployed.json"
        
        data = {
            "symbol": symbol,
            "session": session,
            "indicator": indicator,
            "deployed_at": datetime.now(timezone.utc).isoformat(),
            "baseline_params": result["baseline_params"],
            "tuned_params": result["tuned_params"],
            "baseline_pf_test": result["baseline_pf_test"],
            "tuned_pf_test": result["tuned_pf_test"],
            "improvement": result["improvement_test"],
        }
        
        with open(deploy_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"   Saved to: {deploy_file}")
        return deploy_file
    
    def _update_live_params(self, symbol: str, session: str, params: Dict):
        """Update live ParameterOptimizer with new params."""
        try:
            from src.learning.param_optimizer import ParameterOptimizer
            
            optimizer = ParameterOptimizer()
            if not hasattr(optimizer, 'tuned'):
                optimizer.tuned = {}
            if symbol not in optimizer.tuned:
                optimizer.tuned[symbol] = {}
            
            optimizer.tuned[symbol][session] = params
            logger.info(f"   Updated live ParameterOptimizer for {symbol}/{session}")
        
        except ImportError:
            logger.warning("ParameterOptimizer not available (live update skipped)")
        except Exception as e:
            logger.warning(f"Failed to update live params: {e}")


class NightlyPipeline:
    """Complete end-to-end nightly optimization pipeline."""
    
    def __init__(self, symbols: list = None, sessions: list = None, 
                 timeframes: list = None):
        self.symbols = symbols or ["XAUUSD", "BTCUSD"]
        self.sessions = sessions or ["Asian", "London", "NewYork"]
        self.timeframes = timeframes or ["M1", "M5", "M15", "H1", "H4"]
        
        # Initialize components
        self.discovery = VectorbtDiscovery(
            symbols=self.symbols,
            sessions=self.sessions,
            timeframes=self.timeframes
        )
        self.tuner = Phase2Tuner(n_trials=100)
        self.validator = Phase3Validator()
        
        try:
            self.learning_log = LearningLog()
        except:
            self.learning_log = None
        
        self.deployer = Phase4Deployer(learning_log=self.learning_log)
    
    def run(self) -> Dict:
        """Execute complete pipeline."""
        
        logger.info("\n" + "="*80)
        logger.info("NIGHTLY OPTIMIZATION PIPELINE STARTED")
        logger.info("="*80)
        
        started_at = datetime.now(timezone.utc)
        logger.info(f"Started at: {started_at.isoformat()}")
        
        report = {
            "started_at": started_at.isoformat(),
            "symbols": self.symbols,
            "phases": {},
            "status": "RUNNING",
        }
        
        try:
            # Phase 1: Discovery
            logger.info("\n[1/6] PHASE 1: VECTORBT DISCOVERY")
            phase1_results = {}
            for symbol in self.symbols:
                result = self.discovery.run(symbol)
                phase1_results[symbol] = result
                self.discovery.save_results(symbol)
            
            report["phases"]["phase1_discovery"] = {
                "status": "COMPLETE",
                "symbols_processed": len(phase1_results),
            }
            
            # Phase 2: Optuna Tuning
            logger.info("\n[2/6] PHASE 2: OPTUNA TUNING")
            phase2_results = {}
            for symbol in self.symbols:
                if phase1_results[symbol].get("error"):
                    logger.warning(f"Skipping {symbol} - discovery failed")
                    continue
                
                result = self.tuner.run(phase1_results[symbol])
                phase2_results[symbol] = result
                self.tuner.save_results(symbol, result)
            
            report["phases"]["phase2_optuna"] = {
                "status": "COMPLETE",
                "symbols_processed": len(phase2_results),
            }
            
            # Phase 3: Validation
            logger.info("\n[3/6] PHASE 3: VECTORBT VALIDATION")
            phase3_results = {}
            total_accepted = 0
            total_rejected = 0
            
            for symbol in self.symbols:
                # Load Phase 2 results from file
                phase2_file = Path("data/qmmp") / symbol / f"phase2_optuna_{symbol}.json"
                if not phase2_file.exists():
                    logger.warning(f"Phase 2 results not found for {symbol}")
                    continue
                
                with open(phase2_file) as f:
                    phase2_data = json.load(f)
                
                result = self.validator.run(phase2_data)
                phase3_results[symbol] = result
                self.validator.save_results(symbol, result)
                
                accepted = sum(1 for r in result.values() if isinstance(r, dict) and r.get("accepted"))
                rejected = len(result) - accepted
                total_accepted += accepted
                total_rejected += rejected
            
            report["phases"]["phase3_validation"] = {
                "status": "COMPLETE",
                "symbols_processed": len(phase3_results),
                "total_accepted": total_accepted,
                "total_rejected": total_rejected,
                "acceptance_rate": total_accepted / (total_accepted + total_rejected) if (total_accepted + total_rejected) > 0 else 0,
            }
            
            # Phase 4: Deployment
            logger.info("\n[4/6] PHASE 4: DEPLOYMENT")
            phase4_results = {}
            for symbol in self.symbols:
                if symbol not in phase3_results:
                    continue
                
                # Load Phase 3 results from file
                phase3_file = Path("data/qmmp") / symbol / f"phase3_validation_{symbol}.json"
                if not phase3_file.exists():
                    continue
                
                with open(phase3_file) as f:
                    phase3_data = json.load(f)
                
                result = self.deployer.deploy(symbol, phase3_data.get("results", {}))
                phase4_results[symbol] = result
            
            report["phases"]["phase4_deployment"] = {
                "status": "COMPLETE",
                "symbols_processed": len(phase4_results),
            }
            
            # Phase 5: Live Feedback (Note)
            logger.info("\n[5/6] PHASE 5: LIVE FEEDBACK")
            logger.info("→ Running continuously during live trading (not part of nightly)")
            report["phases"]["phase5_feedback"] = {
                "status": "CONTINUOUS",
                "note": "Collects live trade outcomes throughout the trading day"
            }
            
            # Phase 6: Reporting
            logger.info("\n[6/6] PHASE 6: REPORTING")
            self._generate_report(report)
            report["phases"]["phase6_reporting"] = {"status": "COMPLETE"}
            
            # Final status
            completed_at = datetime.now(timezone.utc)
            duration = (completed_at - started_at).total_seconds()
            
            report["completed_at"] = completed_at.isoformat()
            report["duration_seconds"] = duration
            report["status"] = "SUCCESS"
            
            logger.info("\n" + "="*80)
            logger.info("NIGHTLY OPTIMIZATION PIPELINE COMPLETE")
            logger.info("="*80)
            logger.info(f"Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
            logger.info(f"Status: {report['status']}")
            
            # Save report
            self._save_report(report)
            
        except Exception as e:
            logger.error(f"\n❌ PIPELINE FAILED: {e}", exc_info=True)
            report["status"] = "FAILED"
            report["error"] = str(e)
            report["completed_at"] = datetime.now(timezone.utc).isoformat()
            self._save_report(report)
            self._send_error_notification(report)
        
        return report
    
    def _generate_report(self, report: Dict):
        """Generate and log pipeline report."""
        
        logger.info("\nPipeline Report:")
        logger.info("-" * 80)
        
        for phase_name, phase_data in report.get("phases", {}).items():
            logger.info(f"{phase_name}: {phase_data.get('status', 'UNKNOWN')}")
            
            if "total_accepted" in phase_data:
                logger.info(f"  Accepted: {phase_data['total_accepted']}")
                logger.info(f"  Rejected: {phase_data['total_rejected']}")
                logger.info(f"  Rate: {phase_data['acceptance_rate']*100:.1f}%")
    
    def _save_report(self, report: Dict) -> Path:
        """Save pipeline report to JSON."""
        report_dir = Path("data/reports")
        report_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_file = report_dir / f"nightly_report_{timestamp}.json"
        
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"✓ Report saved to {report_file}")
        return report_file
    
    def _send_error_notification(self, report: Dict):
        """Send error notification (email, etc)."""
        try:
            logger.error(f"Sending error notification...")
            # TODO: Implement email/Slack notification
        except Exception as e:
            logger.warning(f"Failed to send notification: {e}")
    
    def schedule_nightly(self):
        """Schedule pipeline to run at 10pm GMT every Mon-Fri."""
        if BackgroundScheduler is None:
            logger.error("APScheduler not installed. Cannot schedule nightly runs.")
            logger.error("Install with: pip install apscheduler")
            return False
        
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            self.run,
            'cron',
            day_of_week='mon-fri',
            hour=22,  # 10pm GMT
            minute=0,
            second=0,
            id='nightly_optimization',
            name='Nightly Optimization Pipeline',
            replace_existing=True,
        )
        
        try:
            scheduler.start()
            logger.info("="*80)
            logger.info("✓ NIGHTLY SCHEDULER STARTED")
            logger.info("="*80)
            logger.info("Schedule: 10:00pm GMT every Mon-Fri")
            logger.info("Next run: Will be calculated by APScheduler")
            return True
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            return False


def main():
    """Run pipeline immediately or schedule for nightly execution."""
    
    import argparse
    
    parser = argparse.ArgumentParser(description="Nightly Optimization Pipeline")
    parser.add_argument("--run-now", action="store_true", help="Run pipeline immediately")
    parser.add_argument("--schedule", action="store_true", help="Schedule for 10pm GMT Mon-Fri")
    parser.add_argument("--symbols", nargs="+", default=["XAUUSD", "BTCUSD"], 
                       help="Symbols to process")
    parser.add_argument("--sessions", nargs="+", default=["Asian", "London", "NewYork"],
                       help="Sessions to process")
    parser.add_argument("--timeframes", nargs="+", default=["M1", "M5", "M15", "H1", "H4"],
                       help="Timeframes to process")
    
    args = parser.parse_args()
    
    pipeline = NightlyPipeline(
        symbols=args.symbols,
        sessions=args.sessions,
        timeframes=args.timeframes
    )
    
    if args.run_now:
        logger.info("Running pipeline immediately...")
        report = pipeline.run()
        return 0 if report["status"] == "SUCCESS" else 1
    
    elif args.schedule:
        logger.info("Scheduling pipeline for 10pm GMT Mon-Fri...")
        success = pipeline.schedule_nightly()
        
        if success:
            # Keep scheduler running
            try:
                import time
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Scheduler stopped by user")
                return 0
        else:
            return 1
    
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
