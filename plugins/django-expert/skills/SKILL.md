---
name: django-expert
description: Expert Django backend development guidance. Use when creating Django models, views, serializers, or APIs; debugging ORM queries or migrations; optimizing database performance; implementing authentication; writing tests; or working with Django REST Framework. Follows Django best practices and modern patterns.
---

# Django Expert

## Overview

This skill provides expert guidance for Django backend development with comprehensive coverage of models, views, Django REST Framework, forms, authentication, testing, and performance optimization. It follows official Django best practices and modern Python conventions to help you build robust, maintainable applications.

**Key Capabilities:**
- Model design with optimal ORM patterns
- View implementation (FBV, CBV, DRF viewsets)
- Django REST Framework API development
- Query optimization and performance tuning
- Authentication and permissions
- Testing strategies and patterns
- Security best practices

## When to Use

Invoke this skill when you encounter these triggers:

**Model & Database Work:**
- "Create a Django model for..."
- "Optimize this queryset/database query"
- "Generate migrations for..."
- "Design database schema for..."
- "Fix N+1 query problem"

**View & API Development:**
- "Create an API endpoint for..."
- "Build a Django view that..."
- "Implement DRF serializer/viewset"
- "Add filtering/pagination to API"

**Authentication & Security:**
- "Implement authentication/permissions"
- "Create custom user model"
- "Secure this endpoint/view"

**Testing & Quality:**
- "Write tests for this Django app"
- "Debug this Django error/issue"
- "Review Django code for issues"

**Performance & Optimization:**
- "This Django view is slow"
- "Optimize database queries"
- "Add caching to..."

## Instructions

Follow this workflow when handling Django development requests:

### 1. Analyze the Request and Gather Context

**Identify the task type:**
- Model design (database schema, relationships, migrations)
- View/API development (FBV, CBV, DRF viewsets, serializers)
- Query optimization (N+1 problems, database performance)
- Authentication/permissions (user models, access control)
- Testing (unit tests, integration tests, fixtures)
- Security review (CSRF, XSS, SQL injection, permissions)
- Template rendering (Django templates, context processors)

**Leverage available context:**
- If `django-ai-boost` MCP server is available, use it to understand project structure and existing patterns
- Read relevant existing code to understand conventions
- Check Django version for compatibility considerations

### 2. Load Relevant Reference Documentation

Based on the task type, reference the appropriate bundled documentation:

- **Models/ORM work** -> `references/models-and-orm.md`
  - Model design patterns and field choices
  - Relationship configurations (ForeignKey, ManyToMany)
  - Custom managers and QuerySet methods
  - Migration strategies

- **View/API development** -> `references/views-and-urls.md` + `references/drf-guidelines.md`
  - FBV vs CBV decision criteria
  - DRF serializers, viewsets, and routers
  - URL configuration patterns
  - Middleware and request/response handling

- **Performance issues** -> `references/performance-optimization.md`
  - Query optimization techniques (select_related, prefetch_related)
  - Caching strategies (Redis, Memcached, database caching)
  - Database indexing and query profiling
  - Connection pooling and async patterns

- **Security concerns** -> `references/security-checklist.md`
  - CSRF/XSS/SQL injection prevention
  - Authentication and authorization patterns
  - Secure configuration practices
  - Input validation and sanitization

- **Testing tasks** -> `references/testing-strategies.md`
  - Test structure and organization
  - Fixtures and factories
  - Mocking external dependencies
  - Coverage and CI/CD integration

### 3. Implement Following Django Best Practices

**Code quality standards:**
- Follow PEP 8 and Django coding style
- Use Django built-ins over third-party packages when possible
- Keep views thin, use services/managers for business logic
- Write descriptive variable names and add docstrings for complex logic
- Handle errors gracefully with appropriate exceptions

**Django-specific patterns:**
- Use `select_related()` for FK/OneToOne, `prefetch_related()` for reverse FK/M2M
- Leverage class-based views and mixins for code reuse
- Use Django forms/serializers for validation
- Follow Django's migration workflow (never edit applied migrations)
- Use Django's built-in security features (CSRF tokens, auth decorators)

**API development (DRF):**
- Use ModelSerializer for standard CRUD operations
- Implement proper pagination and filtering
- Use appropriate permission classes
- Follow RESTful conventions for endpoints
- Version APIs when making breaking changes

### 4. Validate and Test

Before presenting the solution:

**Code review:**
- Check for N+1 query problems (use Django Debug Toolbar mentally)
- Verify proper error handling and edge cases
- Ensure security best practices are followed
- Confirm migrations are clean and reversible

**Testing considerations:**
- Suggest or write appropriate tests for new functionality
- Verify test coverage for critical paths
- Check that fixtures/factories are maintainable

**Performance check:**
- Review database queries for efficiency
- Consider caching opportunities
- Verify proper use of database indexes

## Bundled Resources

**references/** - Comprehensive Django documentation loaded into context as needed

These reference files provide detailed guidance beyond this SKILL.md overview:

- **`references/models-and-orm.md`** (~11k words)
  - Model field types and best practices
  - Relationship configurations (ForeignKey, OneToOne, ManyToMany)
  - Custom managers and QuerySet methods
  - Migration patterns and common pitfalls
  - Database-level constraints and indexes

- **`references/views-and-urls.md`** (~17k words)
  - Function-based vs class-based view trade-offs
  - CBV mixins and inheritance patterns
  - URL routing and reverse resolution
  - Middleware implementation
  - Request/response lifecycle

- **`references/drf-guidelines.md`** (~18k words)
  - Serializer patterns (ModelSerializer, nested serializers)
  - ViewSet and router configurations
  - Pagination, filtering, and search
  - Authentication and permission classes
  - API versioning strategies
  - Performance optimization for APIs

- **`references/testing-strategies.md`** (~18k words)
  - Test organization and structure
  - Factory patterns vs fixtures
  - Testing views, models, and serializers
  - Mocking external services
  - Test database optimization
  - CI/CD integration

- **`references/security-checklist.md`** (~12k words)
  - CSRF protection implementation
  - XSS prevention techniques
  - SQL injection defense
  - Authentication best practices
  - Permission and authorization patterns
  - Secure settings configuration

- **`references/performance-optimization.md`** (~14k words)
  - Query optimization (select_related, prefetch_related, only, defer)
  - Database indexing strategies
  - Caching layers (Redis, Memcached, database cache)
  - Database connection pooling
  - Profiling and monitoring tools
  - Async views and background tasks

## Examples

### Example 1: Model Design with Custom Manager

**User Request:**
> "Create a User model with email authentication, profile tracking, and a way to query active users"

**Claude Response:**
```
I'll create a custom User model following Django best practices:

1. Extend AbstractUser for email-based authentication
2. Add custom manager for common queries
3. Include proper Meta configuration with indexes
4. Add timestamp tracking fields
```

**Implementation:**
```python
# models.py
from django.contrib.auth.models import AbstractUser
from django.db import models

class UserManager(models.Manager):
    """Custom manager for User model with common query methods."""

    def active_users(self):
        """Return users who are active and email verified."""
        return self.filter(is_active=True, email_verified=True)

    def get_by_email(self, email):
        """Case-insensitive email lookup."""
        return self.get(email__iexact=email)

class User(AbstractUser):
    email = models.EmailField(unique=True, db_index=True)
    email_verified = models.BooleanField(default=False)
    profile_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        db_table = 'users'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email', 'is_active']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return self.email

    def get_full_name(self):
        """Return user's full name or email if name not set."""
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name if full_name else self.email
```

**Next steps:**
- Run `python manage.py makemigrations` to create migrations
- Update settings.py: `AUTH_USER_MODEL = 'yourapp.User'`
- Create email verification workflow if needed

---

### Example 2: Query Optimization (N+1 Problem)

**User Request:**
> "This blog post list view is generating 100+ database queries and it's really slow"

**Current Code (Problematic):**
```python
# ❌ BAD: N+1 query problem
def post_list(request):
    posts = Post.objects.all()  # 1 query
    return render(request, 'posts/list.html', {'posts': posts})

# Template causes N+1:
# {% for post in posts %}
#   {{ post.author.name }}      # 1 query per post
#   {{ post.comments.count }}   # 1 query per post
# {% endfor %}
```

**Claude Response:**
```
I can see the N+1 query problem. The view fetches posts, but the template
accesses related `author` (ForeignKey) and `comments` (reverse ForeignKey)
for each post, causing additional queries.

Solution: Use select_related() for ForeignKey and prefetch_related() for
reverse relationships.
```

**Optimized Code:**
```python
# ✅ GOOD: Optimized with proper eager loading
from django.db.models import Count, Prefetch

def post_list(request):
    posts = Post.objects.select_related(
        'author'  # ForeignKey - use select_related (SQL JOIN)
    ).prefetch_related(
        Prefetch(
            'comments',
            queryset=Comment.objects.select_related('author').filter(is_approved=True)
        )
    ).annotate(
        comment_count=Count('comments', filter=Q(comments__is_approved=True))
    ).order_by('-published_at')

    return render(request, 'posts/list.html', {'posts': posts})

# Now template only uses the prefetched data - no additional queries!
```

**Performance Impact:**
- Before: 1 + N (authors) + N (comment counts) = 201 queries for 100 posts
- After: 3 queries total (posts, authors via JOIN, comments prefetch)

---

### Example 3: Django REST Framework API Endpoint

**User Request:**
> "Create a REST API for my Product model with filtering, pagination, and proper permissions"

**Claude Response:**
```
I'll implement a complete DRF endpoint following best practices:

1. Create ModelSerializer with validation
2. Implement ViewSet with proper permissions
3. Add filtering and search capabilities
4. Configure pagination
5. Set up URL routing
```

**Implementation:**

```python
# serializers.py
from rest_framework import serializers
from .models import Product

class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    is_available = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'price', 'stock',
            'category', 'category_name', 'is_available', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_is_available(self, obj):
        """Check if product is in stock."""
        return obj.stock > 0

    def validate_price(self, value):
        """Ensure price is positive."""
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than zero")
        return value

# views.py
from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from django_filters.rest_framework import DjangoFilterBackend
from .models import Product
from .serializers import ProductSerializer

class ProductViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Product CRUD operations.

    List and retrieve are public, create/update/delete require authentication.
    """
    queryset = Product.objects.select_related('category').filter(is_active=True)
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'stock']
    search_fields = ['name', 'description']
    ordering_fields = ['price', 'created_at', 'stock']
    ordering = ['-created_at']

    def get_queryset(self):
        """Filter products based on query params."""
        queryset = super().get_queryset()

        # Filter by price range
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')

        if min_price:
            queryset = queryset.filter(price__gte=min_price)
        if max_price:
            queryset = queryset.filter(price__lte=max_price)

        return queryset

# urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProductViewSet

router = DefaultRouter()
router.register(r'products', ProductViewSet, basename='product')

urlpatterns = [
    path('api/', include(router.urls)),
]

# settings.py (pagination configuration)
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}
```

**API Usage Examples:**
```bash
# List all products (paginated)
GET /api/products/

# Search products
GET /api/products/?search=laptop

# Filter by category and price range
GET /api/products/?category=electronics&min_price=100&max_price=500

# Order by price ascending
GET /api/products/?ordering=price

# Retrieve single product
GET /api/products/123/

# Create product (requires authentication)
POST /api/products/
```

---

### Example 4: Writing Django Tests

**User Request:**
> "Write tests for the Product API endpoint"

**Claude Response:**
```python
# tests/test_product_api.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from decimal import Decimal
from .models import Product, Category

User = get_user_model()

class ProductAPITestCase(TestCase):
    """Test suite for Product API endpoints."""

    def setUp(self):
        """Set up test data before each test."""
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.category = Category.objects.create(name='Electronics')
        self.product = Product.objects.create(
            name='Test Product',
            description='A test product',
            price=Decimal('99.99'),
            stock=10,
            category=self.category
        )

    def test_list_products_unauthenticated(self):
        """Unauthenticated users can list products."""
        response = self.client.get('/api/products/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    def test_create_product_requires_authentication(self):
        """Creating products requires authentication."""
        data = {
            'name': 'New Product',
            'price': '49.99',
            'stock': 5,
            'category': self.category.id
        }
        response = self.client.post('/api/products/', data)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_product_authenticated(self):
        """Authenticated users can create products."""
        self.client.force_authenticate(user=self.user)
        data = {
            'name': 'New Product',
            'description': 'A new product',
            'price': '49.99',
            'stock': 5,
            'category': self.category.id
        }
        response = self.client.post('/api/products/', data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Product.objects.count(), 2)
        self.assertEqual(response.data['name'], 'New Product')

    def test_filter_by_price_range(self):
        """Products can be filtered by price range."""
        Product.objects.create(
            name='Expensive Product',
            price=Decimal('299.99'),
            stock=5,
            category=self.category
        )

        response = self.client.get('/api/products/?min_price=200')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['name'], 'Expensive Product')

    def test_product_availability_field(self):
        """is_available field correctly reflects stock status."""
        response = self.client.get(f'/api/products/{self.product.id}/')

        self.assertEqual(response.data['is_available'], True)

        # Update stock to 0
        self.product.stock = 0
        self.product.save()

        response = self.client.get(f'/api/products/{self.product.id}/')
        self.assertEqual(response.data['is_available'], False)
```

**Run tests:**
```bash
python manage.py test tests.test_product_api
```

## Additional Notes

**Django Version Compatibility:**
- Always verify Django and DRF versions for compatibility
- Consider LTS releases (4.2, 5.2) for production
- Check deprecation warnings when upgrading
- Use `django-upgrade` tool for automated migration

**Development Philosophy:**
- Prefer Django's built-in solutions over third-party packages
- Follow "explicit is better than implicit" principle
- Use Django's admin interface for rapid prototyping
- Keep business logic in models/services, not views
- Write self-documenting code with clear naming

**Migration Best Practices:**
- Never edit migrations after they're applied or committed
- Use `squashmigrations` for cleaning up migration history
- Test migrations on production-like data
- Use `--fake` carefully and document when used
- Keep data migrations separate from schema migrations

**MCP Server Integration:**
- Use `django-ai-boost` MCP server when available for enhanced context
- MCP provides: project structure, model schemas, URL patterns, settings
- Enables better decision-making with project-specific knowledge

**Common Pitfalls to Avoid:**
- Circular imports (use lazy references or rearrange imports)
- Missing `related_name` on relationships (causes conflicts)
- Forgetting database indexes on frequently queried fields
- Using `get()` without exception handling
- Exposing sensitive data in API responses
- N+1 queries in templates and serializers
