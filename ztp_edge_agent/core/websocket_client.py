"""WebSocket client for backend communication."""

import asyncio
import json
import logging
from typing import Optional, Callable, Dict, Any
import websockets
from websockets.client import WebSocketClientProtocol


class WebSocketClient:
    """WebSocket client for connecting to backend server."""
    
    def __init__(
        self,
        server_url: str,
        auth_token: str,
        on_message: Callable[[Dict[str, Any]], asyncio.Future],
        on_connect: Optional[Callable[[], asyncio.Future]] = None,
        on_disconnect: Optional[Callable[[], asyncio.Future]] = None,
        reconnect_interval: int = 30
    ):
        """Initialize WebSocket client.
        
        Args:
            server_url: WebSocket server URL
            auth_token: Authentication token
            on_message: Callback for incoming messages
            on_connect: Callback for connection established
            on_disconnect: Callback for disconnection
            reconnect_interval: Seconds between reconnection attempts
        """
        self.server_url = server_url
        self.auth_token = auth_token
        self.on_message = on_message
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.reconnect_interval = reconnect_interval
        
        self.logger = logging.getLogger(__name__)
        self._websocket: Optional[WebSocketClientProtocol] = None
        self._running = False
        self._send_queue: asyncio.Queue = asyncio.Queue()
    
    async def start(self):
        """Start WebSocket client with automatic reconnection."""
        self._running = True
        
        while self._running:
            try:
                await self._connect()
            except Exception as e:
                self.logger.error(f"WebSocket connection error: {e}")
                if self.on_disconnect:
                    await self.on_disconnect()
                
                if self._running:
                    self.logger.info(f"Reconnecting in {self.reconnect_interval} seconds...")
                    await asyncio.sleep(self.reconnect_interval)
    
    async def _connect(self):
        """Establish WebSocket connection."""
        headers = {
            "Authorization": f"Bearer {self.auth_token}"
        }
        
        self.logger.info(f"Connecting to {self.server_url}...")
        
        async with websockets.connect(
            self.server_url,
            extra_headers=headers
        ) as websocket:
            self._websocket = websocket
            self.logger.info("WebSocket connection established")
            
            if self.on_connect:
                await self.on_connect()
            
            # Start send and receive tasks
            receive_task = asyncio.create_task(self._receive_loop())
            send_task = asyncio.create_task(self._send_loop())
            
            try:
                await asyncio.gather(receive_task, send_task)
            except websockets.exceptions.ConnectionClosed:
                self.logger.warning("WebSocket connection closed")
            finally:
                self._websocket = None
    
    async def _receive_loop(self):
        """Receive messages from WebSocket."""
        while self._running and self._websocket:
            try:
                message = await self._websocket.recv()
                
                # Parse JSON message
                try:
                    data = json.loads(message)
                    self.logger.debug(f"Received message: {data.get('type', 'unknown')}")
                    
                    # Call message handler
                    if self.on_message:
                        await self.on_message(data)
                        
                except json.JSONDecodeError as e:
                    self.logger.error(f"Failed to parse message: {e}")
                    
            except websockets.exceptions.ConnectionClosed:
                break
            except Exception as e:
                self.logger.error(f"Error receiving message: {e}")
    
    async def _send_loop(self):
        """Send messages from queue."""
        while self._running and self._websocket:
            try:
                # Get message from queue with timeout
                message = await asyncio.wait_for(
                    self._send_queue.get(),
                    timeout=1.0
                )
                
                # Send message
                if self._websocket:
                    await self._websocket.send(json.dumps(message))
                    self.logger.debug(f"Sent message: {message.get('type', 'unknown')}")
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error(f"Error sending message: {e}")
    
    async def send_message(self, message: Dict[str, Any]):
        """Send message to WebSocket server.
        
        Args:
            message: Message dictionary to send
        """
        await self._send_queue.put(message)
    
    async def stop(self):
        """Stop WebSocket client."""
        self.logger.info("Stopping WebSocket client...")
        self._running = False
        
        if self._websocket:
            await self._websocket.close()
            self._websocket = None