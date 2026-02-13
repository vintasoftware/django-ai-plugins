# Django Reviewer Plugin

A Claude Code plugin that provides an autonomous agent for reviewing and refining Django/Python code. Focuses on clarity, consistency, and maintainability while preserving all functionality.

## Overview

The Django Reviewer agent proactively reviews recently modified Django code and applies refinements following Django best practices, PEP 8, and project-specific standards. It operates as a code review specialist — improving how code is written without changing what it does.

## Features

- **Proactive Review**: Automatically reviews code after modifications
- **Django Anti-Pattern Detection**: Identifies N+1 queries, business logic in views, missing indexes, and more
- **PEP 8 & Django Style**: Enforces Python and Django coding conventions
- **ORM Optimization**: Suggests `select_related`/`prefetch_related`, proper queryset usage
- **DRF Best Practices**: Reviews serializers, viewsets, and API patterns
- **Scoped Focus**: Reviews only recently modified code unless instructed otherwise

## Usage

Once installed, the Django Reviewer agent activates proactively after Django code changes. You can also invoke it explicitly:

```
Use the django-reviewer agent to review the recent changes
```

```
Ask the django-reviewer to review this viewset
```

```
Review my Django code for anti-patterns
```

### What It Reviews

- Model definitions (relationships, constraints, managers)
- Views and URL configurations
- DRF serializers and viewsets
- Database queries and ORM usage
- Test structure and coverage patterns
- Import organization and naming conventions

### What It Does NOT Do

- Change functionality or behavior
- Introduce new features or dependencies
- Modify code outside the current scope (unless asked)
- Add type hints to untyped codebases

## Plugin Structure

```
django-reviewer/
├── .claude-plugin/
│   └── plugin.json          # Plugin metadata
├── agents/
│   └── django-reviewer.md   # Agent definition
└── README.md                # This file
```

## License

MIT @ Vinta Software

## Support

For issues, questions, or feature requests:
- GitHub Issues: https://github.com/vintasoftware/django-ai-plugins/issues
