"""Unit tests for WebSocket client."""

import unittest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import asyncio
import json
from ztp_edge_agent.core.websocket_client import WebSocketClient


class TestWebSocketClient(unittest.TestCase):
    """Test WebSocket client."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.on_message = AsyncMock()
        self.on_connect = AsyncMock()
        self.on_disconnect = AsyncMock()
        
        self.client = WebSocketClient(
            server_url="wss://test.com",
            auth_token="test-token",
            on_message=self.on_message,
            on_connect=self.on_connect,
            on_disconnect=self.on_disconnect,
            reconnect_interval=1
        )
    
    @patch('ztp_edge_agent.core.websocket_client.websockets.connect')
    def test_connect_success(self, mock_connect):
        """Test successful WebSocket connection."""
        async def run_test():
            # Mock websocket
            mock_ws = AsyncMock()
            mock_ws.recv = AsyncMock(side_effect=Exception("Test complete"))
            mock_ws.send = AsyncMock()
            
            # Mock context manager
            mock_connect.return_value.__aenter__.return_value = mock_ws
            
            # Connect
            try:
                await self.client._connect()
            except Exception as e:
                if "Test complete" not in str(e):
                    raise
            
            # Verify
            mock_connect.assert_called_once()
            call_args = mock_connect.call_args
            self.assertEqual(call_args[0][0], "wss://test.com")
            self.assertIn("Authorization", call_args[1]["extra_headers"])
            self.assertEqual(
                call_args[1]["extra_headers"]["Authorization"],
                "Bearer test-token"
            )
            
            # Verify callbacks
            self.on_connect.assert_called_once()
        
        asyncio.run(run_test())
    
    def test_send_message(self):
        """Test sending message."""
        async def run_test():
            message = {"type": "test", "data": "value"}
            
            # Send message (should be queued)
            await self.client.send_message(message)
            
            # Verify message was queued
            queued_msg = await asyncio.wait_for(
                self.client._send_queue.get(),
                timeout=1.0
            )
            self.assertEqual(queued_msg, message)
        
        asyncio.run(run_test())
    
    @patch('ztp_edge_agent.core.websocket_client.websockets.connect')
    def test_receive_loop(self, mock_connect):
        """Test message receive loop."""
        async def run_test():
            # Mock websocket
            mock_ws = AsyncMock()
            messages = [
                '{"type": "ping", "data": "test1"}',
                '{"type": "command", "data": "test2"}'
            ]
            mock_ws.recv = AsyncMock(side_effect=messages + [Exception("Done")])
            
            # Set up client with mock websocket
            self.client._websocket = mock_ws
            self.client._running = True
            
            # Run receive loop
            try:
                await self.client._receive_loop()
            except:
                pass
            
            # Verify callbacks
            self.assertEqual(self.on_message.call_count, 2)
            self.on_message.assert_any_call({"type": "ping", "data": "test1"})
            self.on_message.assert_any_call({"type": "command", "data": "test2"})
        
        asyncio.run(run_test())
    
    @patch('ztp_edge_agent.core.websocket_client.websockets.connect')
    def test_send_loop(self, mock_connect):
        """Test message send loop."""
        async def run_test():
            # Mock websocket
            mock_ws = AsyncMock()
            self.client._websocket = mock_ws
            self.client._running = True
            
            # Queue messages
            messages = [
                {"type": "register", "id": "test"},
                {"type": "status", "status": "online"}
            ]
            for msg in messages:
                await self.client._send_queue.put(msg)
            
            # Stop after sending
            async def stop_after_send():
                await asyncio.sleep(0.1)
                self.client._running = False
            
            # Run send loop and stopper concurrently
            await asyncio.gather(
                self.client._send_loop(),
                stop_after_send(),
                return_exceptions=True
            )
            
            # Verify messages sent
            self.assertEqual(mock_ws.send.call_count, 2)
            mock_ws.send.assert_any_call(json.dumps(messages[0]))
            mock_ws.send.assert_any_call(json.dumps(messages[1]))
        
        asyncio.run(run_test())
    
    def test_stop(self):
        """Test stopping client."""
        async def run_test():
            # Mock websocket
            mock_ws = AsyncMock()
            self.client._websocket = mock_ws
            self.client._running = True
            
            # Stop client
            await self.client.stop()
            
            # Verify
            self.assertFalse(self.client._running)
            mock_ws.close.assert_called_once()
            self.assertIsNone(self.client._websocket)
        
        asyncio.run(run_test())


if __name__ == '__main__':
    unittest.main()