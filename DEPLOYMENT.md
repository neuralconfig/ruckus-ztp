# RUCKUS ZTP Agent Deployment Guide

This guide covers deploying the RUCKUS ZTP Agent including the web application, iPhone app, and CLI tool.

## Overview

The RUCKUS ZTP Agent provides multiple interfaces for managing network devices:

### Web Application
- Configuration management for credentials, switches, and network settings
- Real-time monitoring of the ZTP process
- Interactive network topology visualization
- AI agent integration with OpenRouter
- Modern responsive design

### iPhone App
- Native iOS application with full feature parity
- Touch-optimized interface with draggable topology
- Real-time WebSocket chat interface
- File upload integration with iOS Files app
- Pull-to-refresh and native form controls

### Command Line Interface
- Tab completion and help system
- Direct SSH access to switches
- Batch operations and scripting support

## Local Development and Testing

### Prerequisites

- Python 3.9+
- Virtual environment (recommended)
- Git

### Quick Start

1. **Clone and navigate to the project:**
   ```bash
   git clone <your-repo>
   cd ruckus-ztp
   ```

2. **Create and activate virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install the ZTP agent package:**
   ```bash
   pip install -e .
   ```

5. **Test the web application:**
   ```bash
   cd web_app
   python test_webapp.py
   ```

6. **Run the web application:**
   ```bash
   python run.py
   ```
   
   Or with auto-reload for development:
   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

7. **Access the web interface:**
   Open your browser to `http://localhost:8000`

### iPhone App Development Setup

1. **Open the iOS project:**
   ```bash
   cd ios_app
   open ruckus-ztp/ruckus-ztp.xcodeproj
   ```

2. **Configure backend URL for simulator:**
   - Default Config.swift uses `localhost:8000` (works for simulator)
   - No changes needed for simulator development

3. **Configure for real device:**
   Edit `ios_app/ruckus-ztp/ruckus-ztp/Models/Config.swift`:
   ```swift
   // Update with your Mac's IP address
   static let baseURL = "http://192.168.1.100:8000"
   static let wsURL = "ws://192.168.1.100:8000/ws"
   ```

4. **Build and run:**
   - Select your target device or simulator
   - Press Cmd+R to build and run

5. **Enable network access:**
   - Ensure Mac firewall allows connections on port 8000
   - For real devices, backend must be accessible on local network

### Configuration

The web application uses the following configuration structure:

- **Credentials**: Username/password pairs for switch access (super/sp-admin pre-loaded)
- **Preferred Password**: Password to set on switches during first-time login
- **Seed Switches**: IP addresses of initial switches to discover from
- **Base Configuration**: RUCKUS CLI commands to apply to new switches
- **Network Settings**: VLANs, IP pools, gateway configuration
- **AI Agent**: OpenRouter API key and model selection

## Production Deployment on Google Cloud Run

### Prerequisites

- Google Cloud Project with billing enabled
- APIs enabled: Cloud Run, Cloud Build, Container Registry
- gcloud CLI installed and configured
- Docker installed (for local builds)

### Step 1: Prepare Google Cloud Project

1. **Set up your project:**
   ```bash
   export PROJECT_ID=your-gcp-project-id
   gcloud config set project $PROJECT_ID
   ```

2. **Enable required APIs:**
   ```bash
   gcloud services enable cloudbuild.googleapis.com
   gcloud services enable run.googleapis.com
   gcloud services enable containerregistry.googleapis.com
   ```

### Step 2: Deploy Using Cloud Build (Recommended)

1. **Set up automatic deployment:**
   ```bash
   # From the web_app directory
   cd web_app
   
   # Submit build to Cloud Build
   gcloud builds submit --config cloudbuild.yaml .
   ```

2. **Set up continuous deployment (optional):**
   ```bash
   # Create a trigger for automatic builds on git push
   gcloud builds triggers create github \
     --repo-name=your-repo-name \
     --repo-owner=your-github-username \
     --branch-pattern="^main$" \
     --build-config=web_app/cloudbuild.yaml
   ```

### Step 3: Manual Docker Deployment

If you prefer manual deployment:

1. **Build and push Docker image:**
   ```bash
   cd web_app
   
   # Build the image
   docker build -t gcr.io/$PROJECT_ID/ztp-agent-web .
   
   # Push to Container Registry
   docker push gcr.io/$PROJECT_ID/ztp-agent-web
   ```

2. **Deploy to Cloud Run:**
   ```bash
   gcloud run deploy ztp-agent-web \
     --image gcr.io/$PROJECT_ID/ztp-agent-web \
     --platform managed \
     --region us-central1 \
     --allow-unauthenticated \
     --port 8080 \
     --memory 512Mi \
     --cpu 1 \
     --max-instances 10
   ```

### Step 4: Configure Domain (Optional)

1. **Map custom domain:**
   ```bash
   gcloud run domain-mappings create \
     --service ztp-agent-web \
     --domain your-domain.com \
     --region us-central1
   ```

2. **Update DNS records as instructed by the output**

## Configuration for Production

### Environment Variables

Set these in Cloud Run if needed:

```bash
gcloud run services update ztp-agent-web \
  --set-env-vars="LOG_LEVEL=info,PORT=8080" \
  --region us-central1
```

### Security Considerations

1. **Authentication**: Consider adding authentication for production use
2. **HTTPS**: Cloud Run automatically provides HTTPS
3. **Network Access**: Ensure the Cloud Run service can reach your switches
4. **Secrets**: Use Google Secret Manager for sensitive configuration

### Monitoring and Logging

1. **View logs:**
   ```bash
   gcloud logs read --service=ztp-agent-web --limit=100
   ```

2. **Set up monitoring:**
   - Cloud Run automatically provides basic metrics
   - Set up alerting in Cloud Monitoring if needed

## Networking Considerations

### For Local Development

- The web application runs on localhost and can access switches on your local network
- Ensure your development machine can reach the target switches via SSH

### For Cloud Run Deployment

- **VPC Connector**: If switches are on private networks, set up VPC connector:
  ```bash
  gcloud compute networks vpc-access connectors create ztp-connector \
    --region us-central1 \
    --subnet your-subnet \
    --subnet-project $PROJECT_ID
  
  gcloud run services update ztp-agent-web \
    --vpc-connector ztp-connector \
    --region us-central1
  ```

- **Static IP**: For consistent outbound IP, use Cloud NAT
- **Firewall Rules**: Ensure switches allow SSH from Cloud Run IPs

## Usage Workflow

1. **Access the web interface** at your deployed URL
2. **Configure credentials** - add switch username/password pairs
3. **Set preferred password** for first-time login password changes
4. **Add seed switches** by IP address
5. **Select or upload base configuration** for switch setup
6. **Configure network settings** (VLANs, IP pools, etc.)
7. **Add OpenRouter API key** for AI agent functionality
8. **Start the ZTP process** from the Monitoring tab
9. **Monitor progress** and view discovered devices
10. **Visualize topology** in the Topology tab

## Troubleshooting

### Common Issues

1. **Can't reach switches:**
   - Check network connectivity from deployment environment
   - Verify switch SSH access and credentials
   - Check firewall rules

2. **ZTP process fails:**
   - Check logs for detailed error messages
   - Verify base configuration syntax
   - Ensure switch credentials are correct

3. **Web application won't start:**
   - Check that all dependencies are installed
   - Verify Python version compatibility
   - Check for port conflicts

### Debugging

1. **Local debugging:**
   ```bash
   # Enable debug mode
   export LOG_LEVEL=debug
   python run.py
   ```

2. **Cloud Run debugging:**
   ```bash
   # View detailed logs
   gcloud logs read --service=ztp-agent-web --format=json
   
   # Access Cloud Run instance
   gcloud run services proxy ztp-agent-web --port 8080
   ```

### Support

- Check application logs for detailed error information
- Verify network connectivity between deployment and switches
- Ensure all required APIs and permissions are enabled
- Test with a simple switch configuration first

## Scaling and Performance

### Cloud Run Scaling

- **Concurrency**: Default 80 concurrent requests per instance
- **Memory**: 512Mi default, increase if needed for large topologies
- **CPU**: 1 vCPU default, suitable for most deployments
- **Max Instances**: Set based on expected load

### Performance Optimization

- **Polling Interval**: Adjust based on network size and change frequency
- **Database**: Consider adding persistent storage for large deployments
- **Caching**: Implement caching for topology data if needed

## Cost Optimization

### Cloud Run Costs

- Pay per request and compute time
- 2 million requests per month free tier
- Optimize memory and CPU allocation
- Set max instances to control costs

### Monitoring Costs

```bash
# Monitor usage
gcloud run services describe ztp-agent-web \
  --region us-central1 \
  --format="get(status.traffic[0].url)"
```

This deployment guide should get you started with both local development and production deployment on Google Cloud Run.