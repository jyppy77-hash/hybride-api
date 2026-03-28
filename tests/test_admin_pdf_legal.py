"""
Tests for invoice PDF legal compliance (Art. L441-9, A441-2, R123-237 Code de Commerce).
Sprint 1 fixes: A01 (date echeance), A02 (TVA intra), A03 (penalites retard), A09 (forme juridique).
"""

import io
from PyPDF2 import PdfReader
from services.admin_pdf import generate_invoice_pdf


def _base_facture(**overrides):
    f = {
        "numero": "FIA-202603-0001",
        "sponsor_nom": "ACME Corp",
        "sponsor_adresse": "1 rue Test, 75000 Paris",
        "date_emission": "2026-03-01",
        "date_echeance": "2026-03-31",
        "periode_debut": "2026-02-01",
        "periode_fin": "2026-02-28",
        "montant_ht": 100.0,
        "montant_tva": 20.0,
        "montant_ttc": 120.0,
    }
    f.update(overrides)
    return f


def _base_config_ei(**overrides):
    c = {
        "raison_sociale": "LotoIA",
        "siret": "12345678900099",
        "adresse": "10 rue de Paris",
        "code_postal": "75001",
        "ville": "Paris",
        "pays": "France",
        "email": "contact@lotoia.fr",
        "telephone": "",
        "tva_intra": "",
        "taux_tva": 20,
        "iban": "FR76 1234 5678 9012 3456",
        "bic": "BNPAFRPP",
        "forme_juridique": "EI",
        "rcs": "",
        "capital_social": "",
    }
    c.update(overrides)
    return c


def _base_config_sasu(**overrides):
    c = _base_config_ei(
        forme_juridique="SASU",
        rcs="Paris 987 654 321",
        capital_social="10 000",
        tva_intra="FR12 345678901",
    )
    c.update(overrides)
    return c


_SAMPLE_LIGNES = [
    {"description": "Impressions popup", "quantite": 500, "prix_unitaire": 0.01, "total_ht": 5.0},
    {"description": "Clics sponsor", "quantite": 50, "prix_unitaire": 1.90, "total_ht": 95.0},
]


def _pdf_text(buf: io.BytesIO) -> str:
    """Extract text from PDF using PyPDF2."""
    buf.seek(0)
    reader = PdfReader(buf)
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


class TestA01DateEcheance:
    """A01: date d'echeance must appear on the invoice PDF."""

    def test_date_echeance_present(self):
        facture = _base_facture(date_echeance="2026-03-31")
        buf = generate_invoice_pdf(facture, _base_config_ei(), _SAMPLE_LIGNES)
        text = _pdf_text(buf)
        assert "cheance" in text  # "Echeance" in PDF
        assert "31/03/2026" in text

    def test_date_echeance_empty_fallback(self):
        facture = _base_facture(date_echeance="")
        buf = generate_invoice_pdf(facture, _base_config_ei(), _SAMPLE_LIGNES)
        text = _pdf_text(buf)
        assert "cheance" in text
        assert "reception" in text  # "A reception" fallback


class TestA02TVAIntra:
    """A02: TVA intracommunautaire or exoneration 293 B must appear."""

    def test_tva_intra_present_when_set(self):
        config = _base_config_sasu(tva_intra="FR12 345678901")
        buf = generate_invoice_pdf(_base_facture(), config, _SAMPLE_LIGNES)
        text = _pdf_text(buf)
        assert "FR12 345678901" in text
        assert "TVA intra" in text

    def test_tva_exoneration_when_empty(self):
        config = _base_config_ei(tva_intra="")
        buf = generate_invoice_pdf(_base_facture(), config, _SAMPLE_LIGNES)
        text = _pdf_text(buf)
        assert "293 B" in text
        assert "non applicable" in text


class TestA03PenalitesRetard:
    """A03: late payment penalties + 40 EUR recovery indemnity must appear."""

    def test_penalites_retard_present(self):
        buf = generate_invoice_pdf(_base_facture(), _base_config_ei(), _SAMPLE_LIGNES)
        text = _pdf_text(buf)
        assert "L441-10" in text
        assert "40 EUR" in text
        assert "D441-5" in text

    def test_penalites_present_sasu(self):
        buf = generate_invoice_pdf(_base_facture(), _base_config_sasu(), _SAMPLE_LIGNES)
        text = _pdf_text(buf)
        assert "L441-10" in text
        assert "40 EUR" in text


class TestA09FormeJuridique:
    """A09: legal form must appear on emitter block."""

    def test_ei_shows_entrepreneur_individuel(self):
        config = _base_config_ei(forme_juridique="EI")
        buf = generate_invoice_pdf(_base_facture(), config, _SAMPLE_LIGNES)
        text = _pdf_text(buf)
        assert "Entrepreneur Individuel" in text

    def test_ei_default_when_empty(self):
        config = _base_config_ei(forme_juridique="")
        buf = generate_invoice_pdf(_base_facture(), config, _SAMPLE_LIGNES)
        text = _pdf_text(buf)
        assert "Entrepreneur Individuel" in text

    def test_sasu_shows_full_legal_info(self):
        config = _base_config_sasu()
        buf = generate_invoice_pdf(_base_facture(), config, _SAMPLE_LIGNES)
        text = _pdf_text(buf)
        assert "SASU" in text
        assert "10 000" in text  # capital
        assert "RCS" in text
        # PDF may line-wrap long strings, so check key parts
        normalized = text.replace("\n", " ")
        assert "Paris 987 654 321" in normalized


class TestFullComplianceEI:
    """T5: full compliance check for EI mode invoice."""

    def test_ei_invoice_compliance(self):
        buf = generate_invoice_pdf(_base_facture(), _base_config_ei(), _SAMPLE_LIGNES)
        text = _pdf_text(buf)
        # Date echeance
        assert "31/03/2026" in text
        # Emitter
        assert "LotoIA" in text
        assert "12345678900099" in text
        assert "Entrepreneur Individuel" in text
        # TVA exoneration
        assert "293 B" in text
        # Penalites
        assert "L441-10" in text
        assert "40 EUR" in text
        # Line items
        assert "FIA-202603-0001" in text


class TestFullComplianceSASU:
    """T6: full compliance check for SASU mode invoice."""

    def test_sasu_invoice_compliance(self):
        config = _base_config_sasu()
        buf = generate_invoice_pdf(_base_facture(), config, _SAMPLE_LIGNES)
        text = _pdf_text(buf)
        # Forme juridique + RCS + capital
        assert "SASU" in text
        assert "10 000" in text
        assert "RCS" in text
        # TVA intra
        assert "FR12 345678901" in text
        # Date echeance
        assert "31/03/2026" in text
        # Penalites
        assert "L441-10" in text
        assert "40 EUR" in text
