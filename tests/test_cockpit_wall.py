"""
Test du MUR ÉTANCHE tools/ <-> runtime web (CRITIQUE).
======================================================
Scan AST statique : aucun fichier du runtime web (racine + routes/ + services/
+ engine/ + middleware/ + config/) ne doit importer tools.* (tools,
tools.backtest_hybride, tools.signature_features, etc.).

Si un import fautif est introduit → ce test casse le build avec un message
listant fichier + ligne + import. Couvre explicitement les 2 nouveaux fichiers
du cockpit (routes/admin_cockpit.py + services/cockpit_parser.py).

Le scan lit le source et parse l'AST (analyse statique) — il n'importe ni
n'exécute le runtime. Pattern « vrai fichier .py + parsing », jamais d'inline.
"""

import ast
import os

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RUNTIME_DIRS = ["routes", "services", "engine", "middleware", "config"]
_EXCLUDE_DIRS = {"tools", "tests", "scripts", "migrations", "__pycache__",
                 ".git", "venv", ".venv", "node_modules"}


def _iter_runtime_files():
    """Tous les .py du runtime web : racine (non récursif) + 5 sous-dossiers (récursif)."""
    for name in sorted(os.listdir(_REPO)):
        p = os.path.join(_REPO, name)
        if os.path.isfile(p) and name.endswith(".py"):
            yield p
    for d in _RUNTIME_DIRS:
        base = os.path.join(_REPO, d)
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [x for x in dirs if x not in _EXCLUDE_DIRS]
            for fn in sorted(files):
                if fn.endswith(".py"):
                    yield os.path.join(root, fn)


def _tools_imports(source: str, filename: str = "<src>"):
    """Renvoie [(lineno, module)] des imports absolus qui touchent tools.*.

    Détecte `import tools[.x]` et `from tools[.x] import ...`. Ignore les
    lookalikes (toolset, toolkit) et les imports relatifs (level > 0).
    """
    tree = ast.parse(source, filename=filename)
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "tools" or alias.name.startswith("tools."):
                    offenders.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level == 0 and (mod == "tools" or mod.startswith("tools.")):
                offenders.append((node.lineno, mod))
    return offenders


# ── Le test du mur ───────────────────────────────────────────────────────

class TestSealedWall:
    """Aucun import tools.* dans le runtime web."""

    def test_no_runtime_file_imports_tools(self):
        violations = []
        for path in _iter_runtime_files():
            with open(path, encoding="utf-8") as f:
                src = f.read()
            for lineno, mod in _tools_imports(src, path):
                rel = os.path.relpath(path, _REPO)
                violations.append(f"{rel}:{lineno} -> import {mod}")
        assert not violations, (
            "MUR ÉTANCHE FRANCHI — le runtime web importe tools/ :\n  "
            + "\n  ".join(violations)
        )

    def test_new_cockpit_files_are_scanned_and_clean(self):
        scanned = {os.path.relpath(p, _REPO).replace("\\", "/") for p in _iter_runtime_files()}
        assert "routes/admin_cockpit.py" in scanned
        assert "services/cockpit_parser.py" in scanned
        for rel in ("routes/admin_cockpit.py", "services/cockpit_parser.py"):
            with open(os.path.join(_REPO, rel), encoding="utf-8") as f:
                assert _tools_imports(f.read(), rel) == []


# ── Self-tests négatifs : le scanner DOIT détecter une violation ──────────

class TestScannerDetectsViolations:
    """Garantit que le scan échouerait bien si un import tools était ajouté."""

    def test_detects_plain_import(self):
        off = _tools_imports("import tools.signature_features\n")
        assert off and off[0][1] == "tools.signature_features"

    def test_detects_bare_import_tools(self):
        off = _tools_imports("import tools\n")
        assert off and off[0][1] == "tools"

    def test_detects_from_import(self):
        off = _tools_imports("from tools.backtest_hybride import run\n")
        assert off and off[0][1] == "tools.backtest_hybride"

    def test_detects_import_inside_function(self):
        src = "def f():\n    import tools.signature_features as s\n    return s\n"
        assert _tools_imports(src)

    def test_ignores_lookalike_names(self):
        # toolset / toolkit ne doivent PAS être flaggés
        assert _tools_imports("import toolset\n") == []
        assert _tools_imports("from toolkit import x\n") == []

    def test_ignores_relative_import(self):
        # un import relatif ne vise pas le package tools/ racine
        assert _tools_imports("from . import tools\n") == []
