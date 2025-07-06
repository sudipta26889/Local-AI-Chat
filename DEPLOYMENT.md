# DharasLocalAI Deployment Guide

## Production Deployment with Docker Swarm

This guide covers deploying DharasLocalAI using Docker Swarm on your Synology NAS via Portainer.

### Prerequisites

1. **External Services** must be running:
   - PostgreSQL
   - Redis
   - Qdrant (Vector Database)
   - MinIO (Object Storage)
   - LM Studio and/or Ollama
   - LDAP Server (Synology Directory Server)

2. **Docker Swarm** initialized on your NAS
3. **Portainer** installed and configured

### Deployment Steps

#### 1. Prepare Environment Variables

1. Copy the example environment file:
   ```bash
   cp stack.env.example stack.env
   ```

2. Edit `stack.env` with your actual configuration values
   
3. **IMPORTANT**: Keep `stack.env` secure and never commit it to version control

#### 2. Build and Push Images (if needed)

If you're building custom images:

```bash
# Build production images
./build-production.sh

# Push to registry
docker push ghcr.io/sudipta26889/dharas-local-ai-backend:latest
docker push ghcr.io/sudipta26889/dharas-local-ai-nginx:latest
```

#### 3. Initialize Database

Before first deployment, run database migrations:

```bash
docker run --rm \
  --env-file stack.env \
  ghcr.io/sudipta26889/dharas-local-ai-backend:latest \
  sh -c "cd /app && alembic upgrade head"
```

#### 4. Deploy via Portainer

1. Open Portainer and navigate to **Stacks**
2. Click **Add stack**
3. Name your stack (e.g., `dharas-ai`)
4. Choose **Upload** and select `portainer-stack.yml`
5. In the **Environment variables** section:
   - Click **Load variables from .env file**
   - Upload your `stack.env` file
6. Click **Deploy the stack**

#### 5. Verify Deployment

```bash
# Check services
docker service ls

# View logs
docker service logs dharas-ai_backend
docker service logs dharas-ai_nginx

# Check health
curl http://your-nas-ip:5775/health
```

### Resource Usage

The stack is optimized for low memory usage:
- **Backend**: 256MB RAM limit (128MB reserved)
- **Nginx**: 64MB RAM limit (32MB reserved)
- **Total**: ~320MB RAM

### Accessing the Application

- **Local**: http://your-nas-ip:5775
- **HTTPS**: Configure your domain and update `REACT_APP_API_URL` and `REACT_APP_WS_URL` in `stack.env`

### Updating the Stack

1. Update images if needed:
   ```bash
   docker service update --image ghcr.io/sudipta26889/dharas-local-ai-backend:latest dharas-ai_backend
   docker service update --image ghcr.io/sudipta26889/dharas-local-ai-nginx:latest dharas-ai_nginx
   ```

2. Or redeploy the entire stack in Portainer

### Troubleshooting

1. **Services not starting**: Check logs with `docker service logs [service_name]`
2. **Database connection issues**: Verify PostgreSQL is accessible and credentials are correct
3. **LLM connection issues**: Ensure LM Studio/Ollama services are running and accessible
4. **Memory issues**: Monitor with `docker stats` and adjust limits if needed

### Security Considerations

1. Always use `stack.env` for sensitive data
2. Keep `stack.env` in `.gitignore`
3. Use strong passwords for all services
4. Configure HTTPS for production use
5. Regularly update images for security patches