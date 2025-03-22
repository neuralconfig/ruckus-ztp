# Testing the RUCKUS ZTP Agent

This document provides guidance on testing the RUCKUS ZTP Agent with real hardware.

## Prerequisites

- RUCKUS ICX switch(es) with SSH access
- RUCKUS AP(s) connected to the switch(es)
- Network connectivity between your computer and the switch(es)

## Setup for Testing

1. Activate the virtual environment:
   ```bash
   ./activate_venv.sh
   ```

2. Verify installation is working:
   ```bash
   ./test_installation.py
   ```

3. Copy and edit the configuration file:
   ```bash
   cp config/ztp_agent.ini.example ~/.ztp_agent.cfg
   ```
   
   Edit `~/.ztp_agent.cfg` with your preferred text editor to set:
   - Switch credentials
   - Network settings (VLANs, IP pool)
   - OpenRouter API key (for AI chat interface)

## Testing with Real Hardware

### Basic Workflow

1. Start the ZTP agent:
   ```bash
   ztp-agent
   ```

2. Add your first switch:
   ```
   ztp-agent> config switch 192.168.1.1 admin password
   ```

3. Enable the ZTP process:
   ```
   ztp-agent> ztp enable
   ```

4. Monitor the ZTP process:
   ```
   ztp-agent> show switches
   ztp-agent> show aps
   ztp-agent> show ztp
   ```

### Using the Chat Interface

The chat interface allows you to interact with the switches using natural language:

1. Enter chat mode:
   ```
   ztp-agent> chat
   ```

2. Example commands:
   ```
   You: What switches are available?
   You: Check the status of port 1/1/1 on switch 192.168.1.1
   You: Change VLAN on port 1/1/2 to VLAN 20
   You: Disable PoE on port 1/1/3
   ```

3. Exit chat mode:
   ```
   You: exit
   ```

## Troubleshooting

- Check the log file at `~/.ztp_agent.log` for detailed information
- Ensure your switch credentials are correct
- Verify network connectivity to the switches
- Make sure the required ports are open (SSH - TCP/22)

## Common Issues

- **Connection timeout**: Check that the switch is reachable from your computer
- **Authentication failure**: Verify username and password
- **Command error**: Ensure the switch model is supported
- **LLDP not working**: Make sure LLDP is enabled on the switch

## Reporting Issues

If you encounter issues, please report them on GitHub with:
1. Error message and relevant log entries
2. Switch model and firmware version
3. Steps to reproduce the issue