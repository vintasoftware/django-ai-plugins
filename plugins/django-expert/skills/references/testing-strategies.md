# Django Testing Strategies

## Test Organization

### Directory Structure

```
myapp/
├── models.py
├── views.py
├── serializers.py
└── tests/
    ├── __init__.py
    ├── test_models.py
    ├── test_views.py
    ├── test_serializers.py
    ├── test_api.py
    └── factories.py  # Factory Boy factories
```

### Test Discovery

Django automatically discovers tests in:
- Files starting with `test_`
- Files in `tests/` directories

```bash
# Run all tests
python manage.py test

# Run specific app
python manage.py test myapp

# Run specific test file
python manage.py test myapp.tests.test_models

# Run specific test class
python manage.py test myapp.tests.test_models.PostModelTest

# Run specific test method
python manage.py test myapp.tests.test_models.PostModelTest.test_create_post
```

## TestCase vs TransactionTestCase

### TestCase (Recommended)

```python
from django.test import TestCase

# ✅ GOOD: Faster, uses transactions
class PostModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='test', password='pass')
        self.post = Post.objects.create(title='Test', author=self.user)

    def test_post_creation(self):
        self.assertEqual(self.post.title, 'Test')
        self.assertEqual(Post.objects.count(), 1)
```

**Features:**
- Wraps tests in transactions (rolled back after each test)
- Much faster than TransactionTestCase
- Database is reset between tests automatically

### TransactionTestCase

```python
from django.test import TransactionTestCase

# ✅ GOOD: When you need to test transactions
class PaymentProcessingTest(TransactionTestCase):
    def test_atomic_payment(self):
        with transaction.atomic():
            # Test transaction behavior
            ...
```

**Use TransactionTestCase when:**
- Testing transaction behavior (commit/rollback)
- Testing database-level constraints
- Testing raw SQL that doesn't work in transactions

**Rule**: Use TestCase unless you specifically need TransactionTestCase.

## Model Testing

```python
from django.test import TestCase
from django.core.exceptions import ValidationError

# ✅ GOOD: Test model methods and validation
class PostModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

    def test_create_post(self):
        """Test post creation."""
        post = Post.objects.create(
            title='Test Post',
            content='Test content',
            author=self.user
        )
        self.assertEqual(post.title, 'Test Post')
        self.assertEqual(post.author, self.user)
        self.assertIsNotNone(post.created_at)

    def test_str_method(self):
        """Test string representation."""
        post = Post.objects.create(title='Test', author=self.user)
        self.assertEqual(str(post), 'Test')

    def test_slug_generation(self):
        """Test automatic slug generation."""
        post = Post.objects.create(
            title='Test Post Title',
            author=self.user
        )
        self.assertEqual(post.slug, 'test-post-title')

    def test_title_max_length(self):
        """Test title max length validation."""
        long_title = 'x' * 201
        post = Post(title=long_title, author=self.user)

        with self.assertRaises(ValidationError):
            post.full_clean()

    def test_get_absolute_url(self):
        """Test get_absolute_url method."""
        post = Post.objects.create(title='Test', author=self.user)
        expected_url = f'/posts/{post.slug}/'
        self.assertEqual(post.get_absolute_url(), expected_url)

    def test_published_posts_manager(self):
        """Test custom manager."""
        Post.objects.create(title='Published', author=self.user, is_published=True)
        Post.objects.create(title='Draft', author=self.user, is_published=False)

        published = Post.published.all()
        self.assertEqual(published.count(), 1)
        self.assertEqual(published.first().title, 'Published')
```

## View Testing

```python
from django.test import TestCase, Client
from django.urls import reverse

# ✅ GOOD: Test views thoroughly
class PostViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.post = Post.objects.create(
            title='Test Post',
            content='Test content',
            author=self.user
        )

    def test_post_list_view(self):
        """Test post list view."""
        response = self.client.get(reverse('post_list'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'blog/post_list.html')
        self.assertContains(response, 'Test Post')
        self.assertIn('posts', response.context)

    def test_post_detail_view(self):
        """Test post detail view."""
        url = reverse('post_detail', kwargs={'pk': self.post.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['post'], self.post)

    def test_post_detail_404(self):
        """Test 404 for non-existent post."""
        url = reverse('post_detail', kwargs={'pk': 9999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_create_post_authenticated(self):
        """Test creating post when logged in."""
        self.client.login(username='testuser', password='testpass123')

        data = {
            'title': 'New Post',
            'content': 'New content'
        }
        response = self.client.post(reverse('post_create'), data)

        self.assertEqual(response.status_code, 302)  # Redirect after success
        self.assertEqual(Post.objects.count(), 2)
        new_post = Post.objects.latest('created_at')
        self.assertEqual(new_post.title, 'New Post')
        self.assertEqual(new_post.author, self.user)

    def test_create_post_unauthenticated(self):
        """Test creating post when not logged in."""
        data = {'title': 'New Post', 'content': 'New content'}
        response = self.client.post(reverse('post_create'), data)

        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_update_own_post(self):
        """Test updating own post."""
        self.client.login(username='testuser', password='testpass123')

        url = reverse('post_update', kwargs={'pk': self.post.pk})
        data = {'title': 'Updated Title', 'content': 'Updated content'}
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 302)
        self.post.refresh_from_db()
        self.assertEqual(self.post.title, 'Updated Title')

    def test_cannot_update_others_post(self):
        """Test cannot update another user's post."""
        other_user = User.objects.create_user(username='other', password='pass')
        self.client.login(username='other', password='pass')

        url = reverse('post_update', kwargs={'pk': self.post.pk})
        data = {'title': 'Hacked', 'content': 'Hacked'}
        response = self.client.post(url, data)

        # Should get 403 or 404
        self.assertIn(response.status_code, [403, 404])
        self.post.refresh_from_db()
        self.assertNotEqual(self.post.title, 'Hacked')

    def test_delete_post(self):
        """Test deleting post."""
        self.client.login(username='testuser', password='testpass123')

        url = reverse('post_delete', kwargs={'pk': self.post.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Post.objects.count(), 0)
```

## API Testing (DRF)

```python
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

# ✅ GOOD: Test API endpoints
class PostAPITest(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.post = Post.objects.create(
            title='Test Post',
            content='Test content',
            author=self.user
        )

    def test_list_posts(self):
        """Test GET /api/posts/"""
        response = self.client.get('/api/posts/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    def test_retrieve_post(self):
        """Test GET /api/posts/{id}/"""
        response = self.client.get(f'/api/posts/{self.post.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Test Post')

    def test_create_post_authenticated(self):
        """Test POST /api/posts/ when authenticated."""
        self.client.force_authenticate(user=self.user)

        data = {'title': 'New Post', 'content': 'New content'}
        response = self.client.post('/api/posts/', data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Post.objects.count(), 2)
        self.assertEqual(response.data['author'], self.user.id)

    def test_create_post_unauthenticated(self):
        """Test POST /api/posts/ when not authenticated."""
        data = {'title': 'New Post', 'content': 'New content'}
        response = self.client.post('/api/posts/', data, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_post(self):
        """Test PUT /api/posts/{id}/"""
        self.client.force_authenticate(user=self.user)

        data = {'title': 'Updated', 'content': 'Updated content'}
        response = self.client.put(
            f'/api/posts/{self.post.id}/',
            data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.post.refresh_from_db()
        self.assertEqual(self.post.title, 'Updated')

    def test_partial_update_post(self):
        """Test PATCH /api/posts/{id}/"""
        self.client.force_authenticate(user=self.user)

        data = {'title': 'Patched Title'}
        response = self.client.patch(
            f'/api/posts/{self.post.id}/',
            data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.post.refresh_from_db()
        self.assertEqual(self.post.title, 'Patched Title')
        self.assertEqual(self.post.content, 'Test content')  # Unchanged

    def test_delete_post(self):
        """Test DELETE /api/posts/{id}/"""
        self.client.force_authenticate(user=self.user)

        response = self.client.delete(f'/api/posts/{self.post.id}/')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Post.objects.count(), 0)

    def test_filter_by_author(self):
        """Test filtering posts by author."""
        other_user = User.objects.create_user(username='other', password='pass')
        Post.objects.create(title='Other Post', author=other_user)

        response = self.client.get(f'/api/posts/?author={self.user.id}')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['author'], self.user.id)

    def test_search_posts(self):
        """Test searching posts."""
        Post.objects.create(title='Django Tutorial', content='Learn Django', author=self.user)

        response = self.client.get('/api/posts/?search=Django')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
```

## Fixtures and Factories

### Fixtures (JSON)

```python
# fixtures/test_data.json
[
    {
        "model": "auth.user",
        "pk": 1,
        "fields": {
            "username": "testuser",
            "email": "test@example.com"
        }
    },
    {
        "model": "blog.post",
        "pk": 1,
        "fields": {
            "title": "Test Post",
            "author": 1
        }
    }
]

# Using fixtures
class PostTest(TestCase):
    fixtures = ['test_data.json']

    def test_with_fixture(self):
        post = Post.objects.get(pk=1)
        self.assertEqual(post.title, 'Test Post')
```

### Factory Boy (Recommended)

```bash
pip install factory-boy
```

```python
# tests/factories.py
import factory
from factory.django import DjangoModelFactory

class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f'user{n}')
    email = factory.LazyAttribute(lambda obj: f'{obj.username}@example.com')
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')

class PostFactory(DjangoModelFactory):
    class Meta:
        model = Post

    title = factory.Faker('sentence', nb_words=5)
    content = factory.Faker('paragraph', nb_sentences=10)
    author = factory.SubFactory(UserFactory)
    is_published = True

class CommentFactory(DjangoModelFactory):
    class Meta:
        model = Comment

    post = factory.SubFactory(PostFactory)
    author = factory.SubFactory(UserFactory)
    content = factory.Faker('paragraph')

# Usage in tests
class PostTest(TestCase):
    def test_create_post_with_factory(self):
        post = PostFactory()
        self.assertIsNotNone(post.id)
        self.assertIsNotNone(post.author)

    def test_create_multiple_posts(self):
        posts = PostFactory.create_batch(10)
        self.assertEqual(Post.objects.count(), 10)

    def test_custom_values(self):
        user = UserFactory(username='specific_user')
        post = PostFactory(author=user, title='Specific Title')
        self.assertEqual(post.author.username, 'specific_user')
```

## Mocking External Services

```python
from unittest.mock import patch, Mock

# ✅ GOOD: Mock external API calls
class PaymentTest(TestCase):
    @patch('myapp.payment.stripe.Charge.create')
    def test_process_payment(self, mock_charge):
        """Test payment processing."""
        # Configure mock
        mock_charge.return_value = Mock(
            id='ch_123',
            status='succeeded'
        )

        # Call function that uses Stripe
        result = process_payment(amount=1000, token='tok_123')

        # Verify mock was called
        mock_charge.assert_called_once_with(
            amount=1000,
            currency='usd',
            source='tok_123'
        )

        # Verify result
        self.assertTrue(result['success'])
        self.assertEqual(result['charge_id'], 'ch_123')

    @patch('myapp.tasks.send_email.delay')
    def test_user_registration_sends_email(self, mock_send_email):
        """Test registration sends welcome email."""
        user = User.objects.create_user(
            username='test',
            email='test@example.com',
            password='pass'
        )

        # Verify email task was called
        mock_send_email.assert_called_once_with(
            user_id=user.id,
            template='welcome'
        )
```

## Testing Forms

```python
from django.test import TestCase

class PostFormTest(TestCase):
    def test_valid_form(self):
        """Test form with valid data."""
        data = {
            'title': 'Test Post',
            'content': 'Test content'
        }
        form = PostForm(data=data)
        self.assertTrue(form.is_valid())

    def test_invalid_form_missing_title(self):
        """Test form with missing required field."""
        data = {'content': 'Test content'}
        form = PostForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('title', form.errors)

    def test_invalid_form_title_too_long(self):
        """Test form with title exceeding max length."""
        data = {
            'title': 'x' * 201,
            'content': 'Test content'
        }
        form = PostForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('title', form.errors)
```

## Coverage

```bash
pip install coverage
```

```bash
# Run tests with coverage
coverage run --source='.' manage.py test

# View coverage report
coverage report

# Generate HTML report
coverage html
# Open htmlcov/index.html in browser
```

```ini
# .coveragerc
[run]
omit =
    */migrations/*
    */tests/*
    */venv/*
    manage.py

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
    if __name__ == .__main__.:
```

## Performance Testing

```python
from django.test import TestCase
from django.test.utils import override_settings
import time

class PerformanceTest(TestCase):
    def test_query_count(self):
        """Test number of queries."""
        PostFactory.create_batch(10)

        with self.assertNumQueries(2):  # Should be 2 queries max
            posts = Post.objects.select_related('author').all()
            list(posts)  # Force evaluation

    def test_response_time(self):
        """Test view response time."""
        start = time.time()
        response = self.client.get('/posts/')
        duration = time.time() - start

        self.assertEqual(response.status_code, 200)
        self.assertLess(duration, 0.5)  # Should respond in < 500ms
```

## Testing Best Practices Checklist

✅ Test one thing per test method
✅ Use descriptive test names (test_what_when_expected)
✅ Use factories instead of fixtures for flexibility
✅ Test both success and failure cases
✅ Test edge cases and boundary conditions
✅ Test permissions and authorization
✅ Mock external services (APIs, email, etc.)
✅ Use setUp() for common test data
✅ Test database queries (use assertNumQueries)
✅ Aim for >80% code coverage
✅ Run tests before committing code
✅ Use continuous integration (CI) to run tests automatically
✅ Keep tests fast (mock slow operations)
✅ Test what could break, not Django itself

---

**Remember**: Good tests give you confidence to refactor and catch bugs early. Write tests first (TDD) or immediately after (to verify it works).
