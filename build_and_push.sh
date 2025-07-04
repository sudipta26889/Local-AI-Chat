#!/bin/bash

# DharasLocalAI - Build and Push Script
# Builds and pushes Docker images to GitHub Container Registry

set -e

# Set variables
TAG="${1:-latest}"
PLATFORMS="linux/amd64,linux/arm64"

# Service definitions
declare -A SERVICES=(
    ["backend"]="ghcr.io/sudipta26889/dharas-local-ai-backend backend/Dockerfile backend DharasLocalAI Backend"
    ["frontend"]="ghcr.io/sudipta26889/dharas-local-ai-frontend frontend/Dockerfile frontend DharasLocalAI Frontend"
    ["nginx"]="ghcr.io/sudipta26889/dharas-local-ai-nginx nginx/Dockerfile nginx DharasLocalAI Nginx"
)

# Detect service based on first argument
SERVICE=""
if [[ "${1}" == "backend" ]]; then
    SERVICE="backend"
    TAG="${2:-latest}"
elif [[ "${1}" == "frontend" ]]; then
    SERVICE="frontend"
    TAG="${2:-latest}"
elif [[ "${1}" == "nginx" ]]; then
    SERVICE="nginx"
    TAG="${2:-latest}"
elif [[ "${1}" == "--all" ]]; then
    BUILD_ALL=true
    TAG="${2:-latest}"
    SERVICE_NAME="All Services"
elif [[ "${1}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || [[ "${1}" == "latest" ]]; then
    # Tag provided, build all services
    BUILD_ALL=true
    TAG="${1}"
    SERVICE_NAME="All Services"
else
    # Default: build all services
    BUILD_ALL=true
    TAG="${1:-latest}"
    SERVICE_NAME="All Services"
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

error() {
    echo -e "${RED}❌ $1${NC}"
}

print_header() {
    echo "🚀 DharasLocalAI - Docker Build & Push"
    echo "===================================================="
    if [[ "$BUILD_ALL" == "true" ]]; then
        echo "Building ALL services with tag: $TAG"
        echo "Services: Backend (FastAPI), Frontend (React), Nginx (Proxy)"
    else
        echo "Building: $SERVICE service with tag: $TAG"
    fi
    echo "Platforms: $PLATFORMS"
    echo ""
}

check_prerequisites() {
    info "Checking prerequisites..."
    
    # Check if Docker is running
    if ! docker info >/dev/null 2>&1; then
        error "Docker is not running or not accessible"
        exit 1
    fi
    
    # Check if buildx is available
    if ! docker buildx version >/dev/null 2>&1; then
        error "Docker buildx is not available"
        exit 1
    fi
    
    # Check environment variables
    if [[ -z "$GITHUB_USERNAME" || -z "$GITHUB_PAT" ]]; then
        error "GITHUB_USERNAME or GITHUB_PAT environment variables are not set"
        echo ""
        echo "Please set them with:"
        echo "export GITHUB_USERNAME=your_github_username"
        echo "export GITHUB_PAT=your_personal_access_token"
        exit 1
    fi
    
    success "Prerequisites check passed"
}

authenticate_registry() {
    info "Authenticating to GitHub Container Registry..."
    
    echo "$GITHUB_PAT" | docker login ghcr.io -u "$GITHUB_USERNAME" --password-stdin
    if [ $? -ne 0 ]; then
        error "Docker login failed. Ensure your credentials are correct"
        exit 1
    fi
    
    success "Authentication successful"
}

create_builder() {
    info "Creating/using Docker buildx builder..."
    
    # Create builder if it doesn't exist
    if ! docker buildx inspect dharas-ai-builder >/dev/null 2>&1; then
        docker buildx create --name dharas-ai-builder --use
    else
        docker buildx use dharas-ai-builder
    fi
    
    # Bootstrap the builder
    docker buildx inspect --bootstrap
    
    success "Builder ready"
}

build_single_service() {
    local service_key="$1"
    local tag="$2"
    
    # Parse service definition
    IFS=' ' read -r image_name dockerfile_path build_context display_name <<< "${SERVICES[$service_key]}"
    
    info "Building $display_name..."
    
    # Build for multiple platforms and push
    docker buildx build \
        --platform "$PLATFORMS" \
        -f "$dockerfile_path" \
        --tag "$image_name:$tag" \
        --tag "$image_name:latest" \
        --push \
        --progress=plain \
        "$build_context"
    
    if [ $? -ne 0 ]; then
        error "$display_name build/push failed"
        return 1
    fi
    
    success "$display_name built and pushed successfully"
    return 0
}

build_and_push() {
    if [[ "$BUILD_ALL" == "true" ]]; then
        build_all_services
    else
        build_single_service "$SERVICE" "$TAG"
    fi
}

build_all_services() {
    info "Building all services..."
    
    local failed_services=()
    local total_services=${#SERVICES[@]}
    
    # Build each service
    for service_key in "${!SERVICES[@]}"; do
        IFS=' ' read -r image_name dockerfile_path build_context display_name <<< "${SERVICES[$service_key]}"
        
        echo ""
        echo "🔨 Building $display_name..."
        echo "────────────────────────────────────────"
        if ! build_single_service "$service_key" "$TAG"; then
            failed_services+=("$display_name")
        fi
    done
    
    # Report results
    echo ""
    echo "📊 Build Summary"
    echo "════════════════"
    
    if [ ${#failed_services[@]} -eq 0 ]; then
        success "All services built successfully! 🎉"
    else
        error "Some services failed to build:"
        for service in "${failed_services[@]}"; do
            echo "   ❌ $service"
        done
        echo ""
        warning "Successfully built: $(($total_services - ${#failed_services[@]}))/$total_services services"
        exit 1
    fi
}

verify_images() {
    info "Verifying pushed images..."
    
    if [[ "$BUILD_ALL" == "true" ]]; then
        for service_key in "${!SERVICES[@]}"; do
            IFS=' ' read -r image_name dockerfile_path build_context display_name <<< "${SERVICES[$service_key]}"
            echo "Verifying $display_name..."
            docker pull "$image_name:$TAG" >/dev/null 2>&1
            if [ $? -eq 0 ]; then
                local size=$(docker images "$image_name:$TAG" --format "{{.Size}}")
                echo "  ✅ $image_name:$TAG ($size)"
            else
                echo "  ❌ Failed to verify $image_name:$TAG"
            fi
        done
    else
        IFS=' ' read -r image_name dockerfile_path build_context display_name <<< "${SERVICES[$SERVICE]}"
        docker pull "$image_name:$TAG" >/dev/null
        local image_size=$(docker images "$image_name:$TAG" --format "{{.Size}}")
        local image_id=$(docker images "$image_name:$TAG" --format "{{.ID}}")
        echo "Image ID: $image_id"
        echo "Image Size: $image_size"
    fi
    
    success "Image verification completed"
}

generate_deployment_instructions() {
    info "Generating deployment instructions..."
    
    cat > docker_deployment_info.md << EOF
# DharasLocalAI - Docker Deployment Information

## Build Summary
- **Build Date**: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
- **Tag**: $TAG
- **Platforms**: $PLATFORMS
- **Registry**: GitHub Container Registry (ghcr.io)

## Images Built

### Backend (FastAPI)
- **Image**: \`ghcr.io/sudipta26889/dharas-local-ai-backend:$TAG\`
- **Port**: 8000
- **Purpose**: FastAPI backend with LLM integration, WebSocket support

### Frontend (React)
- **Image**: \`ghcr.io/sudipta26889/dharas-local-ai-frontend:$TAG\`
- **Port**: 3000
- **Purpose**: React frontend with TypeScript and TailwindCSS

### Nginx (Reverse Proxy)
- **Image**: \`ghcr.io/sudipta26889/dharas-local-ai-nginx:$TAG\`
- **Port**: 80
- **Purpose**: Nginx reverse proxy and static file serving

## Pull All Images
\`\`\`bash
docker pull ghcr.io/sudipta26889/dharas-local-ai-backend:$TAG
docker pull ghcr.io/sudipta26889/dharas-local-ai-frontend:$TAG
docker pull ghcr.io/sudipta26889/dharas-local-ai-nginx:$TAG
\`\`\`

## Complete Stack Deployment
Use the provided \`stack.yml\` for Portainer deployment.

## Individual Service Commands

### Backend
\`\`\`bash
docker run -d \\
  --name dharas-ai-backend \\
  -p 8000:8000 \\
  -e DATABASE_URL="postgresql://user:pass@host:5432/db" \\
  -e REDIS_URL="redis://redis:6379" \\
  ghcr.io/sudipta26889/dharas-local-ai-backend:$TAG
\`\`\`

### Frontend
\`\`\`bash
docker run -d \\
  --name dharas-ai-frontend \\
  -p 3000:3000 \\
  ghcr.io/sudipta26889/dharas-local-ai-frontend:$TAG
\`\`\`

### Nginx
\`\`\`bash
docker run -d \\
  --name dharas-ai-nginx \\
  -p 5775:80 \\
  ghcr.io/sudipta26889/dharas-local-ai-nginx:$TAG
\`\`\`

## Health Checks
\`\`\`bash
# Backend
curl http://localhost:8000/health

# Frontend (via Nginx)
curl http://localhost:5775/
\`\`\`

## Security Notes
- All images run as non-root user
- Multi-stage builds for minimal attack surface
- Only runtime dependencies included
- Health checks configured for monitoring

## Configuration
- Update \`.env\` file with your settings
- External services: PostgreSQL, Redis, Qdrant, MinIO
- LDAP authentication configured
- Ollama LLM endpoints configured

## Production Deployment
1. Use the provided \`stack.yml\` with Portainer
2. Configure external services (DB, Redis, etc.)
3. Update environment variables
4. Deploy on your Synology NAS
EOF
    
    success "Deployment instructions created: docker_deployment_info.md"
}

cleanup() {
    info "Cleaning up local images..."
    
    # Remove local development images to save space
    docker image prune -f >/dev/null 2>&1 || true
    
    success "Cleanup completed"
}

print_summary() {
    echo ""
    echo "🎉 DharasLocalAI Build and Push Completed Successfully!"
    echo "===================================================="
    echo ""
    echo "📦 Images Built:"
    if [[ "$BUILD_ALL" == "true" ]]; then
        for service_key in "${!SERVICES[@]}"; do
            IFS=' ' read -r image_name dockerfile_path build_context display_name <<< "${SERVICES[$service_key]}"
            echo "  • $image_name:$TAG"
        done
    else
        IFS=' ' read -r image_name dockerfile_path build_context display_name <<< "${SERVICES[$SERVICE]}"
        echo "  • $image_name:$TAG"
    fi
    echo ""
    echo "🌐 Platforms: $PLATFORMS"
    echo ""
    echo "🔗 Registry URLs:"
    echo "  • https://github.com/sudipta26889/Local-AI-Chat/pkgs/container/dharas-local-ai-backend"
    echo "  • https://github.com/sudipta26889/Local-AI-Chat/pkgs/container/dharas-local-ai-frontend"
    echo "  • https://github.com/sudipta26889/Local-AI-Chat/pkgs/container/dharas-local-ai-nginx"
    echo ""
    echo "📋 Next Steps:"
    echo "  1. Use stack.yml for Portainer deployment"
    echo "  2. Configure external services (PostgreSQL, Redis, Qdrant, MinIO)"
    echo "  3. Update environment variables in .env"
    echo "  4. Deploy on your Synology NAS via Portainer"
    echo ""
    echo "📄 Complete deployment guide: docker_deployment_info.md"
    echo ""
}

# Main execution
main() {
    print_header
    check_prerequisites
    authenticate_registry
    create_builder
    build_and_push
    verify_images
    generate_deployment_instructions
    cleanup
    print_summary
}

# Handle script arguments
case "${1:-}" in
    --help|-h)
        echo "Usage: $0 [SERVICE|TAG|--all] [TAG]"
        echo ""
        echo "Builds and pushes Docker images to GitHub Container Registry"
        echo ""
        echo "Arguments:"
        echo "  SERVICE    'backend', 'frontend', or 'nginx'"
        echo "             '--all' to build all services"
        echo "  TAG        Image tag (default: latest)"
        echo ""
        echo "Environment Variables Required:"
        echo "  GITHUB_USERNAME    Your GitHub username"
        echo "  GITHUB_PAT         Your GitHub Personal Access Token"
        echo ""
        echo "Examples:"
        echo "  $0                       # Build all services with 'latest' tag"
        echo "  $0 v1.0.0               # Build all services with 'v1.0.0' tag"
        echo "  $0 backend              # Build backend with 'latest' tag"
        echo "  $0 backend v1.0.0       # Build backend with 'v1.0.0' tag"
        echo "  $0 --all v1.0.0         # Build ALL services with 'v1.0.0' tag"
        exit 0
        ;;
    --*|-*)
        if [[ "${1}" != "--all" ]]; then
            error "Unknown option: $1"
            echo "Use $0 --help for usage information"
            exit 1
        fi
        ;;
esac

# Run main function
main "$@"