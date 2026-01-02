# django-ai-plugins

A collection of AI skills specialized in Django backend development.

## Installation

### Prerequisites

- Claude Code version 1.0.33 or later (run `claude --version` to check)
- If you need to update: `brew upgrade claude-code` (Homebrew) or `npm update -g @anthropic-ai/claude-code` (npm)

### Option 1: Install from GitHub (Recommended)

Add this plugin marketplace to your Claude Code installation:

```bash
# Add the marketplace
/plugin marketplace add vintasoftware/django-ai-skills

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

## Integration with `django-ai-boost` MCP Server

This skill works seamlessly with the [django-ai-boost MCP server](https://github.com/vintasoftware/django-ai-boost), which provides additional Django-specific tools and capabilities for Claude Code.

To use both together:

1. Install the django-ai-boost MCP server following its documentation
2. Install this django-ai-plugins plugin using the instructions above
3. The skills in this plugin will leverage the tools provided by the MCP server for enhanced Django development capabilities

## Usage

Once installed, the Django-specific skills will be available in your Claude Code sessions, providing specialized assistance for Django backend development tasks.