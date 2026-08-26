"""
Symbol Onboarding Management API
Flask backend for vectorbt symbol onboarding UI

Provides REST endpoints for:
- Listing available symbols (from MT5)
- Onboarding symbols with progress tracking
- Managing onboarded symbols
- Retrieving onboarding results
"""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import json
import os
import sys
import threading
import subprocess
from pathlib import Path
from datetime import datetime, timezone
import traceback

# Setup paths
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.data_acquisition.manager import DataManager, DataSourceConfig

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Register all dashboard API blueprints
from src.dashboard.routes_v2 import register_routes as register_v2_routes
register_v2_routes(app)

# Configuration
QMMP_DIR = project_root / "data" / "qmmp"
QMMP_DIR.mkdir(parents=True, exist_ok=True)

# Global state
onboarding_jobs = {}  # Track running onboarding jobs
dm = None

def get_data_manager():
    """Get or create DataManager instance."""
    global dm
    if dm is None:
        dm = DataManager(DataSourceConfig(broker="vt_markets"))
    return dm

def get_available_symbols():
    """Get list of symbols available in MT5."""
    try:
        dm = get_data_manager()
        # Try to get symbols from MT5
        try:
            import MetaTrader5 as mt5
            if mt5.initialize():
                symbols = [s.name for s in mt5.symbols_get(group="*Forex*") or []]
                symbols += [s.name for s in mt5.symbols_get(group="*Crypto*") or []]
                symbols += [s.name for s in mt5.symbols_get(group="*Commodities*") or []]
                mt5.shutdown()
                return sorted(list(set(symbols)))
        except:
            pass
        
        # Fallback: return known symbols
        return ["BTCUSD", "XAUUSD", "GER40", "EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD"]
    except Exception as e:
        print(f"Error getting symbols: {e}")
        return []

def get_onboarded_symbols():
    """Get list of already onboarded symbols."""
    try:
        symbols = []
        for item in QMMP_DIR.iterdir():
            if item.is_dir() and (item / f"{item.name}_vectorbt_results.json").exists():
                symbols.append(item.name)
        return sorted(symbols)
    except:
        return []

def get_symbol_status(symbol):
    """Get status of a symbol (onboarded, in progress, etc)."""
    symbol_dir = QMMP_DIR / symbol
    
    if symbol in onboarding_jobs:
        return {
            'symbol': symbol,
            'status': onboarding_jobs[symbol]['status'],
            'progress': onboarding_jobs[symbol].get('progress', 0),
            'message': onboarding_jobs[symbol].get('message', ''),
            'error': onboarding_jobs[symbol].get('error') if onboarding_jobs[symbol].get('status') == 'error' else None
        }
    
    if symbol_dir.exists():
        results_file = symbol_dir / f"{symbol}_vectorbt_results.json"
        if results_file.exists():
            try:
                with open(results_file) as f:
                    results = json.load(f)
                
                validated = results.get('validated_strategies', {})
                date_range = results.get('date_range', {})
                
                # Build per-session data structure for dashboard
                sessions = {}
                for session_name, strategy in validated.items():
                    sessions[session_name] = {
                        'timeframe': strategy.get('timeframe', 'N/A'),
                        'profit_factor': round(strategy.get('pf', 0), 2),
                        'win_rate': round(strategy.get('wr', 0), 4),
                        'sharpe_ratio': round(strategy.get('sharpe', 0), 2),
                        'best_strategy': strategy.get('primary_ind', 'N/A'),
                        'sl_multiplier': round(strategy.get('sl_mult', 0), 1),
                        'tp_ratio': round(strategy.get('tp_ratio', 0), 1),
                        'total_trades': strategy.get('trades', 0),
                        'floor_config': {
                            'strategy': strategy.get('primary_ind'),
                            'sl': strategy.get('sl_mult'),
                            'tp': strategy.get('tp_ratio')
                        }
                    }
                
                # Calculate best overall results
                best_pf = max([s.get('pf', 0) for s in validated.values()], default=0)
                best_session = max(validated.items(), key=lambda x: x[1].get('pf', 0))[0] if validated else 'N/A'
                avg_wr = sum([s.get('wr', 0) for s in validated.values()]) / len(validated) if validated else 0
                total_trades = sum([s.get('trades', 0) for s in validated.values()])
                
                # Build date range string
                duration_str = 'N/A'
                if date_range and date_range.get('duration_days'):
                    days = date_range['duration_days']
                    duration_str = f"{days} days (~{days/7:.1f}w, ~{days/30:.1f}m)"
                
                return {
                    'symbol': symbol,
                    'status': 'onboarded',
                    'progress': 100,
                    'message': 'Onboarding complete',
                    'last_updated': results.get('timestamp'),
                    'results': {
                        'best_strategy': validated.get(best_session, {}).get('primary_ind', 'N/A') if validated else 'N/A',
                        'best_session': best_session,
                        'profit_factor': round(best_pf, 2),
                        'win_rate': round(avg_wr, 4),
                        'sharpe_ratio': round(max([s.get('sharpe', 0) for s in validated.values()], default=0), 2),
                        'total_trades': total_trades,
                        'validated': True
                    },
                    'date_range': {
                        'start_date': date_range.get('start_date'),
                        'end_date': date_range.get('end_date'),
                        'duration_str': duration_str
                    },
                    'sessions': sessions
                }
            except Exception as e:
                print(f"Error reading {results_file}: {e}")
    
    return {
        'symbol': symbol,
        'status': 'not_onboarded',
        'progress': 0,
        'message': 'Not onboarded',
        'result': None
    }

def _get_top_strategies(results):
    """Extract top 3 strategies from results."""
    try:
        strategies = results.get('validated_strategies', {})
        if not strategies:
            return []
        
        # Sort by PF
        sorted_strats = sorted(
            strategies.items(),
            key=lambda x: x[1].get('pf', 0),
            reverse=True
        )
        
        top_3 = []
        for session, strat in sorted_strats[:3]:
            top_3.append({
                'session': session,
                'primary_ind': strat.get('strategy', 'unknown'),
                'secondary_ind': strat.get('filter', 'none'),
                'pf': round(strat.get('pf', 0), 2),
                'wr': round(strat.get('wr', 0), 3),
                'sharpe': round(strat.get('sharpe', 0), 2)
            })
        
        return top_3
    except:
        return []

def run_onboarding(symbol):
    """Run onboarding in background thread using the src.onboarding pipeline."""
    try:
        onboarding_jobs[symbol] = {
            'status': 'running',
            'progress': 10,
            'message': 'Discovering indicators (VectorBT + ta-lib + pandas_ta)...'
        }

        from src.onboarding import onboard

        result = onboard(symbol)

        onboarding_jobs[symbol] = {
            'status': 'completed',
            'progress': 100,
            'message': 'Onboarding complete!',
            'result': result,
        }

    except Exception as e:
        onboarding_jobs[symbol] = {
            'status': 'error',
            'progress': 0,
            'message': f'Error: {str(e)[:200]}'
        }

# REST API Routes

@app.route('/api/symbols', methods=['GET'])
def api_list_symbols():
    """Get list of available and onboarded symbols with status."""
    try:
        available = get_available_symbols()
        onboarded = get_onboarded_symbols()
        
        symbols = []
        
        # Add onboarded symbols with status
        for symbol in onboarded:
            status = get_symbol_status(symbol)
            symbols.append(status)
        
        # Add available but not onboarded symbols
        for symbol in available:
            if symbol not in onboarded:
                symbols.append({
                    'symbol': symbol,
                    'status': 'not_onboarded',
                    'progress': 0,
                    'message': 'Not onboarded',
                    'result': None
                })
        
        return jsonify({
            'status': 'ok',
            'symbols': symbols,
            'total': len(symbols)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/symbols', methods=['POST'])
def api_add_symbol():
    """Add a symbol for onboarding.
    
    Request: {
      "symbol": "XAUUSD"
    }
    """
    try:
        data = request.get_json() or {}
        symbol = data.get('symbol', '').upper().strip()
        
        if not symbol:
            return jsonify({'error': 'Symbol is required'}), 400
        
        # Start onboarding
        return api_onboard_symbol(symbol)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/symbols/<symbol>/status', methods=['GET'])
def api_get_symbol_status(symbol):
    """Get detailed status of a symbol."""
    return jsonify({'status': 'ok', 'data': get_symbol_status(symbol)})

@app.route('/api/symbols/<symbol>', methods=['DELETE'])
def api_delete_symbol(symbol):
    """Delete/remove a symbol."""
    return api_remove_symbol(symbol)

@app.route('/api/symbols/<symbol>/onboard', methods=['POST'])
def api_onboard_symbol_v2(symbol):
    """Start onboarding for a symbol."""
    return api_onboard_symbol(symbol)

# Legacy endpoints (kept for backward compatibility)
@app.route('/api/symbols/available', methods=['GET'])
def api_available_symbols():
    """Get list of available symbols."""
    return jsonify({
        'symbols': get_available_symbols()
    })

@app.route('/api/symbols/onboarded', methods=['GET'])
def api_onboarded_symbols():
    """Get list of onboarded symbols."""
    return jsonify({
        'symbols': get_onboarded_symbols()
    })

@app.route('/api/symbol/<symbol>/status', methods=['GET'])
def api_symbol_status(symbol):
    """Get status of a symbol."""
    return jsonify(get_symbol_status(symbol))

@app.route('/api/symbol/<symbol>/onboard', methods=['POST'])
def api_onboard_symbol(symbol):
    """Start onboarding a symbol."""
    if symbol in onboarding_jobs and onboarding_jobs[symbol]['status'] == 'running':
        return jsonify({'error': 'Already onboarding'}), 400
    
    # Start in background thread
    thread = threading.Thread(target=run_onboarding, args=(symbol,))
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'onboarding_started', 'symbol': symbol})

@app.route('/api/symbol/<symbol>/remove', methods=['POST'])
def api_remove_symbol(symbol):
    """Remove an onboarded symbol."""
    try:
        symbol_dir = QMMP_DIR / symbol
        if symbol_dir.exists():
            import shutil
            shutil.rmtree(symbol_dir)
        
        if symbol in onboarding_jobs:
            del onboarding_jobs[symbol]
        
        return jsonify({'status': 'removed', 'symbol': symbol})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/symbol/<symbol>/refresh', methods=['POST'])
def api_refresh_symbol(symbol):
    """Refresh/re-onboard a symbol."""
    return api_onboard_symbol(symbol)

@app.route('/api/symbol/<symbol>/use-in-bot', methods=['POST'])
def api_use_in_bot(symbol):
    """Mark symbol to be used in live bot."""
    try:
        # Read current config
        config_file = project_root / "data" / "bot_config.json"
        config = {}
        if config_file.exists():
            with open(config_file) as f:
                config = json.load(f)
        
        # Add symbol to active symbols
        if 'active_symbols' not in config:
            config['active_symbols'] = []
        
        if symbol not in config['active_symbols']:
            config['active_symbols'].append(symbol)
        
        # Save config
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        return jsonify({'status': 'added_to_bot', 'symbol': symbol})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/symbol/<symbol>/generate-ea', methods=['POST'])
def api_generate_ea(symbol):
    """Generate MQL5 EA for symbol."""
    try:
        symbol_dir = QMMP_DIR / symbol
        ea_file = symbol_dir / f"GoldShark_{symbol}_vectorbt.mq5"
        
        if not ea_file.exists():
            return jsonify({'error': 'EA not found'}), 404
        
        with open(ea_file) as f:
            ea_code = f.read()
        
        return jsonify({
            'symbol': symbol,
            'ea_filename': ea_file.name,
            'ea_code': ea_code,
            'size_bytes': len(ea_code)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/symbol/<symbol>/download-ea', methods=['GET'])
def api_download_ea(symbol):
    """Download EA file."""
    try:
        symbol_dir = QMMP_DIR / symbol
        ea_file = symbol_dir / f"GoldShark_{symbol}_vectorbt.mq5"
        
        if not ea_file.exists():
            return jsonify({'error': 'EA not found'}), 404
        
        return send_from_directory(
            str(symbol_dir),
            ea_file.name,
            as_attachment=True
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/tasks', methods=['GET'])
def api_tasks():
    """Get list of onboarding tasks."""
    return jsonify(list(onboarding_jobs.values()))

@app.route('/api/stats', methods=['GET'])
def api_stats():
    """Get overall statistics."""
    try:
        onboarded = get_onboarded_symbols()
        
        total_configs = 0
        total_sessions = 0
        
        for symbol in onboarded:
            results_file = QMMP_DIR / symbol / f"{symbol}_vectorbt_results.json"
            if results_file.exists():
                with open(results_file) as f:
                    results = json.load(f)
                    sessions = results.get('validated_strategies', {})
                    total_sessions += len(sessions)
                    total_configs += len(sessions) * 1584  # Rough estimate
        
        return jsonify({
            'total_onboarded': len(onboarded),
            'total_sessions': total_sessions,
            'total_configs_tested': total_configs
        })
    except:
        return jsonify({
            'total_onboarded': 0,
            'total_sessions': 0,
            'total_configs_tested': 0
        })

@app.route('/')
def index():
    """Serve the React frontend."""
    # Try to serve from dashboard-frontend build first, then fallback
    try:
        return send_from_directory(str(project_root / 'dashboard' / 'public'), 'index.html')
    except:
        try:
            return send_from_directory(str(project_root / 'src' / 'ui' / 'dist'), 'index.html')
        except:
            return jsonify({"error": "Frontend not built"}), 500

@app.route('/<path:filename>')
def serve_static(filename):
    """Serve static files - but NOT api routes."""
    # Don't serve files that look like API routes
    if filename.startswith('api/'):
        return jsonify({"error": f"API endpoint not found"}), 404
    
    # Try to serve from dashboard-frontend build first
    try:
        return send_from_directory(str(project_root / 'dashboard' / 'public'), filename)
    except:
        try:
            return send_from_directory(str(project_root / 'src' / 'ui' / 'dist'), filename)
        except:
            # If no file found, return 404 (don't try to serve as HTML)
            return jsonify({"error": f"File {filename} not found"}), 404

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
