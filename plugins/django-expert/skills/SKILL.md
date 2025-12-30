---
name: django-expert
description: This skill provides comprehensive guidelines for Django backend development following best practices. Expert guidance for Django development including models, views, templates, and best practices. Use when building Django applications, debugging Django issues, or implementing Django features.
---

# Django Expert

## Overview

This skill provides expert guidance for Django backend development, covering models, views, templates, forms, authentication, testing, and deployment. It follows Django best practices and modern Python conventions to help you build robust, maintainable Django applications.

## When to Use

Use this skill when:
- Building new Django applications or features
- Debugging Django-specific issues (ORM queries, migrations, template rendering, etc.)
- Implementing Django models, views, serializers, or forms
- Working with Django REST Framework
- Setting up authentication and permissions
- Writing tests for Django applications
- Optimizing Django performance (query optimization, caching, etc.)
- Following Django coding standards and best practices

## Instructions

### 1. Understand the Request

First, identify what type of Django task is being requested:
- **Model design** - Database models, relationships, migrations
- **View/API development** - Function-based views, class-based views, DRF viewsets
- **Template rendering** - Django templates, template tags, context processors
- **Forms and validation** - Django forms, model forms, custom validation
- **Authentication** - User authentication, permissions, custom user models
- **Testing** - Unit tests, integration tests, test fixtures
- **Performance** - Query optimization, caching strategies, database indexing
- **Deployment** - Settings configuration, static files, production setup

If available, use the `django-ai-boost` MCP server, which provides Django project information to enhance context understanding.

### 2. Apply Django Best Practices

Refer to the bundled references for comprehensive guidelines on:
- Project structure and app organization
- Model design patterns and ORM best practices
- View patterns (FBV vs CBV, when to use each)
- Django REST Framework conventions
- Security best practices (CSRF, XSS, SQL injection prevention)
- Testing strategies and patterns
- Performance optimization techniques

### 3. Implement with Django Conventions

When writing code:
- Follow PEP 8 and Django coding style guidelines
- Use Django built-in features before third-party packages
- Leverage Django class-based views and mixins appropriately
- Write clean, readable querysets with proper select_related/prefetch_related
- Implement proper error handling and validation
- Add docstrings for complex logic
- Follow the "fat models, thin views" principle when appropriate

### 4. Ensure Quality

Before completing the task:
- Verify migrations are generated correctly
- Check for N+1 query problems
- Ensure proper use of Django security features
- Validate form/serializer behavior
- Consider edge cases and error scenarios
- Add appropriate tests if requested

## Bundled Resources

**references/** - Django best practices documentation loaded into context when needed

- `references/models-and-orm.md` - Model design patterns, relationships, query optimization
- `references/views-and-urls.md` - View patterns, URL configuration, middleware
- `references/drf-guidelines.md` - Django REST Framework best practices
- `references/testing-strategies.md` - Testing patterns, fixtures, mocking
- `references/security-checklist.md` - Security best practices and common vulnerabilities
- `references/performance-optimization.md` - Caching, database optimization, profiling

## Examples

### Example 1: Creating a Django Model

```
User: "Create a Blog model with title, content, author, and publication date"

Claude: I'll create a Django model following best practices:

1. Define the model with appropriate field types
2. Add proper Meta options (ordering, indexes)
3. Include __str__ method for admin representation
4. Add any necessary custom methods
5. Generate migrations
```

```python
# ✅ GOOD: Clean model with custom manager
class UserManager(models.Manager):
    def active_users(self):
        return self.filter(is_active=True, email_verified=True)

    def get_by_email(self, email):
        return self.get(email__iexact=email)

class User(AbstractUser):
    email = models.EmailField(unique=True)
    email_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return self.email

    def get_full_name(self):
        """Single-instance operation."""
        return f"{self.first_name} {self.last_name}".strip()
```

### Example 2: Optimizing Django Queries

```
User: "This view is slow - it loads posts with authors and comments"

Claude: Let me analyze the query patterns and optimize:

1. Identify N+1 query problems
2. Add select_related() for foreign keys
3. Add prefetch_related() for reverse relationships
4. Consider using only() or defer() if needed
5. Add database indexes if appropriate

[Provides optimized queryset with explanation]
```

### Example 3: Django REST Framework Serializer

```
User: "Create an API endpoint for my Product model"

Claude: I'll implement a DRF viewset with serializer:

1. Create ModelSerializer with appropriate fields
2. Add validation logic if needed
3. Create ViewSet with proper permissions
4. Configure URL routing
5. Add filtering and pagination

[Implements complete DRF endpoint following best practices]
```

## Progressive Disclosure

This SKILL.md provides core workflow and guidance. For detailed Django best practices, coding patterns, and comprehensive examples, the bundled references/ files will be loaded into context as needed. This keeps the skill focused while providing deep expertise when required.

## Additional Notes

- Always check Django and DRF documentation versions for compatibility
- Consider the Django version being used (LTS vs latest)
- Prefer Django's built-in solutions over custom implementations
- Follow the principle of "explicit is better than implicit"
- Leverage Django's admin interface for rapid development
- Use Django's migration system properly (avoid editing migrations after commit)
