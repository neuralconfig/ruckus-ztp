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

from fastapi import FastAPI, HTTPException, Request, File, UploadFile, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
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
    switches_discovered: int
    switches_configured: int
    aps_discovered: int
    last_poll: Optional[str] = None
    errors: List[str] = []

class DeviceInfo(BaseModel):
    ip: str
    mac: Optional[str] = None
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
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        force=True  # Override any existing logging configuration
    )
    
    # Add custom handler to capture ZTP logs
    web_handler = WebLogHandler()
    web_handler.setLevel(logging.INFO)
    
    # Add to relevant loggers
    ztp_logger = logging.getLogger('ztp_agent')
    ztp_logger.addHandler(web_handler)
    ztp_logger.setLevel(logging.INFO)
    
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
    global ztp_process
    
    if not ztp_process:
        return ZTPStatus(
            running=False,
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
    global ztp_process, app_config
    
    if not app_config:
        raise HTTPException(status_code=400, detail="Configuration not set")
    
    if ztp_process and ztp_process.running:
        return {"message": "ZTP process is already running", "errors": []}
    
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

async def run_ztp_process():
    """Run the ZTP process in the background."""
    global ztp_process
    
    if ztp_process:
        # The ZTP process starts automatically when switches are added
        # We just need to start the background thread
        if not ztp_process.running:
            ztp_process.start()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")