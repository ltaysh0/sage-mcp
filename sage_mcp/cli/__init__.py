# Import submodules to register all commands with `app` and `config_app`
from sage_mcp.cli import cmd_config, cmd_graph, cmd_index, cmd_search  # noqa: F401
from sage_mcp.cli._common import (  # noqa: F401
    DEFAULT_CONFIG,
    app,
    config_app,
    console,
    err_console,
)
