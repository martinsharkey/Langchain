#!/usr/bin/env python
"""
Dashboard v2 Test - Quick verification that dashboard is working.

Run this to test:
    python test_dashboard.py

Then visit:
    http://localhost:5000/v2
"""

import sys
import time
import subprocess
from pathlib import Path

# Add project to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dashboard.app import app

def test_dashboard():
    """Test that dashboard routes work."""
    print("\n" + "="*60)
    print("DASHBOARD V2 TEST")
    print("="*60 + "\n")
    
    with app.test_client() as client:
        # Test 1: Dashboard HTML
        print("1. Testing dashboard HTML route...")
        resp = client.get('/v2')
        if resp.status_code == 200:
            print(f"   ✅ /v2 returns 200 OK ({len(resp.data)} bytes)")
            if b'Trading Dashboard' in resp.data:
                print(f"   ✅ HTML contains dashboard title")
            else:
                print(f"   ❌ HTML doesn't contain expected content")
                return False
        else:
            print(f"   ❌ /v2 returned {resp.status_code}")
            return False
        
        # Test 2: Summary API
        print("\n2. Testing /api/v2/summary...")
        resp = client.get('/api/v2/summary')
        if resp.status_code == 200:
            print(f"   ✅ /api/v2/summary returns 200 OK")
            import json
            data = json.loads(resp.data)
            if 'data' in data:
                print(f"   ✅ Response has 'data' field")
                print(f"   - Total strategies: {data['data'].get('total_strategies', 'N/A')}")
                print(f"   - Validated: {data['data'].get('validated_strategies', 'N/A')}")
            else:
                print(f"   ❌ Response missing 'data' field")
                return False
        else:
            print(f"   ❌ /api/v2/summary returned {resp.status_code}")
            return False
        
        # Test 3: Strategies API
        print("\n3. Testing /api/v2/strategies...")
        resp = client.get('/api/v2/strategies')
        if resp.status_code == 200:
            print(f"   ✅ /api/v2/strategies returns 200 OK")
            import json
            data = json.loads(resp.data)
            if 'data' in data and isinstance(data['data'], list):
                print(f"   ✅ Response has strategies list")
                print(f"   - Strategies found: {len(data['data'])}")
            else:
                print(f"   ⚠️  Response format unexpected")
        else:
            print(f"   ❌ /api/v2/strategies returned {resp.status_code}")
            return False
        
        # Test 4: Discovery API
        print("\n4. Testing /api/v2/vectorbt/discovery...")
        resp = client.get('/api/v2/vectorbt/discovery')
        if resp.status_code == 200:
            print(f"   ✅ /api/v2/vectorbt/discovery returns 200 OK")
        else:
            print(f"   ❌ /api/v2/vectorbt/discovery returned {resp.status_code}")
            return False
    
    return True

if __name__ == "__main__":
    print("\nRunning Dashboard v2 tests...\n")
    
    success = test_dashboard()
    
    if success:
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED")
        print("="*60)
        print("\nDashboard is ready at:")
        print("   http://localhost:5000/v2")
        print("\nTo start the server, run:")
        print("   python app.py")
        print()
    else:
        print("\n" + "="*60)
        print("❌ TESTS FAILED")
        print("="*60)
        sys.exit(1)
