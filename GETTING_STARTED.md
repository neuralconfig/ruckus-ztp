# Getting Started with RUCKUS ZTP Agent

This guide will help you get started with the RUCKUS ZTP Agent.

## Installation

### Prerequisites

- Python 3.8 or higher
- pip package manager
- Network access to your RUCKUS switches

### Steps

1. **Install Dependencies**

   ```bash
   pip install -r requirements.txt
   ```

2. **Install the Package**

   ```bash
   pip install -e .
   ```

   This installs the package in development mode, allowing you to modify the code without reinstalling.

3. **Configure the Agent**

   ```bash
   cp config/ztp_agent.ini.example ~/.ztp_agent.cfg
   ```

   Edit `~/.ztp_agent.cfg` with your preferred text editor to set:
   - Network settings (VLANs, IP pool)
   - OpenRouter API key (for AI chat interface)
   - Switch credentials

## Using the ZTP Agent

### Starting the Agent

Run the agent from the command line:

```bash
ztp-agent
```

You'll see the CLI prompt:

```
====================================
 RUCKUS ZTP Agent CLI
====================================
Type 'help' or '?' for available commands.

ztp-agent>
```

### Basic Workflow

1. **Add a Seed Switch**

   ```
   ztp-agent> config switch 192.168.1.1 admin password
   ```

2. **Enable ZTP Process**

   ```
   ztp-agent> ztp enable
   ```

3. **Monitor Progress**

   ```
   ztp-agent> show switches
   ztp-agent> show aps
   ztp-agent> show ztp
   ```

4. **Use Chat Interface for Advanced Operations**

   ```
   ztp-agent> chat
   
   You: Show me the status of all ports on switch 192.168.1.1
   ```

### Getting Help

- For a list of all commands: `help`
- For help with a specific command: `help <command>`
- For command completions: press TAB
- For command options: type `?`

## Troubleshooting

- Check the log file at `~/.ztp_agent.log` for detailed information
- Ensure your switch credentials are correct
- Verify network connectivity to the switches
- Make sure the required ports are open (SSH - TCP/22)

## Next Steps

- Add more switches through the CLI
- Configure custom VLANs in the config file
- Use the chat interface for complex operations
- Extend the tool with your own custom commands
