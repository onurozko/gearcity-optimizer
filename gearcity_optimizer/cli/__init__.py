"""CLI entry point for GearCity design helper commands."""

from gearcity_optimizer.cli.main import SUBCOMMANDS, _resolve_subcommand, build_streamlit_run_command, main

__all__ = ["SUBCOMMANDS", "_resolve_subcommand", "build_streamlit_run_command", "main"]
