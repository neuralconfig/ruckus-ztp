# RUCKUS ZTP Agent Web Application

A modern web interface for the RUCKUS Zero-Touch Provisioning Agent with a retro hacker theme.

## Features

- **Configuration Management**: Set up credentials, seed switches, and network settings
- **Base Configuration Upload**: Use default configurations or upload custom ones
- **Real-time Monitoring**: Track ZTP process status and discovered devices
- **Network Topology Visualization**: Interactive diagram of discovered network devices
- **AI Agent Integration**: Configure OpenRouter API key and model selection
- **Responsive Design**: Works on desktop and mobile devices

## Local Development

### Prerequisites

- Python 3.9+
- Virtual environment recommended

### Installation

1. Navigate to the web_app directory:
   ```bash
   cd web_app
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Install the ZTP agent package (from project root):
   ```bash
   cd ..
   pip install -e .
   cd web_app
   ```

4. Run the application:
   ```bash
   python main.py
   ```

5. Open your browser to `http://localhost:8000`

### Development with auto-reload:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Configuration

The web application allows you to configure all aspects of the ZTP agent:

### Credentials
- Default super/sp-admin credentials are pre-loaded
- Add additional credential pairs as needed
- Set a preferred password for first-time logins

### Seed Switches
- Add seed switch IP addresses
- Assign credentials to each switch
- Supports multiple seed switches

### Base Configuration
- Select from available base configurations
- Upload custom configuration files
- Preview configuration before use

### Network Settings
- Management VLAN configuration
- Wireless VLANs setup
- IP pool and gateway settings
- Poll interval adjustment

### AI Agent
- OpenRouter API key configuration
- Model selection (Claude, GPT, etc.)

## Deployment to Google Cloud Run

### Prerequisites

- Google Cloud Project with billing enabled
- Cloud Run API enabled
- Cloud Build API enabled
- Container Registry API enabled
- gcloud CLI installed and configured

### Manual Deployment

1. Build and push the Docker image:
   ```bash
   # Set your project ID
   export PROJECT_ID=your-gcp-project-id
   
   # Build the image
   docker build -t gcr.io/$PROJECT_ID/ztp-agent-web .
   
   # Push to Container Registry
   docker push gcr.io/$PROJECT_ID/ztp-agent-web
   ```

2. Deploy to Cloud Run:
   ```bash
   gcloud run deploy ztp-agent-web \
     --image gcr.io/$PROJECT_ID/ztp-agent-web \
     --platform managed \
     --region us-central1 \
     --allow-unauthenticated \
     --port 8080 \
     --memory 512Mi \
     --cpu 1
   ```

### Automated Deployment with Cloud Build

1. Set up Cloud Build trigger:
   ```bash
   gcloud builds triggers create github \
     --repo-name=your-repo-name \
     --repo-owner=your-github-username \
     --branch-pattern="^main$" \
     --build-config=web_app/cloudbuild.yaml
   ```

2. Push to main branch to trigger deployment

### Environment Variables

Set these environment variables in Cloud Run if needed:

- `PORT`: Port to run the application (default: 8080)
- `LOG_LEVEL`: Logging level (default: info)

## API Endpoints

### Configuration
- `GET /api/config` - Get current configuration
- `POST /api/config` - Update configuration

### Base Configurations
- `GET /api/base-configs` - Get available base configurations
- `POST /api/base-configs` - Upload new base configuration

### ZTP Process
- `GET /api/status` - Get ZTP process status
- `POST /api/ztp/start` - Start ZTP process
- `POST /api/ztp/stop` - Stop ZTP process

### Devices
- `GET /api/devices` - Get discovered devices

### Logs
- `GET /api/logs` - Get application logs

## Architecture

### Backend (FastAPI)
- RESTful API endpoints
- Async request handling
- Integration with ZTP agent core
- Background task management

### Frontend (HTML/CSS/JavaScript)
- Retro hacker theme with neon green accents
- Responsive grid layout
- Real-time status updates
- Interactive network topology with D3.js

### Data Flow
1. User configures settings via web interface
2. Configuration is saved to backend state
3. ZTP process is started with configuration
4. Backend polls ZTP process for status updates
5. Frontend displays real-time progress and device discovery

## Security Considerations

- Credentials are handled securely in memory
- HTTPS should be used in production
- Consider authentication for production deployments
- Network access restrictions may be needed for switch connectivity

## Troubleshooting

### Common Issues

1. **Port already in use**: Change the port in main.py or use environment variable PORT
2. **ZTP process fails to start**: Check that seed switches are reachable and credentials are correct
3. **Topology not displaying**: Ensure devices have been discovered and have neighbor relationships

### Logs

Check application logs for detailed error information:
```bash
# Local development
python main.py

# Cloud Run
gcloud logs read --service=ztp-agent-web --limit=100
```

## Contributing

1. Create feature branch
2. Make changes to web_app directory
3. Test locally
4. Submit pull request

The web application is designed to be modular and extensible. New features can be added by:
- Adding API endpoints in main.py
- Adding frontend components in templates/index.html
- Styling with CSS in static/css/styles.css
- Adding JavaScript functionality in static/js/app.js