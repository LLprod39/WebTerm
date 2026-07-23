# Compatibility alias command: ``plugin_validate`` re-exports the ``Command``
# from ``validate_plugin_package`` so ``call_command("plugin_validate", ...)``
# keeps working. The explicit ``as Command`` alias marks it as an intentional
# re-export so ruff's F401 does not strip it.
from plugin_marketplace.management.commands.validate_plugin_package import Command as Command
