#!/bin/bash
# Build production images for DharasLocalAI

set -e

echo "🚀 Building production images for DharasLocalAI"
echo "============================================="

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Registry and image prefix
REGISTRY="ghcr.io/sudipta26889"
VERSION="${1:-latest}"

echo -e "\n${BLUE}Building Backend Image...${NC}"
echo "----------------------------------------"
docker build -t ${REGISTRY}/dharas-local-ai-backend:${VERSION} \
  -f backend/Dockerfile.production \
  ./backend

echo -e "\n${BLUE}Building Nginx Image (with React app)...${NC}"
echo "----------------------------------------"
# Build context needs to include both nginx and frontend directories
docker build -t ${REGISTRY}/dharas-local-ai-nginx:${VERSION} \
  -f nginx/Dockerfile.production \
  --build-arg BUILDKIT_CONTEXT_KEEP_GIT_DIR=true \
  .

echo -e "\n${GREEN}✅ Build complete!${NC}"
echo "============================================="
echo "Images built:"
echo "  - ${REGISTRY}/dharas-local-ai-backend:${VERSION}"
echo "  - ${REGISTRY}/dharas-local-ai-nginx:${VERSION}"
echo ""
echo "To push images to registry:"
echo "  docker push ${REGISTRY}/dharas-local-ai-backend:${VERSION}"
echo "  docker push ${REGISTRY}/dharas-local-ai-nginx:${VERSION}"
echo ""
echo "To deploy with Docker Swarm:"
echo "  docker stack deploy -c portainer-stack.yml dharas-ai"