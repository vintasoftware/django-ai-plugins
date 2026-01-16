# Configuration Guide

## Django-Celery Integration Setup

### Project Structure

```
myproject/
├── myproject/
│   ├── __init__.py
│   ├── celery.py      # Celery app configuration
│   ├── settings.py
│   └── urls.py
├── myapp/
│   ├── __init__.py
│   ├── models.py
│   └── tasks.py       # App-specific tasks
└── manage.py
```

### Celery Application Setup

```python
# myproject/celery.py
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')

app = Celery('myproject')

# Load config from Django settings with CELERY_ prefix
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
```

```python
# myproject/__init__.py
from .celery import app as celery_app

__all__ = ('celery_app',)
```

### Django Settings

```python
# settings.py

# Broker Configuration (choose one)
# Redis
CELERY_BROKER_URL = 'redis://localhost:6379/0'

# RabbitMQ
CELERY_BROKER_URL = 'amqp://guest:guest@localhost:5672//'

# Result Backend (optional, needed if you track results)
CELERY_RESULT_BACKEND = 'redis://localhost:6379/1'
# Or use Django database
CELERY_RESULT_BACKEND = 'django-db'

# Serialization
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']

# Timezone
CELERY_TIMEZONE = 'UTC'
CELERY_ENABLE_UTC = True

# Task settings
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes hard limit
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # 25 minutes soft limit
```

## Broker Configuration

### Redis Broker

```python
# Basic Redis
CELERY_BROKER_URL = 'redis://localhost:6379/0'

# Redis with password
CELERY_BROKER_URL = 'redis://:password@localhost:6379/0'

# Redis Sentinel for HA
CELERY_BROKER_URL = 'sentinel://localhost:26379'
CELERY_BROKER_TRANSPORT_OPTIONS = {
    'master_name': 'mymaster',
    'sentinel_kwargs': {'password': 'sentinel_password'},
}

# Redis Cluster
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_BROKER_TRANSPORT_OPTIONS = {
    'cluster': True,
}

# Connection pool settings
CELERY_BROKER_POOL_LIMIT = 10
CELERY_BROKER_CONNECTION_TIMEOUT = 10
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
```

### RabbitMQ Broker

```python
# Basic RabbitMQ
CELERY_BROKER_URL = 'amqp://guest:guest@localhost:5672//'

# With virtual host
CELERY_BROKER_URL = 'amqp://user:password@localhost:5672/myvhost'

# RabbitMQ with SSL
CELERY_BROKER_URL = 'amqp://user:password@localhost:5671//'
CELERY_BROKER_USE_SSL = {
    'keyfile': '/path/to/key.pem',
    'certfile': '/path/to/cert.pem',
    'ca_certs': '/path/to/ca.pem',
    'cert_reqs': ssl.CERT_REQUIRED,
}

# Connection pool
CELERY_BROKER_POOL_LIMIT = 10
CELERY_BROKER_HEARTBEAT = 10

# Confirm message delivery (recommended for reliability)
CELERY_BROKER_TRANSPORT_OPTIONS = {
    'confirm_publish': True,
}
```

## Broker Transport Options

Critical settings for message delivery reliability.

### Redis Visibility Timeout

When using Redis, set `visibility_timeout` to control how long a task remains invisible after being picked up. If a worker crashes before acknowledging, the task becomes visible again after this timeout.

```python
# Redis visibility timeout (default: 1 hour)
CELERY_BROKER_TRANSPORT_OPTIONS = {
    'visibility_timeout': 3600,  # 1 hour in seconds
}
```

**Important:** Set visibility timeout longer than your longest task. If a task takes longer than the timeout, it will be redelivered to another worker while still running.

### RabbitMQ Publisher Confirms

Enable publisher confirms to ensure messages are actually delivered to the broker.

```python
# RabbitMQ: confirm message delivery
CELERY_BROKER_TRANSPORT_OPTIONS = {
    'confirm_publish': True,
}
```

### SQS Configuration

```python
# AWS SQS
CELERY_BROKER_URL = 'sqs://aws_access_key:aws_secret_key@'
CELERY_BROKER_TRANSPORT_OPTIONS = {
    'region': 'us-east-1',
    'visibility_timeout': 3600,
    'polling_interval': 1,
    'queue_name_prefix': 'celery-',
}
```

## Separating Redis Instances

**Critical:** Use separate Redis instances for different purposes to prevent cascade failures.

```python
# BAD: Single Redis for everything
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CACHES = {'default': {'BACKEND': '...', 'LOCATION': 'redis://localhost:6379/0'}}

# GOOD: Separate Redis instances/databases
CELERY_BROKER_URL = 'redis://localhost:6379/0'      # Task queue
CELERY_RESULT_BACKEND = 'redis://localhost:6379/1'  # Results
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://localhost:6379/2',     # Cache
    }
}

# BEST: Separate Redis servers in production
CELERY_BROKER_URL = 'redis://redis-queue:6379/0'
CELERY_RESULT_BACKEND = 'redis://redis-results:6379/0'
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://redis-cache:6379/0',
    }
}
```

Why separate?
- Cache eviction won't affect task queue
- Result backend memory pressure won't block new tasks
- Easier to scale each component independently
- Isolates failures

## Result Backend Configuration

### Redis Result Backend

```python
CELERY_RESULT_BACKEND = 'redis://localhost:6379/1'

# Result expiration (default: 1 day)
CELERY_RESULT_EXPIRES = 60 * 60 * 24  # 24 hours

# Extended result info
CELERY_RESULT_EXTENDED = True
```

### Django Database Result Backend

```python
# Install: pip install django-celery-results
INSTALLED_APPS = [
    ...
    'django_celery_results',
]

CELERY_RESULT_BACKEND = 'django-db'

# Run migrations
# python manage.py migrate django_celery_results

# Optional: Cache results in addition to database
CELERY_CACHE_BACKEND = 'django-cache'
```

### Disable Results (Fire-and-Forget)

```python
# Global: disable result tracking
CELERY_TASK_IGNORE_RESULT = True

# Per-task: disable result
@shared_task(ignore_result=True)
def fire_and_forget_task(data):
    pass
```

## Worker Configuration

### Concurrency Settings

```python
# Number of worker processes/threads
CELERY_WORKER_CONCURRENCY = 4  # Default: CPU count

# Prefetch multiplier (tasks to prefetch per worker)
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # For fair distribution
# Use 4 (default) for throughput, 1 for latency-sensitive tasks

# Max tasks per worker before restart (memory leak prevention)
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000
```

### Task Execution Settings

```python
# Task time limits
CELERY_TASK_TIME_LIMIT = 300  # Hard kill after 5 min
CELERY_TASK_SOFT_TIME_LIMIT = 240  # Raise exception after 4 min

# Task acknowledgment
CELERY_TASK_ACKS_LATE = True  # Ack after task completes (for reliability)
CELERY_TASK_REJECT_ON_WORKER_LOST = True  # Requeue if worker dies

# Task result compression
CELERY_RESULT_COMPRESSION = 'gzip'
```

## Task Routing and Queues

### Basic Queue Configuration

```python
# Define queues
from kombu import Queue

CELERY_TASK_QUEUES = (
    Queue('default', routing_key='default'),
    Queue('high-priority', routing_key='high'),
    Queue('low-priority', routing_key='low'),
    Queue('emails', routing_key='emails'),
)

CELERY_TASK_DEFAULT_QUEUE = 'default'
```

### Task Routing

```python
# Route tasks to specific queues
CELERY_TASK_ROUTES = {
    # By task name
    'myapp.tasks.send_email': {'queue': 'emails'},
    'myapp.tasks.critical_task': {'queue': 'high-priority'},

    # By pattern
    'myapp.tasks.report_*': {'queue': 'low-priority'},

    # By module
    'myapp.email_tasks.*': {'queue': 'emails'},
}

# Or use a function for dynamic routing
def route_task(name, args, kwargs, options, task=None, **kw):
    if 'urgent' in kwargs.get('priority', ''):
        return {'queue': 'high-priority'}
    return {'queue': 'default'}

CELERY_TASK_ROUTES = (route_task,)
```

### Running Workers for Specific Queues

```bash
# Process only high-priority queue
celery -A myproject worker -Q high-priority

# Process multiple queues with priority
celery -A myproject worker -Q high-priority,default,low-priority

# Dedicated email worker
celery -A myproject worker -Q emails -c 2 -n email-worker@%h
```

## Serialization

### Serializer Options

```python
# JSON (default, safe, recommended)
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']

# Pickle (supports Python objects, security risk!)
CELERY_TASK_SERIALIZER = 'pickle'
CELERY_RESULT_SERIALIZER = 'pickle'
CELERY_ACCEPT_CONTENT = ['pickle', 'json']

# MessagePack (binary, faster than JSON)
# pip install msgpack
CELERY_TASK_SERIALIZER = 'msgpack'
CELERY_RESULT_SERIALIZER = 'msgpack'
CELERY_ACCEPT_CONTENT = ['msgpack', 'json']
```

### Per-Task Serializer

```python
@shared_task(serializer='pickle')
def task_with_complex_objects(data):
    # Can receive Python objects
    pass
```

## Security Settings

### Secure Serialization

```python
# Only accept JSON (never use pickle in production with untrusted data)
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'

# Content signing (for pickle if absolutely needed)
CELERY_TASK_SERIALIZER = 'auth'
CELERY_SECURITY_KEY = '/path/to/private.key'
CELERY_SECURITY_CERTIFICATE = '/path/to/certificate.pem'
CELERY_SECURITY_CERT_STORE = '/path/to/certs/'
```

### Rate Limiting

```python
# Global rate limit (tasks/second)
CELERY_TASK_DEFAULT_RATE_LIMIT = '100/s'

# Per-task rate limit
@shared_task(rate_limit='10/m')  # 10 per minute
def rate_limited_task():
    pass
```

## Environment-Specific Configuration

### Development Settings

```python
# settings/development.py
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/1'

# Eager mode: execute tasks synchronously (for debugging)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
```

### Production Settings

```python
# settings/production.py
import os

CELERY_BROKER_URL = os.environ['CELERY_BROKER_URL']
CELERY_RESULT_BACKEND = os.environ['CELERY_RESULT_BACKEND']

# Never use eager mode in production
CELERY_TASK_ALWAYS_EAGER = False

# Connection resilience
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_CONNECTION_MAX_RETRIES = 10

# Task settings
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# Result expiration
CELERY_RESULT_EXPIRES = 60 * 60 * 24  # 24 hours

# Memory management
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000
```

### Testing Settings

```python
# settings/testing.py
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = 'memory://'
CELERY_RESULT_BACKEND = 'cache+memory://'
```

## Complete Configuration Example

```python
# settings.py - Complete Celery configuration

from kombu import Queue
import os

# Broker
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# Result backend
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'django-db')
CELERY_RESULT_EXPIRES = 60 * 60 * 24  # 24 hours

# Serialization
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']

# Time and timezone
CELERY_TIMEZONE = 'UTC'
CELERY_ENABLE_UTC = True

# Task execution
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 min hard limit
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # 25 min soft limit
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True

# Worker
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000

# Queues
CELERY_TASK_QUEUES = (
    Queue('default'),
    Queue('high-priority'),
    Queue('low-priority'),
)
CELERY_TASK_DEFAULT_QUEUE = 'default'

# Routing
CELERY_TASK_ROUTES = {
    'myapp.tasks.urgent_*': {'queue': 'high-priority'},
    'myapp.tasks.report_*': {'queue': 'low-priority'},
}

# Beat scheduler (for periodic tasks)
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
```
