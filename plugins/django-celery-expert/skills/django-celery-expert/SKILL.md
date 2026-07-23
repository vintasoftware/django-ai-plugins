---
name: django-celery-expert
description: Expert Django Celery guidance for asynchronous task processing. Use when designing background tasks, configuring Celery workers, handling task retries and errors, optimizing Celery performance, implementing periodic tasks with Celery Beat, or setting up production monitoring for Celery. Do not use for general Django questions unrelated to Celery, non-Celery task systems (Django Q, Huey, RQ), ML/data pipeline orchestration (Airflow, Prefect), or frontend and API-only concerns. Follows Vinta's Django Celery best practices.
---

# Django Celery Expert

## Instructions

### Step 1: Classify the Request

Identify the task category from the request:

- **Django integration** — transaction safety, ORM patterns, testing, request correlation → read `references/django-integration.md`
- **Task design** — new tasks, calling patterns, chains/groups/chords, idempotency → read `references/task-design-patterns.md`
- **Configuration** — broker setup, result backend, worker settings, queue routing → read `references/configuration-guide.md`
- **Error handling** — retries, backoff, dead letter queues, timeouts → read `references/error-handling.md`
- **Periodic tasks** — Celery Beat, crontab schedules, dynamic schedules, timezone handling → read `references/periodic-tasks.md`
- **Monitoring** — Flower, Prometheus, logging, debugging stuck tasks → read `references/monitoring-observability.md`
- **Production deployment** — scaling, supervision, containers, health checks → read `references/production-deployment.md`

If the request spans multiple categories, read all relevant reference files before continuing.

### Step 2: Read the Reference File(s)

Read each reference file identified in Step 1. Do not proceed to implementation without reading the relevant reference.

### Step 3: Implement

Apply the patterns from the reference file. Before presenting the solution, verify:

- Task arguments are serializable (pass IDs, not model instances)
- Tasks with retries enabled are idempotent
- Errors are logged with context
- Long-running tasks have timeouts configured

## Examples

### Basic Background Task

**Request:** "Send welcome emails in the background after user registration"

```python
# tasks.py
from celery import shared_task
from django.core.mail import send_mail

@shared_task(bind=True, max_retries=3)
def send_welcome_email(self, user_id):
    from users.models import User

    try:
        user = User.objects.get(id=user_id)
        send_mail(
            subject="Welcome!",
            message=f"Hi {user.name}, welcome to our platform!",
            from_email="noreply@example.com",
            recipient_list=[user.email],
        )
    except User.DoesNotExist:
        pass
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


# views.py — queue only after the transaction commits
from django.db import transaction

def register(request):
    user = User.objects.create(...)
    transaction.on_commit(lambda: send_welcome_email.delay(user.id))
    return redirect("dashboard")
```

### Task with Progress Tracking

**Request:** "Process a large CSV import with progress updates"

```python
@shared_task(bind=True)
def import_csv(self, file_path, total_rows):
    from myapp.models import Record

    with open(file_path) as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            Record.objects.create(**row)
            if i % 100 == 0:
                self.update_state(
                    state="PROGRESS",
                    meta={"current": i, "total": total_rows},
                )

    return {"status": "complete", "processed": total_rows}


# Poll progress
result = import_csv.AsyncResult(task_id)
if result.state == "PROGRESS":
    progress = result.info.get("current", 0) / result.info.get("total", 1)
```

### Workflow with Chains

**Request:** "Process an order: validate inventory, charge payment, then send confirmation"

```python
from celery import chain

@shared_task
def validate_inventory(order_id):
    order = Order.objects.get(id=order_id)
    if not order.items_in_stock():
        raise ValueError("Items out of stock")
    return order_id

@shared_task
def charge_payment(order_id):
    order = Order.objects.get(id=order_id)
    order.charge()
    return order_id

@shared_task
def send_confirmation(order_id):
    Order.objects.get(id=order_id).send_confirmation_email()

def process_order(order_id):
    chain(
        validate_inventory.s(order_id),
        charge_payment.s(),
        send_confirmation.s(),
    ).delay()
```
