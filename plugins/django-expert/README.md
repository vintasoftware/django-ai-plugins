# Django Expert Plugin

A comprehensive Claude Code plugin providing expert guidance for Django backend development following industry best practices.

## Overview

The Django Expert plugin equips Claude Code with deep expertise in Django development, covering models, views, templates, Django REST Framework, testing, security, and performance optimization. It provides intelligent assistance for building robust, maintainable Django applications.

## Features

- **Model Design & ORM**: Expert guidance on models, relationships, migrations, and query optimization
- **Views & URLs**: Best practices for FBV, CBV, and URL routing
- **Django REST Framework**: Comprehensive DRF patterns for serializers, viewsets, and API development
- **Testing Strategies**: Unit testing, integration testing, and test fixtures
- **Security Guidelines**: CSRF, XSS, authentication, and Django security best practices
- **Performance Optimization**: Query optimization, caching, database indexing
- **Progressive Documentation**: On-demand reference files loaded only when needed

## Installation

### Prerequisites

- Claude Code version 1.0.33 or later (run `claude --version` to check)
- If you need to update: `brew upgrade claude-code` (Homebrew) or `npm update -g @anthropic-ai/claude-code` (npm)

### Option 1: Install from GitHub (Recommended)

Add this plugin marketplace to your Claude Code installation:

```bash
# Add the marketplace
/plugin marketplace add vintasoftware/django-ai-plugins

# Install the Django Expert plugin
/plugin install django-expert@vintasoftware-plugins

# Or browse and install interactively
/plugin
```

### Option 2: Local Development/Testing

For local testing or development:

```bash
# Clone the repository
git clone https://github.com/vintasoftware/django-ai-plugins.git
cd django-ai-plugins

# Add the local marketplace
/plugin marketplace add .

# Install the plugin from local marketplace
/plugin install django-expert@vintasoftware-plugins
```

### Verify Installation

List your installed marketplaces and plugins:

```bash
/plugin marketplace list
/plugin list
```

### Installation Scopes

When installing, choose where the plugin should be available:

- **User scope** (default): Available across all your projects
- **Project scope**: Shared with all collaborators via `.claude/settings.json`
- **Local scope**: Available only for you in this specific repository

## Usage

Once installed, the Django Expert skill will be automatically invoked when you:

- Ask Django-related questions
- Request help building Django features
- Debug Django issues
- Work with Django models, views, or APIs
- Need guidance on Django REST Framework
- Optimize Django performance
- Implement Django security best practices

The skill can also call the `django-ai-boost` MCP server if installed, for enhanced capabilities.

### Example Interactions

**Creating Django Models:**
```
User: "Create a Django model for a blog post with title, content, author, and tags"
Claude: [Invokes django-expert skill and provides model with proper fields, relationships, Meta options]
```

**Optimizing Queries:**
```
User: "This Django view is slow when loading posts with comments"
Claude: [Analyzes query patterns, suggests select_related/prefetch_related optimizations]
```

**DRF Implementation:**
```
User: "Build a REST API for my Product model with filtering and pagination"
Claude: [Creates serializer, viewset, and URL configuration following DRF best practices]
```

**Security Review:**
```
User: "Review this Django view for security issues"
Claude: [Checks for CSRF, XSS, SQL injection vulnerabilities and provides fixes]
```

## Plugin Structure

```
django-expert/
├── .claude-plugin/
│   ├── plugin.json          # Plugin metadata
│   └── marketplace.json     # Marketplace configuration
├── skills/
│   ├── SKILL.md            # Main skill instructions
│   └── references/         # Best practices documentation
│       └── README.md       # Guide for populating references
└── README.md               # This file
```

## Customization

### Adding Reference Documentation

The plugin uses progressive disclosure - detailed documentation is loaded on-demand. To enhance the skill with comprehensive Django guidelines:

1. Navigate to `skills/references/`
2. Create markdown files for specific topics:
   - `models-and-orm.md` - Model patterns, relationships, query optimization
   - `views-and-urls.md` - View patterns, URL routing, middleware
   - `drf-guidelines.md` - Django REST Framework best practices
   - `testing-strategies.md` - Testing patterns and fixtures
   - `security-checklist.md` - Security guidelines and checklists
   - `performance-optimization.md` - Caching, database optimization

3. Follow the structure outlined in `references/README.md`

### Customizing SKILL.md

Edit `skills/SKILL.md` to:
- Adjust instructions and workflow
- Add project-specific Django conventions
- Include custom examples
- Configure allowed tools via frontmatter
- Add metadata for categorization

## Development Workflow

### Testing Locally

1. Make changes to the plugin files
2. Reinstall the plugin:
```bash
/plugin uninstall django-expert
/plugin install django-expert@django-expert-dev
```
3. Restart Claude Code
4. Test with Django-related queries

### Iteration Tips

- Test with real Django tasks from your projects
- Refine instructions based on Claude's responses
- Add more examples to SKILL.md for common scenarios
- Populate reference files incrementally as needed
- Use verbose descriptions in frontmatter for better skill discovery

## Version History

- **1.0.0** - Initial release with core Django expertise
  - Model design and ORM guidance
  - Views and URL patterns
  - Django REST Framework support
  - Testing, security, and performance guidelines
  - Reference documentation structure

## License

MIT

## Contributing

Contributions are welcome! To improve this plugin:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly with various Django scenarios
5. Submit a pull request

## Support

For issues, questions, or feature requests:
- GitHub Issues: https://github.com/vintasoftware/django-ai-plugins/issues
- Documentation: See `skills/SKILL.md` and `skills/references/README.md`

