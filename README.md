# django-ai-plugins

A collection of AI skills specialized in Django backend development.

## Installation

### Prerequisites

- Claude Code version 1.0.33 or later (run `claude --version` to check)
- If you need to update: `brew upgrade claude-code` (Homebrew) or `npm update -g @anthropic-ai/claude-code` (npm)

### Installing the Plugin

#### Method 1: Interactive Installation

1. Run the plugin manager:
   ```shell
   /plugin
   ```

2. Navigate to the **Discover** or **Marketplaces** tab to add this plugin's marketplace
3. Browse available plugins and press **Enter** to install

#### Method 2: Direct Command Installation

If this plugin is available in a marketplace, install it directly:

```shell
/plugin install django-ai-plugins@marketplace-name
```

#### Method 3: Install from Local Path

If you've cloned this repository locally:

```shell
/plugin marketplace add /path/to/django-ai-plugins
/plugin install django-ai-plugins@local
```

Or from GitHub:

```shell
/plugin marketplace add vintasoftware/django-ai-plugins
/plugin install django-ai-plugins@vintasoftware
```

### Installation Scopes

When installing, choose where the plugin should be available:

- **User scope** (default): Available across all your projects
- **Project scope**: Shared with all collaborators via `.claude/settings.json`
- **Local scope**: Available only for you in this specific repository

## Integration with django-ai-boost MCP Server

This skill works seamlessly with the [django-ai-boost MCP server](https://github.com/vintasoftware/django-ai-boost), which provides additional Django-specific tools and capabilities for Claude Code.

To use both together:

1. Install the django-ai-boost MCP server following its documentation
2. Install this django-ai-plugins plugin using the instructions above
3. The skills in this plugin will leverage the tools provided by the MCP server for enhanced Django development capabilities

## Usage

Once installed, the Django-specific skills will be available in your Claude Code sessions, providing specialized assistance for Django backend development tasks.