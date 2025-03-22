#!/bin/bash

# Install dependencies
pip install -r requirements.txt

# Install the package in development mode
pip install -e .

# Copy example config if not exists
if [ ! -f ~/.ztp_agent.cfg ]; then
    cp config/ztp_agent.ini.example ~/.ztp_agent.cfg
    echo "Created config file at ~/.ztp_agent.cfg"
    echo "Please edit this file to configure your settings"
fi

# Run the agent
ztp-agent
