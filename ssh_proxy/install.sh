#!/bin/bash
#
# RUCKUS ZTP SSH Proxy Installation Script
# Supports Debian/Ubuntu and RHEL/CentOS based distributions
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Installation paths
INSTALL_DIR="/opt/ruckus-ztp-proxy"
CONFIG_DIR="/etc/ruckus-ztp-proxy"
LOG_DIR="/var/log/ruckus-ztp-proxy"
SERVICE_NAME="ruckus-ztp-proxy"

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
    if ! id "ruckus-proxy" &>/dev/null; then
        useradd -r -s /bin/false -d /nonexistent -c "RUCKUS ZTP Proxy" ruckus-proxy
    fi
    
    # Create directories
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$LOG_DIR"
    
    # Set permissions
    chown -R ruckus-proxy:ruckus-proxy "$LOG_DIR"
}

# Install SSH proxy
install_proxy() {
    print_message $GREEN "Installing SSH proxy..."
    
    # Copy source files
    cp -r ssh_proxy "$INSTALL_DIR/"
    cp requirements.txt "$INSTALL_DIR/"
    
    # Create virtual environment
    cd "$INSTALL_DIR"
    python3 -m venv venv
    
    # Install Python dependencies
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -r requirements.txt
    ./venv/bin/pip install websockets paramiko
    
    # Set ownership
    chown -R ruckus-proxy:ruckus-proxy "$INSTALL_DIR"
}

# Install configuration
install_config() {
    print_message $GREEN "Installing configuration..."
    
    # Copy example config if no config exists
    if [[ ! -f "$CONFIG_DIR/config.ini" ]]; then
        cp ssh_proxy/config/config.ini.example "$CONFIG_DIR/config.ini"
        print_message $YELLOW "Please edit $CONFIG_DIR/config.ini with your settings"
    fi
    
    # Set permissions
    chmod 640 "$CONFIG_DIR/config.ini"
    chown root:ruckus-proxy "$CONFIG_DIR/config.ini"
}

# Install systemd service
install_service() {
    print_message $GREEN "Installing systemd service..."
    
    # Copy service file
    cp ssh_proxy/config/ruckus-ztp-proxy.service /etc/systemd/system/
    
    # Reload systemd
    systemctl daemon-reload
    
    print_message $GREEN "Service installed. To start:"
    print_message $YELLOW "  systemctl start $SERVICE_NAME"
    print_message $YELLOW "  systemctl enable $SERVICE_NAME"
}

# Generate token
generate_token() {
    print_message $GREEN "Generating authentication token..."
    
    # Generate random token
    TOKEN=$(openssl rand -hex 32)
    
    print_message $YELLOW "Generated token: $TOKEN"
    print_message $YELLOW "Add this token to:"
    print_message $YELLOW "  1. $CONFIG_DIR/config.ini"
    print_message $YELLOW "  2. Your backend server configuration"
}

# Main installation
main() {
    print_message $GREEN "RUCKUS ZTP SSH Proxy Installer"
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