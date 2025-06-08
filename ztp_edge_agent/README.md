# RUCKUS ZTP ZTP Edge Agent

The ZTP Edge Agent enables remote SSH access to network devices through the RUCKUS ZTP backend server. It creates an outbound WebSocket connection to the backend, eliminating the need for inbound firewall rules.

## Features

- **Outbound-only connections**: No inbound firewall rules required
- **WebSocket-based communication**: Secure, persistent connection to backend
- **Stateless design**: Creates SSH connections on-demand
- **Simple deployment**: Single Python application with minimal dependencies
- **Linux compatibility**: Runs on any Linux server (not limited to Raspberry Pi)

## Requirements

- Linux server (Debian/Ubuntu or RHEL/CentOS based)
- Python 3.8 or later
- Network access to target devices
- Outbound HTTPS access to backend server

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/neuralconfig/ruckus-ztp.git
cd ruckus-ztp

# Run the installer (as root)
sudo ./ztp_edge_agent/install.sh
```

### 2. Configuration

Edit `/etc/ruckus-ztp-edge-agent/config.ini`:

```ini
[server]
url = wss://your-backend-server.com/ws/edge-agent
token = your-secure-token-here

[proxy]
reconnect_interval = 30
command_timeout = 60

[logging]
level = INFO
file = /var/log/ruckus-ztp-edge-agent/proxy.log
```

### 3. Start the Service

```bash
# Start the service
sudo systemctl start ruckus-ztp-edge-agent

# Enable auto-start on boot
sudo systemctl enable ruckus-ztp-edge-agent

# Check status
sudo systemctl status ruckus-ztp-edge-agent

# View logs
sudo journalctl -u ruckus-ztp-edge-agent -f
```

## Manual Installation

If you prefer manual installation:

```bash
# Create directories
sudo mkdir -p /opt/ruckus-ztp-edge-agent
sudo mkdir -p /etc/ruckus-ztp-edge-agent
sudo mkdir -p /var/log/ruckus-ztp-edge-agent

# Create user
sudo useradd -r -s /bin/false ruckus-edge-agent

# Copy files
sudo cp -r ztp_edge_agent/* /opt/ruckus-ztp-edge-agent/
sudo cp ztp_edge_agent/config/config.ini.example /etc/ruckus-ztp-edge-agent/config.ini

# Install Python dependencies
cd /opt/ruckus-ztp-edge-agent
sudo python3 -m venv venv
sudo ./venv/bin/pip install websockets paramiko

# Set permissions
sudo chown -R ruckus-edge-agent:ruckus-edge-agent /opt/ruckus-ztp-edge-agent
sudo chown -R ruckus-edge-agent:ruckus-edge-agent /var/log/ruckus-ztp-edge-agent

# Install systemd service
sudo cp ztp_edge_agent/config/ruckus-ztp-edge-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
```

## Command Line Usage

For testing or debugging, you can run the proxy manually:

```bash
# Basic usage with config file
python -m ztp_edge_agent.main --config /etc/ruckus-ztp-edge-agent/config.ini

# Override config with command line options
python -m ztp_edge_agent.main \
    --server wss://backend.example.com/ws/edge-agent \
    --token your-token \
    --debug

# All options
python -m ztp_edge_agent.main --help
```

## Architecture

The ZTP Edge Agent follows a simple architecture:

1. **WebSocket Client**: Maintains persistent connection to backend
2. **SSH Handler**: Executes commands using paramiko
3. **Message Protocol**: JSON-based request/response over WebSocket

### Message Flow

```
Backend Server → WebSocket → ZTP Edge Agent → SSH → Network Device
                     ↑                             ↓
                     └─────── Response ────────────┘
```

## Security Considerations

1. **Authentication**: Uses pre-shared bearer tokens
2. **Transport**: All communication over WSS (WebSocket Secure)
3. **Isolation**: Each SSH session is isolated and temporary
4. **Logging**: All commands are logged for audit purposes

## Troubleshooting

### Connection Issues

```bash
# Check service status
sudo systemctl status ruckus-ztp-edge-agent

# View detailed logs
sudo journalctl -u ruckus-ztp-edge-agent -n 100

# Test connectivity to backend
curl -I https://your-backend-server.com

# Test WebSocket upgrade
curl -i -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Key: x3JJHMbDL1EzLkh9GBhXDw==" \
  -H "Sec-WebSocket-Version: 13" \
  https://your-backend-server.com/ws/edge-agent/test
```

### SSH Issues

```bash
# Test SSH connectivity manually
ssh user@device-ip

# Check proxy can reach devices
ping device-ip

# Verify network routing
ip route
```

### Debug Mode

Run with debug logging for detailed output:

```bash
# In config file
[logging]
level = DEBUG

# Or command line
python -m ztp_edge_agent.main --debug
```

## API Integration

The backend server provides REST API endpoints for proxy management:

```bash
# List connected proxies
GET /api/ssh-proxies

# Get proxy details
GET /api/ssh-proxies/{proxy_id}

# Execute SSH command
POST /api/ssh-proxies/{proxy_id}/command
{
    "target_ip": "192.168.1.100",
    "username": "admin",
    "password": "password",
    "command": "show version",
    "timeout": 30
}
```

## Development

### Running Tests

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run unit tests
pytest ztp_edge_agent/tests/unit/

# Run with coverage
pytest --cov=ztp_edge_agent ztp_edge_agent/tests/
```

### Project Structure

```
ztp_edge_agent/
├── __init__.py
├── main.py              # Entry point
├── core/
│   ├── config.py        # Configuration management
│   ├── proxy.py         # Main proxy application
│   └── websocket_client.py  # WebSocket client
├── handlers/
│   └── ssh_handler.py   # SSH command execution
├── utils/
│   └── logger.py        # Logging utilities
├── config/
│   ├── config.ini.example
│   └── ruckus-ztp-edge-agent.service
└── tests/
    ├── unit/
    └── integration/
```

## License

This project is part of the RUCKUS ZTP system. See the main project for license information.