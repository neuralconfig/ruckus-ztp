# Testing Plan for New Edge Agent Architecture

## Overview
This document outlines the testing strategy for the new ZTP Edge Agent architecture where:
- **Web App**: Configuration store and monitoring interface (Cloud Run)
- **Edge Agent**: Local ZTP process execution (Local network)

## Test Scenarios

### 1. Edge Agent Installation & Configuration
- [x] Install edge agent on local system
- [x] Generate configuration with unique agent ID and token
- [x] Start edge agent service
- [x] Verify agent connects to web app
- [x] Check agent registration in web interface

### 2. Web App Dashboard
- [x] Web app starts successfully
- [x] Dashboard shows connected edge agents
- [x] Agent status appears as "online"
- [x] ZTP status shows as available

### 3. ZTP Process Flow
- [ ] Configure ZTP settings in web app
- [ ] Send ZTP configuration to edge agent
- [ ] Edge agent starts ZTP process locally
- [ ] Monitor ZTP events in web interface
- [ ] Verify device discovery events
- [ ] Verify device configuration events

### 4. Event Reporting
- [ ] Edge agent sends events to web app
- [ ] Events appear in dashboard
- [ ] Events appear in events tab
- [ ] Device inventory updates in real-time

### 5. Error Handling
- [ ] Edge agent handles ZTP errors gracefully
- [ ] Error events are reported to web app
- [ ] Web app displays error status correctly

### 6. Connectivity & Resilience
- [ ] Edge agent reconnects after network interruption
- [ ] ZTP continues working during web app disconnection
- [ ] State synchronizes when connection is restored

## Test Environment Requirements

- Python 3.8+ with virtual environment
- Web app running (FastAPI/uvicorn)
- Local network access for edge agent
- Test configuration files

## Test Execution

### Prerequisites Check
1. Verify Python dependencies
2. Check configuration files exist
3. Ensure network connectivity
4. Validate API endpoints

### Basic Functionality Test
1. Start web application
2. Install and configure edge agent
3. Verify connection establishment
4. Test basic ZTP workflow

### Integration Test
1. Full ZTP configuration
2. Multi-device discovery simulation
3. Event flow verification
4. Dashboard monitoring

## Success Criteria

- ✅ Edge agent connects to web app successfully
- ✅ ZTP configuration is sent from web app to edge agent
- ✅ ZTP process runs locally on edge agent
- ✅ Events are reported back to web app in real-time
- ✅ Dashboard shows accurate status and statistics
- ✅ System handles errors and reconnections gracefully

## Known Limitations

- ZTP process may run in "SSH-only mode" if ztp_agent dependencies are not available
- WebSocket connection required for real-time updates
- Configuration changes require restart of edge agent service