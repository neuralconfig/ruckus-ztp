#!/usr/bin/env python3
"""
Test script for RUCKUS ZTP Agent Web Application.
This script performs basic API tests to verify the web application is working.
"""
import asyncio
import json
import sys
from pathlib import Path

# Add the project root to the path so we can import the ZTP agent
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from fastapi.testclient import TestClient
    from web_app.main import app
except ImportError as e:
    print(f"Error importing dependencies: {e}")
    print("Please install dependencies with: pip install -r requirements.txt")
    sys.exit(1)

def test_basic_endpoints():
    """Test basic web application endpoints."""
    client = TestClient(app)
    
    print("Testing RUCKUS ZTP Agent Web Application")
    print("=" * 50)
    
    # Test root endpoint
    print("Testing root endpoint...")
    response = client.get("/")
    if response.status_code == 200:
        print("✓ Root endpoint working")
    else:
        print(f"✗ Root endpoint failed: {response.status_code}")
        return False
    
    # Test config endpoint
    print("Testing config endpoint...")
    response = client.get("/api/config")
    if response.status_code == 200:
        config = response.json()
        print(f"✓ Config endpoint working - credentials: {len(config.get('credentials', []))}")
    else:
        print(f"✗ Config endpoint failed: {response.status_code}")
        return False
    
    # Test base configs endpoint
    print("Testing base configs endpoint...")
    response = client.get("/api/base-configs")
    if response.status_code == 200:
        base_configs = response.json()
        print(f"✓ Base configs endpoint working - configs available: {len(base_configs)}")
    else:
        print(f"✗ Base configs endpoint failed: {response.status_code}")
        return False
    
    # Test status endpoint
    print("Testing status endpoint...")
    response = client.get("/api/status")
    if response.status_code == 200:
        status = response.json()
        print(f"✓ Status endpoint working - ZTP running: {status.get('running', False)}")
    else:
        print(f"✗ Status endpoint failed: {response.status_code}")
        return False
    
    # Test devices endpoint
    print("Testing devices endpoint...")
    response = client.get("/api/devices")
    if response.status_code == 200:
        devices = response.json()
        print(f"✓ Devices endpoint working - devices: {len(devices)}")
    else:
        print(f"✗ Devices endpoint failed: {response.status_code}")
        return False
    
    # Test logs endpoint
    print("Testing logs endpoint...")
    response = client.get("/api/logs")
    if response.status_code == 200:
        logs = response.json()
        print(f"✓ Logs endpoint working - log entries: {len(logs)}")
    else:
        print(f"✗ Logs endpoint failed: {response.status_code}")
        return False
    
    print("\n" + "=" * 50)
    print("All basic endpoint tests passed! ✓")
    return True

def test_config_update():
    """Test configuration update functionality."""
    client = TestClient(app)
    
    print("\nTesting configuration update...")
    
    # Get current config
    response = client.get("/api/config")
    original_config = response.json()
    
    # Update config
    test_config = {
        "credentials": [{"username": "super", "password": "sp-admin"}],
        "preferred_password": "test123",
        "seed_switches": [{"ip": "192.168.1.100", "credentials_id": 0}],
        "base_config_name": "Default RUCKUS Configuration",
        "openrouter_api_key": "",
        "model": "anthropic/claude-3-5-haiku",
        "management_vlan": 10,
        "wireless_vlans": [20, 30, 40],
        "ip_pool": "192.168.10.0/24",
        "gateway": "192.168.10.1",
        "dns_server": "192.168.10.2",
        "poll_interval": 60
    }
    
    response = client.post("/api/config", json=test_config)
    if response.status_code == 200:
        print("✓ Configuration update successful")
        
        # Verify the config was updated
        response = client.get("/api/config")
        updated_config = response.json()
        
        if updated_config["preferred_password"] == "test123":
            print("✓ Configuration verification successful")
        else:
            print("✗ Configuration verification failed")
            return False
    else:
        print(f"✗ Configuration update failed: {response.status_code}")
        return False
    
    return True

def main():
    """Run all tests."""
    try:
        # Test basic endpoints
        if not test_basic_endpoints():
            sys.exit(1)
        
        # Test config update
        if not test_config_update():
            sys.exit(1)
        
        print("\n🎉 All tests passed! The web application is working correctly.")
        print("\nYou can now start the web server with:")
        print("  python run.py")
        print("  or")
        print("  uvicorn main:app --reload --host 0.0.0.0 --port 8000")
        
    except Exception as e:
        print(f"\nError during testing: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()