"""Main SSH proxy application."""

import asyncio
import json
import logging
import signal
import socket
import uuid
from typing import Optional, Dict, Any

from ssh_proxy.core.config import ProxyConfig
from ssh_proxy.core.websocket_client import WebSocketClient
from ssh_proxy.handlers.ssh_handler import SSHHandler
from ssh_proxy.utils.logger import setup_logging


class SSHProxy:
    """Main SSH proxy application."""
    
    def __init__(self, config: ProxyConfig):
        """Initialize SSH proxy."""
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Generate proxy ID if not provided
        if not self.config.proxy_id:
            self.config.proxy_id = str(uuid.uuid4())
        
        # Get network information
        self._get_network_info()
        
        # Initialize components
        self.websocket_client = WebSocketClient(
            server_url=config.server_url,
            auth_token=config.auth_token,
            on_message=self._handle_message,
            on_connect=self._on_connect,
            on_disconnect=self._on_disconnect,
            reconnect_interval=config.reconnect_interval
        )
        
        self.ssh_handler = SSHHandler(
            command_timeout=config.command_timeout
        )
        
        self._running = False
        self._tasks = set()
    
    def _get_network_info(self):
        """Get local network information."""
        try:
            # Get hostname
            self.config.hostname = socket.gethostname()
            
            # Get local IP and subnet (simplified for now)
            # In production, would use more sophisticated network detection
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            
            # Assume /24 subnet for simplicity
            ip_parts = local_ip.split('.')
            self.config.network_subnet = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.0/24"
            
        except Exception as e:
            self.logger.warning(f"Failed to get network info: {e}")
    
    async def _on_connect(self):
        """Handle WebSocket connection established."""
        self.logger.info("Connected to backend server")
        await self._register()
    
    async def _on_disconnect(self):
        """Handle WebSocket disconnection."""
        self.logger.warning("Disconnected from backend server")
    
    async def _register(self):
        """Register proxy with backend."""
        registration = {
            "type": "register",
            "pi_id": self.config.proxy_id,
            "capabilities": ["ssh_proxy"],
            "network_info": {
                "subnet": self.config.network_subnet,
                "hostname": self.config.hostname
            },
            "version": "1.0.0"
        }
        
        await self.websocket_client.send_message(registration)
        self.logger.info(f"Registered proxy with ID: {self.config.proxy_id}")
    
    async def _handle_message(self, message: Dict[str, Any]):
        """Handle incoming WebSocket message."""
        msg_type = message.get("type")
        
        if msg_type == "ssh_command":
            await self._handle_ssh_command(message)
        elif msg_type == "ping":
            await self._handle_ping(message)
        else:
            self.logger.warning(f"Unknown message type: {msg_type}")
    
    async def _handle_ssh_command(self, message: Dict[str, Any]):
        """Handle SSH command request."""
        request_id = message.get("request_id")
        
        try:
            # Extract command parameters
            target_ip = message["target_ip"]
            username = message["username"]
            password = message["password"]
            command = message["command"]
            timeout = message.get("timeout", self.config.command_timeout)
            
            self.logger.info(f"Executing SSH command on {target_ip}: {command}")
            
            # Execute SSH command
            result = await self.ssh_handler.execute_command(
                host=target_ip,
                username=username,
                password=password,
                command=command,
                timeout=timeout
            )
            
            # Send success response
            response = {
                "type": "command_result",
                "request_id": request_id,
                "success": True,
                "output": result["output"],
                "error": None,
                "execution_time_ms": result["execution_time_ms"]
            }
            
        except Exception as e:
            self.logger.error(f"SSH command failed: {e}")
            # Send error response
            response = {
                "type": "command_result",
                "request_id": request_id,
                "success": False,
                "output": None,
                "error": str(e),
                "execution_time_ms": 0
            }
        
        await self.websocket_client.send_message(response)
    
    async def _handle_ping(self, message: Dict[str, Any]):
        """Handle ping message."""
        pong = {
            "type": "pong",
            "timestamp": message.get("timestamp"),
            "pi_id": self.config.proxy_id
        }
        await self.websocket_client.send_message(pong)
    
    async def _send_status_update(self):
        """Send periodic status updates."""
        while self._running:
            try:
                status = {
                    "type": "status",
                    "pi_id": self.config.proxy_id,
                    "status": "online",
                    "last_seen": asyncio.get_event_loop().time()
                }
                await self.websocket_client.send_message(status)
                await asyncio.sleep(60)  # Send status every minute
            except Exception as e:
                self.logger.error(f"Failed to send status update: {e}")
                await asyncio.sleep(60)
    
    async def start(self):
        """Start the SSH proxy."""
        self.logger.info("Starting SSH proxy...")
        self._running = True
        
        # Start WebSocket client
        websocket_task = asyncio.create_task(self.websocket_client.start())
        self._tasks.add(websocket_task)
        
        # Start status updates
        status_task = asyncio.create_task(self._send_status_update())
        self._tasks.add(status_task)
        
        # Wait for shutdown
        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            pass
    
    async def stop(self):
        """Stop the SSH proxy."""
        self.logger.info("Stopping SSH proxy...")
        self._running = False
        
        # Stop WebSocket client
        await self.websocket_client.stop()
        
        # Cancel all tasks
        for task in self._tasks:
            task.cancel()
        
        # Wait for tasks to complete
        await asyncio.gather(*self._tasks, return_exceptions=True)
        
        self.logger.info("SSH proxy stopped")


async def main(config: ProxyConfig):
    """Main entry point."""
    # Setup logging
    setup_logging(config.log_level, config.log_file)
    
    # Create and start proxy
    proxy = SSHProxy(config)
    
    # Setup signal handlers
    loop = asyncio.get_event_loop()
    
    def signal_handler():
        asyncio.create_task(proxy.stop())
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)
    
    try:
        await proxy.start()
    except KeyboardInterrupt:
        pass
    finally:
        await proxy.stop()