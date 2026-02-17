# Cloud-Eye MCP Bridge v0.1.0

> **FastAPI bridge for git operations, filesystem access, and Railway deployment integration with Cloud-Eye AI system**

## Overview

Cloud-Eye MCP Bridge is a secure FastAPI service that provides:

- **Git Operations**: Status, commit, and push via REST API
- **Filesystem Access**: Secure read/write operations with path traversal protection
- **Railway Integration**: GraphQL queries to Railway's deployment API
- **Bearer Token Authentication**: Configurable API token security

## Features

### Git Operations

- `GET /git/status` - Check repository status
- `POST /git/commit` - Stage and commit changes
- `POST /git/push` - Push to remote repository

### Filesystem

- `POST /fs/read` - Read file contents (with security checks)
- `POST /fs/write` - Write file contents (creates directories as needed)

### Railway API

- `POST /railway/query` - Execute GraphQL queries against Railway API

### Health Check

- `GET /health` - Service health and status

## Installation

```bash
# Clone the repository
git clone https://github.com/Cloud-Eye-Prime/cloud-eye-mcp-bridge.git
cd cloud-eye-mcp-bridge

# Install dependencies
pip install -r requirements.txt
```

## Configuration

### Environment Variables

- `CLOUD_EYE_API_TOKEN` - Bearer token for API authentication (default: `wuji-neigong-2026`)
- `RAILWAY_TOKEN` - Railway API token (required for `/railway/query` endpoint)
- `PORT` - Server port (default: `8000`)

### Example .env file

```bash
CLOUD_EYE_API_TOKEN=your-secure-token-here
RAILWAY_TOKEN=your-railway-token-here
PORT=8000
```

## Usage

### Running Locally

```bash
python cloud_eye_mcp_bridge.py
```

The service will start on `http://0.0.0.0:8000`.

### Example API Calls

#### Check Git Status

```bash
curl -H "Authorization: Bearer wuji-neigong-2026" \
  http://localhost:8000/git/status
```

#### Commit Changes

```bash
curl -X POST \
  -H "Authorization: Bearer wuji-neigong-2026" \
  -H "Content-Type: application/json" \
  -d '{"message": "Update configuration"}' \
  http://localhost:8000/git/commit
```

#### Read File

```bash
curl -X POST \
  -H "Authorization: Bearer wuji-neigong-2026" \
  -H "Content-Type: application/json" \
  -d '{"path": "README.md"}' \
  http://localhost:8000/fs/read
```

## Deployment

### Railway

This project includes `railway.json` for one-click Railway deployment:

1. Connect your GitHub repository to Railway
2. Set environment variables:
   - `CLOUD_EYE_API_TOKEN`
   - `RAILWAY_TOKEN` (for Railway API integration)
3. Deploy automatically on push to `main` branch

### Docker (Optional)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY cloud_eye_mcp_bridge.py .
EXPOSE 8000
CMD ["python", "cloud_eye_mcp_bridge.py"]
```

## Security Features

- **Bearer Token Authentication**: All endpoints (except `/health`) require valid bearer token
- **Path Traversal Protection**: Filesystem operations validate paths to prevent directory traversal attacks
- **Timeout Controls**: Git and HTTP operations have configurable timeouts
- **Error Handling**: Comprehensive exception handling with informative error messages

## API Documentation

Once running, interactive API documentation is available at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Integration with Cloud-Eye

This bridge is designed to work with the Cloud-Eye LXR v16 AI system, providing:

- **Autonomous Git Operations**: AI-driven code commits and deployments
- **Dynamic File Management**: Read/write operations for AI-generated code
- **Deployment Monitoring**: Railway API queries for deployment status

## Wu Xing Philosophy

The health endpoint reflects the Water element (流动, liúdòng) - representing flow, adaptability, and the seamless bridge between systems.

## License

MIT License - See LICENSE file for details

## Author

**Cloud-Eye** - [gregorion@gmail.com](mailto:gregorion@gmail.com)

## Repository

[https://github.com/Cloud-Eye-Prime/cloud-eye-mcp-bridge](https://github.com/Cloud-Eye-Prime/cloud-eye-mcp-bridge)
