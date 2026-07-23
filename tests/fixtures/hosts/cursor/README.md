# Cursor host fixture

The Cursor smoke test copies every catalog package into a temporary plugin
home, resolves the `skills` path declared by `.cursor-plugin/plugin.json`, and
requires exactly one package-local skill with the matching ID.

Live Cursor Agent verification is optional because `cursor-agent` is not
available in every development or CI environment.
