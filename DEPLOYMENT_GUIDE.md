# ZTP Edge Agent Deployment Guide

## Overview

This guide covers the complete deployment process for the new ZTP Edge Agent architecture, including cleanup of the old SSH proxy installation, deploying the new edge agent, and testing the system.

## Prerequisites

- Linux server (Debian/Ubuntu or RHEL/CentOS)
- Python 3.8 or later
- Root/sudo access
- Network access to target devices and backend server
- Git repository access

## Part 1: Cleanup Previous Installation

### 1.1 Stop Old Services

```bash
# Stop the old SSH proxy service if running
sudo systemctl stop ruckus-ztp-proxy 2>/dev/null || echo "Service not found"
sudo systemctl disable ruckus-ztp-proxy 2>/dev/null || echo "Service not found"
```

### 1.2 Remove Old Installation

```bash
# Remove old service file
sudo rm -f /etc/systemd/system/ruckus-ztp-proxy.service

# Remove old installation directory
sudo rm -rf /opt/ruckus-ztp-proxy

# Remove old configuration directory
sudo rm -rf /etc/ruckus-ztp-proxy

# Remove old log directory
sudo rm -rf /var/log/ruckus-ztp-proxy

# Remove old user account
sudo userdel ruckus-proxy 2>/dev/null || echo "User not found"

# Reload systemd
sudo systemctl daemon-reload
```

### 1.3 Verify Cleanup

```bash
# Check that old services are gone
systemctl list-units --all | grep ruckus-ztp-proxy || echo "✅ Old services removed"

# Check that old directories are gone
ls -la /opt/ | grep ruckus-ztp-proxy || echo "✅ Old installation directory removed"
ls -la /etc/ | grep ruckus-ztp-proxy || echo "✅ Old configuration directory removed"
```

## Part 2: Install New ZTP Edge Agent

### 2.1 Get Latest Code

```bash
# Navigate to the project directory or clone if needed
cd /path/to/ruckus-ztp

# Pull latest changes if using git
git pull origin main  # or your branch name

# Verify the new edge agent exists
ls -la ztp_edge_agent/
```

### 2.2 Run Edge Agent Installation

The installation script has been updated for the new architecture:

```bash
# Make sure the install script is executable
chmod +x ztp_edge_agent/install.sh

# Run the installation as root
sudo ./ztp_edge_agent/install.sh
```

**Expected Output:**
```
RUCKUS ZTP Edge Agent Installer
==============================
Detected OS: ubuntu 22.04
Installing system dependencies...
Creating user and directories...
Installing edge agent...
Using source directory: ./ztp_edge_agent
Installing configuration...
Installing systemd service...
Generating authentication token and updating configuration...
Generated token: [32-char hex token]
Agent ID: agent-hostname-timestamp
Hostname: your-hostname
IMPORTANT: Save this token for the web interface configuration!

Installation complete!

Next steps:
1. Edit /etc/ruckus-ztp-edge-agent/config.ini with your settings
2. Start the service: systemctl start ruckus-ztp-edge-agent
3. Enable auto-start: systemctl enable ruckus-ztp-edge-agent
4. Check logs: journalctl -u ruckus-ztp-edge-agent -f
```

### 2.3 Configure Edge Agent

Edit the configuration file:

```bash
sudo nano /etc/ruckus-ztp-edge-agent/config.ini
```

**Update these settings:**

```ini
[agent]
agent_id = agent-your-hostname-timestamp  # Generated automatically
auth_token = your-generated-token-here     # Generated automatically
command_timeout = 60

[network]
hostname = your-actual-hostname            # Update if needed
subnet = 192.168.1.0/24                   # Update to your network

[backend]
server_url = https://your-backend-url.com  # Update to your web app URL
websocket_path = /ws/edge-agent
reconnect_interval = 30

[logging]
level = DEBUG                              # Use DEBUG for testing
log_file = /var/log/ruckus-ztp-edge-agent/agent.log

[ztp]
enable_ztp = true
poll_interval = 30
```

### 2.4 Start Edge Agent Service

```bash
# Start the service
sudo systemctl start ruckus-ztp-edge-agent

# Enable auto-start on boot
sudo systemctl enable ruckus-ztp-edge-agent

# Check service status
sudo systemctl status ruckus-ztp-edge-agent
```

**Expected Status:**
```
● ruckus-ztp-edge-agent.service - RUCKUS ZTP Edge Agent
     Loaded: loaded (/etc/systemd/system/ruckus-ztp-edge-agent.service; enabled)
     Active: active (running) since [timestamp]
     Main PID: [pid] (python3)
```

## Part 3: Deploy New Web Application

### 3.1 Update Web App Dependencies

```bash
# Navigate to web app directory
cd web_app

# Install/update dependencies in virtual environment
../venv/bin/python3 -m pip install --upgrade pip
../venv/bin/python3 -m pip install -r requirements.txt

# Verify FastAPI and dependencies
../venv/bin/python3 -c "import fastapi; import uvicorn; print('✅ Web app dependencies ready')"
```

### 3.2 Test Web App Locally

```bash
# Test the web app can start
../venv/bin/python3 -c "
from main import app
print('✅ Web app imports successfully')

# Check new API endpoints
routes = [route.path for route in app.routes if hasattr(route, 'path')]
required = ['/api/edge-agents', '/api/ztp/status', '/api/ztp/events', '/api/ztp/inventory']
for route in required:
    if route in routes:
        print(f'✅ {route}')
    else:
        print(f'❌ {route} missing')
"
```

### 3.3 Start Web App with Debug Logging

```bash
# Start the web app with debug logging
../venv/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload --log-level debug
```

**Expected Output:**
```
INFO:     Will watch for changes in these directories: ['/path/to/web_app']
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [pid]
INFO:     Started server process [pid]
INFO:     Waiting for application startup.
DEBUG:    Web application started
INFO:     Application startup complete.
```

### 3.4 Verify Web App Dashboard

Open your browser and navigate to: `http://your-server-ip:8000`

**You should see:**
- ✅ New "ZTP Control Center" title
- ✅ Dashboard tab as default (instead of Configuration)
- ✅ New tabs: Dashboard, Edge Agents, Events, Configuration
- ✅ Modern dashboard interface with stats cards

## Part 4: Testing and Verification

### 4.1 Check Edge Agent Connection

**In the web app logs, look for:**
```
INFO:     New edge agent connection accepted
INFO:     Edge agent registered: agent-hostname-timestamp (your-hostname)
```

**In the edge agent logs:**
```bash
sudo journalctl -u ruckus-ztp-edge-agent -f
```

**Look for:**
```
INFO - 🚀 Starting RUCKUS ZTP Edge Agent
INFO - ✅ WebSocket connection established successfully
INFO - ✅ Registration sent to backend successfully
INFO - 💓 Heartbeat sent successfully
```

### 4.2 Test Dashboard Interface

1. **Dashboard Tab:**
   - Should show "1" under "Edge Agents"
   - Should show "1" under "Running ZTP" (if ZTP started)
   - Recent events should appear

2. **Edge Agents Tab:**
   - Should show your edge agent card
   - Status should be "online" (green)
   - Should show hostname, network, version info

3. **Events Tab:**
   - Should show ZTP events as they occur
   - Events should have timestamps and agent IDs

### 4.3 Test ZTP Functionality

1. **Configure ZTP in Web App:**
   - Go to Configuration tab
   - Set up credentials and seed switches
   - Enable edge agent integration
   - Save configuration

2. **Start ZTP Process:**
   - Click "Start ZTP Process" in Configuration tab
   - Should see "ZTP configuration sent to 1 edge agent(s)"

3. **Monitor ZTP Execution:**
   - Watch Dashboard for device discovery events
   - Check Events tab for real-time updates
   - Monitor edge agent logs for ZTP activity

### 4.4 Debug Logging Commands

**Web App Debug:**
```bash
# Web app with debug logging
../venv/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --log-level debug

# Test API endpoints
curl http://localhost:8000/api/edge-agents
curl http://localhost:8000/api/ztp/status
curl http://localhost:8000/api/ztp/events
```

**Edge Agent Debug:**
```bash
# View edge agent logs with debug level
sudo journalctl -u ruckus-ztp-edge-agent -f --no-pager

# View specific log file
sudo tail -f /var/log/ruckus-ztp-edge-agent/agent.log

# Test edge agent configuration
sudo -u ruckus-edge-agent /opt/ruckus-ztp-edge-agent/venv/bin/python3 /opt/ruckus-ztp-edge-agent/main.py
```

## Part 5: Troubleshooting

### 5.1 Common Issues

**Edge Agent Won't Connect:**
```bash
# Check configuration
sudo cat /etc/ruckus-ztp-edge-agent/config.ini

# Check network connectivity
curl -I https://your-backend-url.com

# Check WebSocket endpoint
curl -i -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Key: test" \
  -H "Authorization: Bearer your-token" \
  https://your-backend-url.com/ws/edge-agent/test
```

**Web App Issues:**
```bash
# Check all dependencies
../venv/bin/python3 -c "
import sys
modules = ['fastapi', 'uvicorn', 'websockets', 'pydantic']
for module in modules:
    try:
        __import__(module)
        print(f'✅ {module}')
    except ImportError:
        print(f'❌ {module} missing')
"

# Check configuration file exists
ls -la ~/.ztp_agent.cfg || echo "Configuration file missing"
```

### 5.2 Performance Verification

**Check Resource Usage:**
```bash
# CPU and memory usage
top -p $(pgrep -f ruckus-ztp-edge-agent)

# Network connections
sudo netstat -tulpn | grep python3

# Log file sizes
du -sh /var/log/ruckus-ztp-edge-agent/
```

### 5.3 Deployment Verification Checklist

- [ ] Old SSH proxy completely removed
- [ ] New edge agent installed and running
- [ ] Edge agent connects to web app successfully
- [ ] Web app dashboard shows connected agent
- [ ] ZTP configuration can be sent to edge agent
- [ ] Events appear in real-time in dashboard
- [ ] Debug logging shows detailed operation info
- [ ] All API endpoints responding correctly

## Success Criteria

**✅ Deployment Successful When:**
1. Edge agent service is running and stable
2. WebSocket connection established between agent and web app
3. Dashboard shows agent as "online"
4. ZTP events are generated and displayed in real-time
5. Device inventory updates as devices are discovered
6. Debug logs show detailed operational information

## Next Steps

After successful deployment:

1. **Configure ZTP Settings:** Set up credentials, seed switches, and network parameters
2. **Test with Real Devices:** Connect to actual RUCKUS switches for full ZTP testing
3. **Monitor Performance:** Watch resource usage and event processing
4. **Scale Deployment:** Deploy additional edge agents as needed
5. **Production Hardening:** Adjust logging levels and implement monitoring

---

**Note:** This deployment guide assumes the new architecture has been fully implemented. If you encounter issues, check that all code changes from the architecture transformation have been properly applied.