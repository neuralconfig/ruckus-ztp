#!/bin/bash

# Create a virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "Virtual environment created"
fi

# Activate the virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Install the package in development mode
echo "Installing package in development mode..."
pip install -e .

# Copy example config if not exists
if [ ! -f ~/.ztp_agent.cfg ]; then
    cp config/ztp_agent.ini.example ~/.ztp_agent.cfg
    echo "Created config file at ~/.ztp_agent.cfg"
    echo "Please edit this file to configure your settings"
fi

echo "Setup complete. Starting ZTP agent..."

# Run the agent
ztp-agent

# Deactivate the virtual environment when done
deactivate
