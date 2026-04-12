"""
Tests F01 V98 — Verify anti-relance blocks in all 7 chatbot prompts (6 languages).

Each prompt must contain a user-refusal rule block that instructs Gemini
to stop re-engaging after a clear user refusal ("Non", "No thanks", etc.).
"""

import os
import pytest

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")

# (file_path_relative_to_prompts, expected_tag_substring)
_PROMPT_CASES = [
    ("chatbot/prompt_hybride.txt", "[REFUS UTILISATEUR"),
    ("chatbot/prompt_hybride_em.txt", "[REFUS UTILISATEUR"),
    ("em/en/prompt_hybride_em.txt", "[USER REFUSAL"),
    ("em/es/prompt_hybride_em.txt", "[RECHAZO DEL USUARIO"),
    ("em/pt/prompt_hybride_em.txt", "[RECUSA DO UTILIZADOR"),
    ("em/de/prompt_hybride_em.txt", "[ABLEHNUNG DES NUTZERS"),
    ("em/nl/prompt_hybride_em.txt", "[WEIGERING VAN DE GEBRUIKER"),
]


def _read_prompt(rel_path: str) -> str:
    full = os.path.join(PROMPTS_DIR, rel_path)
    with open(full, encoding="utf-8") as f:
        return f.read()


@pytest.mark.parametrize("rel_path, tag", _PROMPT_CASES, ids=[
    "loto_fr", "em_fr", "em_en", "em_es", "em_pt", "em_de", "em_nl",
])
class TestRefusalBlock:
    """Verify anti-relance block presence and content in each prompt."""

    def test_tag_present(self, rel_path, tag):
        """The language-specific refusal tag must be present."""
        content = _read_prompt(rel_path)
        assert tag in content, f"Missing refusal tag '{tag}' in {rel_path}"

    def test_no_question_rule(self, rel_path, tag):
        """The block must contain a 'FORBIDDEN/INTERDIT/PROHIBIDO/PROIBIDO/VERBOTEN/VERBODEN' rule."""
        content = _read_prompt(rel_path)
        forbidden_words = [
            "INTERDIT", "FORBIDDEN", "PROHIBIDO", "PROIBIDO", "VERBOTEN", "VERBODEN",
        ]
        assert any(w in content for w in forbidden_words), (
            f"Missing FORBIDDEN-equivalent keyword in {rel_path}"
        )

    def test_no_question_mark_rule(self, rel_path, tag):
        """The block must mention never ending with '?' after refusal."""
        content = _read_prompt(rel_path)
        assert '"?"' in content or "'?'" in content, (
            f"Missing '?' prohibition in {rel_path}"
        )

    def test_block_before_faq(self, rel_path, tag):
        """The refusal block must appear BEFORE the FAQ section."""
        content = _read_prompt(rel_path)
        tag_pos = content.find(tag)
        # FAQ section markers vary by language
        faq_markers = ["[BASE DE CONNAISSANCES FAQ]", "[FAQ KNOWLEDGE BASE]",
                       "[BASE DE CONOCIMIENTO FAQ]", "[BASE DE CONHECIMENTO FAQ]",
                       "[FAQ-WISSENSBASIS]", "[FAQ-KENNISBANK]"]
        faq_pos = -1
        for marker in faq_markers:
            pos = content.find(marker)
            if pos != -1:
                faq_pos = pos
                break
        assert tag_pos != -1, f"Tag not found in {rel_path}"
        assert faq_pos != -1, f"FAQ section not found in {rel_path}"
        assert tag_pos < faq_pos, f"Refusal block must appear before FAQ in {rel_path}"

    def test_no_residual_fr_in_non_fr(self, rel_path, tag):
        """Non-FR prompts must not contain FR refusal keywords."""
        if "chatbot/" in rel_path:
            pytest.skip("FR prompt — skip residual check")
        content = _read_prompt(rel_path)
        # Extract just the refusal block
        start = content.find(tag)
        # Find next section marker (next line starting with '[')
        end = content.find("\n[", start + 1)
        if end == -1:
            end = len(content)
        block = content[start:end]
        fr_residuals = ["Pas de souci", "D'accord", "Pas besoin", "Ça ira"]
        for fr in fr_residuals:
            assert fr not in block, f"FR residual '{fr}' found in non-FR prompt {rel_path}"
