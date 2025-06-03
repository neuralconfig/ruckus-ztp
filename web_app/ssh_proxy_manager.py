"""SSH Proxy management for backend server."""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Dict, Optional, Set, Any
from dataclasses import dataclass, field

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState


@dataclass
class ProxyConnection:
    """Represents a connected SSH proxy."""
    proxy_id: str
    websocket: WebSocket
    hostname: str
    network_subnet: str
    capabilities: list
    version: str
    connected_at: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)
    status: str = "online"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "proxy_id": self.proxy_id,
            "hostname": self.hostname,
            "network_subnet": self.network_subnet,
            "capabilities": self.capabilities,
            "version": self.version,
            "connected_at": self.connected_at.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "status": self.status
        }


class SSHProxyManager:
    """Manages SSH proxy connections and command routing."""
    
    def __init__(self):
        """Initialize proxy manager."""
        self.logger = logging.getLogger(__name__)
        self._proxies: Dict[str, ProxyConnection] = {}
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()
    
    async def handle_proxy_connection(self, websocket: WebSocket, auth_token: str):
        """Handle incoming proxy WebSocket connection.
        
        Args:
            websocket: WebSocket connection
            auth_token: Authentication token from proxy
        """
        proxy_connection = None
        
        try:
            # Validate auth token (simplified for now)
            if not self._validate_token(auth_token):
                await websocket.close(code=1008, reason="Invalid authentication")
                return
            
            # Accept connection
            await websocket.accept()
            self.logger.info("New proxy connection accepted")
            
            # Wait for registration
            registration = await self._wait_for_registration(websocket)
            if not registration:
                await websocket.close(code=1002, reason="Registration timeout")
                return
            
            # Create proxy connection
            proxy_connection = ProxyConnection(
                proxy_id=registration["pi_id"],
                websocket=websocket,
                hostname=registration["network_info"]["hostname"],
                network_subnet=registration["network_info"]["subnet"],
                capabilities=registration["capabilities"],
                version=registration["version"]
            )
            
            # Register proxy
            async with self._lock:
                self._proxies[proxy_connection.proxy_id] = proxy_connection
            
            self.logger.info(f"Proxy registered: {proxy_connection.proxy_id} ({proxy_connection.hostname})")
            
            # Handle messages
            await self._handle_proxy_messages(proxy_connection)
            
        except WebSocketDisconnect:
            self.logger.info("Proxy disconnected")
        except Exception as e:
            self.logger.error(f"Proxy connection error: {e}")
        finally:
            # Clean up
            if proxy_connection:
                async with self._lock:
                    self._proxies.pop(proxy_connection.proxy_id, None)
                self.logger.info(f"Proxy unregistered: {proxy_connection.proxy_id}")
    
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
        """Wait for proxy registration message.
        
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
                return message
            else:
                self.logger.warning(f"Expected registration, got: {message.get('type')}")
                return None
                
        except asyncio.TimeoutError:
            self.logger.warning("Registration timeout")
            return None
    
    async def _handle_proxy_messages(self, proxy_connection: ProxyConnection):
        """Handle messages from proxy.
        
        Args:
            proxy_connection: Proxy connection
        """
        while True:
            try:
                message = await proxy_connection.websocket.receive_json()
                msg_type = message.get("type")
                
                # Update last seen
                proxy_connection.last_seen = datetime.utcnow()
                
                if msg_type == "command_result":
                    await self._handle_command_result(message)
                elif msg_type == "status":
                    await self._handle_status_update(proxy_connection, message)
                elif msg_type == "pong":
                    self.logger.debug(f"Pong from {proxy_connection.proxy_id}")
                else:
                    self.logger.warning(f"Unknown message type from proxy: {msg_type}")
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                self.logger.error(f"Error handling proxy message: {e}")
                break
    
    async def _handle_command_result(self, message: dict):
        """Handle command result from proxy.
        
        Args:
            message: Command result message
        """
        request_id = message.get("request_id")
        if request_id and request_id in self._pending_requests:
            future = self._pending_requests.pop(request_id)
            if not future.done():
                future.set_result(message)
    
    async def _handle_status_update(self, proxy_connection: ProxyConnection, message: dict):
        """Handle status update from proxy.
        
        Args:
            proxy_connection: Proxy connection
            message: Status message
        """
        proxy_connection.status = message.get("status", "online")
        self.logger.debug(f"Status update from {proxy_connection.proxy_id}: {proxy_connection.status}")
    
    async def execute_ssh_command(
        self,
        proxy_id: str,
        target_ip: str,
        username: str,
        password: str,
        command: str,
        timeout: int = 30
    ) -> dict:
        """Execute SSH command through proxy.
        
        Args:
            proxy_id: Proxy ID to use
            target_ip: Target device IP
            username: SSH username
            password: SSH password
            command: Command to execute
            timeout: Command timeout
            
        Returns:
            Command result dictionary
        """
        # Get proxy connection
        async with self._lock:
            proxy = self._proxies.get(proxy_id)
        
        if not proxy:
            raise ValueError(f"Proxy not found: {proxy_id}")
        
        if proxy.status != "online":
            raise ValueError(f"Proxy not available: {proxy.status}")
        
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
            if proxy.websocket.client_state == WebSocketState.CONNECTED:
                await proxy.websocket.send_json(request)
            else:
                raise ConnectionError("WebSocket not connected")
            
            # Wait for response
            result = await asyncio.wait_for(future, timeout=timeout + 5)
            
            return result
            
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            raise TimeoutError("Command execution timeout")
        except Exception:
            self._pending_requests.pop(request_id, None)
            raise
    
    async def send_ping(self, proxy_id: str):
        """Send ping to proxy.
        
        Args:
            proxy_id: Proxy ID
        """
        async with self._lock:
            proxy = self._proxies.get(proxy_id)
        
        if proxy and proxy.websocket.client_state == WebSocketState.CONNECTED:
            ping = {
                "type": "ping",
                "timestamp": datetime.utcnow().isoformat()
            }
            await proxy.websocket.send_json(ping)
    
    def get_proxies(self) -> list:
        """Get list of connected proxies.
        
        Returns:
            List of proxy information dictionaries
        """
        return [proxy.to_dict() for proxy in self._proxies.values()]
    
    def get_proxy(self, proxy_id: str) -> Optional[dict]:
        """Get proxy information.
        
        Args:
            proxy_id: Proxy ID
            
        Returns:
            Proxy information or None
        """
        proxy = self._proxies.get(proxy_id)
        return proxy.to_dict() if proxy else None
    
    async def disconnect_proxy(self, proxy_id: str):
        """Disconnect a proxy.
        
        Args:
            proxy_id: Proxy ID
        """
        async with self._lock:
            proxy = self._proxies.get(proxy_id)
        
        if proxy:
            await proxy.websocket.close()


# Global instance
proxy_manager = SSHProxyManager()