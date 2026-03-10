"""
CLI commands package.

Purpose:
- Each command encapsulates one user action in the CLI.
- Command pattern makes it easy to:
  - add new commands
  - test commands independently
  - later reuse commands as API endpoint handlers

Commands:
- ingest: fetch RSS -> store articles
- analyze: run provider/visitor -> store BiasScore
- summarize: render output to terminal
"""

from istina.controller.commands.analyze import AnalyzeCommand
from istina.controller.commands.base_command import BaseCommand, CommandResult
from istina.controller.commands.ingest import IngestCommand
from istina.controller.commands.summarize import SummarizeCommand

__all__ = ["BaseCommand", "CommandResult", "IngestCommand", "AnalyzeCommand", "SummarizeCommand"]
