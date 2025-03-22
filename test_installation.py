#!/usr/bin/env python3
"""
Simple script to test if the ZTP Agent package is installed correctly.
"""
import importlib
import sys

def check_module(module_name, display_name=None):
    """Check if a module can be imported."""
    if display_name is None:
        display_name = module_name
    
    try:
        importlib.import_module(module_name)
        print(f"✅ {display_name} successfully imported")
        return True
    except ImportError as e:
        print(f"❌ Failed to import {display_name}: {e}")
        return False

def main():
    """Check if all required modules are installed."""
    success = True
    
    # Check core package
    if not check_module("ztp_agent", "ZTP Agent package"):
        success = False
    
    # Check dependencies
    dependencies = [
        ("cmd2", "cmd2 (CLI framework)"),
        ("prompt_toolkit", "prompt_toolkit"),
        ("paramiko", "paramiko (SSH client)"),
        ("smolagents", "smolagents (AI agent framework)"),
        ("openai", "OpenAI API client"),
        ("yaml", "PyYAML")
    ]
    
    for module, display_name in dependencies:
        if not check_module(module, display_name):
            success = False
    
    # Check submodules
    submodules = [
        "ztp_agent.cli",
        "ztp_agent.network",
        "ztp_agent.ztp",
        "ztp_agent.agent",
        "ztp_agent.utils"
    ]
    
    for module in submodules:
        if not check_module(module):
            success = False
    
    if success:
        print("\n✅ All checks passed! ZTP Agent is installed correctly.")
        print("You can run the agent with the command: ztp-agent")
        return 0
    else:
        print("\n❌ Some checks failed. Please fix the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())