"""
State management module for switch operations.
"""
import logging
from enum import Enum
from typing import Dict, Any, Optional

# Set up logging
logger = logging.getLogger(__name__)

class SwitchState(Enum):
    """Enumeration of switch states in the ZTP process"""
    DISCOVERED = "discovered"
    BASE_CONFIG_APPLIED = "base_config_applied"
    MANAGEMENT_CONFIGURED = "management_configured"
    PORTS_CONFIGURED = "ports_configured"
    FULLY_CONFIGURED = "fully_configured"
    ERROR = "error"

class StateManager:
    """Class for managing switch state transitions"""
    
    def __init__(self):
        """Initialize the state manager"""
        self.switches = {}
    
    def add_switch(self, ip: str, initial_state: SwitchState = SwitchState.DISCOVERED, 
                  metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Add a switch to the state manager.
        
        Args:
            ip: IP address of the switch
            initial_state: Initial state of the switch
            metadata: Additional metadata for the switch
        """
        if metadata is None:
            metadata = {}
            
        self.switches[ip] = {
            'state': initial_state,
            'metadata': metadata,
            'state_history': [initial_state],
            'timestamp': None  # Will be set by transition_to
        }
        
        logger.info(f"Added switch {ip} to state manager with initial state {initial_state.value}")
    
    def get_state(self, ip: str) -> Optional[SwitchState]:
        """
        Get the current state of a switch.
        
        Args:
            ip: IP address of the switch
            
        Returns:
            Current state or None if switch not found
        """
        if ip not in self.switches:
            return None
            
        return self.switches[ip]['state']
    
    def get_metadata(self, ip: str) -> Optional[Dict[str, Any]]:
        """
        Get the metadata for a switch.
        
        Args:
            ip: IP address of the switch
            
        Returns:
            Metadata dictionary or None if switch not found
        """
        if ip not in self.switches:
            return None
            
        return self.switches[ip]['metadata']
    
    def update_metadata(self, ip: str, key: str, value: Any) -> bool:
        """
        Update a metadata value for a switch.
        
        Args:
            ip: IP address of the switch
            key: Metadata key to update
            value: New value
            
        Returns:
            True if successful, False if switch not found
        """
        if ip not in self.switches:
            return False
            
        self.switches[ip]['metadata'][key] = value
        return True
    
    def transition_to(self, ip: str, new_state: SwitchState, reason: Optional[str] = None) -> bool:
        """
        Transition a switch to a new state.
        
        Args:
            ip: IP address of the switch
            new_state: New state
            reason: Reason for the transition
            
        Returns:
            True if successful, False if switch not found
        """
        import time
        
        if ip not in self.switches:
            return False
            
        old_state = self.switches[ip]['state']
        self.switches[ip]['state'] = new_state
        self.switches[ip]['state_history'].append(new_state)
        self.switches[ip]['timestamp'] = time.time()
        
        logger.info(f"Switch {ip} transitioned from {old_state.value} to {new_state.value} - Reason: {reason or 'N/A'}")
        return True
    
    def get_switches_by_state(self, state: SwitchState) -> Dict[str, Dict[str, Any]]:
        """
        Get all switches in a given state.
        
        Args:
            state: State to filter by
            
        Returns:
            Dictionary of switches in the given state
        """
        return {
            ip: data for ip, data in self.switches.items() 
            if data['state'] == state
        }
    
    def remove_switch(self, ip: str) -> bool:
        """
        Remove a switch from the state manager.
        
        Args:
            ip: IP address of the switch
            
        Returns:
            True if successful, False if switch not found
        """
        if ip not in self.switches:
            return False
            
        del self.switches[ip]
        logger.info(f"Removed switch {ip} from state manager")
        return True
