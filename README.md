# DharasLocalAI

A self-hosted conversational AI chat application that leverages multiple local LLM endpoints with advanced features like LDAP authentication, semantic search, and context management.

## Features

- **Multi-Model Support**: Connect to multiple Ollama instances and switch between models
- **LDAP Authentication**: Seamless integration with Synology Directory Server
- **Advanced Context Management**: Sliding window and summary-based compression
- **Semantic Search**: Vector-based search using Qdrant
- **File Attachments**: Store and retrieve files via MinIO
- **Real-time Streaming**: WebSocket-based response streaming
- **Chat History**: Persistent storage with PostgreSQL
- **Response Caching**: Redis-based caching for improved performance
- **PWA Support**: Installable Progressive Web App with offline capabilities
- **Extended Sessions**: 30-day login with automatic token refresh
- **Custom Branding**: Beautiful logo and theming throughout

## Architecture

The application consists of three main components:
- **Frontend**: React with TypeScript and TailwindCSS
- **Backend**: FastAPI with Python
- **Services**: PostgreSQL, Redis, Qdrant, MinIO (external)

## Prerequisites

- Docker and Docker Compose
- Access to:
  - PostgreSQL instance
  - Redis instance
  - Qdrant vector database
  - MinIO object storage
  - LDAP server
  - One or more Ollama instances

## Quick Start

1. Clone the repository:
```bash
git clone https://github.com/yourusername/DharasLocalAI.git
cd DharasLocalAI
```

2. Copy the environment file and configure:
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Initialize the database (first time only):
```bash
docker-compose --profile init up db-init
```

4. Start the application:
```bash
docker-compose up -d
```

5. Access the application at `http://localhost:5775` or `https://chat.sudiptadhara.in`

## Configuration

Edit the `.env` file to configure:
- LLM endpoints
- LDAP settings
- Database connections
- Service endpoints

## Development

### Backend Development
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend Development
```bash
cd frontend
npm install
npm start
```

## Deployment

The application is designed to run on Synology NAS via Portainer. Use the provided `docker-compose.yml` file to deploy.

## Security

- All data is stored locally
- LDAP authentication required
- JWT tokens for session management
- No external API calls except to your configured LLM endpoints

## License

MIT License