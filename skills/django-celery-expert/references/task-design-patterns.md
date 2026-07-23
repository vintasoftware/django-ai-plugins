# Task Design Patterns

## Task Fundamentals

### Basic Task Definition

```python
from celery import shared_task

# Simple task - use for reusable Django apps
@shared_task
def add(x, y):
    return x + y

# Bound task - access to self for retries, logging
@shared_task(bind=True)
def process_data(self, data_id):
    self.update_state(state='PROCESSING')
    # ...
```

### Task Naming

Always use explicit names for production tasks:

```python
# Explicit name - recommended for production
@shared_task(name='orders.tasks.process_order')
def process_order(order_id):
    pass

# Auto-generated name (module.function_name)
# Can break if you refactor or rename
@shared_task
def process_order(order_id):
    pass
```

### Task Signatures

```python
# Different ways to call tasks
task.delay(arg1, arg2)              # Shortcut for apply_async
task.apply_async(args=[arg1, arg2]) # Full control
task.apply_async(
    args=[arg1],
    kwargs={'key': 'value'},
    countdown=60,                    # Delay execution by 60 seconds
    eta=datetime(2024, 1, 1, 12, 0), # Execute at specific time
    expires=3600,                    # Expire if not started in 1 hour
    queue='high-priority',           # Route to specific queue
    priority=9,                      # Task priority (0-9, higher = more priority)
)

# Signature objects for building workflows
from celery import signature
sig = signature('tasks.add', args=(2, 2))
sig = add.s(2, 2)  # Shortcut
sig = add.si(2, 2) # Immutable signature (ignores return from previous task)
```

## Argument Best Practices

### Pass IDs, Not Objects

```python
# BAD - Django objects aren't JSON serializable
@shared_task
def process_order(order):  # Don't pass model instances!
    order.process()

# GOOD - Pass primary keys
@shared_task
def process_order(order_id):
    from orders.models import Order
    order = Order.objects.get(id=order_id)
    order.process()
```

### Handle Missing Objects

```python
@shared_task(bind=True)
def send_notification(self, user_id):
    from users.models import User

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        # Object was deleted between queuing and execution
        # Log and skip - don't retry
        logger.warning(f"User {user_id} not found, skipping notification")
        return None

    user.send_notification()
```

### Serializable Arguments Only

```python
# GOOD - primitive types
@shared_task
def process(user_id, action, options=None):
    pass

process.delay(123, 'activate', {'notify': True})

# BAD - non-serializable types
@shared_task
def process(user, callback_func):  # Can't serialize!
    pass
```

## Idempotency

### Why Idempotency Matters

Tasks may execute multiple times due to:
- Network issues causing duplicate messages
- Worker crashes mid-execution followed by retry
- Manual task replay for debugging

### Idempotent Task Patterns

```python
# BAD - Not idempotent, will increment multiple times on retry
@shared_task
def increment_counter(counter_id):
    counter = Counter.objects.get(id=counter_id)
    counter.value += 1
    counter.save()

# GOOD - Idempotent using state check
@shared_task
def increment_counter(counter_id, expected_value):
    Counter.objects.filter(
        id=counter_id,
        value=expected_value  # Only update if value hasn't changed
    ).update(value=F('value') + 1)

# GOOD - Idempotent using unique constraint
@shared_task
def create_order_item(order_id, product_id, quantity, idempotency_key):
    OrderItem.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            'order_id': order_id,
            'product_id': product_id,
            'quantity': quantity,
        }
    )
```

### Deduplication with Locks

```python
from django.core.cache import cache
from contextlib import contextmanager

@contextmanager
def task_lock(lock_id, timeout=60*10):
    lock_acquired = cache.add(lock_id, 'locked', timeout)
    try:
        yield lock_acquired
    finally:
        if lock_acquired:
            cache.delete(lock_id)

@shared_task(bind=True)
def deduplicated_task(self, resource_id):
    lock_id = f'task-lock-{resource_id}'

    with task_lock(lock_id) as acquired:
        if not acquired:
            # Another task is processing this resource
            logger.info(f"Task for {resource_id} already running, skipping")
            return

        # Safe to process
        process_resource(resource_id)
```

## Workflow Patterns

### Chains - Sequential Execution

```python
from celery import chain

# Each task passes its result to the next
workflow = chain(
    fetch_data.s(url),        # Returns data
    parse_data.s(),           # Receives data, returns parsed
    store_data.s(),           # Receives parsed, stores
    notify_complete.si()      # si() = immutable, ignores input
)
result = workflow.delay()
```

### Groups - Parallel Execution

```python
from celery import group

# Execute tasks in parallel
parallel = group(
    process_item.s(item_id) for item_id in item_ids
)
result = parallel.delay()

# Get all results (blocks until all complete)
results = result.get()
```

### Chords - Parallel with Callback

```python
from celery import chord

# Run tasks in parallel, then call callback with all results
workflow = chord(
    [process_item.s(item_id) for item_id in item_ids],
    aggregate_results.s()  # Called with list of all results
)
result = workflow.delay()
```

### Complex Workflows

```python
from celery import chain, group, chord

# Example: Process order with parallel item processing
workflow = chain(
    validate_order.s(order_id),
    chord(
        [process_item.s(item_id) for item_id in item_ids],
        finalize_order.s(order_id)
    ),
    send_confirmation.s()
)
```

## Task Inheritance

### Base Task Classes

```python
from celery import Task

class DatabaseTask(Task):
    """Base task that ensures database connection."""

    def __call__(self, *args, **kwargs):
        from django.db import connection
        connection.ensure_connection()
        return super().__call__(*args, **kwargs)


class LoggedTask(Task):
    """Base task with automatic logging."""

    def on_success(self, retval, task_id, args, kwargs):
        logger.info(f'Task {self.name}[{task_id}] succeeded')

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f'Task {self.name}[{task_id}] failed: {exc}')

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        logger.warning(f'Task {self.name}[{task_id}] retrying: {exc}')


@shared_task(base=LoggedTask, bind=True)
def my_logged_task(self, data):
    pass
```

### Abstract Base Tasks

```python
from celery import shared_task

class NotificationTaskMixin:
    """Mixin for notification tasks."""
    max_retries = 3
    default_retry_delay = 60

    def get_user(self, user_id):
        from users.models import User
        return User.objects.get(id=user_id)


class EmailNotificationTask(NotificationTaskMixin, Task):
    pass


@shared_task(base=EmailNotificationTask, bind=True)
def send_email_notification(self, user_id, template):
    user = self.get_user(user_id)
    # ...
```

## Task Context and Metadata

### Accessing Task Properties

```python
@shared_task(bind=True)
def task_with_context(self, data):
    # Task metadata
    task_id = self.request.id
    task_name = self.name
    retries = self.request.retries

    # Execution context
    hostname = self.request.hostname
    delivery_info = self.request.delivery_info
    called_directly = self.request.called_directly

    # Parent task (if called from another task)
    parent_id = self.request.parent_id
    root_id = self.request.root_id  # Original task that started the chain

    # Headers (custom metadata)
    custom_header = self.request.headers.get('my_header')
```

### Passing Context Through Chains

```python
# Using headers for context that persists through chain
@shared_task(bind=True)
def step_one(self, data):
    correlation_id = self.request.headers.get('correlation_id')
    logger.info(f"[{correlation_id}] Processing step one")
    return data

# Apply with headers
chain(
    step_one.s(data),
    step_two.s(),
).apply_async(headers={'correlation_id': 'abc-123'})
```

## Long-Running Tasks

### Progress Tracking

```python
@shared_task(bind=True)
def long_running_task(self, items):
    total = len(items)

    for i, item in enumerate(items):
        process_item(item)

        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={
                'current': i + 1,
                'total': total,
                'percent': int((i + 1) / total * 100)
            }
        )

    return {'status': 'complete', 'processed': total}

# Check progress from Django view
def check_progress(request, task_id):
    result = long_running_task.AsyncResult(task_id)

    if result.state == 'PENDING':
        response = {'state': 'PENDING', 'progress': 0}
    elif result.state == 'PROGRESS':
        response = {
            'state': 'PROGRESS',
            'progress': result.info.get('percent', 0)
        }
    elif result.state == 'SUCCESS':
        response = {'state': 'SUCCESS', 'result': result.result}
    else:
        response = {'state': result.state, 'error': str(result.info)}

    return JsonResponse(response)
```

### Chunking Large Datasets

```python
from celery import chord, group

@shared_task
def process_chunk(item_ids):
    items = Item.objects.filter(id__in=item_ids)
    for item in items:
        item.process()
    return len(item_ids)

@shared_task
def aggregate_results(results):
    total = sum(results)
    logger.info(f"Processed {total} items total")
    return total

def process_all_items():
    all_ids = list(Item.objects.values_list('id', flat=True))
    chunk_size = 100

    # Split into chunks
    chunks = [
        all_ids[i:i + chunk_size]
        for i in range(0, len(all_ids), chunk_size)
    ]

    # Process chunks in parallel, aggregate at end
    workflow = chord(
        [process_chunk.s(chunk) for chunk in chunks],
        aggregate_results.s()
    )
    return workflow.delay()
```

## Task Revocation

### Revoking Tasks

```python
from celery.result import AsyncResult

# Revoke a single task
result = my_task.delay(data)
result.revoke()

# Revoke with termination (kills running task)
result.revoke(terminate=True)

# Revoke by task ID
from myproject.celery import app
app.control.revoke(task_id, terminate=True)

# Revoke multiple tasks
app.control.revoke([task_id1, task_id2])
```

### Handling Revocation in Tasks

```python
from celery.exceptions import Terminated

@shared_task(bind=True)
def cancelable_task(self, items):
    for item in items:
        # Check if task was revoked
        if self.is_aborted():
            logger.info("Task was revoked, cleaning up")
            cleanup()
            return

        process_item(item)
```

## Rate Limiting

### Task-Level Rate Limits

```python
# Limit to 10 tasks per minute
@shared_task(rate_limit='10/m')
def rate_limited_task(data):
    pass

# Limit to 100 tasks per hour
@shared_task(rate_limit='100/h')
def hourly_limited_task(data):
    pass

# Limit to 1 task per second
@shared_task(rate_limit='1/s')
def slow_task(data):
    pass
```

### Dynamic Rate Limiting

```python
from celery import shared_task
from time import sleep

@shared_task(bind=True)
def api_call_task(self, endpoint):
    try:
        response = call_api(endpoint)
        return response
    except RateLimitError as exc:
        # Back off and retry
        retry_after = exc.retry_after or 60
        raise self.retry(exc=exc, countdown=retry_after)
```
