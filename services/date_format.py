"""
Lot 1.6.066 — formatage NUMÉRIQUE des dates pour l'affichage : JJ/MM/AAAA.

Consommateurs : filtres Jinja `date_num` / `datetime_num` (config/templates.py, gabarits admin),
PDF admin (services/admin_pdf.py), PDF cockpit (services/cockpit_pdf_generator.py), routes des
PDF méta Loto / EM (routes/api_pdf.py, routes/em_analyse.py).

Règles :
  - aucune conversion de fuseau : la valeur est affichée telle quelle (UTC si la source est en UTC) ;
  - entrées : date, datetime, 'AAAA-MM-JJ', 'AAAA-MM-JJ HH:MM[:SS[.ffffff]]', séparateur ' ' ou 'T',
    suffixe 'Z' ou '+HH:MM' toléré (ignoré) ;
  - None / '' → '' ; valeur non reconnue (ou date impossible) → str(value) inchangé.

⚠️ À NE PAS CONFONDRE avec `services.base_chat_utils._format_date_fr`, qui produit du TEXTE
(« 9 février 2026 ») pour les blocs du chatbot (hors lot 1.6.066). `services.admin_pdf._format_date_fr`
(nom historique) délègue à `format_date_num`.
"""

import re
from datetime import date, datetime

_ISO_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})"
    r"(?:[ T](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?)?"
    r"(?:Z|[+-]\d{2}:?\d{2})?$"
)


def _parse(value) -> tuple[datetime, bool] | None:
    """→ (datetime naïf ou aware, la valeur porte-t-elle une heure ?) ou None si non reconnu."""
    if isinstance(value, datetime):  # avant date : datetime est une sous-classe de date
        return value, True
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day), False
    m = _ISO_RE.match(str(value).strip())
    if not m:
        return None
    y, mo, d, hh, mi, ss = m.groups()
    try:
        dt = datetime(int(y), int(mo), int(d), int(hh or 0), int(mi or 0), int(ss or 0))
    except ValueError:  # 2026-02-30, 2026-13-01, 25:00…
        return None
    return dt, hh is not None


def format_date_num(value) -> str:
    """date / datetime / ISO → 'JJ/MM/AAAA' (l'heure éventuelle est ignorée).

    >>> format_date_num("2026-03-04")
    '04/03/2026'
    """
    if value is None or value == "":
        return ""
    parsed = _parse(value)
    if parsed is None:
        return str(value)
    return parsed[0].strftime("%d/%m/%Y")


def format_datetime_num(value, seconds: bool = True) -> str:
    """datetime / ISO avec heure → 'JJ/MM/AAAA HH:MM:SS' (ou 'JJ/MM/AAAA HH:MM' si seconds=False).

    Une valeur SANS heure (date, 'AAAA-MM-JJ') donne 'JJ/MM/AAAA' seul : pas de minuit inventé.
    """
    if value is None or value == "":
        return ""
    parsed = _parse(value)
    if parsed is None:
        return str(value)
    dt, has_time = parsed
    if not has_time:
        return dt.strftime("%d/%m/%Y")
    return dt.strftime("%d/%m/%Y %H:%M:%S" if seconds else "%d/%m/%Y %H:%M")
