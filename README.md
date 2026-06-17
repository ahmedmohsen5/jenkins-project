# DevOps Cycle Workspace

This workspace now includes a small companion app for tracking services through a simple DevOps flow while Jenkins handles automation.

## Services

- `jenkins-controller`: Jenkins UI on `http://localhost:8080`
- `jenkins-agent`: SSH-based Jenkins agent with Docker, Git, `kubectl`, `jq`, and curl installed
- `docker`: Docker-in-Docker daemon for Jenkins jobs
- `devops-helper`: DevOps cycle dashboard on `http://localhost:5050`

## Start Everything

```powershell
docker compose up --build
```

## Optional Environment Variables

Create values in `.env` if you want to override the defaults:

```dotenv
JENKINS_AGENT_SSH_PUBKEY=ssh-rsa ...
DEVOPS_HELPER_SECRET_KEY=change-this-secret
```

## What The Helper App Does

- Tracks services across `Backlog`, `Build`, `Test`, `Release`, `Deploy`, and `Monitor`
- Lets you quickly update stage and status for each service
- Stores data in SQLite so items survive restarts
- Exposes JSON at `/api/items`
- Exposes health information at `/healthz`
