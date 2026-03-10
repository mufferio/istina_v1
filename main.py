"""
Istina CLI v0 entry point.

Responsibilities:
- Bootstrap the application from environment/config:
  - Load settings (src/config/settings.py)
  - Configure logging (src/utils/logger.py)
  - Construct dependencies (Repository, Provider, Services)
  - Wire up the CLI controller + commands
- Parse CLI arguments and dispatch to the appropriate Command.

How it evolves:
- v0: argparse-based CLI that supports commands like:
  - ingest (fetch RSS -> store Articles)
  - analyze (run bias/fact-check provider -> store results)
  - summarize (render a report)
- v1+: main becomes a thin wrapper around an app container/factory,
  reused by web API and later mobile backends.

Key invariants:
- No domain logic in main.py.
- All real work happens in services and providers.
"""

import sys

from istina.config.settings import load_settings, validate_settings
from istina.controller.cli_controller import CLIController
from istina.model.repositories.file_repository import FileRepository
from istina.model.repositories.memory_repository import MemoryRepository
from istina.utils.error_handling import ConfigError, format_exception
from istina.utils.logger import configure_logger


def main() -> int:
    # Detect --debug early (before full arg parse) so config errors are also verbose.
    debug: bool = "--debug" in sys.argv

    # 1. Load and validate settings
    try:
        settings = load_settings()
        validate_settings(settings)
    except (ConfigError, ValueError) as exc:
        msg = format_exception(exc, debug=debug)
        print(f"Configuration error: {msg}", file=sys.stderr)
        return 1

    # 2. Configure logger early so subsequent steps can log
    logger = configure_logger(settings)
    logger.debug("Settings loaded: env=%s provider=%s", settings.env, settings.provider)

    # 3. Build shared repository (controlled by ISTINA_REPO_TYPE: 'file' or 'memory')
    if settings.repo_type == "file":
        repo = FileRepository(base_dir=settings.data_dir)
    else:
        repo = MemoryRepository()

    # 4. Hand off to CLI controller
    controller = CLIController(settings=settings, repo=repo)
    return controller.run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())