#!/usr/bin/env python3
import asyncio
import websockets
import json

async def test_websocket():
    """Test WebSocket connection to the web app."""
    uri = "ws://localhost:8000/ws/edge-agent/test-client"
    headers = {"Authorization": "Bearer test-token-12345"}
    
    try:
        print(f"Connecting to {uri}...")
        async with websockets.connect(uri, additional_headers=headers) as websocket:
            print("✅ Connected successfully!")
            
            # Send registration
            registration = {
                "type": "register",
                "pi_id": "test-client",
                "capabilities": ["ssh", "ztp"],
                "network_info": {
                    "hostname": "test-host",
                    "subnet": "192.168.1.0/24"
                },
                "version": "2.0.0"
            }
            
            print("Sending registration...")
            await websocket.send(json.dumps(registration))
            print("✅ Registration sent!")
            
            # Wait for response
            print("Waiting for response...")
            response = await asyncio.wait_for(websocket.recv(), timeout=5)
            print(f"📨 Received: {response}")
            
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test_websocket())