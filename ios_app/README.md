# RUCKUS ZTP Agent - iPhone App

Native iOS application providing full feature parity with the web interface for managing RUCKUS network devices.

## Features

The iOS app provides the same functionality as the web frontend with a mobile-optimized interface:

1. **Configuration Tab**
   - Manage credentials for switch access with native iOS forms
   - Configure seed switches with IP address validation
   - Upload base configurations using Files app integration
   - Configure AI agent settings (OpenRouter API key and model selection)
   - Set network parameters (VLANs, IP pools, gateway, DNS)
   - Start/stop ZTP process with real-time status indicators

2. **Monitoring Tab**
   - Real-time ZTP process status with pull-to-refresh
   - Monitor discovered switches and access points
   - Track configuration progress with detailed status indicators
   - View device details including IP, MAC, hostname, and model
   - SSH activity indicators and task completion status

3. **Topology Tab**
   - Interactive network topology with draggable nodes
   - Touch-optimized interface for mobile devices
   - Real-time updates of device connections
   - Switch-to-switch and AP-to-switch connection visualization
   - Auto-refresh and manual refresh options

4. **AI Agent Tab**
   - Natural language interface for network queries
   - Real-time streaming chat responses via WebSocket
   - Execute network commands through conversational interface
   - Get network insights and configuration assistance

5. **Logs Tab**
   - Real-time ZTP process logs with automatic updates
   - Search and filter log entries by level (info, warning, error)
   - Monospace font for better log readability

## Architecture

The app follows MVVM architecture with SwiftUI:

### Models (`Models/`)
- **ZTPModels.swift**: Data models matching backend API with Codable support
- **Config.swift**: Server configuration and endpoint definitions

### Views (`Views/`)
- **ConfigurationView.swift**: Credential and switch management with file upload
- **MonitoringView.swift**: Real-time device status with pull-to-refresh
- **TopologyView.swift**: Interactive network diagram with draggable nodes
- **ChatView.swift**: AI agent interface with streaming WebSocket responses
- **LogsView.swift**: System log viewer with search and filtering

### Managers (`Managers/`)
- **NetworkManager.swift**: API communication, WebSocket handling, and state management
- **ConfigurationManager.swift**: Local configuration state and persistence

### Technologies
- SwiftUI for declarative user interface
- URLSession for REST API communication
- URLSessionWebSocketTask for real-time chat streaming
- Combine framework for reactive programming and data binding
- Native iOS file picker for configuration upload

## Requirements

- iOS 15.0 or later
- Xcode 13+ for development
- Backend server accessible on network

## Setup

### For iOS Simulator (Development)
1. Open `ios_app/ruckus-ztp/ruckus-ztp.xcodeproj` in Xcode
2. The default configuration uses `localhost:8000` which works for simulator
3. Build and run (Cmd+R)

### For Real Device
1. Update `Models/Config.swift` with your Mac's IP address:
   ```swift
   static let baseURL = "http://192.168.1.100:8000"  // Your Mac's IP
   static let wsURL = "ws://192.168.1.100:8000/ws"
   ```
2. Ensure firewall allows connections on port 8000
3. Build and run on device

## API Integration

The app communicates with the same FastAPI backend as the web interface:

### REST Endpoints (Port 8000)
- `GET /api/config` - Application configuration
- `POST /api/config` - Update configuration  
- `GET /api/status` - ZTP process status
- `GET /api/devices` - Device list with status
- `POST /api/ztp/start` - Start ZTP process
- `POST /api/ztp/stop` - Stop ZTP process
- `GET /api/logs` - System logs
- `POST /api/base-configs` - Upload base configuration files

### WebSocket Endpoints
- `/ws/chat` - Real-time AI chat interface with streaming responses

## Key Features Implemented

### File Upload
- Native iOS file picker integration
- Multipart form data upload to `/api/base-configs`
- Support for .txt configuration files

### Real-time Updates
- WebSocket chat interface with streaming responses
- Periodic API polling for device status updates
- Pull-to-refresh for manual updates

### Touch Interface
- Draggable topology nodes optimized for touch
- Native iOS form controls and validation
- Smooth animations and transitions

### Error Handling
- Comprehensive network error handling
- JSON parsing error recovery with AnyCodable wrapper
- User-friendly error messages and retry mechanisms

## Troubleshooting

### Common Issues

1. **Cannot connect to backend:**
   - Verify backend server is running: `cd web_app && python run.py`
   - Check server IP in Config.swift (use Mac's IP for real devices)
   - Ensure firewall allows port 8000

2. **JSON parsing errors:**
   - Check Xcode console for detailed error messages
   - Verify backend API compatibility
   - AnyCodable wrapper handles complex neighbor data

3. **Chat not working:**
   - Ensure OpenRouter API key is configured in backend
   - Check WebSocket connection in network logs

### Debug Output
Enable debug output in Xcode console to see:
- API requests and responses
- JSON parsing details  
- WebSocket connection status
- Topology link creation debugging