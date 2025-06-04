# RUCKUS ZTP Deployment Status

## Completed Tasks

### 1. SSH Proxy Development ✅
- Created complete SSH proxy application in `ssh_proxy/` directory
- WebSocket client for backend communication
- SSH command execution handler
- Systemd service configuration
- Installation script and documentation

### 2. Backend Deployment to Google Cloud Run ✅
- Successfully deployed to Cloud Run (free tier configuration)
- Service URL: https://ruckus-ztp-backend-j6lb5kbmeq-uc.a.run.app
- Configured for public access (unauthenticated)
- API endpoint working: `/api/status` returns correct JSON

### 3. Domain Configuration ✅
- **API Domain**: ruckusztpapi.neuralconfig.com
  - CNAME record added to Namecheap pointing to `ghs.googlehosted.com.`
  - DNS propagated successfully
  - SSL certificate pending (as of deployment time)
  
- **Frontend Domain**: ruckusztp.neuralconfig.com  
  - CNAME record added to Namecheap pointing to `ghs.googlehosted.com.`
  - DNS propagated successfully
  - SSL certificate pending (as of deployment time)

## Current Status

- Both domains point to the same Cloud Run service (which includes both frontend and API)
- Waiting for SSL certificates to be provisioned by Google (typically 15-30 minutes)
- Connection shows "connection closed" error until certificates are ready

## Next Steps

### 1. Verify SSL Certificates
Once certificates are provisioned (check in ~30 minutes):
```bash
# Test both domains
curl https://ruckusztpapi.neuralconfig.com/api/status
curl https://ruckusztp.neuralconfig.com/
```

### 2. Deploy SSH Proxy
On your Linux server:
```bash
# Generate authentication token
openssl rand -hex 32

# Install SSH proxy
cd ruckus-ztp
sudo ./ssh_proxy/install.sh

# Configure with token and WebSocket URL
sudo nano /etc/ruckus-ztp-proxy/config.ini
# Set: url = wss://ruckusztpapi.neuralconfig.com/ws/ssh-proxy

# Start service
sudo systemctl start ruckus-ztp-proxy
sudo systemctl enable ruckus-ztp-proxy
```

### 3. Configure Backend for SSH Proxy
- Add token validation to backend
- Test proxy connection through API

### 4. Run Frontend Locally (Optional)
If you want to run the frontend locally instead:
```bash
cd web_app
export BACKEND_URL="https://ruckusztpapi.neuralconfig.com"
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

## Important URLs

- **Frontend**: https://ruckusztp.neuralconfig.com/
- **API**: https://ruckusztpapi.neuralconfig.com/api/status
- **SSH Proxy WebSocket**: wss://ruckusztpapi.neuralconfig.com/ws/ssh-proxy

## Architecture Summary

```
[RUCKUS Switches] <--SSH--> [Linux Server with SSH Proxy]
                                      |
                                      | WebSocket
                                      v
                            [Cloud Run Backend/Frontend]
                                      ^
                                      | HTTPS
                                      |
                              [Web Browser/iOS App]
```

## Notes

- Using Google Cloud Run free tier (256Mi RAM, 1 CPU, scales to zero)
- Single Cloud Run service serves both frontend and API
- SSH proxy creates outbound WebSocket connection (no inbound firewall rules needed)
- All infrastructure designed to minimize costs and stay within free tier limits