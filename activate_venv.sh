#!/bin/bash

# Create a virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "Virtual environment created"
    
    # Install dependencies and package in development mode
    source venv/bin/activate
    echo "Installing dependencies..."
    pip install -r requirements.txt
    echo "Installing package in development mode..."
    pip install -e .
    echo "Setup complete"
else
    # Just activate if venv exists
    source venv/bin/activate
    echo "Virtual environment activated"
    echo "Use 'deactivate' when you're done"
fi

# Print guidance
echo ""
echo "You can now run the ZTP agent with: ztp-agent"
echo "To run tests (when implemented): pytest"
echo ""