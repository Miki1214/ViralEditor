"""Typer CLI entrypoint."""

from __future__ import annotations

from pathlib import Path

import typer

from viral_editor.config import ConfigError
from viral_editor.dev_runner import DevStartupError, run_dev
from viral_editor.ingest.loader import IngestError
from viral_editor.pipeline import run_pipeline
from viral_editor.utils.ffmpeg import ensure_ffmpeg
from viral_editor.utils.logging import configure_logging, get_logger

app = typer.Typer(
    name="viral-editor",
    help="Automated retention video editor — local-first CLI.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Automated retention video editor — local-first CLI."""


@app.command()
def run(
    config: Path = typer.Argument(
        ...,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path to the job config JSON file.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable debug logging.",
    ),
    keep_temp: bool = typer.Option(
        False,
        "--keep-temp",
        help="Retain intermediate artifacts in temp/ (Phase 7+).",
    ),
) -> None:
    """Run the video editor pipeline for a job config."""
    configure_logging(verbose=verbose)
    logger = get_logger(__name__)

    logger.info("viral-editor run %s", config)
    try:
        ensure_ffmpeg()
    except EnvironmentError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    try:
        run_pipeline(config_path=config, verbose=verbose, keep_temp=keep_temp)
    except (ConfigError, IngestError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind address."),
    port: int = typer.Option(8765, help="Bind port."),
    reload: bool = typer.Option(False, "--reload", help="Reload API on code changes."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Start the Control Room web API (and built UI if present)."""
    configure_logging(verbose=verbose)
    logger = get_logger(__name__)

    try:
        import uvicorn
    except ImportError as exc:
        typer.secho(
            "uvicorn is required for serve. Install with: pip install -e \".[ui]\"",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from exc

    logger.info("Starting Control Room at http://%s:%s", host, port)
    typer.echo(f"Control Room API: http://{host}:{port}/api/health")
    typer.echo("For UI dev with hot reload: python -m viral_editor dev")

    uvicorn.run(
        "viral_editor.api.main:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
    )


@app.command()
def dev(
    host: str = typer.Option("127.0.0.1", help="API bind address."),
    port: int = typer.Option(8765, help="API bind port."),
    reload: bool = typer.Option(True, "--reload/--no-reload", help="Reload API on code changes."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Start Control Room API and Vite dev server together."""
    configure_logging(verbose=verbose)
    try:
        code = run_dev(host=host, port=port, reload=reload)
    except DevStartupError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    if code != 0:
        raise typer.Exit(code=code)


if __name__ == "__main__":
    app()
