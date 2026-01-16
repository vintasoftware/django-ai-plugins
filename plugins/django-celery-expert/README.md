# Django Celery Expert Plugin

A Claude Code plugin providing expert guidance for Django applications using Celery for asynchronous task processing.

## Installation

### Via Plugin Marketplace

```bash
# Add the marketplace
/plugin marketplace add vintasoftware/django-ai-plugins

# Install the plugin
/plugin install django-celery-expert@django-ai-plugins
```

### Local Development

```bash
# Clone the repository
git clone https://github.com/vintasoftware/django-ai-plugins.git

# Add local marketplace
cd django-ai-plugins
/plugin marketplace add .

# Install the plugin
/plugin install django-celery-expert@django-ai-plugins
```

## What's Included

### Skill: django-celery-expert

Provides expert guidance for:

- **Task Design** - Patterns for implementing background tasks, workflows, and job orchestration
- **Configuration** - Django-Celery integration, broker setup, and worker configuration
- **Error Handling** - Retry strategies, backoff patterns, and failure management
- **Periodic Tasks** - Celery Beat scheduling and dynamic task management
- **Monitoring** - Flower setup, Prometheus metrics, and alerting
- **Production Deployment** - Worker supervision, containerization, and scaling

## Usage

The skill is automatically invoked when Claude detects relevant triggers:

- "Create a Celery task for..."
- "Configure Celery workers"
- "Handle task failures"
- "Set up periodic tasks"
- "Monitor Celery tasks"
- "Deploy Celery in production"

## Reference Documentation

The plugin includes comprehensive reference documentation in `skills/references/`:

| File | Topics |
|------|--------|
| `task-design-patterns.md` | Task signatures, idempotency, workflows (chains, groups, chords) |
| `configuration-guide.md` | Django integration, broker setup, queues, serialization |
| `error-handling.md` | Retries, backoff, timeouts, dead letter queues |
| `periodic-tasks.md` | Celery Beat, crontabs, database scheduler |
| `monitoring-observability.md` | Flower, Prometheus, logging, debugging |
| `production-deployment.md` | Systemd, Docker, Kubernetes, scaling |

## Requirements

- Celery 5.x+
- Django 4.x+
- Redis or RabbitMQ as message broker

## License

MIT
