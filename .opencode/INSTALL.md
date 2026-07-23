# OpenCode installation

Clone this repository into the project that should expose the skills, or copy
`.opencode/plugins/django-ai-skills.js`, `package.json`, and `skills/` while
preserving their relative paths. OpenCode automatically loads project plugins
from `.opencode/plugins/`; this adapter only registers the canonical `skills/`
directory.

Do not also install the same skill IDs under `.agents/skills/` or
`.opencode/skills/`, because the duplicate can shadow this registration.
