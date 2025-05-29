#!/usr/bin/env python3
"""
Startup script for RUCKUS ZTP Agent Web Application.
This script sets up the environment and starts the web server.
"""
import os
import sys
import subprocess
from pathlib import Path

def check_dependencies():
    """Check if required dependencies are installed."""
    try:
        import fastapi
        import uvicorn
        import jinja2
        print("✓ Web application dependencies found")
    except ImportError as e:
        print(f"✗ Missing web application dependency: {e}")
        print("Please install dependencies with: pip install -r requirements.txt")
        return False
    
    try:
        import ztp_agent
        print("✓ ZTP Agent package found")
    except ImportError:
        print("✗ ZTP Agent package not found")
        print("Please install ZTP Agent with: pip install -e .. (from web_app directory)")
        return False
    
    return True

def setup_directories():
    """Create necessary directories."""
    web_app_dir = Path(__file__).parent
    
    # Create static directories if they don't exist
    (web_app_dir / "static" / "css").mkdir(parents=True, exist_ok=True)
    (web_app_dir / "static" / "js").mkdir(parents=True, exist_ok=True)
    (web_app_dir / "templates").mkdir(parents=True, exist_ok=True)
    
    # Create upload directory
    (web_app_dir / "uploads").mkdir(exist_ok=True)
    
    print("✓ Directories created/verified")

def check_config_files():
    """Check if required configuration files exist."""
    project_root = Path(__file__).parent.parent
    config_dir = project_root / "config"
    
    if not (config_dir / "base_configuration.txt").exists():
        print("⚠ Warning: base_configuration.txt not found in config directory")
        print("  The web app will still work, but no default base configuration will be available")
    else:
        print("✓ Base configuration file found")

def main():
    """Main startup function."""
    print("RUCKUS ZTP Agent Web Application")
    print("=" * 40)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Setup directories
    setup_directories()
    
    # Check config files
    check_config_files()
    
    # Get configuration
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    log_level = os.getenv("LOG_LEVEL", "info")
    reload = os.getenv("RELOAD", "false").lower() == "true"
    
    print(f"\nStarting web server...")
    print(f"Host: {host}")
    print(f"Port: {port}")
    print(f"Log Level: {log_level}")
    print(f"Reload: {reload}")
    print(f"\nWeb interface will be available at: http://localhost:{port}")
    print("Press Ctrl+C to stop the server")
    print("-" * 40)
    
    # Start the server
    try:
        import uvicorn
        uvicorn.run(
            "main:app",
            host=host,
            port=port,
            log_level=log_level,
            reload=reload
        )
    except KeyboardInterrupt:
        print("\nShutting down web server...")
    except Exception as e:
        print(f"Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()