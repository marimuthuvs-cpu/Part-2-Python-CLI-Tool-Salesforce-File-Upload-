"""
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@Name            __main__.py
@Purpose         Entry point for running the package directly via `python -m headshot_upload`.
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@History
VERSION     AUTHOR              DATE                DETAIL DESCRIPTION
1.0         Marimuthu V S       February 25, 2026   Initial Development
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
"""

from headshot_upload.cli.commands import cli

if __name__ == "__main__":
    cli()
