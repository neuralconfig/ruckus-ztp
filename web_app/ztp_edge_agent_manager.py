"""ZTP Edge Agent management for backend server."""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Dict, Optional, Set, Any, List
from dataclasses import dataclass, field

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState


@dataclass
class EdgeAgentConnection:
    """Represents a connected edge agent."""
    agent_id: str
    websocket: WebSocket
    hostname: str
    network_subnet: str
    capabilities: list
    version: str
    connected_at: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)
    status: str = "online"
    ztp_status: Dict[str, Any] = field(default_factory=dict)
    device_inventory: Dict[str, Any] = field(default_factory=dict)
    config: Optional[Dict[str, Any]] = None
    logs: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "agent_id": self.agent_id,
            "hostname": self.hostname,
            "network_subnet": self.network_subnet,
            "capabilities": self.capabilities,
            "version": self.version,
            "connected_at": self.connected_at.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "status": self.status,
            "ztp_status": self.ztp_status,
            "device_inventory": self.device_inventory
        }


class ZTPEdgeAgentManager:
    """Manages SSH edge agent connections and command routing."""
    
    def __init__(self):
        """Initialize edge agent manager."""
        self.logger = logging.getLogger(__name__)
        self._agents: Dict[str, EdgeAgentConnection] = {}
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()
        
        # Event storage for web interface
        self._events: List[Dict[str, Any]] = []
        self._max_events = 1000  # Keep last 1000 events
        
        # Rate limiting
        self._request_times: Dict[str, list] = {}  # agent_id -> list of request timestamps
        self._max_requests_per_minute = 30  # Maximum requests per agent per minute
        self._request_semaphore = asyncio.Semaphore(10)  # Limit concurrent requests
    
    async def handle_agent_connection(self, websocket: WebSocket, auth_token: str):
        """Handle incoming agent WebSocket connection.
        
        Args:
            websocket: WebSocket connection
            auth_token: Authentication token from agent
        """
        agent_connection = None
        
        try:
            # Validate auth token (simplified for now)
            if not self._validate_token(auth_token):
                await websocket.close(code=1008, reason="Invalid authentication")
                return
            
            # Accept connection
            await websocket.accept()
            self.logger.info("New edge agent connection accepted")
            
            # Wait for registration
            registration = await self._wait_for_registration(websocket)
            if not registration:
                await websocket.close(code=1002, reason="Registration timeout")
                return
            
            # Create edge agent connection
            agent_connection = EdgeAgentConnection(
                agent_id=registration["pi_id"],
                websocket=websocket,
                hostname=registration["network_info"]["hostname"],
                network_subnet=registration["network_info"]["subnet"],
                capabilities=registration["capabilities"],
                version=registration["version"]
            )
            
            # Register agent
            async with self._lock:
                self._agents[agent_connection.agent_id] = agent_connection
            
            self.logger.info(f"Edge agent registered: {agent_connection.agent_id} ({agent_connection.hostname})")
            
            # Handle messages
            await self._handle_agent_messages(agent_connection)
            
        except WebSocketDisconnect:
            self.logger.info("Edge agent disconnected")
        except Exception as e:
            self.logger.error(f"Edge agent connection error: {e}")
        finally:
            # Clean up
            if agent_connection:
                async with self._lock:
                    self._agents.pop(agent_connection.agent_id, None)
                self.logger.info(f"Edge agent unregistered: {agent_connection.agent_id}")
    
    def _validate_token(self, token: str) -> bool:
        """Validate authentication token.
        
        Args:
            token: Authentication token
            
        Returns:
            True if valid, False otherwise
        """
        # TODO: Implement proper token validation
        # For now, accept any non-empty token
        return bool(token)
    
    async def _wait_for_registration(self, websocket: WebSocket, timeout: int = 10) -> Optional[dict]:
        """Wait for agent registration message.
        
        Args:
            websocket: WebSocket connection
            timeout: Registration timeout in seconds
            
        Returns:
            Registration message or None if timeout
        """
        try:
            # Wait for registration with timeout
            message = await asyncio.wait_for(websocket.receive_json(), timeout=timeout)
            
            if message.get("type") == "register":
                # Register agent password if provided
                agent_password = message.get("agent_password")
                if agent_password:
                    from main import register_agent_password
                    register_agent_password(message.get("pi_id"), agent_password)
                
                return message
            else:
                self.logger.warning(f"Expected registration, got: {message.get('type')}")
                return None
                
        except asyncio.TimeoutError:
            self.logger.warning("Registration timeout")
            return None
    
    async def _handle_agent_messages(self, agent_connection: EdgeAgentConnection):
        """Handle messages from agent.
        
        Args:
            agent_connection: Edge agent connection
        """
        while True:
            try:
                message = await agent_connection.websocket.receive_json()
                msg_type = message.get("type")
                
                # Update last seen
                agent_connection.last_seen = datetime.utcnow()
                
                if msg_type == "command_result":
                    await self._handle_command_result(message)
                elif msg_type == "status":
                    await self._handle_status_update(agent_connection, message)
                elif msg_type == "ztp_event":
                    await self._handle_ztp_event(agent_connection, message)
                elif msg_type == "pong":
                    self.logger.debug(f"Pong from {agent_connection.agent_id}")
                else:
                    self.logger.warning(f"Unknown message type from agent: {msg_type}")
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                self.logger.error(f"Error handling agent message: {e}")
                break
    
    async def _handle_command_result(self, message: dict):
        """Handle command result from agent.
        
        Args:
            message: Command result message
        """
        request_id = message.get("request_id")
        if request_id and request_id in self._pending_requests:
            future = self._pending_requests.pop(request_id)
            if not future.done():
                future.set_result(message)
    
    async def _handle_status_update(self, agent_connection: EdgeAgentConnection, message: dict):
        """Handle status update from agent.
        
        Args:
            agent_connection: Edge agent connection
            message: Status message
        """
        agent_connection.status = message.get("status", "online")
        
        # Update ZTP status if provided
        if "ztp_status" in message:
            agent_connection.ztp_status = message["ztp_status"]
            
        self.logger.debug(f"Status update from {agent_connection.agent_id}: {agent_connection.status}")
    
    async def _handle_ztp_event(self, agent_connection: EdgeAgentConnection, message: dict):
        """Handle ZTP event from agent.
        
        Args:
            agent_connection: Edge agent connection
            message: ZTP event message
        """
        event_type = message.get("event_type")
        event_data = message.get("data", {})
        timestamp = message.get("timestamp", time.time())
        
        # Store event
        event = {
            "timestamp": datetime.fromtimestamp(timestamp),
            "agent_id": agent_connection.agent_id,
            "event_type": event_type,
            "data": event_data
        }
        
        self._events.append(event)
        
        # Keep only recent events
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]
        
        # Update device inventory for device events
        if event_type in ["device_discovered", "device_configured"]:
            mac_address = event_data.get("mac_address")
            if mac_address:
                if mac_address not in agent_connection.device_inventory:
                    agent_connection.device_inventory[mac_address] = {}
                
                device = agent_connection.device_inventory[mac_address]
                device.update({
                    "mac_address": mac_address,
                    "ip_address": event_data.get("ip_address"),
                    "device_type": event_data.get("device_type"),
                    "model": event_data.get("model"),
                    "hostname": event_data.get("hostname"),
                    "serial": event_data.get("serial"),
                    "is_seed": event_data.get("is_seed", False),
                    "last_seen": datetime.utcnow(),
                    "status": "configured" if event_type == "device_configured" else "discovered"
                })
                
                if event_type == "device_configured":
                    device["configuration_applied"] = event_data.get("configuration_applied", [])
        
        # Handle full inventory updates
        elif event_type == "inventory_update":
            # Replace agent's device inventory with the new full inventory
            agent_connection.device_inventory = {}
            
            # Process switches
            switches = event_data.get("switches", {})
            for mac, switch_data in switches.items():
                agent_connection.device_inventory[mac] = {
                    "mac_address": mac,
                    "ip_address": switch_data.get("ip_address"),
                    "device_type": "switch",
                    "model": switch_data.get("model"),
                    "hostname": switch_data.get("hostname"),
                    "serial": switch_data.get("serial"),
                    "status": switch_data.get("status", "discovered"),
                    "configured": switch_data.get("configured", False),
                    "base_config_applied": switch_data.get("base_config_applied", False),  # Include base config status
                    "is_seed": switch_data.get("is_seed", False),
                    "neighbor_count": switch_data.get("neighbor_count", 0),
                    "neighbors": switch_data.get("neighbors", {}),  # Full neighbor data for topology
                    "last_seen": datetime.utcnow()
                }
            
            # Process APs
            aps = event_data.get("aps", {})
            for mac, ap_data in aps.items():
                agent_connection.device_inventory[mac] = {
                    "mac_address": mac,
                    "ip_address": ap_data.get("ip_address"),
                    "device_type": "ap",
                    "model": ap_data.get("model"),
                    "hostname": ap_data.get("hostname"),
                    "status": ap_data.get("status", "discovered"),
                    "configured": ap_data.get("configured", False),  # Include configured field for APs
                    "switch_ip": ap_data.get("switch_ip"),
                    "connected_switch": ap_data.get("connected_switch"),  # For topology
                    "port": ap_data.get("port"),
                    "connected_port": ap_data.get("connected_port"),  # For topology
                    "last_seen": datetime.utcnow()
                }
            
            self.logger.debug(f"Updated full inventory for agent {agent_connection.agent_id}: {len(switches)} switches, {len(aps)} APs")
        
        self.logger.info(f"ZTP Event from {agent_connection.agent_id}: {event_type} - {event_data}")
    
    def _check_rate_limit(self, agent_id: str) -> bool:
        """Check if agent is within rate limits."""
        now = time.time()
        minute_ago = now - 60
        
        # Clean old timestamps and check current rate
        if agent_id not in self._request_times:
            self._request_times[agent_id] = []
        
        # Remove timestamps older than 1 minute
        self._request_times[agent_id] = [
            t for t in self._request_times[agent_id] if t > minute_ago
        ]
        
        # Check if under rate limit
        return len(self._request_times[agent_id]) < self._max_requests_per_minute
    
    def _record_request(self, agent_id: str):
        """Record a new request timestamp."""
        now = time.time()
        if agent_id not in self._request_times:
            self._request_times[agent_id] = []
        self._request_times[agent_id].append(now)

    async def execute_ssh_command(
        self,
        agent_id: str,
        target_ip: str,
        username: str,
        password: str,
        command: str,
        timeout: int = 30
    ) -> dict:
        """Execute SSH command through agent.
        
        Args:
            agent_id: Edge agent ID to use
            target_ip: Target device IP
            username: SSH username
            password: SSH password
            command: Command to execute
            timeout: Command timeout
            
        Returns:
            Command result dictionary
        """
        # Check rate limiting
        if not self._check_rate_limit(agent_id):
            raise ValueError(f"Rate limit exceeded for agent {agent_id}")
        
        # Use semaphore to limit concurrent requests
        async with self._request_semaphore:
            # Record this request
            self._record_request(agent_id)
            
            # Get edge agent connection
            async with self._lock:
                agent = self._agents.get(agent_id)
            
            if not agent:
                raise ValueError(f"Edge agent not found: {agent_id}")
            
            if agent.status != "online":
                raise ValueError(f"Edge agent not available: {agent.status}")
            
            # Create request
            request_id = str(uuid.uuid4())
            request = {
                "type": "ssh_command",
                "request_id": request_id,
                "target_ip": target_ip,
                "username": username,
                "password": password,
                "command": command,
                "timeout": timeout
            }
            
            # Create future for response
            future = asyncio.Future()
            self._pending_requests[request_id] = future
            
            try:
                # Send request
                if agent.websocket.client_state == WebSocketState.CONNECTED:
                    await agent.websocket.send_json(request)
                else:
                    raise ConnectionError("WebSocket not connected")
                
                # Wait for response with longer timeout to account for network delays
                result = await asyncio.wait_for(future, timeout=timeout + 15)
                
                return result
                
            except asyncio.TimeoutError:
                self._pending_requests.pop(request_id, None)
                raise TimeoutError("Command execution timeout")
            except Exception:
                self._pending_requests.pop(request_id, None)
                raise
    
    async def send_ping(self, agent_id: str):
        """Send ping to agent.
        
        Args:
            agent_id: Edge agent ID
        """
        async with self._lock:
            agent = self._agents.get(agent_id)
        
        if agent and agent.websocket.client_state == WebSocketState.CONNECTED:
            ping = {
                "type": "ping",
                "timestamp": datetime.utcnow().isoformat()
            }
            await agent.websocket.send_json(ping)
    
    def get_agents(self) -> list:
        """Get list of connected edge agents.
        
        Returns:
            List of agent information dictionaries
        """
        return [agent.to_dict() for agent in self._agents.values()]
    
    def get_agent(self, agent_id: str) -> Optional[dict]:
        """Get agent information.
        
        Args:
            agent_id: Edge agent ID
            
        Returns:
            Edge agent information or None
        """
        agent = self._agents.get(agent_id)
        return agent.to_dict() if agent else None
    
    async def disconnect_agent(self, agent_id: str):
        """Disconnect an edge agent.
        
        Args:
            agent_id: Edge agent ID
        """
        async with self._lock:
            agent = self._agents.get(agent_id)
        
        if agent:
            await agent.websocket.close()


    def has_connected_agents(self) -> bool:
        """Check if any edge agents are connected.
        
        Returns:
            True if any agents are connected, False otherwise
        """
        return len(self._agents) > 0
    
    def get_recent_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent ZTP events.
        
        Args:
            limit: Maximum number of events to return
            
        Returns:
            List of recent events
        """
        events = sorted(self._events, key=lambda x: x["timestamp"], reverse=True)
        return [{
            "timestamp": event["timestamp"].isoformat(),
            "agent_id": event["agent_id"],
            "event_type": event["event_type"],
            "data": event["data"]
        } for event in events[:limit]]
    
    def get_device_inventory(self) -> Dict[str, Any]:
        """Get combined device inventory from all agents.
        
        Returns:
            Combined device inventory
        """
        combined_inventory = {}
        
        for agent in self._agents.values():
            for mac, device in agent.device_inventory.items():
                device_info = device.copy()
                device_info["agent_id"] = agent.agent_id
                device_info["agent_hostname"] = agent.hostname
                combined_inventory[mac] = device_info
        
        return combined_inventory
    
    def get_ztp_summary(self) -> Dict[str, Any]:
        """Get ZTP status summary across all agents.
        
        Returns:
            ZTP summary statistics
        """
        total_devices = 0
        total_configured = 0
        agents_running_ztp = 0
        
        for agent in self._agents.values():
            ztp_status = agent.ztp_status
            if ztp_status.get("running", False):
                agents_running_ztp += 1
            
            total_devices += ztp_status.get("devices_discovered", 0)
            total_configured += ztp_status.get("switches_configured", 0) + ztp_status.get("aps_configured", 0)
        
        return {
            "total_agents": len(self._agents),
            "agents_running_ztp": agents_running_ztp,
            "total_devices_discovered": total_devices,
            "total_devices_configured": total_configured,
            "recent_events_count": len(self._events)
        }
    
    async def send_ztp_config(self, agent_id: str, config: Dict[str, Any]):
        """Send ZTP configuration to an edge agent.
        
        Args:
            agent_id: Edge agent ID
            config: ZTP configuration to send
        """
        agent = self._agents.get(agent_id)
        if not agent:
            raise Exception(f"Edge agent {agent_id} not connected")
        
        config_message = {
            "type": "ztp_config",
            "config": config
        }
        
        try:
            await agent.websocket.send_json(config_message)
            self.logger.info(f"ZTP configuration sent to edge agent {agent_id}")
        except Exception as e:
            self.logger.error(f"Failed to send ZTP config to agent {agent_id}: {e}")
            raise

    async def send_agent_command(self, agent_id: str, command: Dict[str, Any]):
        """Send a command to a specific edge agent.
        
        Args:
            agent_id: Edge agent ID
            command: Command to send
        """
        agent = self._agents.get(agent_id)
        if not agent:
            raise Exception(f"Edge agent {agent_id} not connected")
        
        try:
            await agent.websocket.send_json(command)
            self.logger.info(f"Command sent to edge agent {agent_id}: {command.get('type', 'unknown')}")
        except Exception as e:
            self.logger.error(f"Failed to send command to agent {agent_id}: {e}")
            raise

    # Agent-specific methods for new authentication system
    
    def get_agent_config(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific edge agent.
        
        Args:
            agent_id: Edge agent ID
            
        Returns:
            Agent configuration or None if not found
        """
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        
        # Return stored configuration for this agent
        # For now, we'll return a default config until we implement config storage
        return getattr(agent, 'config', None)
    
    async def send_agent_config(self, agent_id: str, config: Dict[str, Any]):
        """Send configuration to a specific edge agent.
        
        Args:
            agent_id: Edge agent ID
            config: Configuration to send
        """
        agent = self._agents.get(agent_id)
        if not agent:
            raise Exception(f"Edge agent {agent_id} not connected")
        
        # Store configuration for this agent
        agent.config = config
        
        config_message = {
            "type": "update_config",
            "config": config
        }
        
        try:
            await agent.websocket.send_json(config_message)
            self.logger.info(f"Configuration sent to edge agent {agent_id}")
        except Exception as e:
            self.logger.error(f"Failed to send config to agent {agent_id}: {e}")
            raise

    def get_agent_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get status for a specific edge agent.
        
        Args:
            agent_id: Edge agent ID
            
        Returns:
            Agent status or None if not found
        """
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        
        return {
            "agent_id": agent.agent_id,
            "hostname": agent.hostname,
            "network_subnet": agent.network_subnet,
            "status": agent.status,
            "connected_at": agent.connected_at.isoformat(),
            "last_seen": agent.last_seen.isoformat(),
            "ztp_status": agent.ztp_status
        }

    def get_agent_device_inventory(self, agent_id: str) -> List[Dict[str, Any]]:
        """Get device inventory for a specific edge agent.
        
        Args:
            agent_id: Edge agent ID
            
        Returns:
            List of devices for this agent
        """
        agent = self._agents.get(agent_id)
        if not agent:
            return []
        
        devices = []
        for mac, device in agent.device_inventory.items():
            device_info = device.copy()
            device_info["agent_id"] = agent.agent_id
            device_info["agent_hostname"] = agent.hostname
            devices.append(device_info)
        
        return devices

    def get_agent_logs(self, agent_id: str) -> List[Dict[str, Any]]:
        """Get logs for a specific edge agent.
        
        Args:
            agent_id: Edge agent ID
            
        Returns:
            List of log entries for this agent
        """
        agent = self._agents.get(agent_id)
        if not agent:
            return []
        
        # Return stored logs for this agent
        # For now, we'll return empty until we implement log storage
        return getattr(agent, 'logs', [])

    def get_agent_events(self, agent_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get events for a specific edge agent.
        
        Args:
            agent_id: Edge agent ID
            limit: Maximum number of events to return
            
        Returns:
            List of events for this agent
        """
        # Filter events for this specific agent
        agent_events = [event for event in self._events if event.get("agent_id") == agent_id]
        events = sorted(agent_events, key=lambda x: x["timestamp"], reverse=True)
        
        return [{
            "timestamp": event["timestamp"].isoformat(),
            "agent_id": event["agent_id"],
            "event_type": event["event_type"],
            "data": event["data"],
            "message": event.get("message", "")
        } for event in events[:limit]]

    async def send_ztp_command(self, agent_id: str, command: str, config: Optional[Dict[str, Any]] = None):
        """Send ZTP command (start/stop) to a specific edge agent.
        
        Args:
            agent_id: Edge agent ID
            command: Command to send ('start' or 'stop')
            config: Optional configuration for start command
        """
        agent = self._agents.get(agent_id)
        if not agent:
            raise Exception(f"Edge agent {agent_id} not connected")
        
        message = {
            "type": f"ztp_{command}"
        }
        
        if command == "start" and config:
            message["config"] = config
        
        try:
            await agent.websocket.send_json(message)
            self.logger.info(f"ZTP {command} command sent to edge agent {agent_id}")
        except Exception as e:
            self.logger.error(f"Failed to send ZTP {command} to agent {agent_id}: {e}")
            raise


# Global instance
edge_agent_manager = ZTPEdgeAgentManager()