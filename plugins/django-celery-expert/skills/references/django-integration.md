# Django Integration Patterns

Critical patterns for reliable Django and Celery integration.

**Sources:**
- [Celery in the Wild: Tips and Tricks to Run Async Tasks in the Real World](https://www.vintasoftware.com/blog/celery-wild-tips-and-tricks-run-async-tasks-real-world) - Vinta Software
- [A Guide on Django Celery Tasks That Actually Work](https://www.vintasoftware.com/blog/guide-django-celery-tasks) - Vinta Software

## Critical: Use transaction.on_commit()

Always use `transaction.on_commit()` when queuing tasks after database writes. This ensures the database transaction commits before the task is queued, preventing race conditions where the task runs before the data is available.

```python
from django.db import transaction

class SignUpView(CreateView):
    def form_valid(self, form):
        response = super().form_valid(form)
        user_pk = self.object.pk

        # GOOD: Task queued only after transaction commits
        transaction.on_commit(
            lambda: send_activation_email.delay(user_pk)
        )
        return response

# BAD: Task might run before user is committed to DB
def bad_signup(request):
    user = User.objects.create(...)
    send_activation_email.delay(user.pk)  # Race condition!
    return redirect('home')
```

### With Atomic Blocks

```python
from django.db import transaction

def process_order(order_id):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(id=order_id)
        order.status = 'processing'
        order.save()

        # Queue task only after atomic block commits
        transaction.on_commit(
            lambda: notify_warehouse.delay(order.pk)
        )
```

### Nested Transactions

```python
from django.db import transaction

def complex_operation():
    with transaction.atomic():
        create_parent_record()

        with transaction.atomic():
            create_child_record()
            # This on_commit waits for OUTER transaction
            transaction.on_commit(lambda: child_task.delay())

        # This also waits for outer transaction
        transaction.on_commit(lambda: parent_task.delay())
```

## Database as Source of Truth

Don't rely solely on Celery for guaranteed delivery. Use the database as the source of truth and implement recovery tasks.

### Pattern: Flag-Based Recovery

```python
# models.py
class User(models.Model):
    email = models.EmailField()
    is_activation_email_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

# tasks.py
@shared_task(bind=True, max_retries=3)
def send_activation_email(self, user_pk):
    try:
        user = User.objects.get(pk=user_pk)
        if user.is_activation_email_sent:
            return  # Already sent, idempotent

        send_email(user.email, 'Activate your account')

        # Mark as sent atomically
        User.objects.filter(pk=user_pk).update(is_activation_email_sent=True)

    except User.DoesNotExist:
        pass  # User deleted, skip
    except EmailException as exc:
        raise self.retry(exc=exc)

# Recovery task - runs periodically via Celery Beat
@shared_task
def recover_unsent_activation_emails():
    """Catch any missed activation emails."""
    cutoff = timezone.now() - timedelta(hours=24)
    unsent = User.objects.filter(
        is_activation_email_sent=False,
        created_at__lt=timezone.now() - timedelta(minutes=5),  # Grace period
        created_at__gt=cutoff,  # Don't process very old records
    )
    for user_pk in unsent.values_list('pk', flat=True):
        send_activation_email.delay(user_pk)
```

### Celery Beat Schedule for Recovery

```python
CELERY_BEAT_SCHEDULE = {
    'recover-activation-emails': {
        'task': 'users.tasks.recover_unsent_activation_emails',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
    },
}
```

## Atomicity: External Calls Before DB Writes

Execute external API calls before modifying the database. This prevents inconsistent states where the DB is updated but the external call fails.

```python
# GOOD: External call first, then DB update
@shared_task(bind=True, max_retries=3)
def sync_user_to_crm(self, user_id):
    user = User.objects.get(id=user_id)

    try:
        # External call FIRST
        crm_response = crm_api.create_contact(
            email=user.email,
            name=user.name,
        )

        # DB update AFTER external call succeeds
        user.crm_id = crm_response['id']
        user.crm_synced_at = timezone.now()
        user.save()

    except CRMAPIError as exc:
        raise self.retry(exc=exc)

# BAD: DB updated before external call
@shared_task
def bad_sync_user_to_crm(user_id):
    user = User.objects.get(id=user_id)
    user.crm_sync_started = True
    user.save()  # DB updated

    crm_api.create_contact(...)  # This might fail!
    # Now DB is in inconsistent state
```

## Request-Task Correlation with django-guid

Use `django-guid` to trace requests through to Celery tasks for debugging.

```bash
pip install django-guid celery-guid
```

```python
# settings.py
INSTALLED_APPS = [
    ...
    'django_guid',
]

MIDDLEWARE = [
    'django_guid.middleware.guid_middleware',
    ...
]

DJANGO_GUID = {
    'GUID_HEADER_NAME': 'X-Correlation-ID',
    'VALIDATE_GUID': False,
    'RETURN_HEADER': True,
    'INTEGRATIONS': [
        'django_guid.integrations.celery.CeleryIntegration',
    ],
}

# celery.py
from celery import Celery
from django_guid.integrations.celery import CeleryIntegration

app = Celery('myproject')

# Logging format includes correlation ID
LOGGING = {
    'formatters': {
        'correlation': {
            'format': '[%(correlation_id)s] %(levelname)s %(name)s: %(message)s',
        },
    },
}
```

### Manual Correlation Without django-guid

```python
import uuid
from celery import shared_task

@shared_task(bind=True)
def task_with_correlation(self, data):
    correlation_id = self.request.headers.get('correlation_id', 'unknown')
    logger.info(f"[{correlation_id}] Processing task")
    # ... task logic

# Pass correlation ID when calling
def my_view(request):
    correlation_id = request.headers.get('X-Correlation-ID', str(uuid.uuid4()))
    task_with_correlation.apply_async(
        args=[data],
        headers={'correlation_id': correlation_id}
    )
```

## Task-Specific Logging

Use Celery's task logger for proper task context in logs.

```python
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

@shared_task(bind=True)
def process_order(self, order_id):
    logger.info(f'Starting order processing', extra={
        'order_id': order_id,
        'task_id': self.request.id,
    })

    try:
        order = Order.objects.get(id=order_id)
        # ... process order
        logger.info(f'Order processed successfully')

    except Order.DoesNotExist:
        logger.warning(f'Order not found: {order_id}')

    except Exception as exc:
        logger.exception(f'Order processing failed')
        raise
```

## Idempotent ORM Operations

Use Django ORM methods that are naturally idempotent for safe retries.

```python
@shared_task(bind=True, max_retries=5)
def update_user_stats(self, user_id, points_earned):
    try:
        # GOOD: Idempotent with get_or_create
        stats, created = UserStats.objects.get_or_create(
            user_id=user_id,
            defaults={'points': points_earned}
        )

        if not created:
            # GOOD: Idempotent with update_or_create
            UserStats.objects.update_or_create(
                user_id=user_id,
                defaults={'points': F('points') + points_earned}
            )

    except Exception as exc:
        raise self.retry(exc=exc)

# For truly idempotent operations, use unique constraints
@shared_task
def record_event(event_id, user_id, event_type):
    # Idempotency via unique constraint
    Event.objects.get_or_create(
        idempotency_key=event_id,
        defaults={
            'user_id': user_id,
            'event_type': event_type,
        }
    )
```

## Handling Model Changes in Tasks

Tasks may run with stale model data. Always fetch fresh data.

```python
# BAD: Passing model state that might be stale
@shared_task
def bad_task(user_email, user_name):
    send_email(user_email, f"Hello {user_name}")
    # What if user updated their email before task ran?

# GOOD: Fetch fresh data by ID
@shared_task
def good_task(user_id):
    user = User.objects.get(id=user_id)  # Fresh from DB
    send_email(user.email, f"Hello {user.name}")
```

## Testing Django Celery Tasks

### Unit Testing with Eager Mode

```python
# settings/test.py
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# test_tasks.py
from django.test import TestCase, override_settings

@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TaskTestCase(TestCase):
    def test_send_email_task(self):
        user = User.objects.create(email='test@example.com')
        result = send_activation_email.delay(user.pk)

        # Task runs synchronously in tests
        self.assertTrue(result.successful())
        user.refresh_from_db()
        self.assertTrue(user.is_activation_email_sent)
```

### Testing with Mocked Tasks

```python
from unittest.mock import patch

class ViewTestCase(TestCase):
    @patch('myapp.tasks.send_activation_email.delay')
    def test_signup_queues_email(self, mock_task):
        response = self.client.post('/signup/', {
            'email': 'test@example.com',
            'password': 'securepass123',
        })

        self.assertEqual(response.status_code, 302)
        mock_task.assert_called_once()
```

### Testing transaction.on_commit

```python
from django.test import TestCase, TransactionTestCase

class OnCommitTestCase(TransactionTestCase):
    """Use TransactionTestCase for on_commit testing."""

    @patch('myapp.tasks.send_email.delay')
    def test_email_sent_after_commit(self, mock_task):
        # Task is queued after transaction commits
        User.objects.create(email='test@example.com')

        # In TransactionTestCase, on_commit callbacks execute
        mock_task.assert_called_once()
```
