#!/bin/bash

# RUCKUS ZTP Edge Agent Installer Script
# Generates UUID and prompts for password during installation

set -e  # Exit on any error

echo "================================="
echo "RUCKUS ZTP Edge Agent Installer"
echo "================================="
echo

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo "⚠️  This script should not be run as root. Please run as a regular user."
   exit 1
fi

# Check for required commands
for cmd in python3 pip3 systemctl; do
    if ! command -v $cmd &> /dev/null; then
        echo "❌ Error: $cmd is required but not installed."
        exit 1
    fi
done

# Generate unique agent UUID
AGENT_UUID=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
echo "🔧 Generated Agent UUID: $AGENT_UUID"

# Prompt for agent password
echo
echo "🔐 Set up agent access password:"
echo "   This password will be required to access the agent via the web interface."
echo "   Keep this password secure - it cannot be recovered if lost."
echo
while true; do
    read -s -p "Enter agent password: " AGENT_PASSWORD
    echo
    if [[ ${#AGENT_PASSWORD} -lt 8 ]]; then
        echo "❌ Password must be at least 8 characters long."
        continue
    fi
    
    read -s -p "Confirm password: " AGENT_PASSWORD_CONFIRM
    echo
    if [[ "$AGENT_PASSWORD" != "$AGENT_PASSWORD_CONFIRM" ]]; then
        echo "❌ Passwords do not match. Please try again."
        continue
    fi
    
    break
done

# Prompt for web app server URL
echo
read -p "Enter web app server URL (e.g., https://your-app.com or http://localhost:8000): " WEB_APP_URL

# Validate URL format
if [[ ! "$WEB_APP_URL" =~ ^https?:// ]]; then
    echo "❌ Invalid URL format. Please include http:// or https://"
    exit 1
fi

# Remove trailing slash if present
WEB_APP_URL=${WEB_APP_URL%/}

# Create installation directory
INSTALL_DIR="/opt/ruckus-ztp-edge-agent"
CONFIG_DIR="/etc/ruckus-ztp-edge-agent"

echo
echo "📁 Creating installation directories..."
sudo mkdir -p "$INSTALL_DIR"
sudo mkdir -p "$CONFIG_DIR"

# Copy source files
echo "📦 Installing edge agent files..."
sudo cp -r . "$INSTALL_DIR/"
sudo chown -R $USER:$USER "$INSTALL_DIR"

# Create configuration file
CONFIG_FILE="$CONFIG_DIR/ztp_config.ini"
echo "⚙️  Creating configuration file..."

sudo tee "$CONFIG_FILE" > /dev/null << EOF
[agent]
agent_id = $AGENT_UUID
agent_password = $AGENT_PASSWORD
web_app_url = $WEB_APP_URL
auth_token = edge-agent-token-$(date +%s)

[network]
hostname = $(hostname)
subnet = auto

[ztp]
poll_interval = 300
max_retries = 3
retry_delay = 60

[logging]
level = INFO
max_file_size = 10MB
backup_count = 5
log_file = /var/log/ruckus-ztp-edge-agent.log
EOF

# Set secure permissions on config file (contains password)
sudo chmod 600 "$CONFIG_FILE"
sudo chown $USER:$USER "$CONFIG_FILE"

# Install Python dependencies
echo "🐍 Installing Python dependencies..."
cd "$INSTALL_DIR"
pip3 install -r requirements.txt --user

# Create systemd service file
SERVICE_FILE="/etc/systemd/system/ruckus-ztp-edge-agent.service"
echo "🔧 Creating systemd service..."

sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=RUCKUS ZTP Edge Agent
After=network.target
Wants=network.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/main.py --config $CONFIG_FILE
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Environment
Environment=PYTHONPATH=$INSTALL_DIR

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable service
echo "🔄 Configuring systemd service..."
sudo systemctl daemon-reload
sudo systemctl enable ruckus-ztp-edge-agent

# Create log directory
sudo mkdir -p /var/log
sudo touch /var/log/ruckus-ztp-edge-agent.log
sudo chown $USER:$USER /var/log/ruckus-ztp-edge-agent.log

echo
echo "✅ Installation completed successfully!"
echo
echo "📋 Installation Summary:"
echo "   Agent UUID: $AGENT_UUID"
echo "   Web App URL: $WEB_APP_URL"
echo "   Config File: $CONFIG_FILE"
echo "   Service: ruckus-ztp-edge-agent"
echo
echo "🌐 Your unique agent URL:"
echo "   $WEB_APP_URL/$AGENT_UUID"
echo
echo "🔐 Access Instructions:"
echo "   1. Open the URL above in your browser"
echo "   2. Enter the password you just set"
echo "   3. You'll have access to the ZTP control panel"
echo
echo "🚀 Starting the edge agent service..."
sudo systemctl start ruckus-ztp-edge-agent

# Wait a moment and check status
sleep 2
if sudo systemctl is-active --quiet ruckus-ztp-edge-agent; then
    echo "✅ Edge agent service started successfully!"
    echo
    echo "📊 Service Status:"
    sudo systemctl status ruckus-ztp-edge-agent --no-pager -l
else
    echo "❌ Warning: Edge agent service failed to start."
    echo "📋 Check logs with: sudo journalctl -u ruckus-ztp-edge-agent -f"
fi

echo
echo "🎉 Installation complete!"
echo "   You can now access your agent at: $WEB_APP_URL/$AGENT_UUID"
echo
echo "🔧 Useful commands:"
echo "   Start service:   sudo systemctl start ruckus-ztp-edge-agent"
echo "   Stop service:    sudo systemctl stop ruckus-ztp-edge-agent"
echo "   View logs:       sudo journalctl -u ruckus-ztp-edge-agent -f"
echo "   Edit config:     sudo nano $CONFIG_FILE"
echo