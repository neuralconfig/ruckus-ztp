# RUCKUS ZTP Agent

A Zero-Touch Provisioning (ZTP) agent for RUCKUS ICX switches and APs.

## Overview

This tool provides a network engineer-friendly command-line interface for automating the discovery, configuration, and management of RUCKUS network devices. Starting with a single seed switch, the ZTP agent can discover and configure connected devices with minimal manual intervention.

Key features:
- **Web Interface**: Modern web application for managing ZTP processes with real-time monitoring
- **Command-line Interface**: Tab completion and help system for CLI operations
- **MAC-based Device Tracking**: Prevents duplicate entries when device IPs change via DHCP
- **Real-time Status Monitoring**: Live SSH activity indicators and configuration progress tracking
- **Network Topology Visualization**: Interactive topology diagram with device connections and port information
- **Automatic Device Discovery**: Using LLDP and L2 trace to find connected devices
- **Automated Configuration**: Switch and AP configuration with management IP assignment from IP pool
- **Credential Management**: Automatic credential cycling with default and custom credentials
- **Customizable Base Configuration**: Initial switch setup (VLANs, spanning tree, etc.)
- **Intelligent Port Configuration**: Trunk port configuration with appropriate VLAN tagging
- **AI-powered Chat Interface**: Natural language configuration assistance

## Installation

1. Clone this repository or download the source code
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Install the package:
   ```
   pip install -e .
   ```

## Configuration

1. Copy the example configuration file:
   ```
   cp config/ztp_agent.ini.example ~/.ztp_agent.cfg
   ```
2. Edit the configuration file to set:
   - OpenRouter API key for the chat interface
   - Base configuration file (contains VLAN creation and other initial config)
   - Network settings including VLAN IDs (these should match the VLANs in the base config)
   - IP pool for management addresses (e.g., `192.168.10.0/24`)
   - Gateway for new devices

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

### Web Interface

Launch the modern web interface for the ZTP agent:
```bash
cd web_app
python3 run.py
```

The web interface will be available at `http://localhost:8000` and provides:

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

The ZTP process works as follows:

1. Add a seed switch to the inventory using `config switch <ip> <username> <password>`
2. Customize the base configuration file at `config/base_configuration.txt` if needed
3. Update the config file with management VLAN and wireless VLANs that match what's in the base config
4. Enable the ZTP process with `ztp enable`
5. The agent will automatically:
   - Discover neighboring devices using LLDP and L2 trace
   - Apply the base configuration (which creates VLANs with spanning tree and other initial config)
   - Configure trunk ports between switches with appropriate VLAN tagging
   - Configure AP ports with correct wireless VLAN tagging
   - Assign management IPs from the configured IP pool
   - Mark devices as configured once complete

The process runs continuously in the background, periodically checking for new devices and ensuring proper configuration.

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
ztp_agent/
├── cli/                      # Command-line interface
│   └── commands/             # Command modules for different CLI functions
├── network/                  # Network operations
│   └── switch/               # Switch operations, organized by function
│       ├── connection.py     # Core SSH connectivity
│       ├── configuration.py  # Switch configuration operations
│       ├── discovery.py      # Network discovery with LLDP
│       └── enums.py          # Switch-related enumerations
├── ztp/                      # ZTP process
├── agent/                    # AI agent
└── utils/                    # Utilities
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

### Extending the Tool

To add new commands to the CLI:
1. Either add new methods to an existing mixin in `ztp_agent/cli/commands/`
2. Or create a new command mixin file in `ztp_agent/cli/commands/` and add it to the class inheritance in `ztp_agent/cli/base.py`
3. Use the `@with_category` and `@with_argparser` decorators for command methods

To add new switch functionality:
1. Add methods to the appropriate file in `ztp_agent/network/switch/` based on the functionality
2. If adding an entirely new category of functionality, create a new module file

To add new AI agent capabilities:
1. Add new tools in `ztp_agent/agent/tools.py`
2. Update the tool list in `get_network_tools()`
