# Edge Agent Architecture Design

## Overview

This document outlines the architectural changes to move the ZTP process from the cloud-hosted web application to a local edge agent, reducing cloud communication and improving system efficiency.

## Current Architecture

```
┌─────────────────┐         ┌──────────────────┐
│   Web App       │ ◄─────► │   SSH Proxy      │
│  (Cloud Run)    │WebSocket│  (Local Network) │
│                 │         │                  │
│ - ZTP Process   │         │ - SSH Execution  │
│ - Monitoring    │         │   Only           │
│ - Configuration │         │                  │
└─────────────────┘         └──────────────────┘
                                     │
                                     ▼
                            ┌──────────────────┐
                            │  RUCKUS Switches │
                            └──────────────────┘
```

## Proposed Architecture

```
┌─────────────────┐         ┌──────────────────┐
│   Web App       │ ◄─────► │  ZTP Edge Agent  │
│  (Cloud Run)    │WebSocket│  (Local Network) │
│                 │ Events  │                  │
│ - Configuration │         │ - ZTP Process    │
│   Store         │         │ - SSH Execution  │
│ - Monitoring UI │         │ - Discovery      │
│ - API Gateway   │         │ - Configuration  │
└─────────────────┘         └──────────────────┘
                                     │
                                     ▼
                            ┌──────────────────┐
                            │  RUCKUS Switches │
                            └──────────────────┘
```

## Key Changes

### 1. Edge Agent (formerly SSH Proxy)
- **New Responsibilities:**
  - Runs the full ZTP process locally
  - Performs device discovery and configuration
  - Manages local device inventory
  - Reports events to web app (not continuous polling)
  
- **Event Types to Report:**
  - Device discovered
  - Device configured
  - Configuration error
  - Status changes
  - Periodic heartbeat with summary

### 2. Web Application
- **New Role:**
  - Configuration management (API key, VLANs, IP pools)
  - Monitoring dashboard
  - Historical data storage
  - User interface for viewing network state
  - Chat interface (commands forwarded to edge agent)

### 3. Communication Pattern
- **Before:** Continuous bidirectional commands and responses
- **After:** Event-driven updates from edge to cloud
  - Edge agent pushes events when state changes
  - Web app can request full inventory refresh
  - Chat commands are forwarded but results are streamed

## Benefits

1. **Reduced Cloud Costs**
   - Minimal egress traffic (events only, not continuous SSH traffic)
   - Stays within Cloud Run free tier limits
   
2. **Better Performance**
   - ZTP runs locally with direct network access
   - No latency for SSH commands
   - Faster discovery and configuration
   
3. **Improved Reliability**
   - Edge agent continues operating if cloud connection drops
   - Local state maintained at edge
   - Automatic reconnection and state sync

4. **Scalability**
   - Multiple edge agents can connect to single web app
   - Each edge agent manages its local network segment
   - Cloud app becomes multi-tenant capable

## Implementation Plan

### Phase 1: Rename and Refactor
1. Rename `ssh_proxy` to `ztp_edge_agent`
2. Update all references in code and documentation
3. Maintain backward compatibility temporarily

### Phase 2: Move ZTP Process
1. Import ZTPProcess into edge agent
2. Initialize and run ZTP loop in edge agent
3. Remove ZTP process from web app

### Phase 3: Event System
1. Define event message protocol
2. Implement event publishing in edge agent
3. Add event handlers in web app
4. Update database schema for event storage

### Phase 4: Web App Refactor
1. Remove direct SSH execution code
2. Focus on configuration API endpoints
3. Enhance monitoring UI with event data
4. Update chat interface to forward commands

### Phase 5: Testing and Deployment
1. Test edge agent locally
2. Test cloud communication
3. Update deployment documentation
4. Create migration guide

## Event Protocol

### Event Message Format
```json
{
  "event_type": "device_discovered|device_configured|error|heartbeat",
  "timestamp": "2024-01-20T10:30:00Z",
  "agent_id": "edge-agent-1",
  "data": {
    // Event-specific data
  }
}
```

### Example Events

**Device Discovered:**
```json
{
  "event_type": "device_discovered",
  "timestamp": "2024-01-20T10:30:00Z",
  "agent_id": "edge-agent-1",
  "data": {
    "mac_address": "00:11:22:33:44:55",
    "ip_address": "192.168.1.100",
    "device_type": "switch",
    "model": "ICX7150-48P",
    "hostname": "switch-1"
  }
}
```

**Configuration Complete:**
```json
{
  "event_type": "device_configured",
  "timestamp": "2024-01-20T10:35:00Z",
  "agent_id": "edge-agent-1",  
  "data": {
    "mac_address": "00:11:22:33:44:55",
    "configuration_applied": ["hostname", "vlans", "management_ip"],
    "status": "success"
  }
}
```

**Heartbeat:**
```json
{
  "event_type": "heartbeat",
  "timestamp": "2024-01-20T11:00:00Z",
  "agent_id": "edge-agent-1",
  "data": {
    "devices_total": 15,
    "devices_configured": 12,
    "devices_pending": 3,
    "uptime_seconds": 3600
  }
}
```

## Migration Strategy

1. **Dual Mode Operation**
   - Keep both architectures working initially
   - Add feature flag to switch between modes
   - Test thoroughly before deprecating old mode

2. **Gradual Rollout**
   - Deploy to test environment first
   - Monitor performance and reliability
   - Roll out to production sites gradually

3. **Rollback Plan**
   - Maintain ability to switch back to old architecture
   - Keep SSH proxy functionality intact initially
   - Remove only after successful migration