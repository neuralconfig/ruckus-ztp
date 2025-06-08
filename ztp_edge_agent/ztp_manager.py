#!/usr/bin/env python3
"""
ZTP Manager for Edge Agent - Runs ZTP process locally
"""
import asyncio
import sys
import os
import json
import logging
from pathlib import Path

# Add the parent directory to Python path to import ztp_agent
sys.path.insert(0, str(Path(__file__).parent.parent))

# Try to import ZTP components
ZTP_AVAILABLE = False
try:
    from ztp_agent.ztp.process import ZTPProcess
    from ztp_agent.ztp.config import load_config as load_ztp_config
    from ztp_agent.utils.logger import setup_logging as setup_ztp_logging
    ZTP_AVAILABLE = True
    print("✅ ZTP agent modules imported successfully")
except ImportError as e:
    # If we can't import ztp_agent, we'll run in SSH-only mode
    print(f"⚠️ ZTP agent not available: {e}")
    print("🔧 Edge agent will run in SSH-only mode")
    ZTPProcess = None
    load_ztp_config = None
    setup_ztp_logging = None


class EventReporter:
    """Reports ZTP events back to the web application."""
    
    def __init__(self, websocket=None, agent_id=None):
        self.websocket = websocket
        self.agent_id = agent_id
        self.logger = logging.getLogger(__name__)
    
    async def report_event(self, event_type, data=None):
        """Report an event to the web application."""
        if not self.websocket:
            self.logger.debug(f"No websocket connection, skipping event: {event_type}")
            return
            
        event = {
            "type": "ztp_event", 
            "event_type": event_type,
            "agent_id": self.agent_id,
            "timestamp": asyncio.get_event_loop().time(),
            "data": data or {}
        }
        
        try:
            await self.websocket.send(json.dumps(event))
            self.logger.debug(f"Reported event: {event_type}")
        except Exception as e:
            self.logger.error(f"Failed to report event {event_type}: {e}")
    
    def set_websocket(self, websocket):
        """Update the websocket connection."""
        self.websocket = websocket


class ZTPManager:
    """Manages the ZTP process on the edge agent."""
    
    def __init__(self, config_file=None, event_reporter=None):
        self.logger = logging.getLogger(__name__)
        self.config_file = config_file or "/etc/ruckus-ztp-edge-agent/ztp_config.ini"
        self.event_reporter = event_reporter or EventReporter()
        self.ztp_process = None
        self.running = False
        self.task = None
        self.current_config = None  # Configuration from web app
        
    async def start(self):
        """Start the ZTP process."""
        if self.running:
            self.logger.warning("ZTP process is already running")
            return
            
        self.logger.info("Starting ZTP process on edge agent")
        
        # Report ZTP start event
        await self.event_reporter.report_event("ztp_starting", {
            "message": "ZTP process is starting on edge agent"
        })
        
        try:
            # Check if ZTP is available
            if not ZTP_AVAILABLE:
                self.logger.warning("ZTP process not available - ztp_agent not imported")
                self.logger.info("Edge agent will operate in SSH-only mode")
                await self.event_reporter.report_event("info", {
                    "message": "ZTP process not available - operating in SSH-only mode"
                })
                return
                
            config = await self._load_ztp_config()
            if not config:
                self.logger.error("Failed to load ZTP configuration")
                await self.event_reporter.report_event("error", {
                    "message": "Failed to load ZTP configuration"
                })
                return
            
            # Create ZTP process with local SSH executor (no proxy)
            self.ztp_process = ZTPProcess(config, ssh_executor=None)
            
            await self.event_reporter.report_event("ztp_started", {
                "config_file": self.config_file
            })
            
            # Start ZTP process in background
            self.running = True
            self.task = asyncio.create_task(self._run_ztp_process())
            
            self.logger.info("ZTP process started successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to start ZTP process: {e}")
            await self.event_reporter.report_event("error", {
                "message": f"Failed to start ZTP process: {str(e)}"
            })
    
    async def stop(self):
        """Stop the ZTP process."""
        if not self.running:
            return
            
        self.logger.info("Stopping ZTP process")
        self.running = False
        
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        # Stop the actual ZTP process if it's running
        if self.ztp_process and hasattr(self.ztp_process, 'stop'):
            try:
                self.ztp_process.stop()
                self.logger.info("Stopped ZTP process background thread")
            except Exception as e:
                self.logger.warning(f"Error stopping ZTP process: {e}")
            
        self.ztp_process = None
        
        await self.event_reporter.report_event("ztp_stopped")
        self.logger.info("ZTP process stopped")
    
    async def get_status(self):
        """Get current ZTP status with separate switch/AP counts."""
        if not self.ztp_process:
            return {
                "running": False,
                "devices_discovered": 0,
                "switches_discovered": 0,
                "aps_discovered": 0,
                "devices_configured": 0,
                "switches_configured": 0,
                "aps_configured": 0,
                "errors": []
            }
        
        # Access inventory directly from ZTP process
        inventory = getattr(self.ztp_process, 'inventory', {})
        switches = inventory.get('switches', {})
        aps = inventory.get('aps', {})
        
        # Count configured devices by checking 'configured' flag
        switches_configured = len([s for s in switches.values() if s.get('configured', False)])
        aps_configured = len([a for a in aps.values() if a.get('configured', False)])
        
        # Check if we have actual configuration to work with
        config = await self._load_ztp_config()
        has_seed_switches = config and config.get('seed_switches') and len(config['seed_switches']) > 0
        has_credentials = config and config.get('credentials') and len(config['credentials']) > 0
        
        # ZTP is only truly "running" if we have configuration and the manager is active
        ztp_process_running = getattr(self.ztp_process, 'running', False)
        ztp_actually_running = self.running and has_seed_switches and has_credentials and ztp_process_running
        
        return {
            "running": ztp_actually_running,
            "manager_active": self.running,  # Background task is running
            "ztp_thread_active": ztp_process_running,  # ZTP background thread is running
            "has_configuration": has_seed_switches and has_credentials,
            "devices_discovered": len(switches) + len(aps),
            "switches_discovered": len(switches),
            "aps_discovered": len(aps),
            "devices_configured": switches_configured + aps_configured,
            "switches_configured": switches_configured,
            "aps_configured": aps_configured,
            "seed_switches_count": len(config.get('seed_switches', [])) if config else 0,
            "credentials_count": len(config.get('credentials', [])) if config else 0,
            "errors": []  # TODO: Track errors from ZTP process
        }
    
    async def get_inventory(self):
        """Get device inventory."""
        if not self.ztp_process:
            return {}
        # Access inventory directly from ZTP process
        return getattr(self.ztp_process, 'inventory', {})
    
    async def _load_ztp_config(self):
        """Load ZTP configuration."""
        try:
            # First, check if we have configuration from the web app
            if self.current_config:
                self.logger.info("Using configuration from web app")
                
                # Check if we have base config content directly from the web app
                base_config_content = self.current_config.get('base_config_content')
                base_config_name = self.current_config.get('base_config_name')
                
                if base_config_content:
                    self.logger.info(f"Using base configuration content from web app: '{base_config_name}' ({len(base_config_content)} characters)")
                    # Structure the configuration properly for the ZTP process
                    structured_config = self._structure_config_for_ztp(self.current_config)
                    return structured_config
                elif base_config_name:
                    self.logger.warning(f"Base config name '{base_config_name}' provided but no content - using default configuration")
                    # Load the default base configuration as fallback
                    try:
                        # Use relative path from the edge agent to the project config
                        default_config_path = str(Path(__file__).parent.parent / "config" / "base_configuration.txt")
                        with open(default_config_path, 'r') as f:
                            default_content = f.read()
                        config_with_base = self.current_config.copy()
                        config_with_base['base_config_content'] = default_content
                        self.logger.info(f"Using default base configuration ({len(default_content)} characters)")
                        # Structure the configuration properly for the ZTP process
                        structured_config = self._structure_config_for_ztp(config_with_base)
                        return structured_config
                    except Exception as e:
                        self.logger.warning(f"Failed to load default base config: {e}")
                
                # Structure the configuration properly for the ZTP process even without base config
                structured_config = self._structure_config_for_ztp(self.current_config)
                return structured_config
            
            if ZTP_AVAILABLE and load_ztp_config:
                # Look for ZTP config file
                ztp_config_path = os.path.expanduser("~/.ztp_agent.cfg")
                if not os.path.exists(ztp_config_path):
                    self.logger.warning(f"ZTP config file not found at {ztp_config_path}")
                    return None
                return load_ztp_config(ztp_config_path)
            else:
                # Create a minimal config for testing (no seed switches = not truly running)
                self.logger.info("Using minimal ZTP configuration (no seed switches)")
                return {
                    "credentials": [{"username": "super", "password": "sp-admin"}],
                    "preferred_password": "sp-admin",
                    "seed_switches": [],  # Empty = ZTP won't actually run
                    "base_config_name": "Default RUCKUS Configuration",
                    "management_vlan": 10,
                    "wireless_vlans": [20, 30, 40],
                    "ip_pool": "192.168.10.0/24",
                    "gateway": "192.168.10.1",
                    "dns_server": "192.168.10.2",
                    "poll_interval": 300
                }
        except Exception as e:
            self.logger.error(f"Failed to load ZTP config: {e}")
            return None
    
    async def _run_ztp_process(self):
        """Run the ZTP process loop."""
        try:
            while self.running:
                try:
                    # Run one cycle of the ZTP process
                    if self.ztp_process:
                        self.logger.debug("Running ZTP process cycle")
                        
                        # Get previous inventory for comparison
                        old_inventory = getattr(self.ztp_process, 'inventory', {}).copy()
                        
                        # Run ZTP process (this is synchronous in the original code)
                        # We'll need to run it in a thread pool to avoid blocking
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(None, self._run_ztp_cycle)
                        
                        # Check for changes and report events
                        new_inventory = getattr(self.ztp_process, 'inventory', {})
                        await self._check_and_report_changes(old_inventory, new_inventory)
                    
                    # Wait before next cycle - faster for better responsiveness  
                    await asyncio.sleep(30)  # Run every 30 seconds for monitoring
                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self.logger.error(f"Error in ZTP process cycle: {e}")
                    await self.event_reporter.report_event("error", {
                        "message": f"ZTP process cycle error: {str(e)}"
                    })
                    await asyncio.sleep(60)  # Wait longer on error
                    
        except asyncio.CancelledError:
            self.logger.info("ZTP process cancelled")
        except Exception as e:
            self.logger.error(f"Fatal error in ZTP process: {e}")
            await self.event_reporter.report_event("error", {
                "message": f"Fatal ZTP process error: {str(e)}"
            })
    
    def _run_ztp_cycle(self):
        """Run one cycle of the ZTP process (synchronous)."""
        if self.ztp_process and ZTP_AVAILABLE:
            try:
                # Check if we have configuration to work with
                if not hasattr(self, 'current_config') or not self.current_config:
                    self.logger.debug("No configuration available for ZTP process")
                    return
                
                seed_switches = self.current_config.get('seed_switches', [])
                credentials = self.current_config.get('credentials', [])
                
                if not seed_switches or not credentials:
                    self.logger.debug("No seed switches or credentials configured")
                    return
                
                # Check if the ZTP process is already running its own background thread
                if getattr(self.ztp_process, 'running', False):
                    # ZTP process is running autonomously, just check status
                    if hasattr(self.ztp_process, 'get_status'):
                        status = self.ztp_process.get_status()
                        self.logger.debug(f"ZTP process running autonomously - status: {status}")
                    return
                
                # Add all configured seed switches - ZTP process will handle duplicates
                self.logger.info(f"🌱 Ensuring {len(seed_switches)} seed switches are in inventory")
                added_count = 0
                for switch in seed_switches:
                    switch_ip = switch if isinstance(switch, str) else switch.get('ip')
                    if switch_ip:
                        success = self._add_seed_switch_sync(switch_ip, credentials)
                        if success:
                            added_count += 1
                            self.logger.info(f"✅ Seed switch {switch_ip} ready in inventory")
                        else:
                            self.logger.error(f"❌ Failed to add seed switch {switch_ip}")
                
                self.logger.info(f"📊 Successfully processed {added_count}/{len(seed_switches)} seed switches")
                
                # Give switches time to be fully registered in inventory
                if added_count > 0:
                    import time
                    time.sleep(0.5)  # Reduced from 2 seconds
                    self.logger.debug("Waited for switches to be fully registered in inventory")
                
                # Now check if we should start the ZTP process
                # Only start if we have switches in inventory and ZTP is not already running
                inventory = getattr(self.ztp_process, 'inventory', {})
                switches = inventory.get('switches', {})
                
                if switches and not getattr(self.ztp_process, 'running', False):
                    self.logger.info(f"🚀 Starting ZTP process with {len(switches)} switches in inventory")
                    self.logger.info("🔄 ZTP will run continuous discovery and configuration")
                    success = self.ztp_process.start()
                    if success:
                        self.logger.info("✅ ZTP process started and running autonomously")
                    else:
                        self.logger.error("❌ Failed to start ZTP process")
                elif not switches:
                    self.logger.warning("⚠️ No switches in inventory - ZTP cannot start")
                else:
                    self.logger.debug("ZTP process already running")
                        
            except Exception as e:
                self.logger.error(f"❌ ZTP cycle error: {e}")
                import traceback
                self.logger.debug(f"Full traceback: {traceback.format_exc()}")
        else:
            self.logger.debug("ZTP cycle skipped - ZTP not available")
    
    async def _check_and_report_changes(self, old_inventory, new_inventory):
        """Check for changes in inventory and report events."""
        if not isinstance(new_inventory, dict):
            return
            
        # Handle switches
        old_switches = old_inventory.get('switches', {}) if old_inventory else {}
        new_switches = new_inventory.get('switches', {})
        
        for mac, device in new_switches.items():
            if mac not in old_switches:
                await self.event_reporter.report_event("device_discovered", {
                    "mac_address": mac,
                    "ip_address": device.get('ip'),
                    "device_type": "switch",
                    "model": device.get('model'),
                    "hostname": device.get('hostname'),
                    "serial": device.get('serial'),
                    "is_seed": device.get('is_seed', False)
                })
                self.logger.info(f"📡 Reported switch discovery: {device.get('hostname', 'Unknown')} ({mac})")
        
        # Check for switch status changes
        for mac, device in new_switches.items():
            old_device = old_switches.get(mac, {})
            old_configured = old_device.get('configured', False)
            new_configured = device.get('configured', False)
            
            if not old_configured and new_configured:
                await self.event_reporter.report_event("device_configured", {
                    "mac_address": mac,
                    "ip_address": device.get('ip'),
                    "device_type": "switch",
                    "hostname": device.get('hostname'),
                    "configuration_applied": ["base_config", "management_vlan", "hostname"]
                })
                self.logger.info(f"⚙️ Reported switch configuration: {device.get('hostname', 'Unknown')} ({mac})")
        
        # Handle APs
        old_aps = old_inventory.get('aps', {}) if old_inventory else {}
        new_aps = new_inventory.get('aps', {})
        
        for mac, device in new_aps.items():
            if mac not in old_aps:
                await self.event_reporter.report_event("device_discovered", {
                    "mac_address": mac,
                    "ip_address": device.get('ip'),
                    "device_type": "ap",
                    "model": device.get('model'),
                    "hostname": device.get('hostname'),
                    "switch_ip": device.get('switch_ip'),
                    "port": device.get('port')
                })
                self.logger.info(f"📡 Reported AP discovery: {device.get('hostname', 'Unknown')} ({mac})")
        
        # Report inventory update to web app
        await self._report_inventory_update(new_inventory)
    
    async def _report_inventory_update(self, inventory):
        """Report full inventory update to web app."""
        if not inventory:
            return
            
        # Prepare inventory data for web app
        inventory_data = {
            "switches": {},
            "aps": {},
            "timestamp": asyncio.get_event_loop().time()
        }
        
        # Process switches
        for mac, switch in inventory.get('switches', {}).items():
            inventory_data["switches"][mac] = {
                "mac_address": mac,
                "ip_address": switch.get('ip'),
                "hostname": switch.get('hostname'),
                "model": switch.get('model'),
                "serial": switch.get('serial'),
                "status": switch.get('status', 'Unknown'),
                "configured": switch.get('configured', False),
                "base_config_applied": switch.get('base_config_applied', False),  # Include base config status for progress indicator
                "is_seed": switch.get('is_seed', False),
                "neighbor_count": len(switch.get('neighbors', {})),
                "neighbors": switch.get('neighbors', {})  # Include full neighbor data for topology
            }
        
        # Process APs
        for mac, ap in inventory.get('aps', {}).items():
            inventory_data["aps"][mac] = {
                "mac_address": mac,
                "ip_address": ap.get('ip'),
                "hostname": ap.get('hostname'),
                "model": ap.get('model'),
                "configured": ap.get('configured', False),  # Include configured field for progress indicator
                "switch_ip": ap.get('switch_ip'),
                "connected_switch": ap.get('switch_ip'),  # For topology compatibility
                "port": ap.get('switch_port'),
                "connected_port": ap.get('switch_port'),  # For topology compatibility
                "status": ap.get('status', 'Unknown')
            }
        
        await self.event_reporter.report_event("inventory_update", inventory_data)
        self.logger.debug(f"📊 Reported inventory update: {len(inventory_data['switches'])} switches, {len(inventory_data['aps'])} APs")
    
    def set_event_reporter(self, event_reporter):
        """Update the event reporter."""
        self.event_reporter = event_reporter
    
    
    def _add_seed_switch_sync(self, switch_ip, credentials):
        """Add a seed switch by trying all credentials (synchronous version)."""
        self.logger.info(f"🔍 Attempting to add seed switch {switch_ip}")
        self.logger.info(f"📋 Will try {len(credentials)} credential sets")
        
        for i, cred in enumerate(credentials):
            username = cred['username']
            password = cred['password']
            self.logger.info(f"🔑 Trying credentials {i+1}/{len(credentials)} for {switch_ip}: {username} / {password}")
            
            try:
                # Try to add the switch - ZTP process handles duplicate checking
                # Pass preferred password for first-time login handling
                preferred_password = self.current_config.get('preferred_password') if self.current_config else None
                success = self.ztp_process.add_switch(switch_ip, username, password, preferred_password=preferred_password)
                
                if success:
                    self.logger.info(f"✅ SUCCESS! Switch {switch_ip} added/updated with credentials {i+1}: {username} / {password}")
                    return True
                else:
                    self.logger.warning(f"❌ Credentials {i+1} failed for {switch_ip} ({username} / {password})")
                    continue
                    
            except Exception as e:
                self.logger.warning(f"❌ Credentials {i+1} failed for {switch_ip} ({username} / {password}): {e}")
                continue
        
        self.logger.error(f"💥 FAILED! All {len(credentials)} credential sets failed for switch {switch_ip}")
        return False
    
    def _structure_config_for_ztp(self, config):
        """Convert web app configuration to ZTP process format."""
        # Validate and get base configuration
        base_config_content = config.get('base_config_content', '')
        if not base_config_content:
            self.logger.warning("⚠️ No base configuration content provided")
        else:
            # Basic validation of base config
            if 'vlan' not in base_config_content.lower():
                self.logger.warning("⚠️ Base configuration does not contain VLAN commands")
            self.logger.info(f"✅ Base configuration loaded ({len(base_config_content)} characters)")
        
        # Validate credentials
        credentials = config.get('credentials', [])
        if not credentials:
            self.logger.warning("⚠️ No credentials configured")
        else:
            self.logger.info(f"📋 {len(credentials)} credential sets configured")
        
        # Validate seed switches
        seed_switches = config.get('seed_switches', [])
        if not seed_switches:
            self.logger.warning("⚠️ No seed switches configured")
        else:
            self.logger.info(f"🌱 {len(seed_switches)} seed switches configured")
        
        # Structure the configuration as expected by the ZTP process
        ztp_config = {
            # Root level fields that ZTP process expects  
            'poll_interval': config.get('poll_interval', 15 if config.get('fast_discovery', True) else 60),  # Fast discovery mode
            'credentials': credentials,
            'preferred_password': config.get('preferred_password', 'sp-admin'),
            'seed_switches': seed_switches,
            
            # Network configuration section
            'network': {
                'base_config': base_config_content,  # ZTP expects this field
                'management_vlan': config.get('management_vlan', 10),
                'wireless_vlans': config.get('wireless_vlans', [20, 30, 40]),
                'ip_pool': config.get('ip_pool', '192.168.10.0/24'),
                'gateway': config.get('gateway', '192.168.10.1'),
                'dns_server': config.get('dns_server', '192.168.10.2'),
            },
            
            # Agent configuration section (for future use)
            'agent': {
                'openrouter_api_key': config.get('openrouter_api_key', ''),
                'model': config.get('model', 'anthropic/claude-3-5-haiku'),
            },
            
            # Testing/development options
            'allow_configured_switches': config.get('allow_configured_switches', True),  # Allow topology from configured switches
            'fast_discovery': config.get('fast_discovery', True),  # Enable faster discovery for lab environments
        }
        
        self.logger.debug(f"Structured ZTP config with base_config length: {len(ztp_config['network']['base_config'])}")
        self.logger.debug(f"ZTP config keys: {list(ztp_config.keys())}")
        return ztp_config
    
    async def update_configuration(self, config):
        """Update ZTP configuration and restart process if running."""
        self.logger.info("Updating ZTP configuration")
        self.logger.debug(f"Received config keys: {list(config.keys())}")
        self.logger.debug(f"Seed switches in config: {config.get('seed_switches', 'NOT FOUND')}")
        
        # Store the new configuration
        self.current_config = config
        
        # If ZTP is currently running, restart it with new config
        if self.running:
            self.logger.info("Restarting ZTP process with new configuration")
            await self.stop()
            await self.start()
        
        await self.event_reporter.report_event("config_updated", {
            "has_seed_switches": bool(config.get('seed_switches')),
            "credentials_count": len(config.get('credentials', [])),
            "management_vlan": config.get('management_vlan'),
        })