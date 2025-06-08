"""
Web application for RUCKUS ZTP Agent.
Provides a web interface for configuring and monitoring the ZTP process.
"""
import os
import json
import asyncio
import logging
import hashlib
import secrets
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, File, UploadFile, WebSocket, Header, Form, Cookie
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, RedirectResponse
from pydantic import BaseModel, validator
import uvicorn

# Import edge agent manager
from ztp_edge_agent_manager import edge_agent_manager

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
    edge_agent_enabled: bool = False
    edge_agent_id: Optional[str] = None
    edge_agent_token: Optional[str] = None
    poll_interval: int = 300

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
    base_config_applied: bool = False  # For switches: whether base configuration has been applied
    configured: bool = False  # For all devices: whether configuration is complete

# FastAPI app
app = FastAPI(title="RUCKUS ZTP Agent Web Interface", version="1.0.0")

# Global state  
app_config: Dict[str, Any] = {}
base_configs: Dict[str, str] = {}
status_log: List[Dict[str, Any]] = []

# Agent authentication
agent_passwords: Dict[str, str] = {}  # agent_uuid -> password_hash
agent_sessions: Dict[str, str] = {}   # session_id -> agent_uuid

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
    
    print(f"Loading base configs from: {config_dir}")
    
    # Load default base configuration
    default_config_path = config_dir / "base_configuration.txt"
    print(f"Looking for default config at: {default_config_path}")
    
    if default_config_path.exists():
        with open(default_config_path, 'r') as f:
            content = f.read()
            base_configs["Default RUCKUS Configuration"] = content
            print(f"Loaded default config with {len(content)} characters")
    else:
        print("Default config file not found!")
    
    # Look for other .txt files in config directory
    for config_file in config_dir.glob("*.txt"):
        if config_file.name != "base_configuration.txt":
            config_name = config_file.stem.replace("_", " ").title()
            with open(config_file, 'r') as f:
                base_configs[config_name] = f.read()
                print(f"Loaded additional config: {config_name}")
    
    print(f"Total base configs loaded: {len(base_configs)}")
    print(f"Available configs: {list(base_configs.keys())}")

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

def hash_password(password: str) -> str:
    """Hash a password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash."""
    return hash_password(password) == hashed

def create_session(agent_uuid: str) -> str:
    """Create a session for an agent and return session ID."""
    session_id = secrets.token_urlsafe(32)
    agent_sessions[session_id] = agent_uuid
    return session_id

def get_session_agent(session_id: str) -> Optional[str]:
    """Get agent UUID from session ID."""
    return agent_sessions.get(session_id)

def register_agent_password(agent_uuid: str, password: str):
    """Register agent password hash."""
    agent_passwords[agent_uuid] = hash_password(password)
    log_status(f"Agent {agent_uuid} registered with password")

def verify_agent_auth(agent_uuid: str, password: str) -> bool:
    """Verify agent authentication."""
    if agent_uuid not in agent_passwords:
        return False
    return verify_password(password, agent_passwords[agent_uuid])

def get_authenticated_agent(session: Optional[str] = None) -> Optional[str]:
    """Get authenticated agent UUID from session cookie."""
    if not session:
        return None
    return get_session_agent(session)

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

# SSH functions removed - all SSH operations now handled by edge agents

async def execute_ssh_via_edge_agent(agent_uuid: str, target_ip: str, username: str, password: str, command: str, timeout: int = 30):
    """Execute SSH command through edge agent for AI tools."""
    try:
        result = await edge_agent_manager.execute_ssh_command(
            agent_id=agent_uuid,
            target_ip=target_ip,
            username=username,
            password=password,
            command=command,
            timeout=timeout
        )
        return result.get("output", "")
    except Exception as e:
        logger.error(f"SSH command failed via edge agent: {e}")
        return f"Error: {str(e)}"

# Routes
@app.get("/", response_class=HTMLResponse)
async def agent_list(request: Request):
    """Show list of connected agents."""
    agents = edge_agent_manager.get_agents()
    return templates.TemplateResponse("agent_list.html", {
        "request": request, 
        "agents": agents
    })

@app.get("/{agent_uuid}", response_class=HTMLResponse)
async def agent_dashboard(request: Request, agent_uuid: str, session: str = Cookie(None)):
    """Show agent dashboard or login prompt."""
    # Check if agent exists
    agent = edge_agent_manager.get_agent(agent_uuid)
    if not agent:
        return templates.TemplateResponse("agent_not_found.html", {
            "request": request,
            "agent_uuid": agent_uuid
        })
    
    # Check authentication
    if session and get_session_agent(session) == agent_uuid:
        # User is authenticated for this agent
        return templates.TemplateResponse("index.html", {
            "request": request,
            "agent_uuid": agent_uuid,
            "agent": agent
        })
    else:
        # Show login prompt
        return templates.TemplateResponse("agent_login.html", {
            "request": request,
            "agent_uuid": agent_uuid,
            "agent": agent
        })

@app.post("/{agent_uuid}/auth")
async def authenticate_agent(request: Request, agent_uuid: str, password: str = Form(...)):
    """Authenticate user for agent access."""
    if verify_agent_auth(agent_uuid, password):
        session_id = create_session(agent_uuid)
        response = RedirectResponse(url=f"/{agent_uuid}", status_code=302)
        response.set_cookie(key="session", value=session_id, httponly=True)
        return response
    else:
        agent = edge_agent_manager.get_agent(agent_uuid)
        return templates.TemplateResponse("agent_login.html", {
            "request": request,
            "agent_uuid": agent_uuid,
            "agent": agent,
            "error": "Invalid password"
        })

@app.get("/api/{agent_uuid}/config")
async def get_agent_config(agent_uuid: str, session: str = Cookie(None)) -> Dict[str, Any]:
    """Get agent configuration."""
    authenticated_agent = get_authenticated_agent(session)
    if authenticated_agent != agent_uuid:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Get configuration from edge agent
    agent_config = edge_agent_manager.get_agent_config(agent_uuid)
    if not agent_config:
        # Provide defaults if config is empty
        agent_config = {
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
            "poll_interval": 300
        }
    
    return agent_config

@app.post("/api/{agent_uuid}/config")
async def update_agent_config(agent_uuid: str, config: ZTPConfig, session: str = Cookie(None)) -> Dict[str, str]:
    """Update agent configuration."""
    authenticated_agent = get_authenticated_agent(session)
    if authenticated_agent != agent_uuid:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Send configuration to edge agent
    await edge_agent_manager.send_agent_config(agent_uuid, config.dict())
    
    log_status(f"Configuration updated for agent {agent_uuid}")
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

@app.get("/api/{agent_uuid}/status")
async def get_agent_status(agent_uuid: str, session: str = Cookie(None)) -> ZTPStatus:
    """Get ZTP process status for specific edge agent."""
    authenticated_agent = get_authenticated_agent(session)
    if authenticated_agent != agent_uuid:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Get status from specific edge agent
    agent_status = edge_agent_manager.get_agent_status(agent_uuid)
    if not agent_status:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    ztp_status = agent_status.get('ztp_status', {})
    
    return ZTPStatus(
        running=ztp_status.get('running', False),
        starting=ztp_status.get('starting', False),
        switches_discovered=ztp_status.get('switches_discovered', 0),
        switches_configured=ztp_status.get('switches_configured', 0),
        aps_discovered=ztp_status.get('aps_discovered', 0),
        last_poll=ztp_status.get('last_poll')
    )

@app.get("/api/{agent_uuid}/devices")
async def get_agent_devices(agent_uuid: str, session: str = Cookie(None)) -> List[DeviceInfo]:
    """Get discovered devices from specific edge agent."""
    authenticated_agent = get_authenticated_agent(session)
    if authenticated_agent != agent_uuid:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    devices = []
    
    # Get device inventory from specific edge agent
    inventory = edge_agent_manager.get_agent_device_inventory(agent_uuid)
    
    # Get agent configuration for seed switch IPs
    agent_config = edge_agent_manager.get_agent_config(agent_uuid)
    seed_ips = set()
    if agent_config:
        for switch_config in agent_config.get('seed_switches', []):
            seed_ips.add(switch_config['ip'])
    
    # Convert edge agent inventory format to DeviceInfo format
    for device_data in inventory:
        # Determine if this is a seed device
        is_seed = device_data.get('ip_address') in seed_ips
        
        # Handle switch devices
        if device_data.get('device_type') == 'switch':
            devices.append(DeviceInfo(
                ip=device_data.get('ip_address', 'Unknown'),
                mac=device_data.get('mac_address', 'Unknown'),
                hostname=device_data.get('hostname'),
                model=device_data.get('model'),
                serial=device_data.get('serial'),
                status=device_data.get('status', 'discovered'),
                device_type='switch',
                neighbors=device_data.get('neighbors', {}),  # Full neighbor data for topology
                tasks_completed=device_data.get('tasks_completed', []),
                tasks_failed=device_data.get('tasks_failed', []),
                is_seed=is_seed,
                ap_ports=device_data.get('ap_ports', []),
                connected_switch=None,
                connected_port=None,
                ssh_active=device_data.get('ssh_active', False),
                base_config_applied=device_data.get('base_config_applied', False),  # Include for progress indicator
                configured=device_data.get('configured', False)  # Include configured field for switches
            ))
        # Handle AP devices
        elif device_data.get('device_type') == 'ap':
            devices.append(DeviceInfo(
                ip=device_data.get('ip_address', 'Unknown'),
                mac=device_data.get('mac_address', 'Unknown'),
                hostname=device_data.get('hostname'),
                model=device_data.get('model'),
                serial=device_data.get('serial', ''),
                status=device_data.get('status', 'discovered'),
                device_type='ap',
                neighbors={},  # APs don't have neighbors
                tasks_completed=device_data.get('tasks_completed', []),
                tasks_failed=device_data.get('tasks_failed', []),
                is_seed=False,  # APs are never seed devices
                ap_ports=[],
                connected_switch=device_data.get('connected_switch'),  # For topology
                connected_port=device_data.get('connected_port'),  # For topology
                ssh_active=False,
                configured=device_data.get('configured', False)  # Include configured field for APs
            ))
        # Handle unknown device types
        else:
            devices.append(DeviceInfo(
                ip=device_data.get('ip_address', 'Unknown'),
                mac=device_data.get('mac_address', 'Unknown'),
                hostname=device_data.get('hostname'),
                model=device_data.get('model'),
                serial=device_data.get('serial'),
                status=device_data.get('status', 'discovered'),
                device_type=device_data.get('device_type', 'unknown'),
                neighbors=device_data.get('neighbors', {}),
                tasks_completed=device_data.get('tasks_completed', []),
                tasks_failed=device_data.get('tasks_failed', []),
                is_seed=is_seed,
                ap_ports=device_data.get('ap_ports', []),
                connected_switch=device_data.get('connected_switch'),
                connected_port=device_data.get('connected_port'),
                ssh_active=device_data.get('ssh_active', False)
            ))
    
    return devices

@app.post("/api/{agent_uuid}/ztp/start")
async def start_agent_ztp(agent_uuid: str, session: str = Cookie(None)) -> Dict[str, Any]:
    """Start ZTP process on specific edge agent."""
    authenticated_agent = get_authenticated_agent(session)
    if authenticated_agent != agent_uuid:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Get agent configuration
    agent_config = edge_agent_manager.get_agent_config(agent_uuid)
    if not agent_config:
        raise HTTPException(status_code=400, detail="Agent configuration not set")
    
    try:
        # Send start ZTP command to edge agent
        await edge_agent_manager.send_ztp_command(agent_uuid, "start", agent_config)
        
        log_status(f"ZTP started on edge agent {agent_uuid}")
        return {
            "message": "ZTP process started on edge agent",
            "errors": [],
            "success": True
        }
        
    except Exception as e:
        error_msg = f"Failed to start ZTP on edge agent: {str(e)}"
        log_status(error_msg, "error")
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/api/{agent_uuid}/ztp/stop")
async def stop_agent_ztp(agent_uuid: str, session: str = Cookie(None)) -> Dict[str, str]:
    """Stop ZTP process on specific edge agent."""
    authenticated_agent = get_authenticated_agent(session)
    if authenticated_agent != agent_uuid:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Send stop command to edge agent
        await edge_agent_manager.send_ztp_command(agent_uuid, "stop")
        
        log_status(f"ZTP stop command sent to edge agent {agent_uuid}")
        return {"message": "ZTP process stopped on edge agent"}
        
    except Exception as e:
        error_msg = f"Failed to stop ZTP on edge agent: {str(e)}"
        log_status(error_msg, "error")
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/api/{agent_uuid}/logs")
async def get_agent_logs(agent_uuid: str, session: str = Cookie(None)) -> List[Dict[str, Any]]:
    """Get logs for specific edge agent."""
    authenticated_agent = get_authenticated_agent(session)
    if authenticated_agent != agent_uuid:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Get logs from specific edge agent
    agent_logs = edge_agent_manager.get_agent_logs(agent_uuid)
    return agent_logs or []

@app.get("/api/{agent_uuid}/events")
async def get_agent_events(agent_uuid: str, limit: int = 100, session: str = Cookie(None)):
    """Get recent ZTP events for specific edge agent."""
    authenticated_agent = get_authenticated_agent(session)
    if authenticated_agent != agent_uuid:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Get events from specific edge agent
    agent_events = edge_agent_manager.get_agent_events(agent_uuid, limit)
    return agent_events or []

@app.post("/api/{agent_uuid}/openrouter-key")
async def save_openrouter_key(agent_uuid: str, request: dict, session: str = Cookie(None)):
    """Save OpenRouter API key for specific agent."""
    authenticated_agent = get_authenticated_agent(session)
    if authenticated_agent != agent_uuid:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    api_key = request.get("api_key", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required")
    
    # Get current agent configuration
    agent_config = edge_agent_manager.get_agent_config(agent_uuid) or {}
    
    # Update with new API key
    agent_config["openrouter_api_key"] = api_key
    
    # Save configuration back to agent
    await edge_agent_manager.send_agent_config(agent_uuid, agent_config)
    
    log_status(f"OpenRouter API key updated for agent {agent_uuid}")
    return {"message": "OpenRouter API key saved successfully"}

@app.post("/api/{agent_uuid}/chat")
async def chat_with_ai(agent_uuid: str, message: ChatMessage, session: str = Cookie(None)) -> ChatResponse:
    """Send message to AI agent and get response."""
    authenticated_agent = get_authenticated_agent(session)
    if authenticated_agent != agent_uuid:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Get agent configuration to get OpenRouter API key
    agent_config = edge_agent_manager.get_agent_config(agent_uuid)
    if not agent_config:
        raise HTTPException(status_code=400, detail="Agent configuration not found")
    
    # Check if OpenRouter API key is configured
    openrouter_api_key = agent_config.get('openrouter_api_key', '')
    if not openrouter_api_key:
        raise HTTPException(status_code=400, detail="OpenRouter API key not configured. Please add your API key in the AI Agent tab.")
    
    try:
        # Import the LangChain chat interface here to avoid circular imports
        from ztp_agent.agent.langchain_chat_interface import LangChainChatInterface as ChatInterface
        
        # Get model from config
        model = agent_config.get('model', 'anthropic/claude-3-5-haiku')
        
        # Get switches from agent device inventory
        devices = edge_agent_manager.get_agent_device_inventory(agent_uuid)
        switches = {device['mac_address']: device for device in devices if device.get('device_type') == 'switch'}
        
        # Create a partial function for the SSH executor with agent UUID
        def ssh_executor_for_agent(target_ip: str, username: str, password: str, command: str, timeout: int = 30):
            return execute_ssh_via_edge_agent(agent_uuid, target_ip, username, password, command, timeout)
        
        # Create chat interface with edge agent-aware tools
        chat_interface = ChatInterface(
            openrouter_api_key=openrouter_api_key,
            model=model,
            switches=switches,
            ztp_process=None,  # Not needed for edge agent mode
            ssh_executor=ssh_executor_for_agent
        )
        
        # Get response from AI
        response = await asyncio.get_event_loop().run_in_executor(
            None, chat_interface.process_message, message.message
        )
        
        log_status(f"AI Agent ({agent_uuid}) - User: {message.message[:50]}{'...' if len(message.message) > 50 else ''}")
        log_status(f"AI Agent ({agent_uuid}) - Response: {response[:50]}{'...' if len(response) > 50 else ''}")
        
        return ChatResponse(response=response)
        
    except Exception as e:
        error_msg = f"AI agent error: {str(e)}"
        log_status(error_msg, "error")
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/api/{agent_uuid}/chat/stream")
async def chat_with_ai_stream(agent_uuid: str, message: ChatMessage, session: str = Cookie(None)):
    """Send message to AI agent and get streaming response."""
    authenticated_agent = get_authenticated_agent(session)
    if authenticated_agent != agent_uuid:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Get agent configuration to get OpenRouter API key
    agent_config = edge_agent_manager.get_agent_config(agent_uuid)
    if not agent_config:
        raise HTTPException(status_code=400, detail="Agent configuration not found")
    
    openrouter_api_key = agent_config.get('openrouter_api_key', '')
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
                    # Get model from agent config
                    model = agent_config.get('model', 'anthropic/claude-3-5-haiku')
                    
                    # Get switches from agent device inventory
                    devices = edge_agent_manager.get_agent_device_inventory(agent_uuid)
                    switches = {device['mac_address']: device for device in devices if device.get('device_type') == 'switch'}
                    
                    # Create a partial function for the SSH executor with agent UUID
                    def ssh_executor_for_agent(target_ip: str, username: str, password: str, command: str, timeout: int = 30):
                        return execute_ssh_via_edge_agent(agent_uuid, target_ip, username, password, command, timeout)
                    
                    # Create chat interface with edge agent-aware tools
                    chat_interface = ChatInterface(
                        openrouter_api_key=openrouter_api_key,
                        model=model,
                        switches=switches,
                        ztp_process=None,  # Not needed for edge agent mode
                        ssh_executor=ssh_executor_for_agent
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

@app.websocket("/ws/edge-agent/{agent_id}")
async def websocket_edge_agent(websocket: WebSocket, agent_id: str, authorization: Optional[str] = Header(None)):
    """WebSocket endpoint for edge agent connections."""
    # Extract token from Authorization header
    auth_token = ""
    if authorization and authorization.startswith("Bearer "):
        auth_token = authorization[7:]
    
    # Handle edge agent connection
    await edge_agent_manager.handle_agent_connection(websocket, auth_token)

@app.get("/api/edge-agents")
async def get_edge_agents():
    """Get list of connected edge agents."""
    return edge_agent_manager.get_agents()

@app.get("/api/ztp/status")
async def get_ztp_status():
    """Get ZTP status summary across all edge agents."""
    return edge_agent_manager.get_ztp_summary()

@app.get("/api/ztp/events")
async def get_ztp_events(limit: int = 100):
    """Get recent ZTP events."""
    return edge_agent_manager.get_recent_events(limit)

@app.get("/api/ztp/inventory")
async def get_device_inventory():
    """Get device inventory from all edge agents."""
    return edge_agent_manager.get_device_inventory()

@app.get("/api/edge-agents/{agent_id}")
async def get_edge_agent(agent_id: str):
    """Get specific edge agent information."""
    agent = edge_agent_manager.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Edge agent not found")
    return agent

@app.post("/api/edge-agents/{agent_id}/command")
async def execute_ssh_command(agent_id: str, command: dict):
    """Execute SSH command through edge agent."""
    try:
        result = await edge_agent_manager.execute_ssh_command(
            agent_id=agent_id,
            target_ip=command["target_ip"],
            username=command["username"],
            password=command["password"],
            command=command["command"],
            timeout=command.get("timeout", 30)
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/edge-agents/{agent_id}/start-ztp")
async def start_agent_ztp(agent_id: str):
    """Start ZTP process on specific edge agent."""
    try:
        agent = edge_agent_manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Edge agent not found")
        
        # Send start ZTP command to the specific agent
        await edge_agent_manager.send_agent_command(agent_id, {
            "type": "start_ztp",
            "message": "Start ZTP process"
        })
        
        log_status(f"ZTP start command sent to edge agent {agent_id}")
        return {"message": f"ZTP start command sent to agent {agent_id}"}
        
    except Exception as e:
        error_msg = f"Failed to start ZTP on agent {agent_id}: {str(e)}"
        log_status(error_msg, "error")
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/api/edge-agents/{agent_id}/stop-ztp")
async def stop_agent_ztp(agent_id: str):
    """Stop ZTP process on specific edge agent."""
    try:
        agent = edge_agent_manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Edge agent not found")
        
        # Send stop ZTP command to the specific agent
        await edge_agent_manager.send_agent_command(agent_id, {
            "type": "stop_ztp",
            "message": "Stop ZTP process"
        })
        
        log_status(f"ZTP stop command sent to edge agent {agent_id}")
        return {"message": f"ZTP stop command sent to agent {agent_id}"}
        
    except Exception as e:
        error_msg = f"Failed to stop ZTP on agent {agent_id}: {str(e)}"
        log_status(error_msg, "error")
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/api/edge-agents/{agent_id}/logs")
async def get_agent_logs(agent_id: str):
    """Get logs from specific edge agent."""
    try:
        agent = edge_agent_manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Edge agent not found")
        
        # For now, return filtered logs from the global log
        # In the future, this could request logs directly from the agent
        agent_logs = []
        for log_entry in status_log:
            if f"agent {agent_id}" in log_entry.get("message", "").lower() or \
               f"edge agent {agent_id}" in log_entry.get("message", "").lower():
                agent_logs.append(log_entry)
        
        return agent_logs[-50:]  # Return last 50 relevant log entries
        
    except Exception as e:
        error_msg = f"Failed to get logs for agent {agent_id}: {str(e)}"
        log_status(error_msg, "error")
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/api/edge-agents/{agent_id}/config")
async def send_agent_config(agent_id: str, config: dict):
    """Send configuration to specific edge agent."""
    try:
        agent = edge_agent_manager.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Edge agent not found")
        
        # Send configuration to the specific agent
        await edge_agent_manager.send_ztp_config(agent_id, config)
        
        log_status(f"Configuration sent to edge agent {agent_id}")
        return {"message": f"Configuration sent to agent {agent_id}"}
        
    except Exception as e:
        error_msg = f"Failed to send configuration to agent {agent_id}: {str(e)}"
        log_status(error_msg, "error")
        raise HTTPException(status_code=500, detail=error_msg)

@app.websocket("/ws/{agent_uuid}/chat")
async def websocket_chat(websocket: WebSocket, agent_uuid: str):
    """WebSocket endpoint for real-time chat streaming."""
    await websocket.accept()
    
    try:
        # Receive the message
        data = await websocket.receive_json()
        message = data.get("message", "")
        
        # Get agent configuration to get OpenRouter API key
        agent_config = edge_agent_manager.get_agent_config(agent_uuid)
        if not agent_config:
            await websocket.send_json({"type": "error", "content": "Agent configuration not found"})
            return
        
        openrouter_api_key = agent_config.get('openrouter_api_key', '')
        if not openrouter_api_key:
            await websocket.send_json({"type": "error", "content": "OpenRouter API key not configured"})
            return
        
        # Create chat interface
        from ztp_agent.agent.langchain_chat_interface import LangChainChatInterface as ChatInterface
        
        model = agent_config.get('model', 'anthropic/claude-3-5-haiku')
        
        # Get switches from agent device inventory
        devices = edge_agent_manager.get_agent_device_inventory(agent_uuid)
        switches = {device['mac_address']: device for device in devices if device.get('device_type') == 'switch'}
        
        # Create a partial function for the SSH executor with agent UUID
        def ssh_executor_for_agent(target_ip: str, username: str, password: str, command: str, timeout: int = 30):
            return execute_ssh_via_edge_agent(agent_uuid, target_ip, username, password, command, timeout)
        
        chat_interface = ChatInterface(
            openrouter_api_key=openrouter_api_key,
            model=model,
            switches=switches,
            ztp_process=None,  # Not needed for edge agent mode
            ssh_executor=ssh_executor_for_agent
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

# Background ZTP process removed - all ZTP operations now handled by edge agents

if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port, log_level="info")