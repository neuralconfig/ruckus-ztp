# Ruckus ZTP iOS App

This is the iOS frontend for the Ruckus Zero-Touch Provisioning (ZTP) system.

## Features

The iOS app provides the same functionality as the web frontend:

1. **Configuration Tab**
   - Manage credentials for switch access
   - Configure seed switches
   - Upload and select base configurations
   - Configure AI agent settings (OpenRouter API key and model selection)
   - Set network parameters (VLANs, IP pools, etc.)

2. **Monitoring Tab**
   - View ZTP process status
   - Monitor discovered switches and access points
   - Track configuration progress
   - View device details and connection status

3. **Topology Tab**
   - Visual network topology display
   - Real-time updates of network connections
   - Export topology diagrams

4. **AI Agent Tab**
   - Natural language interface for network queries
   - Execute network commands via chat
   - Get network insights and recommendations

5. **Logs Tab**
   - View real-time ZTP process logs
   - Filter and search log entries

## Architecture

The app uses:
- SwiftUI for the user interface
- URLSession for REST API communication
- URLSessionWebSocketTask for real-time WebSocket updates
- Combine framework for reactive programming
- Swift Charts for topology visualization

## Requirements

- iOS 15.0+
- Xcode 14+
- Swift 5.7+

## Setup

1. Open `RuckusZTP.xcodeproj` in Xcode
2. Update the API endpoint in `Config.swift` to point to your backend server
3. Build and run on simulator or device

## API Integration

The app communicates with the FastAPI backend running at:
- REST endpoints: `http://<server>:8080/api/*`
- WebSocket: `ws://<server>:8080/ws`