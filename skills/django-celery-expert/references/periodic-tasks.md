# Periodic Tasks with Celery Beat

## Celery Beat Overview

Celery Beat is a scheduler that kicks off tasks at regular intervals. Tasks are executed by available workers.

### Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Celery Beat    │────▶│  Message Broker │────▶│  Celery Worker  │
│  (scheduler)    │     │  (Redis/RMQ)    │     │  (executor)     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

**Important:** Only run ONE Beat scheduler instance to avoid duplicate task execution.

## Basic Configuration

### Static Schedule in Settings

```python
# settings.py
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    # Execute every 30 seconds
    'check-heartbeat': {
        'task': 'myapp.tasks.check_heartbeat',
        'schedule': 30.0,
    },

    # Execute every minute
    'process-queue': {
        'task': 'myapp.tasks.process_queue',
        'schedule': 60.0,
        'args': (),
    },

    # Execute at midnight every day
    'daily-cleanup': {
        'task': 'myapp.tasks.daily_cleanup',
        'schedule': crontab(hour=0, minute=0),
    },

    # Execute Monday at 7:30am
    'weekly-report': {
        'task': 'myapp.tasks.send_weekly_report',
        'schedule': crontab(hour=7, minute=30, day_of_week=1),
    },

    # Every hour on the hour
    'hourly-sync': {
        'task': 'myapp.tasks.sync_data',
        'schedule': crontab(minute=0),
    },
}
```

### Schedule Types

```python
from celery.schedules import crontab, solar
from datetime import timedelta

CELERY_BEAT_SCHEDULE = {
    # Timedelta - simple intervals
    'every-10-seconds': {
        'task': 'myapp.tasks.quick_check',
        'schedule': timedelta(seconds=10),
    },

    'every-5-minutes': {
        'task': 'myapp.tasks.periodic_check',
        'schedule': timedelta(minutes=5),
    },

    # Crontab - cron-like schedule
    'weekday-mornings': {
        'task': 'myapp.tasks.morning_task',
        'schedule': crontab(hour=8, minute=0, day_of_week='mon-fri'),
    },

    # First of every month
    'monthly-report': {
        'task': 'myapp.tasks.monthly_report',
        'schedule': crontab(day_of_month=1, hour=0, minute=0),
    },

    # Every quarter (1st of Jan, Apr, Jul, Oct)
    'quarterly-report': {
        'task': 'myapp.tasks.quarterly_report',
        'schedule': crontab(day_of_month=1, month_of_year='1,4,7,10', hour=0, minute=0),
    },

    # Solar schedule - based on sunrise/sunset
    'at-sunrise': {
        'task': 'myapp.tasks.sunrise_task',
        'schedule': solar('sunrise', -37.81753, 144.96715),  # Melbourne
    },
}
```

## Crontab Reference

```python
from celery.schedules import crontab

# Crontab arguments:
# minute, hour, day_of_week, day_of_month, month_of_year

# Every minute
crontab()

# Every hour at minute 0
crontab(minute=0)

# Every day at midnight
crontab(minute=0, hour=0)

# Every Monday
crontab(minute=0, hour=0, day_of_week=1)

# Every 15 minutes
crontab(minute='*/15')

# Every hour between 9am-5pm on weekdays
crontab(minute=0, hour='9-17', day_of_week='mon-fri')

# At 12:30 on the 15th of every month
crontab(minute=30, hour=12, day_of_month=15)

# Multiple specific values
crontab(minute=0, hour='0,12')  # Midnight and noon
crontab(day_of_week='mon,wed,fri')  # MWF
```

## Django Database Scheduler

### Setup

```bash
pip install django-celery-beat
```

```python
# settings.py
INSTALLED_APPS = [
    ...
    'django_celery_beat',
]

# Use database scheduler
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
```

```bash
python manage.py migrate django_celery_beat
```

### Managing Schedules via Admin

```python
# admin.py
from django_celery_beat.models import (
    PeriodicTask,
    IntervalSchedule,
    CrontabSchedule,
)

# These are auto-registered, but you can customize:
from django.contrib import admin
from django_celery_beat.admin import PeriodicTaskAdmin
from django_celery_beat.models import PeriodicTask

class CustomPeriodicTaskAdmin(PeriodicTaskAdmin):
    list_display = ['name', 'task', 'enabled', 'last_run_at']
    list_filter = ['enabled', 'task']

admin.site.unregister(PeriodicTask)
admin.site.register(PeriodicTask, CustomPeriodicTaskAdmin)
```

### Creating Schedules Programmatically

```python
from django_celery_beat.models import (
    PeriodicTask,
    IntervalSchedule,
    CrontabSchedule,
)
import json

# Create interval schedule (every 10 minutes)
schedule, created = IntervalSchedule.objects.get_or_create(
    every=10,
    period=IntervalSchedule.MINUTES,
)

# Create periodic task with interval
PeriodicTask.objects.create(
    interval=schedule,
    name='Sync Data Every 10 Minutes',
    task='myapp.tasks.sync_data',
    args=json.dumps([]),
    kwargs=json.dumps({}),
)

# Create crontab schedule (daily at 6am)
cron_schedule, _ = CrontabSchedule.objects.get_or_create(
    minute='0',
    hour='6',
    day_of_week='*',
    day_of_month='*',
    month_of_year='*',
)

# Create periodic task with crontab
PeriodicTask.objects.create(
    crontab=cron_schedule,
    name='Daily Report',
    task='myapp.tasks.generate_daily_report',
    args=json.dumps(['pdf']),
    kwargs=json.dumps({'include_charts': True}),
    enabled=True,
)
```

### Dynamic Schedule Management

```python
from django_celery_beat.models import PeriodicTask, IntervalSchedule
import json

def create_user_notification_schedule(user_id, interval_minutes):
    """Create a periodic task for user-specific notifications."""
    schedule, _ = IntervalSchedule.objects.get_or_create(
        every=interval_minutes,
        period=IntervalSchedule.MINUTES,
    )

    task_name = f'notify-user-{user_id}'

    PeriodicTask.objects.update_or_create(
        name=task_name,
        defaults={
            'interval': schedule,
            'task': 'notifications.tasks.send_user_digest',
            'kwargs': json.dumps({'user_id': user_id}),
            'enabled': True,
        }
    )

def disable_user_notifications(user_id):
    """Disable notifications for a user."""
    task_name = f'notify-user-{user_id}'
    PeriodicTask.objects.filter(name=task_name).update(enabled=False)

def delete_user_notifications(user_id):
    """Remove notification schedule for a user."""
    task_name = f'notify-user-{user_id}'
    PeriodicTask.objects.filter(name=task_name).delete()
```

## Timezone Handling

### Configuration

```python
# settings.py
CELERY_TIMEZONE = 'America/New_York'
CELERY_ENABLE_UTC = True  # Store in UTC, display in timezone

# Or use Django's timezone
CELERY_TIMEZONE = TIME_ZONE
```

### Timezone-Aware Crontabs

```python
from celery.schedules import crontab
import pytz

CELERY_BEAT_SCHEDULE = {
    # This runs at 9am in the configured CELERY_TIMEZONE
    'morning-email': {
        'task': 'myapp.tasks.send_morning_email',
        'schedule': crontab(hour=9, minute=0),
    },
}

# For database scheduler, set timezone on CrontabSchedule
from django_celery_beat.models import CrontabSchedule

schedule = CrontabSchedule.objects.create(
    minute='0',
    hour='9',
    timezone=pytz.timezone('America/New_York'),
)
```

## Task Arguments and Options

### Passing Arguments

```python
CELERY_BEAT_SCHEDULE = {
    'daily-report': {
        'task': 'myapp.tasks.generate_report',
        'schedule': crontab(hour=6, minute=0),
        'args': ('daily', 'pdf'),
        'kwargs': {'include_charts': True, 'recipients': ['admin@example.com']},
    },
}
```

### Task Options

```python
CELERY_BEAT_SCHEDULE = {
    'priority-task': {
        'task': 'myapp.tasks.important_task',
        'schedule': crontab(minute='*/5'),
        'options': {
            'queue': 'high-priority',
            'priority': 9,
            'expires': 300,  # Expire if not started in 5 min
        },
    },
}
```

## Preventing Duplicate Executions

### Using Locks

```python
from django.core.cache import cache
from celery import shared_task
from contextlib import contextmanager

@contextmanager
def beat_lock(lock_id, timeout=60*60):
    """Prevent duplicate periodic task execution."""
    lock_acquired = cache.add(lock_id, 'locked', timeout)
    try:
        yield lock_acquired
    finally:
        if lock_acquired:
            cache.delete(lock_id)

@shared_task
def hourly_sync():
    with beat_lock('hourly-sync-lock') as acquired:
        if not acquired:
            return  # Another instance is running

        # Safe to execute
        perform_sync()
```

### Using celery-once

```bash
pip install celery-once
```

```python
from celery_once import QueueOnce

@shared_task(base=QueueOnce, once={'graceful': True})
def slow_task():
    # Only one instance runs at a time
    perform_slow_operation()
```

## Running Celery Beat

### Development

```bash
# Run beat with worker (for development only)
celery -A myproject worker --beat --loglevel=info

# Run beat separately
celery -A myproject beat --loglevel=info
```

### Production

```bash
# Run beat as separate process
celery -A myproject beat --loglevel=info --pidfile=/var/run/celery/beat.pid

# With database scheduler
celery -A myproject beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

## Best Practices

### Schedule Design

```python
# GOOD: Offset schedules to avoid thundering herd
CELERY_BEAT_SCHEDULE = {
    'task-a': {'task': 'app.task_a', 'schedule': crontab(minute=0)},  # :00
    'task-b': {'task': 'app.task_b', 'schedule': crontab(minute=5)},  # :05
    'task-c': {'task': 'app.task_c', 'schedule': crontab(minute=10)}, # :10
}

# BAD: All tasks at the same time
CELERY_BEAT_SCHEDULE = {
    'task-a': {'task': 'app.task_a', 'schedule': crontab(minute=0)},
    'task-b': {'task': 'app.task_b', 'schedule': crontab(minute=0)},
    'task-c': {'task': 'app.task_c', 'schedule': crontab(minute=0)},
}
```

### Handling Long-Running Tasks

```python
@shared_task(
    soft_time_limit=3600,  # 1 hour soft limit
    time_limit=3660,       # Hard limit slightly longer
)
def daily_report():
    """Generate daily report - may take up to 1 hour."""
    # Set schedule to run with enough gap
    pass

CELERY_BEAT_SCHEDULE = {
    'daily-report': {
        'task': 'myapp.tasks.daily_report',
        'schedule': crontab(hour=2, minute=0),  # 2am, plenty of time before business hours
        'options': {'expires': 3600 * 3},  # Expire if not started in 3 hours
    },
}
```

### Monitoring Beat Health

```python
@shared_task
def beat_health_check():
    """Record that beat is running."""
    cache.set('celery-beat-heartbeat', timezone.now(), timeout=120)

CELERY_BEAT_SCHEDULE = {
    'beat-health-check': {
        'task': 'myapp.tasks.beat_health_check',
        'schedule': 60.0,  # Every minute
    },
}

# Check beat health
def is_beat_healthy():
    last_heartbeat = cache.get('celery-beat-heartbeat')
    if not last_heartbeat:
        return False
    return (timezone.now() - last_heartbeat).seconds < 120
```

### Cleanup Old Task Results

```python
# Clean up task results periodically
@shared_task
def cleanup_task_results():
    """Remove old task results from database."""
    from django_celery_results.models import TaskResult

    cutoff = timezone.now() - timedelta(days=7)
    TaskResult.objects.filter(date_created__lt=cutoff).delete()

CELERY_BEAT_SCHEDULE = {
    'cleanup-results': {
        'task': 'myapp.tasks.cleanup_task_results',
        'schedule': crontab(hour=3, minute=0),  # Daily at 3am
    },
}
```

## Common Patterns

### Conditional Execution

```python
@shared_task
def conditional_task():
    """Only execute if conditions are met."""
    if not should_run_today():
        return

    perform_task()

def should_run_today():
    # Skip weekends
    if timezone.now().weekday() >= 5:
        return False
    # Skip holidays
    if Holiday.objects.filter(date=timezone.now().date()).exists():
        return False
    return True
```

### Chained Periodic Tasks

```python
from celery import chain

@shared_task
def start_daily_pipeline():
    """Kick off daily processing pipeline."""
    workflow = chain(
        fetch_data.s(),
        process_data.s(),
        generate_report.s(),
        send_notifications.s(),
    )
    workflow.delay()

CELERY_BEAT_SCHEDULE = {
    'daily-pipeline': {
        'task': 'myapp.tasks.start_daily_pipeline',
        'schedule': crontab(hour=6, minute=0),
    },
}
```
