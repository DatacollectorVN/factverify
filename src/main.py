"""FactVerify unified application entry point (FV-ARCH-001).

Usage:
    python -m src.main --config PATH
    python -m src.main --config PATH --set dotted.path=value
    python -m src.main --config PATH --dry-run
    python -m src.main --config PATH --rerun

This module may:
  1. parse CLI arguments
  2. load and validate configuration
  3. construct a RunContext
  4. resolve a task handler
  5. execute the handler
  6. convert the result into a process exit code

It must NOT contain data loading, model loading, epoch loops, evaluation
logic, SQL statements, or checkpoint serialization.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
import yaml

from src.services.common.config import config_hash, load_config, apply_overrides
from src.services.common.context import build_context
from src.services.common.errors import ConfigurationError, FactVerifyError
from src.services.common.logging import setup_logging
from src.services.common.paths import RuntimePaths, discover_repository_root
from src.services.common.registry import get_task_handler
from src.services.common.types import AppConfig, RunResult


@click.command("factverify")
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to a YAML run configuration.",
)
@click.option(
    "--set",
    "overrides",
    multiple=True,
    help="Override a config value: --set dotted.path=value",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Validate and print the resolved run plan without executing.",
)
@click.option(
    "--rerun",
    is_flag=True,
    default=False,
    help="Create a new attempt even if a matching run succeeded.",
)
def main(
    config_path: Path,
    overrides: tuple[str, ...],
    dry_run: bool,
    rerun: bool,
) -> None:
    """FactVerify unified application entry point."""
    try:
        # 1. Discover repo root and load configuration
        repo_root = discover_repository_root(config_path.parent)
        config = load_config(config_path)

        # 2. Apply CLI overrides
        if overrides:
            config = apply_overrides(config, list(overrides))

        # 2b. --rerun disables resume
        if rerun:
            config = apply_overrides(config, ["runtime.resume=false"])

        # 3. Resolve task handler (validates task name)
        handler = get_task_handler(config.task)

        # 4. Dry-run: print plan and exit
        if dry_run:
            _print_dry_run(config, repo_root)
            return

        # 6. Build run context
        context = build_context(
            config,
            repository_root=repo_root,
        )

        # 7. Set up logging
        paths = RuntimePaths(context.runtime_root, repo_root)
        log_file = paths.log_file(context.job_name, context.run_id)
        logger = setup_logging(log_file=log_file)
        # Replace the context logger (RunContext is frozen, so rebuild)
        from dataclasses import replace

        context = replace(context, logger=logger)

        # 8. Write resolved config before expensive work
        run_dir = paths.run_dir(context.job_name, context.run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        resolved_path = paths.resolved_config_path(context.job_name, context.run_id)
        resolved_path.write_text(
            yaml.safe_dump(config.raw, default_flow_style=False, sort_keys=True),
            encoding="utf-8",
        )

        # 9. Execute task handler
        logger.info(
            "starting task=%s job=%s run=%s attempt=%s",
            config.task,
            config.job.name,
            context.run_id,
            context.attempt_id,
        )
        result = handler(config, context)

        # 10. Exit code
        if result.status == "succeeded":
            logger.info("completed successfully")
        else:
            logger.error("failed: %s", result.error or "unknown error")
            sys.exit(1)

    except ConfigurationError as exc:
        click.echo(f"Configuration error: {exc}", err=True)
        sys.exit(2)
    except FactVerifyError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nInterrupted.", err=True)
        sys.exit(130)


def _print_dry_run(config: AppConfig, repo_root: Path) -> None:
    """Print the resolved run plan without creating any state."""
    click.echo("=== Dry Run ===")
    click.echo(f"Task:           {config.task}")
    click.echo(f"Job:            {config.job.name}")
    click.echo(f"Role:           {config.job.role}")
    click.echo(f"Split:          {config.job.split}")
    click.echo(f"Seeds:          {config.job.seeds}")
    click.echo(f"Schema version: {config.schema_version}")
    click.echo(f"Config hash:    {config_hash(config)}")
    click.echo(f"Output root:    {config.runtime.output_root}")
    click.echo(f"Device:         {config.runtime.device}")
    click.echo(f"Deterministic:  {config.runtime.deterministic}")
    click.echo(f"Resume:         {config.runtime.resume}")
    click.echo(f"Source:         {config.source_path}")
    click.echo()
    click.echo("Resolved configuration:")
    click.echo(yaml.safe_dump(config.raw, default_flow_style=False, sort_keys=True))


if __name__ == "__main__":
    main()
