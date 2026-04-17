"""
Test F02 V122 — convention migrations : tout fichier migrations/*.sql doit contenir un bloc DOWN.

Enforcement CI : ce test échoue si une future migration est ajoutée sans bloc `-- DOWN`.
Protège la convention pour V130, V200... — un dev qui oublie le bloc DOWN verra le CI fail.

Voir migrations/MIGRATION_CONVENTION.md §5 pour la règle d'enforcement.
"""

from pathlib import Path


def test_all_migrations_have_down_block():
    """V122 F02 : every migration must contain a -- DOWN block."""
    migrations_dir = Path(__file__).parent.parent / "migrations"
    sql_files = sorted(migrations_dir.glob("*.sql"))

    assert len(sql_files) > 0, f"No migration found in {migrations_dir}"

    missing = []
    for sql_file in sql_files:
        content = sql_file.read_text(encoding="utf-8")
        if "-- DOWN" not in content:
            missing.append(sql_file.name)

    assert not missing, (
        f"{len(missing)} migration(s) sans bloc -- DOWN : {missing}. "
        f"Voir migrations/MIGRATION_CONVENTION.md §1 pour le format obligatoire."
    )
