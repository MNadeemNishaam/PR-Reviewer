# PR Reviewer

An intelligent, multi-agent PR review system that uses specialized LLM agents to provide comprehensive code reviews on GitHub pull requests.

## Architecture

The system follows an asynchronous worker pattern to handle scale and avoid timeouts:

```
GitHub Webhook → API Gateway (FastAPI) → Redis Queue → Orchestration Engine → Multi-LLM Pipeline → GitHub API
```

### Components

1. **API Gateway**: FastAPI service receiving GitHub webhooks
2. **Message Queue**: Upstash Redis (free tier)
3. **Orchestration Engine**: Worker service managing LLM pipeline
4. **Database**: Supabase PostgreSQL (free tier)
5. **Multi-LLM Pipeline**: 5 specialized agents

### Multi-Agent Pipeline

| Agent | Focus Area | Model |
|-------|-----------|-------|
| **Scout** | Filters diff to remove noise (lock files, assets) | GPT-4o-mini |
| **Guardian** | Scans for hardcoded secrets and OWASP vulnerabilities | Claude 3.5 Sonnet |
| **Architect** | Analyzes logic flow, complexity, and DRY principles | GPT-4o |
| **Stylist** | Checks naming conventions and linting "nitpicks" | GPT-4o-mini |
| **Synthesizer** | Aggregates all feedback into a single, cohesive PR comment | GPT-4o |

## Features

- ✅ Asynchronous processing (no timeouts)
- ✅ Multi-agent specialized review
- ✅ Security vulnerability scanning
- ✅ Architecture and code quality analysis
- ✅ Style and naming convention checks
- ✅ Rate limiting and error handling
- ✅ Free tier deployment ready

## Prerequisites

- Python 3.11+
- GitHub App (with Read & Write access to Pull Requests)
- Supabase PostgreSQL database (free tier)
- Upstash Redis (free tier)
- OpenAI API key
- Anthropic API key

## Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd PR-Reviewer
```

### 2. Create GitHub App

1. Go to [GitHub Developer Settings](https://github.com/settings/developers)
2. Create a new GitHub App
3. Set permissions:
   - Pull requests: Read & Write
   - Contents: Read
4. Subscribe to events:
   - Pull request
5. Generate a private key and save it
6. Note your App ID and Webhook Secret

### 3. Set Up Supabase

1. Create a [Supabase](https://supabase.com) account
2. Create a new project
3. Get your PostgreSQL connection string from Settings → Database

### 4. Set Up Upstash Redis

1. Create an [Upstash](https://upstash.com) account
2. Create a Redis database
3. Get your Redis connection URL

### 5. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Required variables:
- `GITHUB_APP_ID`: Your GitHub App ID
- `GITHUB_APP_PRIVATE_KEY`: Your GitHub App private key (PEM format)
- `GITHUB_WEBHOOK_SECRET`: Your GitHub App webhook secret
- `OPENAI_API_KEY`: Your OpenAI API key
- `ANTHROPIC_API_KEY`: Your Anthropic API key
- `DATABASE_URL`: Supabase PostgreSQL connection string
- `REDIS_URL`: Upstash Redis connection URL

### 6. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 7. Local Development

Start services with Docker Compose:

```bash
docker-compose up
```

Or run manually:

```bash
# Terminal 1: API Gateway
cd backend
python -m uvicorn backend.api.main:app --reload

# Terminal 2: Worker
cd backend
python -m backend.workers.orchestrator
```

## Deployment to Railway

### 1. Create Railway Account

1. Sign up at [Railway](https://railway.app)
2. Connect your GitHub repository

### 2. Deploy API Gateway

1. Create a new service from your GitHub repo
2. Railway will auto-detect the Dockerfile
3. Set the start command: `python -m uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT`
4. Add all environment variables from your `.env` file
5. Deploy

### 3. Deploy Worker

1. Create a second service from the same repo
2. Set the start command: `python -m backend.workers.orchestrator`
3. Add the same environment variables
4. Deploy

### 4. Configure GitHub App Webhook

1. Get your Railway API Gateway URL (e.g., `https://your-app.railway.app`)
2. Go to your GitHub App settings
3. Set webhook URL to: `https://your-app.railway.app/api/webhook`
4. Set content type to `application/json`
5. Save

### 5. Install GitHub App

1. Go to your GitHub App settings
2. Click "Install App"
3. Select repositories or all repositories
4. Install

## Usage

Once deployed and configured:

1. Create a pull request in a repository where the app is installed
2. The webhook will trigger the review process
3. The worker will process the PR through all agents
3. A comprehensive review comment will be posted on the PR

## Project Structure

```
PR-Reviewer/
├── backend/
│   ├── api/                    # FastAPI webhook handler
│   │   ├── main.py            # FastAPI app
│   │   └── webhook.py         # Webhook signature verification
│   ├── workers/
│   │   ├── orchestrator.py    # Main orchestration logic
│   │   └── agents/            # LLM agents
│   ├── services/              # Core services
│   ├── models/                # Pydantic models
│   ├── config/                # Configuration
│   └── requirements.txt
├── docker-compose.yml
├── Procfile                   # Railway deployment
└── README.md
```

## Free Tier Considerations

- **Upstash Redis**: 10K commands/day (~100 PRs/day)
- **Supabase**: 500MB storage, 2GB bandwidth
- **Railway**: $5 free credit/month
- **OpenAI/Anthropic**: Pay-as-you-go (set usage limits)

## Rate Limiting

The system includes built-in rate limiting:
- GitHub API: 30 requests/minute
- OpenAI API: 60 requests/minute
- Anthropic API: 50 requests/minute

## Error Handling

- Failed PRs are retried up to 3 times
- After max retries, tasks move to dead letter queue
- All errors are logged with structured logging
- Database tracks all review statuses

## Monitoring

Check review status in the database:
- `pr_reviews` table: Review status and metadata
- `review_results` table: Agent outputs and final comments
- `api_usage` table: Token usage and cost tracking

## Development

### Running Tests

```bash
# TODO: Add tests
pytest
```

### Code Style

```bash
# TODO: Add linting
black backend/
flake8 backend/
```

## Troubleshooting

### Webhook Not Receiving Events

1. Check webhook URL is correct in GitHub App settings
2. Verify webhook secret matches
3. Check Railway logs for errors

### Worker Not Processing

1. Verify Redis connection
2. Check worker logs
3. Ensure environment variables are set correctly

### Database Connection Issues

1. Verify Supabase connection string
2. Check database is accessible
3. Verify tables were created (check logs on startup)

