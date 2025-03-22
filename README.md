# RUCKUS ZTP Agent

A Zero-Touch Provisioning (ZTP) agent for RUCKUS ICX switches and APs.

## Overview

This tool provides a network engineer-friendly command-line interface for automating the discovery, configuration, and management of RUCKUS network devices. Starting with a single seed switch, the ZTP agent can discover and configure connected devices with minimal manual intervention.

Key features:
- Command-line interface with tab completion and help system
- Automatic device discovery using LLDP
- Automated switch and AP configuration
- Chat interface powered by AI for natural language configuration

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
2. Edit the configuration file to set your OpenRouter API key and other settings.

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
- `show switches` - Show configured switches
- `show aps` - Show discovered APs
- `show ztp` - Show ZTP status
- `chat` - Enter chat interface with AI agent

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
├── cli/            # Command-line interface
├── network/        # Network operations
├── ztp/            # ZTP process
├── agent/          # AI agent
└── utils/          # Utilities
```

### Extending the Tool

To add new commands to the CLI:
1. Edit `ztp_agent/cli/base.py`
2. Add new command methods using the `@with_category` and `@with_argparser` decorators

To add new AI agent capabilities:
1. Add new tools in `ztp_agent/agent/tools.py`
2. Update the tool list in `get_network_tools()`
