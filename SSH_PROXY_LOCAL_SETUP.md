# SSH Proxy Local Deployment Guide

This guide covers deploying the SSH proxy on your Linux server to connect with the Cloud Run backend.

## Prerequisites

- Linux server with Python 3.8+
- Network access to your RUCKUS switches
- Outbound HTTPS access (port 443)
- Backend deployed to Cloud Run (https://ruckusztp.neuralconfig.com)

## Step 1: Generate Authentication Token

First, generate a secure token for the proxy:

```bash
# Generate a secure random token
openssl rand -hex 32
# Example output: a1b2c3d4e5f6789...

# Save this token - you'll need it for both proxy and backend configuration
```

## Step 2: Install SSH Proxy

### Option A: Quick Install Script

```bash
# Clone the repository
git clone https://github.com/neuralconfig/ruckus-ztp.git
cd ruckus-ztp

# Run installer as root
sudo ./ssh_proxy/install.sh
```

### Option B: Manual Installation

```bash
# Create directories
sudo mkdir -p /opt/ruckus-ztp-proxy
sudo mkdir -p /etc/ruckus-ztp-proxy
sudo mkdir -p /var/log/ruckus-ztp-proxy

# Create service user
sudo useradd -r -s /bin/false ruckus-proxy

# Copy files
sudo cp -r ssh_proxy/* /opt/ruckus-ztp-proxy/
cd /opt/ruckus-ztp-proxy

# Create virtual environment
sudo python3 -m venv venv
sudo ./venv/bin/pip install --upgrade pip
sudo ./venv/bin/pip install websockets paramiko

# Set ownership
sudo chown -R ruckus-proxy:ruckus-proxy /opt/ruckus-ztp-proxy
sudo chown -R ruckus-proxy:ruckus-proxy /var/log/ruckus-ztp-proxy
```

## Step 3: Configure SSH Proxy

Edit the configuration file:

```bash
sudo nano /etc/ruckus-ztp-proxy/config.ini
```

```ini
[server]
# Cloud Run backend WebSocket URL
url = wss://ruckusztp.neuralconfig.com/ws/ssh-proxy
# Use the token generated in Step 1
token = YOUR_GENERATED_TOKEN_HERE

[proxy]
# Optional: Give this proxy a unique ID
id = linux-server-01
# Reconnection settings
reconnect_interval = 30
command_timeout = 60

[logging]
level = INFO
file = /var/log/ruckus-ztp-proxy/proxy.log
```

## Step 4: Install Systemd Service

```bash
# Copy service file
sudo cp /opt/ruckus-ztp-proxy/config/ruckus-ztp-proxy.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start service
sudo systemctl enable ruckus-ztp-proxy
sudo systemctl start ruckus-ztp-proxy
```

## Step 5: Verify Connection

```bash
# Check service status
sudo systemctl status ruckus-ztp-proxy

# View logs
sudo journalctl -u ruckus-ztp-proxy -f

# You should see:
# - "Connecting to wss://ruckusztp.neuralconfig.com/ws/ssh-proxy..."
# - "WebSocket connection established"
# - "Registered proxy with ID: linux-server-01"
```

## Step 6: Configure Backend Token

The backend needs to accept the same token. For Cloud Run, this would typically be:

1. Store the token as a Secret in Google Secret Manager
2. Reference it in your Cloud Run deployment
3. Or use a simple token validation for testing

For testing, you can temporarily modify the backend to accept any token.

## Step 7: Test SSH Proxy

### From the Backend API

Once the proxy is connected, test it via the backend API:

```bash
# List connected proxies
curl https://ruckusztp.neuralconfig.com/api/ssh-proxies

# Execute test command through proxy
curl -X POST https://ruckusztp.neuralconfig.com/api/ssh-proxies/linux-server-01/command \
  -H "Content-Type: application/json" \
  -d '{
    "target_ip": "192.168.1.100",
    "username": "super",
    "password": "sp-admin",
    "command": "show version",
    "timeout": 30
  }'
```

## Step 8: Run Web Frontend Locally

Since you want to run the web frontend on the same Linux server:

```bash
# Install web app dependencies
cd /path/to/ruckus-ztp/web_app
pip install -r requirements.txt

# Create a simple run script
cat > run_local.sh << 'EOF'
#!/bin/bash
# Point to Cloud Run backend
export BACKEND_URL="https://ruckusztp.neuralconfig.com"
export PYTHONPATH=/path/to/ruckus-ztp

# Run locally on port 8000
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
EOF

chmod +x run_local.sh

# Run the web frontend
./run_local.sh
```

Access the web UI at: http://your-linux-server:8000

## Troubleshooting

### Connection Issues

```bash
# Test WebSocket connectivity
python3 -c "
import websockets
import asyncio

async def test():
    uri = 'wss://ruckusztp.neuralconfig.com/ws/ssh-proxy/test'
    async with websockets.connect(uri) as ws:
        print('Connected!')

asyncio.run(test())
"

# Check network connectivity
ping -c 4 ruckusztp.neuralconfig.com
curl -I https://ruckusztp.neuralconfig.com/api/status
```

### SSH Issues

```bash
# Test local SSH connectivity
ssh super@192.168.1.100

# Check proxy can resolve and reach switches
ping 192.168.1.100
```

### Debug Mode

For detailed logging:

```bash
# Stop service
sudo systemctl stop ruckus-ztp-proxy

# Run manually with debug
cd /opt/ruckus-ztp-proxy
sudo -u ruckus-proxy ./venv/bin/python -m ssh_proxy.main \
  --config /etc/ruckus-ztp-proxy/config.ini \
  --debug
```

## Security Notes

1. **Token Security**: Keep the authentication token secure
2. **Network Isolation**: Ensure the proxy server is on a trusted network
3. **Firewall**: No inbound ports needed, only outbound HTTPS (443)
4. **Updates**: Regularly update the proxy software

## Monitoring

Set up monitoring for:
- Proxy service status
- WebSocket connection health
- SSH command success rate
- Log file size and rotation

```bash
# Simple monitoring script
cat > /usr/local/bin/check-proxy.sh << 'EOF'
#!/bin/bash
if systemctl is-active --quiet ruckus-ztp-proxy; then
    echo "Proxy is running"
else
    echo "Proxy is down!"
    systemctl start ruckus-ztp-proxy
fi
EOF

chmod +x /usr/local/bin/check-proxy.sh

# Add to crontab
echo "*/5 * * * * /usr/local/bin/check-proxy.sh" | crontab -
```