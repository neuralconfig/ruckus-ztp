#!/usr/bin/env python3
"""
RUCKUS ZTP Edge Agent - Runs ZTP process locally
"""
import argparse
import asyncio
import configparser
import json
import logging
import os
import socket
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import paramiko
import websockets

# Import ZTP manager
from ztp_manager import ZTPManager, EventReporter


def setup_logging(level="INFO", log_file=None):
    """Setup logging configuration."""
    level_obj = getattr(logging, level.upper(), logging.INFO)
    
    # Configure logging
    logging_config = {
        'level': level_obj,
        'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        'datefmt': '%Y-%m-%d %H:%M:%S'
    }
    
    # Setup handlers
    handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level_obj)
    handlers.append(console_handler)
    
    # File handler if specified
    if log_file:
        try:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(level_obj)
            handlers.append(file_handler)
        except Exception as e:
            print(f"Warning: Could not create log file {log_file}: {e}")
    
    # Configure root logger (Python 3.6 compatible)
    root_logger = logging.getLogger()
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Set level and add our handlers
    root_logger.setLevel(level_obj)
    for handler in handlers:
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
    
    # Reduce noise from other libraries
    logging.getLogger('paramiko').setLevel(logging.WARNING)
    logging.getLogger('websockets').setLevel(logging.WARNING)


def load_config(config_path=None):
    """Load configuration from file."""
    if config_path and os.path.exists(config_path):
        config_file = config_path
    else:
        # Try multiple possible locations
        possible_configs = [
            "/etc/ruckus-ztp-edge-agent/ztp_config.ini",
            "/etc/ruckus-ztp-edge-agent/config.ini",
            "config.ini"
        ]
        
        config_file = None
        for path in possible_configs:
            if os.path.exists(path):
                config_file = path
                break
        
        if not config_file:
            raise FileNotFoundError(f"Configuration file not found in any of: {possible_configs}")
    
    if not os.path.exists(config_file):
        raise FileNotFoundError(f"Configuration file not found: {config_file}")
    
    config = configparser.ConfigParser()
    config.read(config_file)
    
    return config


class SSHHandler:
    """Handler for SSH command execution."""
    
    def __init__(self, command_timeout=60):
        self.command_timeout = command_timeout
        self.logger = logging.getLogger(__name__)
        self._executor = ThreadPoolExecutor(max_workers=1)
    
    async def execute_command(self, host, username, password, command, timeout=None):
        """Execute SSH command on remote host."""
        timeout = timeout or self.command_timeout
        start_time = time.time()
        
        try:
            # Run SSH command in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self._executor,
                self._execute_ssh_sync,
                host, username, password, command, timeout
            )
            
            execution_time = int((time.time() - start_time) * 1000)
            
            return {
                "output": result,
                "execution_time_ms": execution_time
            }
            
        except Exception as e:
            self.logger.error(f"SSH command execution failed: {e}")
            raise
    
    def _execute_ssh_sync(self, host, username, password, command, timeout):
        """Execute SSH command synchronously."""
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            self.logger.debug(f"Connecting to {host}...")
            ssh.connect(
                hostname=host,
                username=username,
                password=password,
                timeout=10,
                look_for_keys=False,
                allow_agent=False
            )
            
            self.logger.debug(f"Executing command: {command}")
            stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
            
            output = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')
            
            if error:
                self.logger.warning(f"Command stderr: {error}")
            
            return output
            
        finally:
            ssh.close()


class ZTPEdgeAgent:
    """Main ZTP Edge Agent application."""
    
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Extract configuration
        self.agent_id = config.get('agent', 'agent_id')
        self.agent_password = config.get('agent', 'agent_password', fallback='')
        self.auth_token = config.get('agent', 'auth_token')
        self.server_url = config.get('agent', 'web_app_url', fallback=config.get('backend', 'server_url'))
        self.reconnect_interval = config.getint('backend', 'reconnect_interval', fallback=30)
        self.command_timeout = config.getint('agent', 'command_timeout', fallback=60)
        
        # Build WebSocket URL
        self.ws_url = self._build_websocket_url()
        
        # Network info
        self.hostname = config.get('network', 'hostname', fallback=socket.gethostname())
        self.subnet = config.get('network', 'subnet', fallback='192.168.1.0/24')
        
        # SSH handler
        self.ssh_handler = SSHHandler(self.command_timeout)
        
        # ZTP manager with event reporter
        self.event_reporter = EventReporter(agent_id=self.agent_id)
        self.ztp_manager = ZTPManager(event_reporter=self.event_reporter)
        
        self._running = False
    
    def _build_websocket_url(self):
        """Build WebSocket URL."""
        if self.server_url.startswith('https://'):
            ws_url = self.server_url.replace('https://', 'wss://')
        elif self.server_url.startswith('http://'):
            ws_url = self.server_url.replace('http://', 'ws://')
        else:
            ws_url = f"wss://{self.server_url}"
        
        ws_url += f"/ws/edge-agent/{self.agent_id}"
        self.logger.debug(f"Built WebSocket URL: {ws_url}")
        return ws_url
    
    async def start(self):
        """Start the ZTP Edge Agent."""
        self.logger.info(f"Starting ZTP Edge Agent with ID: {self.agent_id}")
        self.logger.info(f"Backend server: {self.server_url}")
        self.logger.info(f"WebSocket URL: {self.ws_url}")
        self.logger.info(f"Network info - Hostname: {self.hostname}, Subnet: {self.subnet}")
        self.logger.info(f"Timeouts - Command: {self.command_timeout}s, Reconnect: {self.reconnect_interval}s")
        
        self._running = True
        connection_attempts = 0
        
        while self._running:
            try:
                connection_attempts += 1
                self.logger.info(f"Connection attempt #{connection_attempts}")
                await self._connect()
            except Exception as e:
                self.logger.error(f"Connection attempt #{connection_attempts} failed: {e}")
                if self._running:
                    self.logger.info(f"Waiting {self.reconnect_interval} seconds before next attempt...")
                    await asyncio.sleep(self.reconnect_interval)
    
    async def _connect(self):
        """Connect to WebSocket server."""
        headers = {'Authorization': f'Bearer {self.auth_token[:10]}...'}  # Log partial token for security
        self.logger.debug(f"Connecting with headers: {headers}")
        
        try:
            self.logger.debug("Initiating WebSocket connection...")
            # Add connection timeout and ping settings
            # Build headers for connection
            headers = {'Authorization': f'Bearer {self.auth_token}'}
            
            # Use different connection method based on websockets version
            import websockets
            ws_version = tuple(map(int, websockets.__version__.split('.')[:2]))
            
            if ws_version >= (10, 0):
                # New API (websockets 10.0+)
                async with websockets.connect(
                    self.ws_url,
                    additional_headers=headers,
                    ping_interval=30,
                    ping_timeout=10,
                    close_timeout=10
                ) as websocket:
                    self.logger.info("✅ WebSocket connection established successfully")
                    self.logger.debug(f"WebSocket state: {websocket.state}")
                    
                    # Send registration
                    self.logger.debug("Sending registration to backend...")
                    await self._register(websocket)
                    
                    # Set websocket for event reporting
                    self.event_reporter.set_websocket(websocket)
                    
                    # Start ZTP process
                    await self.ztp_manager.start()
                    
                    # Start heartbeat task
                    self.logger.debug("Starting heartbeat task...")
                    heartbeat_task = asyncio.create_task(self._heartbeat_loop(websocket))
                    
                    try:
                        # Handle messages
                        self.logger.debug("Starting message loop...")
                        await self._message_loop(websocket)
                    except Exception as e:
                        self.logger.error(f"Message loop error: {e}")
                    finally:
                        self.logger.debug("Stopping ZTP process and heartbeat task...")
                        # Stop ZTP process
                        await self.ztp_manager.stop()
                        
                        # Cancel heartbeat task
                        heartbeat_task.cancel()
                        try:
                            await heartbeat_task
                        except asyncio.CancelledError:
                            self.logger.debug("Heartbeat task cancelled")
            else:
                # Old API (websockets < 10.0)
                async with websockets.connect(
                    self.ws_url,
                    extra_headers=headers,
                    ping_interval=30,
                    ping_timeout=10,
                    close_timeout=10
                ) as websocket:
                    self.logger.info("✅ WebSocket connection established successfully")
                    self.logger.debug(f"WebSocket state: {websocket.state}")
                    
                    # Send registration
                    self.logger.debug("Sending registration to backend...")
                    await self._register(websocket)
                    
                    # Set websocket for event reporting
                    self.event_reporter.set_websocket(websocket)
                    
                    # Start ZTP process
                    await self.ztp_manager.start()
                    
                    # Start heartbeat task
                    self.logger.debug("Starting heartbeat task...")
                    heartbeat_task = asyncio.create_task(self._heartbeat_loop(websocket))
                    
                    try:
                        # Handle messages
                        self.logger.debug("Starting message loop...")
                        await self._message_loop(websocket)
                    except Exception as e:
                        self.logger.error(f"Message loop error: {e}")
                    finally:
                        self.logger.debug("Stopping ZTP process and heartbeat task...")
                        # Stop ZTP process
                        await self.ztp_manager.stop()
                        
                        # Cancel heartbeat task
                        heartbeat_task.cancel()
                        try:
                            await heartbeat_task
                        except asyncio.CancelledError:
                            self.logger.debug("Heartbeat task cancelled")
                
        except websockets.exceptions.ConnectionClosed as e:
            self.logger.warning(f"WebSocket connection closed: code={e.code}, reason={e.reason}")
        except websockets.exceptions.InvalidStatusCode as e:
            self.logger.error(f"WebSocket connection failed with HTTP status {e.status_code}")
            if e.status_code == 429:
                self.logger.error("❌ Rate limit exceeded! Backend is rejecting connections.")
            elif e.status_code == 401:
                self.logger.error("❌ Authentication failed! Check your proxy token.")
            elif e.status_code == 404:
                self.logger.error("❌ WebSocket endpoint not found! Check backend URL.")
            raise
        except ConnectionRefusedError as e:
            self.logger.error(f"❌ Connection refused: {e}")
            self.logger.error("Backend server may be down or unreachable")
            raise
        except Exception as e:
            self.logger.error(f"❌ Unexpected WebSocket error: {type(e).__name__}: {e}")
            raise
    
    async def _register(self, websocket):
        """Register with backend."""
        registration = {
            "type": "register",
            "pi_id": self.agent_id,
            "agent_password": self.agent_password,
            "capabilities": ["ssh", "ztp"],
            "network_info": {
                "hostname": self.hostname,
                "subnet": self.subnet
            },
            "version": "2.0.0"
        }
        
        self.logger.debug(f"Sending registration: {json.dumps(registration, indent=2)}")
        await websocket.send(json.dumps(registration))
        self.logger.info("✅ Registration sent to backend successfully")
    
    async def _heartbeat_loop(self, websocket):
        """Send periodic status updates to keep connection alive."""
        heartbeat_count = 0
        while self._running:
            try:
                await asyncio.sleep(60)  # Send status every minute
                
                # Check websocket state based on version
                ws_version = tuple(map(int, websockets.__version__.split('.')[:2]))
                if ws_version >= (10, 0):
                    if websocket.state != 1:  # 1 = OPEN
                        self.logger.warning("WebSocket not open, stopping heartbeat")
                        break
                else:
                    if websocket.closed:
                        self.logger.warning("WebSocket closed, stopping heartbeat")
                        break
                    
                heartbeat_count += 1
                # Get ZTP status
                ztp_status = await self.ztp_manager.get_status()
                
                status = {
                    "type": "status",
                    "pi_id": self.agent_id,
                    "status": "online",
                    "timestamp": int(time.time() * 1000),
                    "ztp_status": ztp_status
                }
                
                self.logger.debug(f"Sending heartbeat #{heartbeat_count}: {json.dumps(status)}")
                await asyncio.wait_for(websocket.send(json.dumps(status)), timeout=5)
                self.logger.debug(f"💓 Heartbeat #{heartbeat_count} sent successfully")
                
            except asyncio.TimeoutError:
                self.logger.warning(f"❌ Heartbeat #{heartbeat_count} send timeout")
                break
            except websockets.exceptions.ConnectionClosed:
                self.logger.debug(f"WebSocket closed during heartbeat #{heartbeat_count}")
                break
            except Exception as e:
                self.logger.error(f"❌ Heartbeat #{heartbeat_count} error: {e}")
                break
    
    async def _message_loop(self, websocket):
        """Handle incoming messages."""
        message_count = 0
        try:
            self.logger.info("📨 Starting message loop...")
            # Check websocket state based on version
            ws_version = tuple(map(int, websockets.__version__.split('.')[:2]))
            while self._running:
                if ws_version >= (10, 0):
                    # New API uses state property
                    if websocket.state != 1:  # 1 = OPEN
                        self.logger.debug("WebSocket is not open, exiting message loop")
                        break
                else:
                    # Old API uses closed property
                    if websocket.closed:
                        self.logger.debug("WebSocket is closed, exiting message loop")
                        break
                try:
                    # Wait for message with timeout
                    self.logger.debug("Waiting for message...")
                    message = await asyncio.wait_for(websocket.recv(), timeout=120)
                    message_count += 1
                    
                    self.logger.debug(f"📨 Received message #{message_count}: {message[:100]}{'...' if len(message) > 100 else ''}")
                    
                    try:
                        data = json.loads(message)
                        msg_type = data.get('type')
                        
                        self.logger.info(f"📨 Processing message #{message_count} type: {msg_type}")
                        
                        if msg_type == 'ssh_command':
                            # Handle SSH command in background to not block message loop
                            self.logger.info(f"🔧 Creating SSH command task for message #{message_count}")
                            asyncio.create_task(self._handle_ssh_command(websocket, data))
                        elif msg_type == 'ping':
                            self.logger.debug(f"🏓 Handling ping for message #{message_count}")
                            await self._handle_ping(websocket, data)
                        elif msg_type == 'get_status':
                            self.logger.debug(f"📊 Handling status request for message #{message_count}")
                            await self._handle_status_request(websocket, data)
                        elif msg_type == 'get_inventory':
                            self.logger.debug(f"📋 Handling inventory request for message #{message_count}")
                            await self._handle_inventory_request(websocket, data)
                        elif msg_type == 'update_config':
                            self.logger.info(f"⚙️ Handling configuration update for message #{message_count}")
                            await self._handle_config_update(websocket, data)
                        elif msg_type == 'ztp_start':
                            self.logger.info(f"🚀 Handling ZTP start with configuration for message #{message_count}")
                            await self._handle_ztp_start(websocket, data)
                        else:
                            self.logger.warning(f"❓ Unknown message type '{msg_type}' in message #{message_count}")
                            
                    except json.JSONDecodeError as e:
                        self.logger.error(f"❌ Invalid JSON in message #{message_count}: {e}")
                        self.logger.debug(f"Raw message: {message}")
                    except Exception as e:
                        self.logger.error(f"❌ Error handling message #{message_count}: {e}")
                        
                except asyncio.TimeoutError:
                    # No message received within timeout - this is normal
                    self.logger.debug("⏰ No message received within 120s timeout (normal)")
                    continue
                except websockets.exceptions.ConnectionClosed:
                    self.logger.info(f"🔌 WebSocket connection closed during message receive (processed {message_count} messages)")
                    break
                    
        except Exception as e:
            self.logger.error(f"❌ Message loop error after {message_count} messages: {e}")
            raise
    
    async def _handle_ssh_command(self, websocket, data):
        """Handle SSH command request."""
        request_id = data.get('request_id')
        start_time = time.time()
        
        try:
            target_ip = data['target_ip']
            username = data['username']
            password = data['password']
            command = data['command']
            timeout = data.get('timeout', self.command_timeout)
            
            self.logger.info(f"🔧 SSH Command Request {request_id[:8]}:")
            self.logger.info(f"   Target: {target_ip}")
            self.logger.info(f"   User: {username}")
            self.logger.info(f"   Command: {command}")
            self.logger.info(f"   Timeout: {timeout}s")
            
            # Add overall timeout for the entire operation
            self.logger.debug(f"Executing SSH command with {timeout + 10}s total timeout...")
            result = await asyncio.wait_for(
                self.ssh_handler.execute_command(
                    host=target_ip,
                    username=username,
                    password=password,
                    command=command,
                    timeout=timeout
                ),
                timeout=timeout + 10  # Add 10 seconds buffer
            )
            
            execution_time = int((time.time() - start_time) * 1000)
            self.logger.info(f"✅ SSH Command {request_id[:8]} completed in {execution_time}ms")
            self.logger.debug(f"Output length: {len(result['output'])} characters")
            
            response = {
                "type": "command_result",
                "request_id": request_id,
                "success": True,
                "output": result["output"],
                "error": None,
                "execution_time_ms": result["execution_time_ms"]
            }
            
        except asyncio.TimeoutError:
            execution_time = int((time.time() - start_time) * 1000)
            self.logger.error(f"❌ SSH Command {request_id[:8]} timed out after {execution_time}ms (limit: {timeout}s)")
            response = {
                "type": "command_result",
                "request_id": request_id,
                "success": False,
                "output": None,
                "error": f"Command timed out after {timeout} seconds",
                "execution_time_ms": timeout * 1000
            }
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            self.logger.error(f"❌ SSH Command {request_id[:8]} failed after {execution_time}ms: {e}")
            response = {
                "type": "command_result",
                "request_id": request_id,
                "success": False,
                "output": None,
                "error": str(e),
                "execution_time_ms": 0
            }
        
        try:
            # Send response with timeout
            self.logger.debug(f"Sending response for {request_id[:8]}...")
            await asyncio.wait_for(websocket.send(json.dumps(response)), timeout=10)
            self.logger.debug(f"✅ Response sent for {request_id[:8]}")
        except asyncio.TimeoutError:
            self.logger.error(f"❌ Failed to send response for {request_id[:8]} - websocket send timeout")
        except websockets.exceptions.ConnectionClosed:
            self.logger.warning(f"🔌 WebSocket closed while sending response for {request_id[:8]}")
        except Exception as e:
            self.logger.error(f"❌ Error sending response for {request_id[:8]}: {e}")
    
    async def _handle_ping(self, websocket, data):
        """Handle ping message."""
        pong = {
            "type": "pong",
            "timestamp": data.get("timestamp"),
            "pi_id": self.agent_id
        }
        await websocket.send(json.dumps(pong))
    
    async def _handle_status_request(self, websocket, data):
        """Handle status request."""
        try:
            ztp_status = await self.ztp_manager.get_status()
            response = {
                "type": "status_response",
                "request_id": data.get("request_id"),
                "status": ztp_status
            }
            await websocket.send(json.dumps(response))
        except Exception as e:
            self.logger.error(f"Error handling status request: {e}")
    
    async def _handle_inventory_request(self, websocket, data):
        """Handle inventory request."""
        try:
            inventory = await self.ztp_manager.get_inventory()
            response = {
                "type": "inventory_response",
                "request_id": data.get("request_id"),
                "inventory": inventory
            }
            await websocket.send(json.dumps(response))
        except Exception as e:
            self.logger.error(f"Error handling inventory request: {e}")
    
    async def _handle_config_update(self, websocket, data):
        """Handle configuration update from web app."""
        try:
            config = data.get("config", {})
            self.logger.info(f"⚙️ Received configuration update:")
            self.logger.info(f"   Credentials: {len(config.get('credentials', []))} sets")
            self.logger.info(f"   Seed switches: {len(config.get('seed_switches', []))}")
            self.logger.info(f"   Management VLAN: {config.get('management_vlan', 'N/A')}")
            
            # Update ZTP manager configuration
            await self.ztp_manager.update_configuration(config)
            
            # Send acknowledgment
            response = {
                "type": "config_update_response",
                "request_id": data.get("request_id"),
                "success": True,
                "message": "Configuration updated successfully"
            }
            await websocket.send(json.dumps(response))
            self.logger.info("✅ Configuration update completed successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Error handling configuration update: {e}")
            # Send error response
            try:
                response = {
                    "type": "config_update_response",
                    "request_id": data.get("request_id"),
                    "success": False,
                    "message": f"Configuration update failed: {str(e)}"
                }
                await websocket.send(json.dumps(response))
            except Exception as send_error:
                self.logger.error(f"❌ Failed to send error response: {send_error}")
    
    async def _handle_ztp_start(self, websocket, data):
        """Handle ZTP start with configuration from web app."""
        try:
            config = data.get("config", {})
            self.logger.info(f"🚀 Received ZTP start command with configuration:")
            self.logger.info(f"   Credentials: {len(config.get('credentials', []))} sets")
            self.logger.info(f"   Seed switches: {len(config.get('seed_switches', []))}")
            self.logger.info(f"   Management VLAN: {config.get('management_vlan', 'N/A')}")
            
            # Update ZTP manager configuration and start
            await self.ztp_manager.update_configuration(config)
            
            # If ZTP is not running, start it
            if not self.ztp_manager.running:
                await self.ztp_manager.start()
            
            # Send acknowledgment
            response = {
                "type": "ztp_start_response",
                "request_id": data.get("request_id"),
                "success": True,
                "message": "ZTP started successfully with new configuration"
            }
            await websocket.send(json.dumps(response))
            self.logger.info("✅ ZTP start completed successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Error handling ZTP start: {e}")
            # Send error response
            try:
                response = {
                    "type": "ztp_start_response", 
                    "request_id": data.get("request_id"),
                    "success": False,
                    "message": f"ZTP start failed: {str(e)}"
                }
                await websocket.send(json.dumps(response))
            except Exception as send_error:
                self.logger.error(f"❌ Failed to send error response: {send_error}")
    
    def stop(self):
        """Stop the edge agent."""
        self._running = False


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='RUCKUS ZTP Edge Agent')
    parser.add_argument('--config', '-c', help='Path to configuration file', 
                        default=None)
    args = parser.parse_args()
    
    try:
        # Load configuration
        if args.config:
            print(f"Loading configuration from: {args.config}")
        else:
            print("Loading configuration from default location...")
        config = load_config(args.config)
        
        # Setup logging
        log_level = config.get('logging', 'level', fallback='INFO')
        log_file = config.get('logging', 'log_file', fallback=None)
        setup_logging(log_level, log_file)
        
        logger = logging.getLogger(__name__)
        logger.info("🚀 Starting RUCKUS ZTP Edge Agent")
        logger.info(f"📋 Configuration loaded successfully:")
        if args.config:
            logger.info(f"   Config file: {args.config}")
        logger.info(f"   Agent ID: {config.get('agent', 'agent_id', fallback='N/A')}")
        logger.info(f"   Backend: {config.get('backend', 'server_url', fallback='N/A')}")
        logger.info(f"   Log level: {log_level}")
        logger.info(f"   Log file: {log_file or 'Console only'}")
        
        # Create and start edge agent
        logger.info("🔧 Creating ZTP Edge Agent instance...")
        agent = ZTPEdgeAgent(config)
        
        try:
            await agent.start()
        except KeyboardInterrupt:
            logger.info("🛑 Shutdown requested by user (Ctrl+C)")
        finally:
            logger.info("🔄 Stopping edge agent...")
            agent.stop()
            logger.info("✅ Edge agent stopped")
            
    except FileNotFoundError as e:
        print(f"❌ Configuration error: {e}")
        if args.config:
            print(f"Please ensure {args.config} exists and is readable")
        else:
            print("Please ensure /etc/ruckus-ztp-edge-agent/config.ini exists and is readable")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # Python 3.6 compatibility - asyncio.run() was added in Python 3.7
    try:
        # Try Python 3.7+ method
        asyncio.run(main())
    except AttributeError:
        # Fallback for Python 3.6
        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(main())
        finally:
            loop.close()