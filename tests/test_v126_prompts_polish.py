"""
V126 Sous-phase 3/5 — Polish bloc [INTERDICTION CODE] dans 9 prompts.

Ajout : JSON, YAML, XML, Markdown blocks ``` explicitement mentionnés.
Non-régression V86 F05 : Python + SQL + JavaScript toujours présents.

Liste des 9 prompts couverts (identifiés via grep [INTERDICTION CODE]) :
- prompts/chatbot/prompt_hybride.txt (FR Loto)
- prompts/chatbot/prompt_hybride_em.txt (FR EM)
- prompts/chatbot/prompt_hybride_em_en.txt (EN EM chatbot dir)
- prompts/em/{fr,en,es,pt,de,nl}/prompt_hybride_em.txt (6 EM file-based)
"""

from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).parent.parent
_PROMPTS_9 = [
    _REPO_ROOT / "prompts" / "chatbot" / "prompt_hybride.txt",
    _REPO_ROOT / "prompts" / "chatbot" / "prompt_hybride_em.txt",
    _REPO_ROOT / "prompts" / "chatbot" / "prompt_hybride_em_en.txt",
    _REPO_ROOT / "prompts" / "em" / "fr" / "prompt_hybride_em.txt",
    _REPO_ROOT / "prompts" / "em" / "en" / "prompt_hybride_em.txt",
    _REPO_ROOT / "prompts" / "em" / "es" / "prompt_hybride_em.txt",
    _REPO_ROOT / "prompts" / "em" / "pt" / "prompt_hybride_em.txt",
    _REPO_ROOT / "prompts" / "em" / "de" / "prompt_hybride_em.txt",
    _REPO_ROOT / "prompts" / "em" / "nl" / "prompt_hybride_em.txt",
]


@pytest.mark.parametrize("prompt_path", _PROMPTS_9, ids=lambda p: p.as_posix().split("prompts/")[1])
class TestV126PromptsPolish:
    """V126 3/5 : chaque prompt DOIT mentionner JSON/YAML/XML ET préserver
    V86 F05 Python/SQL/JavaScript (non-régression)."""

    def test_prompt_exists(self, prompt_path):
        assert prompt_path.exists(), f"Missing prompt file: {prompt_path}"

    def test_mentions_json(self, prompt_path):
        content = prompt_path.read_text(encoding="utf-8")
        assert "JSON" in content, f"{prompt_path.name}: JSON absent (V126 3/5)"

    def test_mentions_yaml(self, prompt_path):
        content = prompt_path.read_text(encoding="utf-8")
        assert "YAML" in content, f"{prompt_path.name}: YAML absent (V126 3/5)"

    def test_mentions_xml(self, prompt_path):
        content = prompt_path.read_text(encoding="utf-8")
        assert "XML" in content, f"{prompt_path.name}: XML absent (V126 3/5)"

    def test_mentions_markdown(self, prompt_path):
        content = prompt_path.read_text(encoding="utf-8")
        assert "Markdown" in content, f"{prompt_path.name}: Markdown absent (V126 3/5)"

    def test_ajustement_A3_keeps_python(self, prompt_path):
        """A3 non-régression V86 F05 : Python toujours cité."""
        content = prompt_path.read_text(encoding="utf-8")
        assert "Python" in content, (
            f"{prompt_path.name}: Python absent (régression V86 F05)"
        )

    def test_ajustement_A3_keeps_sql(self, prompt_path):
        """A3 non-régression V86 F05 : SQL toujours cité."""
        content = prompt_path.read_text(encoding="utf-8").lower()
        assert "sql" in content, (
            f"{prompt_path.name}: SQL absent (régression V86 F05)"
        )

    def test_ajustement_A3_keeps_javascript(self, prompt_path):
        """A3 non-régression V86 F05 : JavaScript toujours cité."""
        content = prompt_path.read_text(encoding="utf-8")
        assert "JavaScript" in content, (
            f"{prompt_path.name}: JavaScript absent (régression V86 F05)"
        )


class TestV126PromptsNineCount:
    """Invariant : exactement 9 prompts sont couverts."""

    def test_nine_prompts_in_scope(self):
        assert len(_PROMPTS_9) == 9
