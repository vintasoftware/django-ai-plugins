# Django Celery Expert - Reference Documentation

This directory contains comprehensive Django and Celery best practices documentation that will be loaded into Claude's context when needed.

## Purpose

Reference files provide detailed guidelines, patterns, and examples that would make SKILL.md too long. Claude will read these files as needed based on the specific Celery task at hand.

## Reference Files

- **`django-integration.md`** - Django-specific patterns (transaction.on_commit, recovery tasks, testing)
- **`task-design-patterns.md`** - Task implementation patterns and workflows
- **`configuration-guide.md`** - Django-Celery setup, broker transport options, configuration
- **`error-handling.md`** - Retry strategies and failure handling
- **`periodic-tasks.md`** - Celery Beat and scheduled tasks
- **`monitoring-observability.md`** - Monitoring, logging, and debugging
- **`production-deployment.md`** - Production deployment, warnings, and scaling

## Sources

Best practices incorporated from:
- [Celery in the Wild: Tips and Tricks](https://www.vintasoftware.com/blog/celery-wild-tips-and-tricks-run-async-tasks-real-world) - Vinta Software
- [A Guide on Django Celery Tasks That Actually Work](https://www.vintasoftware.com/blog/guide-django-celery-tasks) - Vinta Software

## Usage

Claude will automatically read these files when working on Celery tasks. You don't need to manually reference them - Claude will determine which references are needed based on the task.
