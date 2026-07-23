# Production Deployment

## Worker Deployment Patterns

### Basic Worker Command

```bash
celery -A myproject worker --loglevel=info
```

### Worker Options

```bash
celery -A myproject worker \
    --loglevel=info \
    --concurrency=4 \
    --hostname=worker1@%h \
    --queues=default,high-priority \
    --prefetch-multiplier=1 \
    --max-tasks-per-child=1000 \
    --time-limit=300 \
    --soft-time-limit=240
```

| Option | Description |
|--------|-------------|
| `-c, --concurrency` | Number of worker processes |
| `-n, --hostname` | Worker hostname (use %h for machine hostname) |
| `-Q, --queues` | Queues to consume from |
| `--prefetch-multiplier` | Tasks to prefetch (1 for fair, higher for throughput) |
| `--max-tasks-per-child` | Restart worker after N tasks (prevents memory leaks) |
| `--time-limit` | Hard time limit per task |
| `--soft-time-limit` | Soft limit (raises exception) |

## Process Supervision

### Systemd Configuration

```ini
# /etc/systemd/system/celery.service
[Unit]
Description=Celery Service
After=network.target

[Service]
Type=forking
User=celery
Group=celery
EnvironmentFile=/etc/conf.d/celery
WorkingDirectory=/opt/myproject
ExecStart=/bin/sh -c '${CELERY_BIN} -A ${CELERY_APP} multi start ${CELERYD_NODES} \
    --pidfile=${CELERYD_PID_FILE} \
    --logfile=${CELERYD_LOG_FILE} \
    --loglevel=${CELERYD_LOG_LEVEL} \
    ${CELERYD_OPTS}'
ExecStop=/bin/sh -c '${CELERY_BIN} multi stopwait ${CELERYD_NODES} \
    --pidfile=${CELERYD_PID_FILE}'
ExecReload=/bin/sh -c '${CELERY_BIN} -A ${CELERY_APP} multi restart ${CELERYD_NODES} \
    --pidfile=${CELERYD_PID_FILE} \
    --logfile=${CELERYD_LOG_FILE} \
    --loglevel=${CELERYD_LOG_LEVEL} \
    ${CELERYD_OPTS}'
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# /etc/conf.d/celery
CELERY_BIN="/opt/myproject/venv/bin/celery"
CELERY_APP="myproject"
CELERYD_NODES="worker1 worker2"
CELERYD_OPTS="--time-limit=300 --concurrency=4"
CELERYD_PID_FILE="/var/run/celery/%n.pid"
CELERYD_LOG_FILE="/var/log/celery/%n%I.log"
CELERYD_LOG_LEVEL="INFO"
```

### Systemd for Beat

```ini
# /etc/systemd/system/celerybeat.service
[Unit]
Description=Celery Beat Service
After=network.target

[Service]
Type=simple
User=celery
Group=celery
EnvironmentFile=/etc/conf.d/celery
WorkingDirectory=/opt/myproject
ExecStart=/bin/sh -c '${CELERY_BIN} -A ${CELERY_APP} beat \
    --pidfile=${CELERYBEAT_PID_FILE} \
    --logfile=${CELERYBEAT_LOG_FILE} \
    --loglevel=${CELERYD_LOG_LEVEL} \
    --scheduler django_celery_beat.schedulers:DatabaseScheduler'
Restart=always

[Install]
WantedBy=multi-user.target
```

### Supervisor Configuration

```ini
# /etc/supervisor/conf.d/celery.conf
[program:celery-worker]
command=/opt/myproject/venv/bin/celery -A myproject worker --loglevel=INFO --concurrency=4
directory=/opt/myproject
user=celery
numprocs=1
stdout_logfile=/var/log/celery/worker.log
stderr_logfile=/var/log/celery/worker.log
autostart=true
autorestart=true
startsecs=10
stopwaitsecs=600
stopasgroup=true
priority=1000

[program:celery-beat]
command=/opt/myproject/venv/bin/celery -A myproject beat --loglevel=INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler
directory=/opt/myproject
user=celery
numprocs=1
stdout_logfile=/var/log/celery/beat.log
stderr_logfile=/var/log/celery/beat.log
autostart=true
autorestart=true
startsecs=10
priority=999
```

## Containerized Deployment

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create non-root user
RUN useradd -m celery
USER celery

# Default command (override in compose)
CMD ["celery", "-A", "myproject", "worker", "--loglevel=info"]
```

### Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data

  web:
    build: .
    command: gunicorn myproject.wsgi:application --bind 0.0.0.0:8000
    volumes:
      - .:/app
    ports:
      - "8000:8000"
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/1
    depends_on:
      - redis

  celery-worker:
    build: .
    command: celery -A myproject worker --loglevel=info --concurrency=4
    volumes:
      - .:/app
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/1
    depends_on:
      - redis
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 512M

  celery-beat:
    build: .
    command: celery -A myproject beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
    volumes:
      - .:/app
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
    depends_on:
      - redis
    deploy:
      replicas: 1  # Only one beat instance!

  flower:
    build: .
    command: celery -A myproject flower --port=5555
    ports:
      - "5555:5555"
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
    depends_on:
      - redis

volumes:
  redis-data:
```

### Kubernetes Deployment

```yaml
# celery-worker-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: celery-worker
spec:
  replicas: 3
  selector:
    matchLabels:
      app: celery-worker
  template:
    metadata:
      labels:
        app: celery-worker
    spec:
      containers:
      - name: celery-worker
        image: myproject:latest
        command: ["celery", "-A", "myproject", "worker", "--loglevel=info"]
        env:
        - name: CELERY_BROKER_URL
          valueFrom:
            secretKeyRef:
              name: celery-secrets
              key: broker-url
        resources:
          limits:
            memory: "512Mi"
            cpu: "500m"
          requests:
            memory: "256Mi"
            cpu: "250m"
        livenessProbe:
          exec:
            command:
            - celery
            - -A
            - myproject
            - inspect
            - ping
          initialDelaySeconds: 30
          periodSeconds: 60
---
# celery-beat-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: celery-beat
spec:
  replicas: 1  # Must be exactly 1
  strategy:
    type: Recreate  # Prevent duplicate beats during deploy
  selector:
    matchLabels:
      app: celery-beat
  template:
    metadata:
      labels:
        app: celery-beat
    spec:
      containers:
      - name: celery-beat
        image: myproject:latest
        command: ["celery", "-A", "myproject", "beat", "--loglevel=info"]
        env:
        - name: CELERY_BROKER_URL
          valueFrom:
            secretKeyRef:
              name: celery-secrets
              key: broker-url
```

## Scaling Strategies

### Horizontal Scaling

```yaml
# Scale workers based on queue length
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: celery-worker-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: celery-worker
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: External
    external:
      metric:
        name: celery_queue_length
      target:
        type: AverageValue
        averageValue: 100  # Scale up when > 100 tasks per worker
```

### Queue-Based Scaling

```bash
# Dedicated workers for different queues
# High-priority: More workers, less concurrency (faster response)
celery -A myproject worker -Q high-priority -c 2 -n high@%h

# Default: Balanced
celery -A myproject worker -Q default -c 4 -n default@%h

# Low-priority: Fewer workers, more concurrency (batch processing)
celery -A myproject worker -Q low-priority -c 8 -n low@%h
```

## Deployment Warnings

### Task Signature Changes

**Critical:** Drain all queues before deploying changes to task signatures (adding, removing, or renaming parameters).

```python
# BEFORE: Task with two parameters
@shared_task
def process_order(order_id, notify=True):
    pass

# AFTER: Task with changed signature
@shared_task
def process_order(order_id, notify=True, priority='normal'):  # New param
    pass
```

**Problem:** Old messages in the queue have the old signature. When new workers pick them up, they may fail or behave unexpectedly.

**Solution:**

```bash
# 1. Stop producers (or pause task creation)
# 2. Wait for queues to drain
celery -A myproject inspect reserved
celery -A myproject inspect active

# 3. Verify queues are empty
celery -A myproject inspect stats  # Check queue lengths

# 4. Deploy new code
# 5. Restart workers
# 6. Resume producers
```

**Alternative: Backwards-Compatible Changes**

```python
# Make new parameters optional with defaults
@shared_task
def process_order(order_id, notify=True, priority=None):
    if priority is None:
        priority = 'normal'  # Handle old messages
    pass
```

### Avoid Long ETAs and Countdowns

Tasks with long `eta` or `countdown` values can cause issues:

```python
# BAD: Task scheduled far in the future
my_task.apply_async(eta=datetime.now() + timedelta(days=30))
my_task.apply_async(countdown=60*60*24*30)  # 30 days

# Problems:
# - Task signature might change before execution
# - Broker restarts may lose the task
# - Visibility timeout issues with Redis/SQS
```

**Better alternatives:**
- Use Celery Beat for scheduled tasks
- Store future tasks in database with a periodic recovery task
- Use a dedicated scheduling service

## Soft Shutdown (Celery 5.5+)

Celery 5.5+ introduced soft shutdown for cleaner worker termination.

```python
# settings.py
CELERY_WORKER_ENABLE_SOFT_SHUTDOWN_ON_IDLE = True
CELERY_WORKER_SOFT_SHUTDOWN_TIMEOUT = 60  # Wait up to 60s for tasks to complete
```

```bash
# Gracefully shutdown with soft timeout
celery -A myproject control shutdown --soft-timeout=60
```

Benefits:
- Workers finish current tasks before shutting down
- No task loss during deployments
- Cleaner rolling updates in Kubernetes

## Graceful Shutdown

### Signal Handling

```python
# celery.py
from celery.signals import worker_shutting_down

@worker_shutting_down.connect
def worker_shutting_down_handler(sig, how, exitcode, **kwargs):
    logger.info(f'Worker shutting down: signal={sig}, how={how}')
    # Perform cleanup
    cleanup_connections()
```

### Kubernetes Graceful Shutdown

```yaml
spec:
  containers:
  - name: celery-worker
    lifecycle:
      preStop:
        exec:
          command: ["/bin/sh", "-c", "celery -A myproject control shutdown"]
    terminationGracePeriodSeconds: 300  # 5 minutes for tasks to complete
```

### Docker Compose Graceful Shutdown

```yaml
services:
  celery-worker:
    stop_grace_period: 5m  # Wait up to 5 minutes
    stop_signal: SIGTERM   # Send SIGTERM for graceful shutdown
```

## Health Checks

### Liveness Probe

```python
# health.py
from celery import current_app

def celery_liveness():
    """Check if worker can receive tasks."""
    try:
        result = current_app.control.ping(timeout=5)
        return bool(result)
    except Exception:
        return False
```

```yaml
# Kubernetes liveness probe
livenessProbe:
  exec:
    command:
    - python
    - -c
    - "from myproject.health import celery_liveness; exit(0 if celery_liveness() else 1)"
  initialDelaySeconds: 30
  periodSeconds: 30
  timeoutSeconds: 10
```

### Readiness Probe

```python
def celery_readiness():
    """Check if worker is ready to accept tasks."""
    try:
        inspect = current_app.control.inspect()
        stats = inspect.stats()
        return bool(stats)
    except Exception:
        return False
```

## Production Settings Checklist

```python
# settings/production.py

# Broker
CELERY_BROKER_URL = os.environ['CELERY_BROKER_URL']
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_CONNECTION_MAX_RETRIES = 10

# Result backend
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'django-db')
CELERY_RESULT_EXPIRES = 60 * 60 * 24  # 24 hours

# Serialization (JSON only for security)
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']

# Task execution
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 min
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60

# Worker
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000
CELERY_WORKER_DISABLE_RATE_LIMITS = False

# Beat (single instance only)
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# Monitoring
CELERY_SEND_EVENTS = True
CELERY_SEND_TASK_SENT_EVENT = True
```

## Security Considerations

### Network Security

```yaml
# docker-compose - internal network
services:
  redis:
    networks:
      - internal
    # No ports exposed to host

  celery-worker:
    networks:
      - internal
    # Access redis via internal network

networks:
  internal:
    driver: bridge
```

### Secrets Management

```python
# Never hardcode credentials
# Use environment variables or secrets manager
import os

CELERY_BROKER_URL = os.environ['CELERY_BROKER_URL']

# Or use AWS Secrets Manager, HashiCorp Vault, etc.
from myproject.secrets import get_secret
CELERY_BROKER_URL = get_secret('celery/broker-url')
```

### Task Argument Validation

```python
@shared_task(bind=True)
def secure_task(self, user_id, action):
    # Validate inputs
    if not isinstance(user_id, int):
        raise ValueError("Invalid user_id type")
    if action not in ['activate', 'deactivate']:
        raise ValueError("Invalid action")

    # Process safely
    process_action(user_id, action)
```

## Deployment Checklist

- [ ] Use process supervisor (systemd, supervisor, K8s)
- [ ] Only one Beat instance running
- [ ] Graceful shutdown configured
- [ ] Health checks in place
- [ ] Logging to persistent storage
- [ ] Monitoring and alerting configured
- [ ] Secrets properly managed
- [ ] Resource limits set
- [ ] Backup strategy for broker/backend
- [ ] Auto-scaling configured (if needed)
- [ ] Security groups/firewall rules configured
- [ ] SSL/TLS for broker connections (production)
