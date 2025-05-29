"""
Compatibility module that re-exports SwitchOperation as the old class name.

This maintains backward compatibility with existing imports while using
the new modular structure.
"""

# Import the new SwitchOperation class
from ztp_agent.network.switch.operation import SwitchOperation

# For backward compatibility, provide the old class name
SwitchConnection = SwitchOperation

# Re-export for direct imports
__all__ = ['SwitchOperation', 'SwitchConnection']