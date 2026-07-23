# Error Handling and Retry Strategies

## Basic Retry Configuration

### Simple Retry

```python
from celery import shared_task

@shared_task(bind=True, max_retries=3)
def task_with_retry(self, data):
    try:
        process(data)
    except TemporaryError as exc:
        # Retry with default delay (3 minutes)
        raise self.retry(exc=exc)
```

### Custom Retry Delay

```python
@shared_task(bind=True, max_retries=5)
def task_with_custom_retry(self, data):
    try:
        process(data)
    except TemporaryError as exc:
        # Retry after 60 seconds
        raise self.retry(exc=exc, countdown=60)
```

### Exponential Backoff

```python
@shared_task(bind=True, max_retries=5)
def task_with_backoff(self, data):
    try:
        process(data)
    except TemporaryError as exc:
        # Exponential backoff: 1min, 2min, 4min, 8min, 16min
        countdown = 60 * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)
```

### Retry with Jitter

```python
import random

@shared_task(bind=True, max_retries=5)
def task_with_jitter(self, data):
    try:
        process(data)
    except TemporaryError as exc:
        # Add randomness to prevent thundering herd
        base_delay = 60 * (2 ** self.request.retries)
        jitter = random.uniform(0, base_delay * 0.1)
        raise self.retry(exc=exc, countdown=base_delay + jitter)
```

## Auto-Retry Decorator

### Using autoretry_for

```python
@shared_task(
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=600,  # Max 10 minutes between retries
    retry_jitter=True,
    max_retries=5,
)
def auto_retry_task(self, data):
    # Will automatically retry on ConnectionError or TimeoutError
    response = call_external_api(data)
    return response
```

### Multiple Exception Types

```python
@shared_task(
    autoretry_for=(
        ConnectionError,
        TimeoutError,
        requests.exceptions.RequestException,
    ),
    retry_backoff=60,  # Start with 60 second delay
    retry_backoff_max=3600,  # Max 1 hour
    max_retries=10,
)
def robust_api_call(url):
    return requests.get(url, timeout=30).json()
```

## Exception Handling Patterns

### Handle Specific Exceptions Differently

```python
from celery.exceptions import MaxRetriesExceededError

@shared_task(bind=True, max_retries=3)
def task_with_exception_handling(self, order_id):
    try:
        order = Order.objects.get(id=order_id)
        order.process()

    except Order.DoesNotExist:
        # Permanent failure - don't retry
        logger.error(f"Order {order_id} not found")
        return None

    except PaymentGatewayError as exc:
        # Temporary - retry with backoff
        logger.warning(f"Payment gateway error: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))

    except InsufficientFundsError:
        # Business logic failure - don't retry
        order.mark_payment_failed()
        return {'status': 'failed', 'reason': 'insufficient_funds'}

    except MaxRetriesExceededError:
        # All retries exhausted
        order.mark_requires_manual_review()
        notify_admin(f"Order {order_id} requires manual review")
        raise
```

### Cleanup on Failure

```python
@shared_task(bind=True, max_retries=3)
def task_with_cleanup(self, resource_id):
    resource = None
    try:
        resource = acquire_resource(resource_id)
        process(resource)
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            # Final failure - cleanup
            if resource:
                cleanup_resource(resource)
            mark_as_failed(resource_id)
        raise self.retry(exc=exc, countdown=60)
    finally:
        if resource:
            release_resource(resource)
```

## Timeout Handling

### Soft Time Limit

```python
from celery.exceptions import SoftTimeLimitExceeded

@shared_task(
    bind=True,
    soft_time_limit=300,  # Raise exception after 5 min
    time_limit=360,       # Kill process after 6 min
)
def task_with_timeout(self, large_dataset):
    try:
        for item in large_dataset:
            process_item(item)
    except SoftTimeLimitExceeded:
        # Graceful cleanup
        logger.warning("Task timeout approaching, saving progress")
        save_progress()
        # Optionally retry with remaining items
        raise self.retry(countdown=60)
```

### Per-Execution Timeout

```python
@shared_task(bind=True)
def dynamic_timeout_task(self, data, timeout=300):
    # Apply timeout dynamically
    self.request.timelimit = (timeout, timeout + 60)
    process(data)
```

## Dead Letter Queue Pattern

### Manual Dead Letter Queue

```python
from kombu import Queue

CELERY_TASK_QUEUES = (
    Queue('default'),
    Queue('dead_letter'),
)

@shared_task(bind=True, max_retries=3)
def task_with_dlq(self, data):
    try:
        process(data)
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            # Send to dead letter queue for manual processing
            handle_dead_letter.delay(
                task_name=self.name,
                args=self.request.args,
                kwargs=self.request.kwargs,
                exception=str(exc),
                traceback=traceback.format_exc(),
            )
            return
        raise self.retry(exc=exc, countdown=60)


@shared_task(queue='dead_letter')
def handle_dead_letter(task_name, args, kwargs, exception, traceback):
    # Store for manual review
    DeadLetterMessage.objects.create(
        task_name=task_name,
        args=args,
        kwargs=kwargs,
        exception=exception,
        traceback=traceback,
    )
    notify_admin(f"Dead letter: {task_name}")
```

### RabbitMQ Dead Letter Exchange

```python
from kombu import Exchange, Queue

# Configure dead letter exchange in RabbitMQ
dlx = Exchange('dlx', type='direct')
dead_letter_queue = Queue(
    'dead_letters',
    exchange=dlx,
    routing_key='dead_letter',
)

main_queue = Queue(
    'default',
    queue_arguments={
        'x-dead-letter-exchange': 'dlx',
        'x-dead-letter-routing-key': 'dead_letter',
    },
)

CELERY_TASK_QUEUES = (main_queue, dead_letter_queue)
```

## Error Callbacks

### Using on_failure

```python
from celery import Task

class TaskWithErrorCallback(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(
            f'Task {self.name}[{task_id}] failed: {exc}',
            exc_info=einfo.exc_info,
        )
        # Send notification
        send_alert(
            title=f"Task Failed: {self.name}",
            message=str(exc),
            task_id=task_id,
        )


@shared_task(base=TaskWithErrorCallback, bind=True)
def task_with_error_callback(self, data):
    process(data)
```

### Link Error Callback

```python
@shared_task
def error_handler(request, exc, traceback):
    logger.error(
        f'Task {request.id} raised exception: {exc}',
        extra={
            'task_id': request.id,
            'task_name': request.task,
            'args': request.args,
            'kwargs': request.kwargs,
        }
    )

# Attach error callback when calling
my_task.apply_async(
    args=[data],
    link_error=error_handler.s(),
)
```

## Idempotent Error Handling

### Safe Retry Pattern

```python
@shared_task(bind=True, max_retries=5)
def idempotent_payment_task(self, order_id, idempotency_key):
    # Check if already processed
    if PaymentRecord.objects.filter(idempotency_key=idempotency_key).exists():
        logger.info(f"Payment {idempotency_key} already processed")
        return {'status': 'already_processed'}

    try:
        result = process_payment(order_id)

        # Record successful payment
        PaymentRecord.objects.create(
            idempotency_key=idempotency_key,
            order_id=order_id,
            result=result,
        )
        return result

    except PaymentGatewayError as exc:
        # Safe to retry - payment won't be duplicated
        raise self.retry(exc=exc, countdown=60)
```

### Transactional Safety

```python
from django.db import transaction

@shared_task(bind=True, max_retries=3)
def transactional_task(self, order_id):
    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().get(id=order_id)

            if order.status == 'processed':
                return {'status': 'already_processed'}

            # All-or-nothing processing
            process_order(order)
            update_inventory(order)
            order.status = 'processed'
            order.save()

    except Order.DoesNotExist:
        return None
    except Exception as exc:
        # Transaction rolled back, safe to retry
        raise self.retry(exc=exc, countdown=60)
```

## Monitoring Failed Tasks

### Logging Configuration

```python
# celery.py
import logging

logger = logging.getLogger('celery.task')

@signals.task_failure.connect
def log_task_failure(sender, task_id, exception, args, kwargs, traceback, einfo, **kw):
    logger.error(
        f'Task {sender.name}[{task_id}] failed',
        exc_info=einfo.exc_info,
        extra={
            'task_name': sender.name,
            'task_id': task_id,
            'args': args,
            'kwargs': kwargs,
        }
    )

@signals.task_retry.connect
def log_task_retry(sender, request, reason, einfo, **kw):
    logger.warning(
        f'Task {sender.name}[{request.id}] retrying: {reason}',
        extra={
            'task_name': sender.name,
            'task_id': request.id,
            'retry_count': request.retries,
        }
    )
```

### Storing Failed Tasks

```python
# models.py
class FailedTask(models.Model):
    task_id = models.CharField(max_length=255, unique=True)
    task_name = models.CharField(max_length=255)
    args = models.JSONField()
    kwargs = models.JSONField()
    exception = models.TextField()
    traceback = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    retried = models.BooleanField(default=False)

# signals
@signals.task_failure.connect
def store_failed_task(sender, task_id, exception, args, kwargs, traceback, einfo, **kw):
    FailedTask.objects.update_or_create(
        task_id=task_id,
        defaults={
            'task_name': sender.name,
            'args': list(args),
            'kwargs': dict(kwargs),
            'exception': str(exception),
            'traceback': einfo.traceback if einfo else '',
        }
    )
```

## Retry Best Practices Summary

| Scenario | Retry Strategy |
|----------|---------------|
| Network errors | Exponential backoff with jitter, 5+ retries |
| Rate limiting | Respect Retry-After header, or fixed backoff |
| Database locks | Short delay (1-5s), few retries |
| External API down | Long backoff (minutes), many retries |
| Invalid data | Don't retry, log and alert |
| Resource not found | Don't retry (usually permanent) |
| Authentication errors | Don't retry, investigate |
| Timeout | Retry with same/increased timeout |

### Configuration Recommendations

```python
# Production retry configuration
@shared_task(
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,        # Exponential backoff
    retry_backoff_max=600,     # Max 10 min between retries
    retry_jitter=True,         # Add randomness
    max_retries=5,             # Limit total attempts
    acks_late=True,            # Ack after completion
    reject_on_worker_lost=True # Requeue if worker dies
)
def production_task(self, data):
    pass
```
