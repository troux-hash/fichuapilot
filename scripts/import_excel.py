"""Import an Excel file straight into the configured database (no web UI needed).

    python scripts/import_excel.py data/samples/all_hotels_synthetic.xlsx

Uses DATABASE_URL, so the same command loads local SQLite or Supabase.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fichua.db import db  # noqa: E402
from fichua.services.importer import import_workbook  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    path = Path(sys.argv[1])
    with db.connect() as conn:
        result = import_workbook(conn, path.read_bytes())
    if not result.ok:
        print("Nothing imported:\n  " + "\n  ".join(result.errors))
        return 1
    print(f"Imported {result.hotels} hotels, {result.rooms} rooms, {result.rate_nights} rate nights "
          f"into {db.dialect}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
