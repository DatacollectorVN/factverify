#!/usr/bin/env python3
"""Launch a DuckDB web UI connected to one or more SQLite databases.

Usage:
    uv run --with duckdb tools/duck_explorer.py
    uv run --with duckdb tools/duck_explorer.py --port 9999
    uv run --with duckdb tools/duck_explorer.py --db .factverify_internal/eval/eval.sqlite
    uv run --with duckdb tools/duck_explorer.py --db .factverify_internal/train/train.sqlite --db .factverify_internal/eval/eval.sqlite
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import webbrowser
from pathlib import Path
from subprocess import Popen

ALL_DBS = [
    ".factverify_internal/train/train.sqlite",
    ".factverify_internal/eval/eval.sqlite",
    ".factverify_internal/data/tofu/pipeline.sqlite",
]


def _derive_name(db_path: Path) -> str:
    """Derive a short schema name from the path: parent_stem."""
    return f"{db_path.parent.name}_{db_path.stem}"


def main() -> None:
    parser = argparse.ArgumentParser(description="DuckDB web UI for SQLite databases")
    parser.add_argument(
        "--db",
        action="append",
        dest="dbs",
        metavar="PATH",
        help="SQLite database path (repeatable). Default: all known DBs.",
    )
    parser.add_argument("--port", type=int, default=4213, help="Web UI port")
    parser.add_argument(
        "--no-browser", action="store_true", help="Don't open browser automatically"
    )
    args = parser.parse_args()

    # Resolve database paths
    if args.dbs:
        db_paths = [Path(p).resolve() for p in args.dbs]
    else:
        db_paths = [Path(p).resolve() for p in ALL_DBS if Path(p).is_file()]

    if not db_paths:
        print("error: no databases found", file=sys.stderr)
        sys.exit(1)

    for p in db_paths:
        if not p.is_file():
            print(f"error: database not found: {p}", file=sys.stderr)
            sys.exit(1)

    try:
        import duckdb
    except ImportError:
        print(
            "duckdb not found. Run with:\n"
            "  uv run --with duckdb tools/duck_explorer.py",
            file=sys.stderr,
        )
        sys.exit(1)

    # Create a path for the DuckDB file (must not exist yet — DuckDB creates it)
    fd, duck_path = tempfile.mkstemp(suffix=".duckdb")
    os.close(fd)
    os.unlink(duck_path)  # DuckDB needs to create the file itself

    conn = duckdb.connect(duck_path)
    conn.execute("INSTALL sqlite; LOAD sqlite;")

    # Attach all databases
    names: list[str] = []
    for db_path in db_paths:
        name = _derive_name(db_path)
        conn.execute(f"ATTACH '{db_path}' AS {name} (TYPE sqlite, READ_ONLY);")
        names.append(name)
        tables = conn.execute(
            f"SELECT table_name FROM information_schema.tables "
            f"WHERE table_catalog = '{name}'"
        ).fetchall()
        table_list = ", ".join(t[0] for t in tables) if tables else "(empty)"
        print(f"  {name}: {table_list}")

    # Default to first attached DB
    conn.execute(f"USE {names[0]};")
    print(f"\nAttached {len(names)} database(s): {', '.join(names)}")
    print(f"Default schema: {names[0]}")
    print(f"\nQuery across databases with: SELECT * FROM {names[0]}.table_name")
    print(f"\nStarting DuckDB web UI on http://localhost:{args.port}")
    print("Press Ctrl+C to stop.\n")

    conn.close()

    # Build init SQL that the CLI runs on startup
    init_parts = [
        "INSTALL sqlite; LOAD sqlite;",
        f"LOAD ui; SET ui_local_port={args.port};",
    ]
    for db_path in db_paths:
        name = _derive_name(db_path)
        init_parts.append(f"ATTACH '{db_path}' AS {name} (TYPE sqlite, READ_ONLY);")
    init_parts.append(f"USE {names[0]};")

    # Write init SQL to a temp file (CLI -init reads it on startup)
    fd_init, init_path = tempfile.mkstemp(suffix=".sql")
    os.write(fd_init, "\n".join(init_parts).encode())
    os.close(fd_init)

    # Launch duckdb CLI with web UI
    url = f"http://localhost:{args.port}"
    if not args.no_browser:
        webbrowser.open(url)

    try:
        proc = Popen(["duckdb", "-init", init_path, "-ui", duck_path])
        proc.wait()
    except FileNotFoundError:
        print("duckdb CLI not found, using Python connection...")
        conn = duckdb.connect(duck_path)
        for db_path in db_paths:
            name = _derive_name(db_path)
            conn.execute(f"ATTACH '{db_path}' AS {name} (TYPE sqlite, READ_ONLY);")
        conn.execute(f"USE {names[0]};")
        print("\nEntering interactive mode. Type SQL queries, 'quit' to exit.\n")
        while True:
            try:
                query = input("duckdb> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not query or query.lower() in ("quit", "exit", "\\q"):
                break
            try:
                result = conn.execute(query)
                print(result.fetchdf().to_string())
            except Exception as e:
                print(f"error: {e}")
        conn.close()
    except KeyboardInterrupt:
        print("\nStopped.")
        proc.terminate()
    finally:
        Path(init_path).unlink(missing_ok=True)
        Path(duck_path).unlink(missing_ok=True)
        Path(duck_path + ".wal").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
