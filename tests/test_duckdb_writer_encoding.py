"""Regression test: DuckDBJournal must read db/schema.sql as UTF-8 explicitly.

db/schema.sql legitimately contains non-ASCII bytes (Hebrew comments, an
em-dash) -- on Windows, Path.read_text() without an explicit encoding falls
back to the platform's locale-default codec (e.g. cp1255), which cannot
decode those bytes and raises UnicodeDecodeError before any Journal logic
runs. Reproduced and diagnosed on Windows; fixed by
src/journal/duckdb_writer.py's DuckDBJournal.__init__ passing
encoding="utf-8" explicitly.
"""

from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "db" / "schema.sql"
DUCKDB_WRITER_PATH = Path(__file__).resolve().parents[1] / "src" / "journal" / "duckdb_writer.py"


def test_schema_sql_contains_non_ascii_content():
    """Documents why an explicit encoding is required -- not a hypothetical risk."""
    raw = SCHEMA_PATH.read_bytes()
    text = raw.decode("utf-8")  # must not raise
    assert any(ord(ch) > 127 for ch in text), (
        "db/schema.sql was expected to contain non-ASCII (Hebrew comments/em-dash); "
        "if this now fails, the encoding regression this test guards against may "
        "no longer be representative -- investigate before loosening the guard."
    )


def test_duckdb_writer_reads_schema_with_explicit_utf8():
    """Source guard: DuckDBJournal.__init__ must not regress to a bare
    read_text() (locale-default encoding) -- the exact bug reproduced on Windows."""
    source = DUCKDB_WRITER_PATH.read_text(encoding="utf-8")
    assert 'read_text(encoding="utf-8")' in source, (
        "DuckDBJournal.__init__ must read schema_path via "
        "read_text(encoding=\"utf-8\") explicitly -- a bare read_text() falls back "
        "to the platform locale (e.g. Windows cp1255), which fails to decode "
        "db/schema.sql's Hebrew comments/em-dash with UnicodeDecodeError."
    )
