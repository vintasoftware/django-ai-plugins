# Django Agent Skills

A collection of skills for AI coding agents specialized in Django backend development. Skills are packaged instructions and references that extend agent capabilities.

Skills follow the [Agent Skills](https://agentskills.io/) format and work with any compatible AI coding agent.

## Available Skills

### django-expert

Comprehensive Django development guidelines from Vinta Software. Contains best practices across multiple categories for building robust Django applications.

**Use when:**
- Building new Django models, views, or APIs
- Implementing authentication or authorization
- Setting up Django REST Framework endpoints
- Reviewing Django code for best practices
- Optimizing database queries and performance

**Categories covered:**
- Project structure and configuration
- Models and database design
- Views and URL routing
- Django REST Framework integration
- Security best practices
- Testing strategies
- Performance optimization

## Installation

```bash
npx add-skill vintasoftware/django-ai-plugins
```

To list available skills before installing:

```bash
npx add-skill vintasoftware/django-ai-plugins -l
```

## Usage

Skills are automatically available once installed. The agent will use them when relevant tasks are detected.

**Examples:**
```
Create a new Django model for user profiles
```
```
Set up a REST API endpoint with authentication
```
```
Review this Django view for security issues
```

## Skill Structure

Each skill contains:
- `SKILL.md` - Instructions for the agent
- `references/` - Supporting documentation

## Integration with django-ai-boost MCP Server

This skill works seamlessly with the [django-ai-boost MCP server](https://github.com/vintasoftware/django-ai-boost), which provides additional Django-specific tools and capabilities.

To use both together:

1. Install the django-ai-boost MCP server following its documentation
2. Install this skill using the instructions above
3. The skills will leverage the tools provided by the MCP server for enhanced Django development capabilities

## License

MIT @ Vinta Software
