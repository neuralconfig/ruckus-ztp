"""
Inventory management utilities for ZTP Agent.
"""
import os
import json
import logging
from typing import Dict, List, Any, Optional

# Set up logging
logger = logging.getLogger(__name__)

class Inventory:
    """Class for managing device inventory"""
    
    def __init__(self, inventory_file: str = '~/.ztp_agent_inventory.json'):
        """
        Initialize inventory.
        
        Args:
            inventory_file: Path to inventory file.
        """
        self.inventory_file = os.path.expanduser(inventory_file)
        self.inventory = {
            'switches': {},
            'aps': {}
        }
        
        # Load inventory if it exists
        self.load()
    
    def load(self) -> bool:
        """
        Load inventory from file.
        
        Returns:
            True if successful, False otherwise.
        """
        if not os.path.exists(self.inventory_file):
            logger.info(f"Inventory file {self.inventory_file} does not exist, using empty inventory")
            return False
        
        try:
            with open(self.inventory_file, 'r') as f:
                self.inventory = json.load(f)
            
            logger.info(f"Loaded inventory with {len(self.inventory['switches'])} switches and {len(self.inventory['aps'])} APs")
            return True
        
        except Exception as e:
            logger.error(f"Error loading inventory from {self.inventory_file}: {e}", exc_info=True)
            return False
    
    def save(self) -> bool:
        """
        Save inventory to file.
        
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.inventory_file), exist_ok=True)
            
            # Save inventory
            with open(self.inventory_file, 'w') as f:
                json.dump(self.inventory, f, indent=2)
            
            logger.info(f"Saved inventory to {self.inventory_file}")
            return True
        
        except Exception as e:
            logger.error(f"Error saving inventory to {self.inventory_file}: {e}", exc_info=True)
            return False
    
    def add_switch(self, ip: str, username: str, password: str) -> bool:
        """
        Add a switch to the inventory.
        
        Args:
            ip: IP address of the switch.
            username: Username for switch access.
            password: Password for switch access.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            self.inventory['switches'][ip] = {
                'ip': ip,
                'username': username,
                'password': password,
                'status': 'Added',
                'configured': False,
                'neighbors': {},
                'ports': {}
            }
            
            self.save()
            logger.info(f"Added switch {ip} to inventory")
            return True
        
        except Exception as e:
            logger.error(f"Error adding switch {ip} to inventory: {e}", exc_info=True)
            return False
    
    def add_ap(self, mac: str, ip: str, switch_ip: str, port: str) -> bool:
        """
        Add an AP to the inventory.
        
        Args:
            mac: MAC address of the AP.
            ip: IP address of the AP.
            switch_ip: IP of the connected switch.
            port: Port on the switch.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            self.inventory['aps'][mac] = {
                'mac': mac,
                'ip': ip,
                'switch_ip': switch_ip,
                'port': port,
                'status': 'Added'
            }
            
            self.save()
            logger.info(f"Added AP {mac} to inventory")
            return True
        
        except Exception as e:
            logger.error(f"Error adding AP {mac} to inventory: {e}", exc_info=True)
            return False
    
    def get_switches(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all switches in the inventory.
        
        Returns:
            Dictionary of switch IP to switch information.
        """
        return self.inventory['switches']
    
    def get_aps(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all APs in the inventory.
        
        Returns:
            Dictionary of AP MAC to AP information.
        """
        return self.inventory['aps']
    
    def update_switch(self, ip: str, updates: Dict[str, Any]) -> bool:
        """
        Update switch information.
        
        Args:
            ip: IP address of the switch.
            updates: Dictionary of updates.
            
        Returns:
            True if successful, False otherwise.
        """
        if ip not in self.inventory['switches']:
            logger.error(f"Switch {ip} not found in inventory")
            return False
        
        try:
            self.inventory['switches'][ip].update(updates)
            self.save()
            logger.info(f"Updated switch {ip} in inventory")
            return True
        
        except Exception as e:
            logger.error(f"Error updating switch {ip} in inventory: {e}", exc_info=True)
            return False
    
    def update_ap(self, mac: str, updates: Dict[str, Any]) -> bool:
        """
        Update AP information.
        
        Args:
            mac: MAC address of the AP.
            updates: Dictionary of updates.
            
        Returns:
            True if successful, False otherwise.
        """
        if mac not in self.inventory['aps']:
            logger.error(f"AP {mac} not found in inventory")
            return False
        
        try:
            self.inventory['aps'][mac].update(updates)
            self.save()
            logger.info(f"Updated AP {mac} in inventory")
            return True
        
        except Exception as e:
            logger.error(f"Error updating AP {mac} in inventory: {e}", exc_info=True)
            return False
