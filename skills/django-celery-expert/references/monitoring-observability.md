# Monitoring and Observability

## Flower - Real-Time Monitor

### Installation and Setup

```bash
pip install flower
```

```bash
# Basic usage
celery -A myproject flower

# With options
celery -A myproject flower \
    --port=5555 \
    --broker=redis://localhost:6379/0 \
    --basic_auth=admin:password

# Persistent storage
celery -A myproject flower --persistent=True --db=flower.db
```

### Flower Configuration

```python
# flower_config.py
broker_api = 'redis://localhost:6379/0'
port = 5555
basic_auth = ['admin:secure_password']
persistent = True
db = '/var/lib/flower/flower.db'
max_tasks = 10000
purge_offline_workers = 300  # Remove offline workers after 5 min
```

```bash
celery -A myproject flower --conf=flower_config.py
```

### Flower in Production

```python
# docker-compose.yml
services:
  flower:
    image: mher/flower
    command: celery flower --broker=redis://redis:6379/0
    ports:
      - "5555:5555"
    environment:
      - FLOWER_BASIC_AUTH=admin:password
    depends_on:
      - redis
      - worker
```

### Flower API

```python
import requests

# List workers
response = requests.get('http://localhost:5555/api/workers')
workers = response.json()

# Get task info
response = requests.get(f'http://localhost:5555/api/task/info/{task_id}')
task_info = response.json()

# Revoke task
requests.post(f'http://localhost:5555/api/task/revoke/{task_id}')

# Queue length
response = requests.get('http://localhost:5555/api/queues/length')
queue_lengths = response.json()
```

## Logging Best Practices

### Task Logging Configuration

```python
# settings.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'celery': {
            'format': '[%(asctime)s: %(levelname)s/%(processName)s] [%(task_name)s(%(task_id)s)] %(message)s',
        },
    },
    'handlers': {
        'celery': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/celery/tasks.log',
            'maxBytes': 1024 * 1024 * 100,  # 100MB
            'backupCount': 10,
            'formatter': 'celery',
        },
    },
    'loggers': {
        'celery': {
            'handlers': ['celery'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery.task': {
            'handlers': ['celery'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
```

### Structured Logging

```python
import structlog
from celery import shared_task

logger = structlog.get_logger()

@shared_task(bind=True)
def process_order(self, order_id):
    log = logger.bind(
        task_id=self.request.id,
        task_name=self.name,
        order_id=order_id,
    )

    log.info('starting_order_processing')

    try:
        order = Order.objects.get(id=order_id)
        log = log.bind(user_id=order.user_id)

        result = process(order)
        log.info('order_processed', result=result)
        return result

    except Order.DoesNotExist:
        log.error('order_not_found')
        raise
    except Exception as e:
        log.exception('order_processing_failed', error=str(e))
        raise
```

### Celery Signals for Logging

```python
from celery import signals
import logging

logger = logging.getLogger('celery.task')

@signals.task_prerun.connect
def task_prerun_handler(task_id, task, args, kwargs, **kw):
    logger.info(f'Task starting: {task.name}[{task_id}]')

@signals.task_postrun.connect
def task_postrun_handler(task_id, task, args, kwargs, retval, state, **kw):
    logger.info(f'Task completed: {task.name}[{task_id}] state={state}')

@signals.task_failure.connect
def task_failure_handler(task_id, exception, args, kwargs, traceback, einfo, **kw):
    logger.error(
        f'Task failed: {task_id}',
        exc_info=True,
        extra={'args': args, 'kwargs': kwargs}
    )

@signals.task_retry.connect
def task_retry_handler(request, reason, einfo, **kw):
    logger.warning(f'Task retrying: {request.id} reason={reason}')
```

## Prometheus Metrics

### Setup with celery-exporter

```bash
pip install celery-exporter
```

```bash
celery-exporter --broker-url=redis://localhost:6379/0 --port=9808
```

### Queue Monitoring

```python
from celery import current_app
from prometheus_client import Gauge

QUEUE_LENGTH = Gauge('celery_queue_length', 'Queue length', ['queue'])

def update_queue_metrics():
    """Update queue length metrics."""
    with current_app.connection() as conn:
        for queue in ['default', 'high-priority', 'low-priority']:
            try:
                length = conn.default_channel.queue_declare(
                    queue=queue, passive=True
                ).message_count
                QUEUE_LENGTH.labels(queue=queue).set(length)
            except Exception:
                pass

# Call periodically via Beat
@shared_task
def collect_queue_metrics():
    update_queue_metrics()
```

## Health Checks

### Worker Health Check

```python
from celery import current_app

def check_celery_health():
    """Check if Celery workers are healthy."""
    try:
        # Ping workers
        result = current_app.control.ping(timeout=5)
        if not result:
            return {'healthy': False, 'error': 'No workers responded'}

        # Check active workers
        active = current_app.control.inspect().active()
        if not active:
            return {'healthy': False, 'error': 'No active workers'}

        return {
            'healthy': True,
            'workers': len(active),
            'worker_names': list(active.keys()),
        }
    except Exception as e:
        return {'healthy': False, 'error': str(e)}
```

### Django Health Check Integration

```python
# healthchecks.py
from health_check.backends import BaseHealthCheckBackend
from health_check.exceptions import HealthCheckException
from celery import current_app

class CeleryHealthCheck(BaseHealthCheckBackend):
    critical_service = True

    def check_status(self):
        try:
            result = current_app.control.ping(timeout=3)
            if not result:
                raise HealthCheckException('No Celery workers available')
        except Exception as e:
            raise HealthCheckException(str(e))

    def identifier(self):
        return 'Celery Workers'
```

```python
# settings.py
INSTALLED_APPS = [
    ...
    'health_check',
    'health_check.contrib.celery',
]
```

### Beat Health Check

```python
from django.core.cache import cache
from django.utils import timezone

@shared_task
def beat_heartbeat():
    """Record Beat scheduler heartbeat."""
    cache.set('celery_beat_heartbeat', timezone.now().isoformat(), timeout=120)

def check_beat_health():
    """Check if Beat is running."""
    heartbeat = cache.get('celery_beat_heartbeat')
    if not heartbeat:
        return {'healthy': False, 'error': 'No heartbeat recorded'}

    last_beat = timezone.datetime.fromisoformat(heartbeat)
    age = (timezone.now() - last_beat).seconds

    if age > 120:
        return {'healthy': False, 'error': f'Heartbeat is {age}s old'}

    return {'healthy': True, 'last_heartbeat': heartbeat}
```

## Debugging Stuck Tasks

### Inspecting Workers

```python
from celery import current_app

def inspect_workers():
    """Get detailed worker information."""
    inspect = current_app.control.inspect()

    return {
        'active': inspect.active(),      # Currently executing tasks
        'reserved': inspect.reserved(),   # Prefetched tasks
        'scheduled': inspect.scheduled(), # ETA/countdown tasks
        'stats': inspect.stats(),         # Worker statistics
    }

def get_active_tasks():
    """List all currently running tasks."""
    inspect = current_app.control.inspect()
    active = inspect.active()

    tasks = []
    for worker, task_list in (active or {}).items():
        for task in task_list:
            tasks.append({
                'worker': worker,
                'task_id': task['id'],
                'task_name': task['name'],
                'args': task['args'],
                'started': task.get('time_start'),
            })
    return tasks
```

### Finding Long-Running Tasks

```python
import time

def find_long_running_tasks(threshold_seconds=300):
    """Find tasks running longer than threshold."""
    inspect = current_app.control.inspect()
    active = inspect.active() or {}

    long_running = []
    now = time.time()

    for worker, tasks in active.items():
        for task in tasks:
            start_time = task.get('time_start')
            if start_time:
                duration = now - start_time
                if duration > threshold_seconds:
                    long_running.append({
                        'worker': worker,
                        'task_id': task['id'],
                        'task_name': task['name'],
                        'duration_seconds': int(duration),
                    })

    return long_running
```

### Queue Inspection

```python
def inspect_queues():
    """Get queue information."""
    from kombu import Connection

    with Connection(current_app.conf.broker_url) as conn:
        queues = {}
        for queue_name in ['default', 'high-priority', 'low-priority']:
            try:
                queue = conn.SimpleQueue(queue_name)
                queues[queue_name] = {
                    'length': len(queue),
                }
                queue.close()
            except Exception as e:
                queues[queue_name] = {'error': str(e)}

    return queues
```

## Alerting

### Slack Alerts

```python
import requests
from celery import signals

SLACK_WEBHOOK_URL = 'https://hooks.slack.com/services/XXX/YYY/ZZZ'

def send_slack_alert(message, level='warning'):
    color = {'info': '#36a64f', 'warning': '#ff9800', 'error': '#f44336'}
    requests.post(SLACK_WEBHOOK_URL, json={
        'attachments': [{
            'color': color.get(level, '#808080'),
            'text': message,
        }]
    })

@signals.task_failure.connect
def alert_on_failure(sender, task_id, exception, **kwargs):
    message = f"Task `{sender.name}` failed: {exception}"
    send_slack_alert(message, level='error')

@signals.task_retry.connect
def alert_on_retry(sender, request, reason, **kwargs):
    if request.retries >= 3:  # Only alert after multiple retries
        message = f"Task `{sender.name}` retrying ({request.retries}): {reason}"
        send_slack_alert(message, level='warning')
```

### PagerDuty Integration

```python
import pypd
from celery import signals

pypd.api_key = 'your-api-key'

@signals.task_failure.connect
def pagerduty_alert(sender, task_id, exception, **kwargs):
    # Only page for critical tasks
    critical_tasks = ['process_payment', 'send_critical_notification']

    if sender.name in critical_tasks:
        pypd.Event.create(data={
            'service_key': 'your-service-key',
            'event_type': 'trigger',
            'description': f'Critical task failed: {sender.name}',
            'details': {
                'task_id': task_id,
                'exception': str(exception),
            }
        })
```

## Dashboard Queries

### Key Metrics to Monitor

| Metric | Alert Threshold | Description |
|--------|-----------------|-------------|
| Queue length | > 1000 | Tasks piling up |
| Worker count | < expected | Workers died |
| Task failure rate | > 5% | High failure rate |
| Task duration p95 | > SLA | Tasks taking too long |
| Retry rate | > 10% | Transient issues |
| Beat heartbeat age | > 2 min | Beat stopped |
