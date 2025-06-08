# ZTP Edge Agent Testing Guide

This document outlines the testing procedures for the RUCKUS ZTP Edge Agent system after the architectural transformation from SSH proxy to local ZTP execution.

## Overview

We've implemented a comprehensive ZTP Edge Agent system that executes ZTP processes locally at the edge with cloud monitoring and management. Key features include:

- **Local ZTP execution**: Full ZTP process runs locally on edge agents, reducing cloud costs
- **Event-driven communication**: Real-time events pushed to cloud dashboard
- **Multi-agent support**: Single web dashboard manages multiple edge agents
- **WebSocket communication**: Bi-directional real-time messaging with automatic reconnection
- **Modern UI**: New dashboard with real-time monitoring and statistics

## Testing Environment

### Current Deployment
- **Cloud Dashboard**: Google Cloud Run at `https://ruckusztp.neuralconfig.com`
- **Edge Agents**: Local installations on network-connected devices (Ubuntu/Debian recommended)
- **Feature Branch**: `feature/ssh-proxy` (contains edge agent implementation)

## Pre-Testing Checklist

### 1. Verify Cloud Dashboard Deployment
```bash
# Check if the web application is accessible
curl -I https://ruckusztp.neuralconfig.com

# Expected: HTTP 200 response with new dashboard interface
```

### 2. Verify Edge Agent Installation
```bash
# On the edge device, check if service is installed
sudo systemctl status ruckus-ztp-edge-agent

# Check configuration file exists and has correct values
sudo cat /etc/ruckus-ztp-edge-agent/config.ini

# Expected sections: [agent], [network], [backend], [logging], [ztp]
```

### 3. Generate Fresh Agent Credentials
```bash
# On edge device, install and configure the agent
cd /path/to/ztp_edge_agent
sudo ./install.sh

# Save the generated agent ID and token for dashboard registration
```

## Testing Procedures

### Phase 1: Edge Agent Connection Testing

#### 1.1 Start Edge Agent Service
```bash
# On edge device
sudo systemctl start ruckus-ztp-edge-agent
sudo systemctl enable ruckus-ztp-edge-agent

# Monitor startup logs
sudo journalctl -u ruckus-ztp-edge-agent -f
```

**Expected behavior:**
- ✅ Service starts without errors
- 🚀 Connection attempt to cloud dashboard WebSocket
- ✅ WebSocket connection established 
- 📋 Agent registration sent to dashboard
- 💓 Heartbeat events every 60 seconds
- 🔍 Local ZTP process initialization

#### 1.2 Verify Agent Registration
```bash
# Test edge agents API endpoint
curl https://ruckusztp.neuralconfig.com/api/edge-agents

# Expected: JSON array with your agent listed
```

### Phase 2: Dashboard Interface Testing

#### 2.1 Access New Dashboard
1. Navigate to `https://ruckusztp.neuralconfig.com`
2. Check the new **Dashboard** tab (default view)
3. Verify **Edge Agents** tab shows connected agents
4. Check **Events** tab for real-time event stream

#### 2.2 Monitor Edge Agent Status
1. In **Edge Agents** tab, verify your agent appears
2. Check agent status (Connected/Disconnected)
3. Review agent details (IP, hostname, last seen)
4. Test **View Logs** button for agent-specific logs

**Expected behavior:**
- Agent appears in dashboard after registration
- Status shows "Connected" with green indicator
- Last seen timestamp updates regularly
- Agent details display correctly

#### 2.3 Test Local ZTP Execution
1. Configure seed switches in **Configuration** tab
2. The ZTP process now runs automatically on the edge agent
3. Monitor progress in **Dashboard** and **Events** tabs
4. Check **Monitoring** tab for device inventory

**Expected behavior:**
- ZTP events appear in real-time in Events tab
- Dashboard statistics update (devices discovered, configured)
- Local ZTP process executes without cloud dependency
- Events include: device_discovered, device_configured, error, heartbeat

### Phase 3: Event Processing and Stability Testing

#### 3.1 Monitor Edge Agent Logs
```bash
# Watch edge agent logs for events and connection issues
sudo journalctl -u ruckus-ztp-edge-agent -f

# Look for these indicators:
# ✅ - Successful operations
# ❌ - Errors or failures  
# 💓 - Heartbeat events
# 📨 - Event publishing
# 🔍 - ZTP process updates
# 🔧 - Local SSH operations
```

#### 3.2 Verify Event Flow
- **Architecture**: Local ZTP execution with event-driven communication
- **Events**: device_discovered, device_configured, error, heartbeat
- **Rate Limiting**: 30 requests/minute per agent built into dashboard
- **Test**: Let ZTP run and verify events flow properly to dashboard

#### 3.3 WebSocket Stability Test
- **Improvements**: Automatic reconnection, connection health monitoring
- **Local Resilience**: ZTP continues during temporary dashboard disconnection
- **Test**: Let system run for several hours, verify reconnection behavior

### Phase 4: Functional Testing

#### 4.1 AI Agent Chat Testing
1. Go to **AI Agent** tab
2. Test commands that now execute locally on edge agent:
   - "Show me all switches in the network"
   - "What's the status of ZTP process?"
   - "Get the running config for switch X.X.X.X"

**Expected behavior:**
- Commands execute locally on edge agent
- Results streamed back through WebSocket
- Events logged in Events tab
- No dependency on cloud connectivity for device access

#### 4.2 Local Network Operations
Test edge agent's local network operations:
1. Device discovery (runs continuously)
2. Switch configuration (automatic based on base config)
3. Port status monitoring
4. LLDP neighbor discovery
5. Inventory management (local database)

### Phase 5: Error Handling Testing

#### 5.1 Dashboard Connectivity Testing
1. Temporarily block internet access on edge agent
2. Verify ZTP continues to run locally
3. Check reconnection behavior when restored
4. Verify events are queued and sent when reconnected

#### 5.2 Authentication Testing
1. Test with invalid agent token
2. Verify proper error handling in dashboard
3. Test agent re-registration scenarios

## Expected Debug Log Patterns

### Successful Local ZTP Operations
```
🔍 ZTP Discovery: Found device 192.168.1.100 (RUCKUS ICX-7150)
🔧 Local SSH to 192.168.1.100: show version
✅ Device configured successfully: 192.168.1.100
📨 Event published: device_configured
```

### Event Publishing and Connection Health
```
💓 Heartbeat event sent to dashboard
📨 Publishing event: device_discovered
✅ WebSocket connection healthy
🔧 Local ZTP process running (iteration #45)
```

### Edge Agent Resilience
```
❌ Dashboard connection lost, continuing local operations
🔄 Attempting reconnection to dashboard...
✅ Dashboard reconnected, syncing queued events
```

## Troubleshooting Common Issues

### Issue: Edge Agent Not Appearing in Dashboard
**Solution:**
1. Check edge agent service status: `sudo systemctl status ruckus-ztp-edge-agent`
2. Verify WebSocket connection in logs
3. Check firewall settings for outbound connections
4. Confirm dashboard URL in agent config

### Issue: Local ZTP Not Discovering Devices
**Solution:**
1. Check network connectivity from edge agent to target devices
2. Verify SSH credentials are correct in configuration
3. Check LLDP discovery is enabled on network switches
4. Monitor edge agent logs for specific error messages

### Issue: Dashboard Connection Issues
**Solution:**
1. Check for rate limiting in dashboard logs (30 req/min per agent)
2. Verify agent authentication token
3. Monitor network stability between agent and dashboard
4. Check WebSocket connection health indicators

## Success Criteria

The testing is successful if:

1. ✅ Edge agent connects and registers with dashboard
2. ✅ Dashboard shows agent in Edge Agents tab with correct status
3. ✅ Local ZTP process runs continuously and discovers/configures devices
4. ✅ Real-time events flow from edge agent to dashboard
5. ✅ AI agent commands execute locally with results streamed back
6. ✅ System continues ZTP operations during dashboard disconnection
7. ✅ Dashboard provides comprehensive monitoring and statistics
8. ✅ Multi-agent architecture supports multiple edge deployments

## Next Steps After Testing

If testing is successful:

1. **Merge to main branch**: `git checkout main && git merge feature/ssh-proxy`
2. **Production deployment**: Deploy dashboard and edge agents to production
3. **Documentation**: Update README with edge agent architecture details
4. **Monitoring**: Implement production monitoring for multi-agent deployments

If issues are found:
1. Document specific failures and error messages
2. Check recent commits for potential regression
3. Review edge agent configuration and network connectivity
4. Test fixes on feature branch before retrying

## Notes

- **Architecture**: Local ZTP execution with event-driven dashboard communication
- **Python Version**: Edge agent compatible with Python 3.6+ for Ubuntu 18.04+
- **Logging Level**: Set to DEBUG for comprehensive troubleshooting
- **WebSocket Connection**: Persistent connection with automatic reconnection
- **Rate Limits**: 30 requests/minute per agent built into dashboard
- **Local Resilience**: ZTP continues during dashboard connectivity issues
- **Event Types**: device_discovered, device_configured, error, heartbeat