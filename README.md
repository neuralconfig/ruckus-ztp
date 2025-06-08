# RUCKUS ZTP Agent

A Zero-Touch Provisioning (ZTP) system for RUCKUS ICX switches and APs with edge agent architecture for local execution and cloud monitoring.

> **Recent Updates**: Configuration progress indicators and AP model display have been fixed and enhanced. See [RECENT_CHANGES.md](RECENT_CHANGES.md) for details.

## Overview

This tool provides a scalable, edge-based network automation solution for RUCKUS network devices. The system features a distributed architecture with local ZTP agents that execute provisioning locally while providing centralized monitoring through a cloud dashboard.

### Architecture Features:
- **Edge Agent Deployment**: ZTP processes run locally on edge devices, reducing cloud costs and improving reliability
- **Cloud Dashboard**: Centralized monitoring and management of multiple edge agents with real-time events
- **Event-Driven Communication**: Real-time event streaming from edge agents to cloud dashboard
- **Local Resilience**: ZTP operations continue during cloud connectivity issues
- **Multi-Agent Support**: Single dashboard manages multiple distributed edge deployments

### Key Capabilities:
- **Web Dashboard**: Modern cloud interface with real-time monitoring of multiple edge agents
- **iPhone App**: Native iOS application with full feature parity to the web interface
- **Command-line Interface**: Local CLI on edge agents with tab completion and help system
- **MAC-based Device Tracking**: Prevents duplicate entries when device IPs change via DHCP
- **Real-time Event Streaming**: Live updates from edge agents to cloud dashboard
- **Network Topology Visualization**: Interactive topology diagram with device connections and port information
- **Automatic Device Discovery**: Using LLDP and L2 trace to find connected devices
- **Local ZTP Execution**: Switch and AP configuration with management IP assignment from IP pool
- **Credential Management**: Automatic credential cycling with default and custom credentials
- **Customizable Base Configuration**: Initial switch setup (VLANs, spanning tree, etc.)
- **Intelligent Port Configuration**: Trunk port configuration with appropriate VLAN tagging
- **AI-powered Chat Interface**: Natural language configuration assistance

## Installation

### Edge Agent Installation

For local ZTP execution on edge devices:

1. Clone this repository on the edge device:
   ```bash
   git clone <repository-url>
   cd ruckus-ztp
   ```
2. Install the edge agent:
   ```bash
   cd ztp_edge_agent
   sudo ./install.sh
   ```
3. The installer will:
   - Install Python dependencies
   - Create configuration files
   - Set up systemd service
   - Generate agent credentials

### Development Installation

For development or CLI-only usage:

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Install the package:
   ```bash
   pip install -e .
   ```

## Configuration

1. Copy the example configuration file:
   ```
   cp config/ztp_agent.ini.example config/ztp_agent.ini
   ```
   
2. Edit `config/ztp_agent.ini` to set your environment-specific values:
   - **preferred_password**: Set a secure password for switch management
   - **openrouter_api_key**: Add your OpenRouter API key for the AI chat interface (optional)
   - **network settings**: Configure VLANs, IP pool, and gateway for your network
   - **base_config_file**: Path to your base configuration template

**Important**: The `config/ztp_agent.ini` file contains sensitive credentials and is excluded from version control. Never commit this file to your repository.

### Switch Default Credentials

When connecting to a new RUCKUS ICX switch for the first time, the default credentials are:
- Username: `super`
- Password: `sp-admin`

The ZTP agent automatically handles the required password change on first login. When adding a switch with default credentials, you'll need to specify the new password you want to use:

```
ztp-agent> config switch 192.168.1.1 super your-new-password
```

The agent will use `sp-admin` as the initial password, perform the required password change, and set it to your specified password.

## Usage

### Cloud Dashboard

Access the centralized dashboard for monitoring multiple edge agents:

**Production**: https://ruckusztp.neuralconfig.com

**Local Development**:
```bash
cd web_app
python3 run.py
```

The dashboard provides:
- **Dashboard Tab**: Overview statistics and status of all connected edge agents
- **Edge Agents Tab**: Detailed view of each agent (status, location, devices managed)
- **Events Tab**: Real-time event stream from all edge agents
- **Configuration Tab**: Global configuration for edge agents
- **Monitoring Tab**: Device inventory across all agents
- **AI Agent Tab**: Natural language interface for network operations

### Edge Agent Operations

The edge agent runs automatically as a systemd service after installation:

```bash
# Check service status
sudo systemctl status ruckus-ztp-edge-agent

# View logs
sudo journalctl -u ruckus-ztp-edge-agent -f

# Restart service
sudo systemctl restart ruckus-ztp-edge-agent
```

The edge agent will:
- Connect to the cloud dashboard automatically
- Begin ZTP operations based on configuration
- Stream events to the dashboard in real-time
- Continue operations during dashboard disconnection

### iPhone App

The native iOS application provides the same functionality as the web interface with an optimized mobile experience:

#### Features
- **Real-time Device Monitoring**: Live status updates with pull-to-refresh
- **Interactive Configuration**: Native iOS forms for credential and switch management  
- **Network Topology View**: Draggable nodes with touch-optimized interface
- **AI Chat Interface**: Natural language configuration assistance with real-time streaming
- **Log Viewer**: Searchable and filterable system logs
- **File Upload**: Camera roll and Files app integration for base configuration upload

#### Requirements
- iOS 15.0 or later
- Xcode 13+ for development
- Backend server running on accessible network

#### Setup for Development
1. Open `ios_app/ruckus-ztp/ruckus-ztp.xcodeproj` in Xcode
2. Update `Config.swift` with your backend server IP:
   ```swift
   // For iOS Simulator (backend on same Mac)
   static let baseURL = "http://localhost:8000"
   
   // For real device (update with your Mac's IP)
   static let baseURL = "http://192.168.1.100:8000"
   ```
3. Build and run the app

#### Backend Compatibility
The iPhone app uses the same REST API endpoints as the web interface:

- **Real-time Device Monitoring**: Live status updates with SSH activity indicators
- **Interactive Configuration**: Easy credential management and seed switch setup
- **Network Topology View**: Visual representation of device connections with port information
- **Status Tracking**: Granular device states (discovered → configuring → configured)
- **MAC-based Device Tracking**: Prevents duplicate entries from DHCP IP changes
- **Live Logs**: Real-time ZTP process logging and error reporting

#### Device Status Indicators

- **Green (Configured)**: Device is fully configured and operational
- **Blue (Configuring)**: Device is actively being configured with commands
- **Orange (Discovered)**: Device has been discovered but not yet configured
- **Yellow Highlight + "● SSH"**: Device is currently accessed via SSH (real-time indicator)

#### Configuration Progress Indicators

The dashboard displays visual progress indicators for device configuration:

- **Switches**: Two circles showing configuration phases
  - Circle 1: Base configuration (VLANs, spanning tree) - Grey (pending) → Green (completed)
  - Circle 2: Device configuration (hostname, management IP) - Grey (pending) → Green (completed)
- **Access Points**: One circle showing port configuration
  - Circle 1: Port configuration (VLAN tagging) - Grey (pending) → Green (completed)

#### Device Information Display

- **Model Detection**: Automatic model extraction from LLDP for accurate device identification (e.g., "R350", "R750" for APs)
- **Topology Visualization**: Shows switch port connections for AP devices
- **Real-time Updates**: Live status changes during configuration phases

#### Topology Visualization

- **Rectangles**: Represent switches
- **Circles**: Represent access points
- **Port Labels**: Show switch port numbers on connections
- **Color Coding**: Status-based colors for quick network health assessment

### Command Line Interface

Run the ZTP agent CLI:
```
ztp-agent
```

For help with available commands:
```
ztp-agent> help
```

### Basic Commands

- `config switch <ip> <username> <password>` - Add a switch to the inventory
- `ztp enable` - Enable the ZTP process
- `ztp disable` - Disable the ZTP process
- `ztp discover <ip>` - Run a one-time network discovery on a specific switch
- `vlan add <id> <name> <type>` - Add a VLAN (types: management, wireless, other)
- `vlan load <file_path>` - Load VLANs from a CSV file
- `vlan set-management <id>` - Set the management VLAN ID
- `show switches` - Show configured switches
- `show aps` - Show discovered APs
- `show vlans` - Show configured VLANs
- `show ztp` - Show ZTP status
- `chat` - Enter chat interface with AI agent

### Zero Touch Provisioning Process

The ZTP process now runs locally on edge agents with cloud monitoring:

#### Edge Agent Setup:
1. Install edge agent on a network-connected device (see Installation section)
2. Configure seed switches and network settings through the cloud dashboard
3. The edge agent automatically downloads configuration and begins ZTP operations

#### Automated Process:
The edge agent continuously:
1. **Discovers** neighboring devices using LLDP and L2 trace
2. **Configures** devices with base configuration (VLANs, spanning tree, etc.)
3. **Manages** trunk ports between switches with appropriate VLAN tagging
4. **Assigns** management IPs from the configured IP pool
5. **Reports** real-time events to the cloud dashboard
6. **Maintains** local device inventory and configuration state

#### Event Monitoring:
The cloud dashboard receives real-time events:
- `device_discovered`: New device found on network
- `device_configured`: Device successfully configured
- `error`: Configuration or connectivity issues
- `heartbeat`: Agent health and status updates

The process is fully autonomous once configured, with the edge agent handling all local operations while providing visibility through the cloud dashboard.

### Base Configuration File

The base configuration file (`config/base_configuration.txt`) contains the initial configuration applied to each newly discovered switch. This includes VLAN creation, spanning tree settings, and any other global settings. The file uses standard RUCKUS ICX CLI syntax and allows for comments (lines starting with '!').

Example:
```
! Management VLAN
vlan 10 name Management
spanning-tree 802-1w
exit

! Wireless VLANs
vlan 20 name Wireless-20
spanning-tree 802-1w
exit

vlan 30 name Wireless-30
spanning-tree 802-1w
exit

! Global spanning tree settings
spanning-tree
spanning-tree 802-1w
```

This approach provides flexibility to customize the initial configuration for all switches without modifying code.

## Testing

For development and testing:

1. Activate the virtual environment:
   ```bash
   ./activate_venv.sh
   ```

2. Verify the installation:
   ```bash
   ./test_installation.py
   ```

3. Run the ZTP agent:
   ```bash
   ztp-agent
   ```

4. Connect to a switch with default credentials:
   ```
   ztp-agent> config switch 192.168.1.1 super your-new-password
   ```
   This will automatically handle the password change on first login.

5. Test LLDP discovery:
   ```
   ztp-agent> ztp enable
   ztp-agent> show switches
   ```

See the [TESTING.md](TESTING.md) file for detailed testing procedures with real hardware.

### Chat Interface

The chat interface allows you to interact with an AI agent that can perform network operations using natural language. Examples:

- "What switches are available?"
- "Check the status of port 1/1/1 on switch 192.168.1.1"
- "Change VLAN on port 1/1/2 to VLAN 20"
- "Disable PoE on port 1/1/3"

## Development

### Project Structure

```
├── ztp_agent/               # Core ZTP library (used by edge agents and CLI)
│   ├── cli/                 # Command-line interface
│   │   └── commands/        # Command modules for different CLI functions
│   ├── network/             # Network operations
│   │   └── switch/          # Switch operations, organized by function
│   │       ├── connection.py     # Core SSH connectivity
│   │       ├── configuration.py  # Switch configuration operations
│   │       ├── discovery.py      # Network discovery with LLDP
│   │       └── enums.py          # Switch-related enumerations
│   ├── ztp/                 # ZTP process
│   ├── agent/               # AI agent
│   └── utils/               # Utilities
├── ztp_edge_agent/          # Edge agent for local ZTP execution
│   ├── core/                # Core edge agent functionality
│   │   ├── config.py        # Configuration management
│   │   ├── proxy.py         # WebSocket communication
│   │   └── websocket_client.py  # Dashboard connectivity
│   ├── handlers/            # Request handlers
│   ├── ztp_manager.py       # Local ZTP process management
│   ├── main.py              # Edge agent entry point
│   └── install.sh           # Installation script
├── web_app/                 # Cloud dashboard
│   ├── main.py              # FastAPI backend server
│   ├── ztp_edge_agent_manager.py  # Multi-agent management
│   ├── static/              # CSS, JavaScript for dashboard UI
│   └── templates/           # HTML templates with new dashboard
└── ios_app/                 # iPhone application
    └── ruckus-ztp/          # Xcode project
        ├── Models/          # Data models and API communication
        ├── Views/           # SwiftUI views (Configuration, Monitoring, etc.)
        ├── Managers/        # Network and configuration managers
        └── Assets.xcassets  # App icons and images
```

### Base Configuration File

The base configuration file (`config/base_configuration.txt`) contains the initial configuration to be applied to each switch. This includes VLAN creation, spanning tree configuration, and any other common settings. The file format uses RUCKUS ICX CLI commands, with one command per line. Comments start with an exclamation mark (!).

Example base configuration file:
```
! Management VLAN
vlan 10 name Management
spanning-tree 802-1w
exit

! Wireless VLANs
vlan 20 name Wireless-20
spanning-tree 802-1w
exit

vlan 30 name Wireless-30
spanning-tree 802-1w
exit

! Global spanning tree settings
spanning-tree
spanning-tree 802-1w
```

You can customize this file to include any initial configuration you want to apply to all switches. This provides greater flexibility than hardcoding VLAN creation in the code.

### Extending the System

#### Adding CLI Commands:
1. Add new methods to existing mixins in `ztp_agent/cli/commands/`
2. Or create new command mixin files and add to inheritance in `ztp_agent/cli/base.py`
3. Use `@with_category` and `@with_argparser` decorators

#### Adding Network Functionality:
1. Add methods to appropriate files in `ztp_agent/network/switch/`
2. Create new module files for entirely new functionality categories

#### Adding Edge Agent Features:
1. Extend `ztp_manager.py` for new ZTP capabilities
2. Add event types in the communication protocol
3. Update dashboard to handle new event types

#### Adding Dashboard Features:
1. Add API endpoints in `web_app/main.py`
2. Update `ztp_edge_agent_manager.py` for multi-agent coordination
3. Extend the dashboard UI with new tabs/functionality

#### Adding AI Agent Capabilities:
1. Add new tools in `ztp_agent/agent/tools.py`
2. Update the tool list in `get_network_tools()`
3. Edge agents will automatically get new AI capabilities
