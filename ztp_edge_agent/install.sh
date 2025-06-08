#!/bin/bash
#
# RUCKUS ZTP Edge Agent Installation Script
# Supports Debian/Ubuntu and RHEL/CentOS based distributions
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Installation paths
INSTALL_DIR="/opt/ruckus-ztp-edge-agent"
CONFIG_DIR="/etc/ruckus-ztp-edge-agent"
LOG_DIR="/var/log/ruckus-ztp-edge-agent"
SERVICE_NAME="ruckus-ztp-edge-agent"

# Print colored message
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_message $RED "This script must be run as root"
        exit 1
    fi
}

# Detect OS
detect_os() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS=$ID
        VER=$VERSION_ID
    else
        print_message $RED "Cannot detect OS"
        exit 1
    fi
}

# Install system dependencies
install_dependencies() {
    print_message $GREEN "Installing system dependencies..."
    
    if [[ "$OS" == "ubuntu" ]] || [[ "$OS" == "debian" ]]; then
        apt-get update
        apt-get install -y python3 python3-pip python3-venv
    elif [[ "$OS" == "centos" ]] || [[ "$OS" == "rhel" ]] || [[ "$OS" == "fedora" ]]; then
        yum install -y python3 python3-pip
    else
        print_message $RED "Unsupported OS: $OS"
        exit 1
    fi
}

# Create user and directories
create_user_and_dirs() {
    print_message $GREEN "Creating user and directories..."
    
    # Create user if doesn't exist
    if ! id "ruckus-edge-agent" &>/dev/null; then
        useradd -r -s /bin/false -d /nonexistent -c "RUCKUS ZTP Proxy" ruckus-edge-agent
    fi
    
    # Create directories
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$LOG_DIR"
    
    # Set permissions
    chown -R ruckus-edge-agent:ruckus-edge-agent "$LOG_DIR"
}

# Install edge agent
install_proxy() {
    print_message $GREEN "Installing edge agent..."
    
    # Determine the source directory
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    
    # Check if we're in the ztp_edge_agent directory or parent directory
    if [[ -f "$SCRIPT_DIR/main.py" ]]; then
        # We're in the ztp_edge_agent directory
        SOURCE_DIR="$SCRIPT_DIR"
    elif [[ -d "$SCRIPT_DIR/../ztp_edge_agent" && -f "$SCRIPT_DIR/../ztp_edge_agent/main.py" ]]; then
        # We're in parent directory and ztp_edge_agent is a subdirectory
        SOURCE_DIR="$SCRIPT_DIR/../ztp_edge_agent"
    elif [[ -d "ztp_edge_agent" && -f "ztp_edge_agent/main.py" ]]; then
        # ztp_edge_agent directory exists in current working directory
        SOURCE_DIR="./ztp_edge_agent"
    else
        print_message $RED "Cannot find edge agent source files"
        print_message $RED "Expected to find main.py in ztp_edge_agent directory"
        exit 1
    fi
    
    print_message $GREEN "Using source directory: $SOURCE_DIR"
    
    # Copy source files (everything except install.sh)
    cp -r "$SOURCE_DIR"/* "$INSTALL_DIR/" 2>/dev/null || true
    
    # Remove install.sh from installation directory if it was copied
    rm -f "$INSTALL_DIR/install.sh"
    
    # Ensure requirements.txt exists
    if [[ ! -f "$INSTALL_DIR/requirements.txt" ]]; then
        print_message $YELLOW "Creating requirements.txt file..."
        cat > "$INSTALL_DIR/requirements.txt" << 'EOF'
websockets>=8.1,<10.0
paramiko>=2.7.0,<3.0.0
pyyaml>=5.0.0
configparser
EOF
    fi
    
    # Create virtual environment
    cd "$INSTALL_DIR"
    python3 -m venv venv
    
    # Install Python dependencies
    ./venv/bin/python3 -m pip install --upgrade pip
    ./venv/bin/python3 -m pip install -r requirements.txt
    
    # Set ownership
    chown -R ruckus-edge-agent:ruckus-edge-agent "$INSTALL_DIR"
}

# Install configuration
install_config() {
    print_message $GREEN "Installing configuration..."
    
    # Always create new configuration (overwrite existing)
    if [[ -f "$INSTALL_DIR/config/config.ini.example" ]]; then
        cp "$INSTALL_DIR/config/config.ini.example" "$CONFIG_DIR/config.ini"
        print_message $GREEN "Configuration template copied from example"
    else
        print_message $YELLOW "Creating default configuration file..."
        cat > "$CONFIG_DIR/config.ini" << 'EOF'
[agent]
agent_id = REPLACE_WITH_AGENT_ID
auth_token = REPLACE_WITH_GENERATED_TOKEN
command_timeout = 60

[network]
hostname = REPLACE_WITH_HOSTNAME
subnet = 192.168.1.0/24

[backend]
server_url = https://ruckusztp.neuralconfig.com
websocket_path = /ws/edge-agent
reconnect_interval = 30

[logging]
level = DEBUG
log_file = /var/log/ruckus-ztp-edge-agent/proxy.log
EOF
    fi
    
    # Set permissions
    chmod 640 "$CONFIG_DIR/config.ini"
    chown root:ruckus-edge-agent "$CONFIG_DIR/config.ini"
}

# Install systemd service
install_service() {
    print_message $GREEN "Installing systemd service..."
    
    # Copy service file if it exists, otherwise create it
    if [[ -f "$INSTALL_DIR/config/ruckus-ztp-edge-agent.service" ]]; then
        cp "$INSTALL_DIR/config/ruckus-ztp-edge-agent.service" /etc/systemd/system/
    else
        print_message $YELLOW "Creating systemd service file..."
        cat > /etc/systemd/system/ruckus-ztp-edge-agent.service << 'EOF'
[Unit]
Description=RUCKUS ZTP Edge Agent
After=network.target
Wants=network.target

[Service]
Type=simple
User=ruckus-edge-agent
Group=ruckus-edge-agent
WorkingDirectory=/opt/ruckus-ztp-edge-agent
Environment=PYTHONPATH=/opt/ruckus-ztp-edge-agent
ExecStart=/opt/ruckus-ztp-edge-agent/venv/bin/python3 /opt/ruckus-ztp-edge-agent/main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    fi
    
    # Reload systemd
    systemctl daemon-reload
    
    print_message $GREEN "Service installed. To start:"
    print_message $YELLOW "  systemctl start $SERVICE_NAME"
    print_message $YELLOW "  systemctl enable $SERVICE_NAME"
}

# Generate token and update config
generate_token() {
    print_message $GREEN "Generating authentication token and updating configuration..."
    
    # Generate random token
    TOKEN=$(openssl rand -hex 32)
    
    # Generate agent ID
    AGENT_ID="agent-$(hostname -s)-$(date +%s)"
    
    # Auto-detect hostname
    HOSTNAME=$(hostname -f)
    
    # Update the configuration file with generated values
    sed -i "s/REPLACE_WITH_GENERATED_TOKEN/$TOKEN/g" "$CONFIG_DIR/config.ini"
    sed -i "s/REPLACE_WITH_AGENT_ID/$AGENT_ID/g" "$CONFIG_DIR/config.ini"
    sed -i "s/REPLACE_WITH_HOSTNAME/$HOSTNAME/g" "$CONFIG_DIR/config.ini"
    
    print_message $GREEN "Configuration updated successfully!"
    print_message $YELLOW "Generated token: $TOKEN"
    print_message $YELLOW "Agent ID: $AGENT_ID"
    print_message $YELLOW "Hostname: $HOSTNAME"
    print_message $YELLOW ""
    print_message $YELLOW "IMPORTANT: Save this token for the web interface configuration!"
}

# Main installation
main() {
    print_message $GREEN "RUCKUS ZTP Edge Agent Installer"
    print_message $GREEN "=============================="
    
    check_root
    detect_os
    
    print_message $GREEN "Detected OS: $OS $VER"
    
    install_dependencies
    create_user_and_dirs
    install_proxy
    install_config
    install_service
    generate_token
    
    print_message $GREEN ""
    print_message $GREEN "Installation complete!"
    print_message $GREEN ""
    print_message $YELLOW "Next steps:"
    print_message $YELLOW "1. Edit $CONFIG_DIR/config.ini with your settings"
    print_message $YELLOW "2. Start the service: systemctl start $SERVICE_NAME"
    print_message $YELLOW "3. Enable auto-start: systemctl enable $SERVICE_NAME"
    print_message $YELLOW "4. Check logs: journalctl -u $SERVICE_NAME -f"
}

# Run main
main