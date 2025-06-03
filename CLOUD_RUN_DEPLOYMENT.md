# Google Cloud Run Deployment Guide (Free Tier)

This guide covers deploying the RUCKUS ZTP backend to Google Cloud Run using only free tier services.

## Prerequisites

- Google Cloud account (free tier includes $300 credit)
- `gcloud` CLI installed and authenticated
- Domain verified in Google Cloud (neuralconfig.com)
- Docker installed locally (optional, for testing)

## Free Tier Limits

Google Cloud Run free tier includes:
- 2 million requests per month
- 360,000 GB-seconds of memory
- 180,000 vCPU-seconds of compute time
- 1 GB network egress per month

Our configuration stays within these limits.

## Step 1: Initial Setup

```bash
# Set your project ID
export PROJECT_ID=your-project-id
gcloud config set project $PROJECT_ID

# Enable required APIs
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud services enable compute.googleapis.com
```

## Step 2: Deploy Backend to Cloud Run

### Option A: Using Cloud Build (Recommended)

```bash
# From the repository root
cd /path/to/ruckus-ztp

# Submit build to Cloud Build
gcloud builds submit --config=web_app/cloudbuild.yaml .

# This will:
# 1. Build the Docker image
# 2. Push to Container Registry
# 3. Deploy to Cloud Run
```

### Option B: Manual Deployment

```bash
# Build locally
docker build -t gcr.io/$PROJECT_ID/ruckus-ztp-backend -f web_app/Dockerfile .

# Push to Container Registry
docker push gcr.io/$PROJECT_ID/ruckus-ztp-backend

# Deploy to Cloud Run (Free Tier)
gcloud run deploy ruckus-ztp-backend \
  --image gcr.io/$PROJECT_ID/ruckus-ztp-backend \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --memory 256Mi \
  --cpu 1 \
  --max-instances 1 \
  --min-instances 0 \
  --timeout 300 \
  --cpu-throttling
```

## Step 3: Configure Custom Domain

```bash
# Map domain to Cloud Run service
gcloud run domain-mappings create \
  --service ruckus-ztp-backend \
  --domain ruckusztp.neuralconfig.com \
  --region us-central1

# This will provide DNS records to add to your domain
```

## Step 4: Add DNS Records

After running the domain mapping command, you'll see output like:

```
NAME                      RECORD TYPE  CONTENTS
ruckusztp.neuralconfig.com  A           35.244.xxx.xxx
ruckusztp.neuralconfig.com  AAAA        2600:1901:0:xxx::xxx
```

Add these records to your DNS provider for neuralconfig.com.

**Note**: The IP addresses shown are Google's Cloud Run load balancer IPs, not dedicated to your service. This is normal and part of the free tier - Google handles the routing.

## Step 5: Verify SSL Certificate

Cloud Run automatically provisions SSL certificates. Wait 15-30 minutes for propagation.

```bash
# Check domain mapping status
gcloud run domain-mappings list --region us-central1

# Test the deployment
curl https://ruckusztp.neuralconfig.com/api/status
```

## Step 6: Get Backend URL for SSH Proxy

Your backend WebSocket URL for the SSH proxy will be:
```
wss://ruckusztp.neuralconfig.com/ws/ssh-proxy
```

## Environment Variables (Optional)

If you need to set environment variables:

```bash
gcloud run services update ruckus-ztp-backend \
  --region us-central1 \
  --update-env-vars KEY1=value1,KEY2=value2
```

## Monitoring and Logs

```bash
# View logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=ruckus-ztp-backend" --limit 50

# Stream logs
gcloud alpha run services logs tail ruckus-ztp-backend --region us-central1

# View metrics in Cloud Console
echo "https://console.cloud.google.com/run/detail/us-central1/ruckus-ztp-backend/metrics"
```

## Troubleshooting

### Check Service Status
```bash
gcloud run services describe ruckus-ztp-backend --region us-central1
```

### Test WebSocket Endpoint
```bash
# Install wscat if needed
npm install -g wscat

# Test WebSocket connection
wscat -c wss://ruckusztp.neuralconfig.com/ws/ssh-proxy \
  -H "Authorization: Bearer your-test-token"
```

### Common Issues

1. **502 Bad Gateway**: Check application logs, ensure the app starts within timeout
2. **WebSocket connection fails**: Cloud Run supports WebSockets, ensure using HTTP/2
3. **Domain not working**: Wait for DNS propagation (up to 48 hours)

## Free Tier Optimization Tips

1. **Scale to Zero**: With `--min-instances 0`, the service costs nothing when idle
2. **Memory Usage**: 256Mi is sufficient for the backend API
3. **Request Limits**: Monitor usage to stay within 2 million requests/month
4. **Storage**: Container Registry allows 0.5 GB free storage
5. **Networking**: 1 GB egress free per month (sufficient for API/WebSocket)

## Monitoring Free Tier Usage

```bash
# Check current month's usage
gcloud alpha billing budgets list

# View Cloud Run metrics
gcloud monitoring metrics list --filter="metric.type:run.googleapis.com"
```

## Next Steps

Once the backend is deployed and accessible at https://ruckusztp.neuralconfig.com:

1. Generate a secure token for SSH proxy authentication
2. Configure your SSH proxy with the WebSocket URL
3. Deploy the SSH proxy to your Linux server
4. Test the connection between proxy and backend