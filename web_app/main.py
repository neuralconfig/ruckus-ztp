"""
Web application for RUCKUS ZTP Agent.
Provides a web interface for configuring and monitoring the ZTP process.
"""
import os
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, File, UploadFile, BackgroundTasks, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, validator
import uvicorn

# Import ZTP components
from ztp_agent.ztp.process import ZTPProcess
from ztp_agent.ztp.config import load_config

# Set up logging
logger = logging.getLogger(__name__)

# Pydantic models for API
class CredentialPair(BaseModel):
    username: str
    password: str

class SeedSwitch(BaseModel):
    ip: str
    credentials_id: Optional[int] = None

class ZTPConfig(BaseModel):
    credentials: List[CredentialPair]
    preferred_password: str
    seed_switches: List[SeedSwitch]
    base_config_name: str
    openrouter_api_key: Optional[str] = ""
    model: str = "anthropic/claude-3-5-haiku"
    management_vlan: int = 10
    wireless_vlans: List[int] = [20, 30, 40]
    ip_pool: str = "192.168.10.0/24"
    gateway: str = "192.168.10.1"
    dns_server: str = "192.168.10.2"
    poll_interval: int = 60

class ZTPStatus(BaseModel):
    running: bool
    starting: bool = False
    switches_discovered: int
    switches_configured: int
    aps_discovered: int
    last_poll: Optional[str] = None
    errors: List[str] = []

class ChatMessage(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

class DeviceInfo(BaseModel):
    ip: str
    mac: Optional[str] = None
    hostname: Optional[str] = None
    model: Optional[str] = None
    serial: Optional[str] = None
    status: str  # discovered, configured, error
    device_type: str  # switch, ap
    neighbors: Dict[str, Any] = {}
    tasks_completed: List[str] = []
    tasks_failed: List[str] = []
    is_seed: bool = False
    ap_ports: List[str] = []  # For switches: list of ports with configured APs
    connected_switch: Optional[str] = None  # For APs: switch they're connected to
    connected_port: Optional[str] = None    # For APs: port they're connected to
    ssh_active: bool = False  # Whether currently being accessed via SSH

# FastAPI app
app = FastAPI(title="RUCKUS ZTP Agent Web Interface", version="1.0.0")

# Global state
ztp_process: Optional[ZTPProcess] = None
app_config: Dict[str, Any] = {}
base_configs: Dict[str, str] = {}
status_log: List[Dict[str, Any]] = []
ztp_starting: bool = False  # Track if ZTP is being started

# Static files and templates
web_app_dir = Path(__file__).parent

# Ensure static and template directories exist
(web_app_dir / "static").mkdir(exist_ok=True)
(web_app_dir / "templates").mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=web_app_dir / "static"), name="static")
templates = Jinja2Templates(directory=str(web_app_dir / "templates"))

def load_base_configs():
    """Load available base configurations."""
    global base_configs
    config_dir = Path(__file__).parent.parent / "config"
    
    # Load default base configuration
    default_config_path = config_dir / "base_configuration.txt"
    if default_config_path.exists():
        with open(default_config_path, 'r') as f:
            base_configs["Default RUCKUS Configuration"] = f.read()
    
    # Look for other .txt files in config directory
    for config_file in config_dir.glob("*.txt"):
        if config_file.name != "base_configuration.txt":
            config_name = config_file.stem.replace("_", " ").title()
            with open(config_file, 'r') as f:
                base_configs[config_name] = f.read()

def log_status(message: str, level: str = "info"):
    """Add a status message to the log."""
    global status_log
    status_log.append({
        "timestamp": datetime.now().isoformat(),
        "level": level,
        "message": message
    })
    # Keep only last 200 messages for more history
    if len(status_log) > 200:
        status_log = status_log[-200:]
    
    # Also log to console for debugging
    if level == "error":
        logger.error(message)
    elif level == "warning":
        logger.warning(message)
    else:
        logger.info(message)

class WebLogHandler(logging.Handler):
    """Custom logging handler to forward logs to web interface."""
    
    def emit(self, record):
        try:
            # Filter for relevant loggers
            if record.name.startswith('ztp_agent'):
                message = self.format(record)
                level = "error" if record.levelno >= logging.ERROR else "warning" if record.levelno >= logging.WARNING else "info"
                log_status(f"[{record.name}] {record.getMessage()}", level)
        except Exception:
            pass  # Ignore logging errors

@app.on_event("startup")
async def startup_event():
    """Initialize the application."""
    # Setup basic logging for web app
    import logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True  # Override any existing logging configuration
    )
    
    # Add custom handler to capture ZTP logs
    web_handler = WebLogHandler()
    web_handler.setLevel(logging.DEBUG)
    
    # Add to relevant loggers
    ztp_logger = logging.getLogger('ztp_agent')
    ztp_logger.addHandler(web_handler)
    ztp_logger.setLevel(logging.DEBUG)
    
    load_base_configs()
    log_status("Web application started")

# Routes
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Serve the main page."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/config")
async def get_config() -> Dict[str, Any]:
    """Get current configuration."""
    global app_config
    
    # Provide defaults if config is empty
    if not app_config:
        app_config = {
            "credentials": [{"username": "super", "password": "sp-admin"}],
            "preferred_password": "",
            "seed_switches": [],
            "base_config_name": "Default RUCKUS Configuration",
            "openrouter_api_key": "",
            "model": "anthropic/claude-3-5-haiku",
            "management_vlan": 10,
            "wireless_vlans": [20, 30, 40],
            "ip_pool": "192.168.10.0/24",
            "gateway": "192.168.10.1",
            "dns_server": "192.168.10.2",
            "poll_interval": 60
        }
    
    return app_config

@app.post("/api/config")
async def update_config(config: ZTPConfig) -> Dict[str, str]:
    """Update configuration."""
    global app_config
    app_config = config.dict()
    log_status("Configuration updated")
    return {"message": "Configuration updated successfully"}

@app.get("/api/base-configs")
async def get_base_configs() -> Dict[str, str]:
    """Get available base configurations."""
    return base_configs

@app.post("/api/base-configs")
async def upload_base_config(name: str, file: UploadFile = File(...)) -> Dict[str, str]:
    """Upload a new base configuration."""
    global base_configs
    
    if not file.filename.endswith('.txt'):
        raise HTTPException(status_code=400, detail="File must be a .txt file")
    
    content = await file.read()
    base_configs[name] = content.decode('utf-8')
    log_status(f"Base configuration '{name}' uploaded")
    
    return {"message": f"Base configuration '{name}' uploaded successfully"}

@app.get("/api/status")
async def get_status() -> ZTPStatus:
    """Get ZTP process status."""
    global ztp_process, ztp_starting
    
    if not ztp_process:
        return ZTPStatus(
            running=False,
            starting=ztp_starting,
            switches_discovered=0,
            switches_configured=0,
            aps_discovered=0
        )
    
    # Count devices
    switches_discovered = len(ztp_process.inventory.get('switches', {}))
    aps_discovered = len(ztp_process.inventory.get('aps', {}))
    
    # Count configured switches
    switches_configured = sum(
        1 for switch in ztp_process.inventory.get('switches', {}).values()
        if switch.get('configured', False)
    )
    
    return ZTPStatus(
        running=ztp_process.running,
        starting=ztp_starting and not ztp_process.running,  # Only starting if not yet running
        switches_discovered=switches_discovered,
        switches_configured=switches_configured,
        aps_discovered=aps_discovered,
        last_poll=datetime.now().isoformat() if ztp_process.running else None
    )

@app.get("/api/devices")
async def get_devices() -> List[DeviceInfo]:
    """Get discovered devices."""
    global ztp_process
    devices = []
    
    if not ztp_process:
        return devices
    
    # Get seed switch IPs for marking
    seed_ips = set()
    if app_config:
        for switch_config in app_config.get('seed_switches', []):
            seed_ips.add(switch_config['ip'])
    
    # Add switches
    for mac, switch_data in ztp_process.inventory.get('switches', {}).items():
        # Build task status
        tasks_completed = []
        tasks_failed = []
        ap_ports = []
        
        if switch_data.get('base_config_applied'):
            tasks_completed.append("Base configuration applied")
        if switch_data.get('configured'):
            tasks_completed.append("Basic switch configuration")
            
        # Count AP ports configured on this switch - look for APs connected to this switch
        for ap_mac, ap_data in ztp_process.inventory.get('aps', {}).items():
            if ap_data.get('switch_ip') == switch_data.get('ip'):
                port = ap_data.get('switch_port', 'Unknown')
                if port != 'Unknown':
                    ap_ports.append(port)
        
        # Determine status with more granular states
        status = "discovered"
        if switch_data.get('configuring'):
            status = "configuring"
        elif switch_data.get('configured'):
            status = "configured"
        
        devices.append(DeviceInfo(
            ip=switch_data.get('ip', 'Unknown'),
            mac=mac,
            hostname=switch_data.get('hostname'),
            model=switch_data.get('model'),
            serial=switch_data.get('serial'),
            status=status,
            device_type="switch",
            neighbors=switch_data.get('neighbors', {}),
            tasks_completed=tasks_completed,
            tasks_failed=tasks_failed,
            is_seed=switch_data.get('is_seed', False) or switch_data.get('ip') in seed_ips,
            ap_ports=ap_ports,
            ssh_active=switch_data.get('ssh_active', False)
        ))
    
    # Add APs
    for mac, ap_data in ztp_process.inventory.get('aps', {}).items():
        tasks_completed = []
        if ap_data.get('status') == 'Configured':
            tasks_completed.append("Port configured for AP traffic")
        
        # Determine AP status with more granular states
        ap_status = "discovered"
        if ap_data.get('configuring'):
            ap_status = "configuring"
        elif ap_data.get('status') == 'Configured':
            ap_status = "configured"
            
        devices.append(DeviceInfo(
            ip=ap_data.get('ip', 'Unknown'),
            mac=mac,
            hostname=ap_data.get('hostname') or ap_data.get('system_name'),
            model=ap_data.get('model') or ap_data.get('system_name'),
            serial=ap_data.get('serial', mac),
            status=ap_status,
            device_type="ap",
            neighbors={},
            tasks_completed=tasks_completed,
            tasks_failed=[],
            is_seed=False,
            ap_ports=[],
            connected_switch=ap_data.get('switch_ip'),
            connected_port=ap_data.get('switch_port'),
            ssh_active=ap_data.get('ssh_active', False)
        ))
    
    return devices

@app.post("/api/ztp/start")
async def start_ztp(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """Start the ZTP process."""
    global ztp_process, app_config, ztp_starting
    
    if not app_config:
        raise HTTPException(status_code=400, detail="Configuration not set")
    
    if ztp_process and ztp_process.running:
        return {"message": "ZTP process is already running", "errors": []}
    
    if ztp_starting:
        return {"message": "ZTP process is starting", "errors": []}
    
    # Set starting flag
    ztp_starting = True
    
    try:
        # Convert app config to ZTP config format
        config = {
            'ztp': {'poll_interval': app_config.get('poll_interval', 60)},
            'network': {
                'base_config': base_configs.get(app_config.get('base_config_name', '')),
                'management_vlan': app_config.get('management_vlan', 10),
                'wireless_vlans': app_config.get('wireless_vlans', [20, 30, 40]),
                'ip_pool': app_config.get('ip_pool', '192.168.10.0/24'),
                'gateway': app_config.get('gateway', '192.168.10.1'),
            },
            'agent': {
                'openrouter_api_key': app_config.get('openrouter_api_key', ''),
                'model': app_config.get('model', 'anthropic/claude-3-5-haiku'),
            },
            'credentials': app_config.get('credentials', [])  # Pass credentials to ZTP process
        }
        
        # Create ZTP process
        ztp_process = ZTPProcess(config)
        
        # Track connection errors
        connection_errors = []
        successful_switches = 0
        
        # Add seed switches with automatic credential cycling
        for switch_config in app_config.get('seed_switches', []):
            ip = switch_config['ip']
            preferred_password = app_config.get('preferred_password', '')
            
            # Build list of credentials to try (default first, then user-added)
            credentials_to_try = [{"username": "super", "password": "sp-admin"}]  # Default first
            user_credentials = app_config.get('credentials', [])
            for cred in user_credentials:
                # Skip if it's the same as default
                if not (cred['username'] == 'super' and cred['password'] == 'sp-admin'):
                    credentials_to_try.append(cred)
            
            # Try each credential until one works
            switch_added = False
            attempted_creds = []
            
            for i, cred in enumerate(credentials_to_try):
                username = cred['username']
                password = cred['password']
                attempted_creds.append(f"{username}/{'*' * len(password)}")
                
                log_status(f"Trying to connect to seed switch {ip} with credentials {username}/{'*' * len(password)}")
                
                # Suppress errors for all attempts except the last one
                suppress_errors = i < len(credentials_to_try) - 1
                
                if ztp_process.add_switch(ip, username, password, preferred_password, suppress_errors=suppress_errors):
                    successful_switches += 1
                    log_status(f"Successfully connected to seed switch {ip} with credentials {username}/{'*' * len(password)}")
                    switch_added = True
                    break
            
            if not switch_added:
                error_msg = f"Failed to connect to seed switch {ip} with any available credentials (tried: {', '.join(attempted_creds)}). Check network connectivity and credentials."
                connection_errors.append(error_msg)
                log_status(error_msg, "error")
        
        # Check if we have any successful connections
        if successful_switches == 0:
            error_msg = "No seed switches could be connected. Please check credentials and network connectivity."
            log_status(error_msg, "error")
            return {
                "message": error_msg,
                "errors": connection_errors,
                "success": False
            }
        
        # Start the process if we have at least one successful connection
        background_tasks.add_task(run_ztp_process)
        
        # Don't clear starting flag here - let run_ztp_process clear it after actually starting
        
        if connection_errors:
            message = f"ZTP process started with {successful_switches} seed switch(es), but {len(connection_errors)} failed to connect"
            log_status(message, "warning")
            return {
                "message": message,
                "errors": connection_errors,
                "success": True
            }
        else:
            message = f"ZTP process started successfully with {successful_switches} seed switch(es)"
            log_status(message)
            return {
                "message": message,
                "errors": [],
                "success": True
            }
        
    except Exception as e:
        # Clear starting flag on error
        ztp_starting = False
        error_msg = f"Failed to start ZTP process: {str(e)}"
        log_status(error_msg, "error")
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/api/ztp/stop")
async def stop_ztp() -> Dict[str, str]:
    """Stop the ZTP process."""
    global ztp_process
    
    if not ztp_process or not ztp_process.running:
        return {"message": "ZTP process is not running"}
    
    ztp_process.stop()
    log_status("ZTP process stopped")
    
    return {"message": "ZTP process stopped successfully"}

@app.get("/api/logs")
async def get_logs() -> List[Dict[str, Any]]:
    """Get status logs."""
    return status_log

@app.post("/api/chat")
async def chat_with_ai(message: ChatMessage) -> ChatResponse:
    """Send message to AI agent and get response."""
    global ztp_process, app_config
    
    if not ztp_process:
        raise HTTPException(status_code=400, detail="ZTP process not initialized. Please start the ZTP process first.")
    
    if not app_config:
        raise HTTPException(status_code=400, detail="Configuration not set. Please configure the application first.")
    
    # Check if OpenRouter API key is configured
    openrouter_api_key = app_config.get('openrouter_api_key', '')
    if not openrouter_api_key:
        raise HTTPException(status_code=400, detail="OpenRouter API key not configured. Please add your API key in the Agent Configuration section.")
    
    try:
        # Import the LangChain chat interface here to avoid circular imports
        from ztp_agent.agent.langchain_chat_interface import LangChainChatInterface as ChatInterface
        
        # Get model from config
        model = app_config.get('model', 'anthropic/claude-3-5-haiku')
        
        # Get switches from ZTP process inventory
        switches = ztp_process.inventory.get('switches', {})
        
        # Create chat interface with proper parameters
        chat_interface = ChatInterface(
            openrouter_api_key=openrouter_api_key,
            model=model,
            switches=switches,
            ztp_process=ztp_process
        )
        
        # Get response from AI
        response = await asyncio.get_event_loop().run_in_executor(
            None, chat_interface.process_message, message.message
        )
        
        log_status(f"AI Agent - User: {message.message[:50]}{'...' if len(message.message) > 50 else ''}")
        log_status(f"AI Agent - Response: {response[:50]}{'...' if len(response) > 50 else ''}")
        
        return ChatResponse(response=response)
        
    except Exception as e:
        error_msg = f"AI agent error: {str(e)}"
        log_status(error_msg, "error")
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/api/chat/stream")
async def chat_with_ai_stream(message: ChatMessage):
    """Send message to AI agent and get streaming response."""
    global ztp_process, app_config
    
    if not ztp_process:
        raise HTTPException(status_code=400, detail="ZTP process not initialized")
    
    if not app_config:
        raise HTTPException(status_code=400, detail="Configuration not set")
    
    openrouter_api_key = app_config.get('openrouter_api_key', '')
    if not openrouter_api_key:
        raise HTTPException(status_code=400, detail="OpenRouter API key not configured")
    
    async def generate_stream():
        """Generate Server-Sent Events stream."""
        try:
            # Send multiple initial chunks to prime browser buffer
            for i in range(3):
                yield f": initializing stream {i}\n\n"
                await asyncio.sleep(0.001)  # Force async yield
            
            # Send a large initial chunk
            yield ": " + "x" * 8192 + "\n\n"
            await asyncio.sleep(0.001)
            
            # Import here to avoid circular imports
            from ztp_agent.agent.langchain_chat_interface import LangChainChatInterface as ChatInterface
            import queue
            import threading
            import asyncio
            
            # Create a queue to communicate between threads
            message_queue = queue.Queue()
            final_response = {"response": "", "error": None}
            
            def stream_callback(step_type: str, content: str):
                """Callback function to receive streaming updates."""
                logger.debug(f"Stream callback received: {step_type} - {content[:100]}{'...' if len(content) > 100 else ''}")
                message_queue.put({"type": step_type, "content": content})
                # Add a small delay to ensure message is processed
                import time
                time.sleep(0.01)
            
            def run_agent():
                """Run the agent in a separate thread."""
                try:
                    # Get model and switches
                    model = app_config.get('model', 'anthropic/claude-3-5-haiku')
                    switches = ztp_process.inventory.get('switches', {})
                    
                    # Create chat interface
                    chat_interface = ChatInterface(
                        openrouter_api_key=openrouter_api_key,
                        model=model,
                        switches=switches,
                        ztp_process=ztp_process
                    )
                    
                    # Process with streaming callback
                    response = chat_interface.process_message_with_streaming(
                        message.message, stream_callback
                    )
                    
                    final_response["response"] = response
                    
                except Exception as e:
                    final_response["error"] = str(e)
                finally:
                    # Signal completion
                    message_queue.put({"type": "complete", "content": ""})
            
            # Start agent in background thread
            agent_thread = threading.Thread(target=run_agent)
            agent_thread.start()
            
            # Stream messages as they come in
            while True:
                try:
                    # Get message from queue (blocks until available)
                    msg = message_queue.get(timeout=1)
                    
                    if msg["type"] == "complete":
                        # Send final response if no error
                        if final_response["error"]:
                            logger.debug(f"Streaming: Sending error - {final_response['error']}")
                            padding = " " * 1024
                            yield f"data: {json.dumps({'type': 'error', 'content': final_response['error']})}\n\n{padding}\n\n"
                        elif final_response["response"]:
                            logger.debug(f"Streaming: Sending final response - {final_response['response'][:50]}...")
                            padding = " " * 1024
                            yield f"data: {json.dumps({'type': 'final', 'content': final_response['response']})}\n\n{padding}\n\n"
                        break
                    else:
                        # Send intermediate step
                        logger.debug(f"Streaming: Sending intermediate step - {msg['type']}: {msg['content'][:50]}...")
                        # Add padding and multiple chunks to force browser to flush buffer
                        yield f"data: {json.dumps(msg)}\n\n"
                        await asyncio.sleep(0.001)  # Force async processing
                        
                        # Send padding in separate chunk
                        padding = "x" * 2048
                        yield f": {padding}\n\n"
                        await asyncio.sleep(0.001)
                        
                except queue.Empty:
                    # Send heartbeat to keep connection alive
                    padding = " " * 1024  # 1KB of padding
                    yield f"data: {json.dumps({'type': 'heartbeat', 'content': ''})}\n\n{padding}\n\n"
                    continue
            
            # Wait for thread to finish
            agent_thread.join(timeout=5)
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control"
        }
    )

async def send_heartbeats(websocket: WebSocket):
    """Send periodic heartbeat messages to keep WebSocket alive during processing."""
    try:
        while True:
            await asyncio.sleep(2)  # Send heartbeat every 2 seconds
            if websocket.application_state == websocket.application_state.CONNECTED:
                try:
                    await websocket.send_json({"type": "heartbeat", "content": "keeping connection alive"})
                    logger.debug("Sent WebSocket heartbeat")
                except Exception as e:
                    logger.debug(f"Failed to send heartbeat: {e}")
                    break
            else:
                break
    except asyncio.CancelledError:
        logger.debug("Heartbeat task cancelled")
        raise
    except Exception as e:
        logger.error(f"Heartbeat task error: {e}")

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for real-time chat streaming."""
    await websocket.accept()
    
    try:
        # Receive the message
        data = await websocket.receive_json()
        message = data.get("message", "")
        
        if not ztp_process:
            await websocket.send_json({"type": "error", "content": "ZTP process not initialized"})
            return
        
        if not app_config:
            await websocket.send_json({"type": "error", "content": "Configuration not set"})
            return
        
        openrouter_api_key = app_config.get('openrouter_api_key', '')
        if not openrouter_api_key:
            await websocket.send_json({"type": "error", "content": "OpenRouter API key not configured"})
            return
        
        # Create chat interface
        from ztp_agent.agent.langchain_chat_interface import LangChainChatInterface as ChatInterface
        
        model = app_config.get('model', 'anthropic/claude-3-5-haiku')
        switches = ztp_process.inventory.get('switches', {})
        
        chat_interface = ChatInterface(
            openrouter_api_key=openrouter_api_key,
            model=model,
            switches=switches,
            ztp_process=ztp_process
        )
        
        # Define WebSocket callback with connection check
        async def ws_callback(step_type: str, content: str):
            """Send message immediately via WebSocket if still connected."""
            if websocket.application_state == websocket.application_state.CONNECTED:
                try:
                    # Ensure content is a string
                    if not isinstance(content, str):
                        content = str(content)
                    
                    # Log what we're sending for debugging
                    if step_type == "final":
                        logger.info(f"Sending final answer, length: {len(content)}")
                    
                    await websocket.send_json({"type": step_type, "content": content})
                except Exception as e:
                    logger.error(f"WebSocket send failed for {step_type}: {e}", exc_info=True)
        
        # Start heartbeat task to keep WebSocket alive during processing
        heartbeat_task = asyncio.create_task(send_heartbeats(websocket))
        logger.info("Started WebSocket heartbeat task")
        
        # Process message with WebSocket streaming
        try:
            response = await chat_interface.process_message_with_async_streaming(message, ws_callback)
            
            # Log the response details
            logger.info(f"Agent returned response: {response is not None}, length: {len(response) if response else 0}")
            
            # Check WebSocket state before sending
            ws_state = websocket.application_state
            logger.info(f"WebSocket state before sending final: {ws_state}")
            
            # Send the final response directly if it wasn't already sent through callback
            # Always send as "final" type to ensure proper styling
            if response:
                if websocket.application_state == websocket.application_state.CONNECTED:
                    try:
                        logger.info(f"Sending final answer directly with styling, length: {len(response)}")
                        await websocket.send_json({"type": "final", "content": response})
                        logger.info("Final answer sent successfully with proper styling")
                    except Exception as e:
                        logger.error(f"Failed to send final answer: {e}", exc_info=True)
                        # Try to send error message if still connected
                        try:
                            if websocket.application_state == websocket.application_state.CONNECTED:
                                await websocket.send_json({"type": "error", "content": "Failed to send complete response"})
                        except:
                            pass
                else:
                    logger.error(f"WebSocket not connected when trying to send final answer. State: {ws_state}")
            else:
                logger.info("Final answer was already sent through callback or no response generated")
            
            logger.info("Chat processing completed successfully")
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Chat processing error: {error_msg}", exc_info=True)
            
            # Special handling for the asyncio error
            if "cannot access local variable 'asyncio'" in error_msg:
                logger.error("Asyncio scope error detected - attempting workaround")
                # Don't send this confusing error to the user
                error_msg = "An internal error occurred while processing the response. Please try again."
            
            if websocket.application_state == websocket.application_state.CONNECTED:
                try:
                    await websocket.send_json({"type": "error", "content": error_msg})
                except:
                    pass
        finally:
            # Always cancel heartbeat task when done
            logger.debug("Cancelling heartbeat task")
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                logger.debug("Heartbeat task cancelled successfully")
                pass
            except Exception as e:
                logger.error(f"Error cancelling heartbeat task: {e}")
        
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket.application_state == websocket.application_state.CONNECTED:
            try:
                await websocket.send_json({"type": "error", "content": str(e)})
            except:
                pass
    finally:
        if websocket.application_state == websocket.application_state.CONNECTED:
            await websocket.close()

async def run_ztp_process():
    """Run the ZTP process in the background."""
    global ztp_process, ztp_starting
    import asyncio
    
    if ztp_process:
        # The ZTP process starts automatically when switches are added
        # We just need to start the background thread
        if not ztp_process.running:
            ztp_process.start()
            
        # Clear the starting flag immediately after calling start()
        ztp_starting = False
        log_status("ZTP process started successfully")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")