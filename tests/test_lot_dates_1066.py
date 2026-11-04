"""
Tests — Lot 1.6.066 « formats de date » : JJ/MM/AAAA pour toute date numérique affichée (05/11/2026).

Décisions D0-D14, chatbot exclu (option A). Couvre :
  1. services/date_format.py (format_date_num / format_datetime_num) ;
  2. filtres Jinja date_num / datetime_num (gabarits admin factures / contrats ; value= ISO conservé) ;
  3. PDF : sponsor (jour + période personnalisée), realtime (date/heure), cockpit (pied de page) ;
  4. routes PDF méta Loto + EM (le générateur reçoit JJ/MM/AAAA ; _fetch_last_draw_date_* restent ISO
     pour le sitemap) ;
  5. e-mail d'alerte (Timestamp JJ/MM/AAAA HH:MM:SS UTC) ;
  6. sources JS / gabarits (tests statiques) + exécution node des helpers et de H1 (ignorés sans node) ;
  7. cache-busters ?v= ;
  8. en.po (16 msgstr, aucun ordre mois-jour ni AM/PM) + rendu /en/euromillions/hybride sans exemple FR.
"""

import asyncio
import gettext
import io
import json
import os
import re
import shutil
import subprocess
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PyPDF2 import PdfReader
from starlette.testclient import TestClient

from services.date_format import format_date_num, format_datetime_num

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_NODE = shutil.which("node")
_ISO_ANY = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")


def _read(rel: str) -> str:
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _js_function(src: str, name: str) -> str:
    """Source complète de `function name(...) { ... }` (accolades équilibrées)."""
    start = src.index("function " + name + "(")
    depth = 0
    for k in range(src.index("{", start), len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[start:k + 1]
    raise AssertionError(f"fonction {name} non fermée")


def _pdf_text(buf: io.BytesIO) -> str:
    buf.seek(0)
    return "\n".join((page.extract_text() or "") for page in PdfReader(buf).pages)


# ═══════════════════════════════════════════════════════════════════════
# 1. services/date_format.py
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("value,expected", [
    (date(2026, 11, 4), "04/11/2026"),
    (datetime(2026, 11, 4, 5, 32, 47), "04/11/2026"),
    ("2026-11-04", "04/11/2026"),
    ("2026-11-04 05:32:47", "04/11/2026"),
    ("2026-11-04T05:32:47", "04/11/2026"),
    ("2026-11-04 05:32", "04/11/2026"),
    ("2026-11-04T05:32:47.123456", "04/11/2026"),
    ("2026-11-04T05:32:47Z", "04/11/2026"),
    (" 2026-11-04 ", "04/11/2026"),
    # jour ≤ 12 : tranché par le code (AAAA-MM-JJ → JJ/MM/AAAA), jamais l'inverse
    ("2026-03-04", "04/03/2026"),
    (date(2026, 3, 4), "04/03/2026"),
    ("2026-12-01", "01/12/2026"),
    ("", ""),
    (None, ""),
    ("not-a-date", "not-a-date"),
    ("2026-13-01", "2026-13-01"),
    ("2026-02-30", "2026-02-30"),
    ("04/11/2026", "04/11/2026"),
    ("permanent", "permanent"),
])
def test_format_date_num(value, expected):
    assert format_date_num(value) == expected


@pytest.mark.parametrize("value,kwargs,expected", [
    (datetime(2026, 11, 4, 5, 32, 47), {}, "04/11/2026 05:32:47"),
    ("2026-11-04 05:32:47", {}, "04/11/2026 05:32:47"),
    ("2026-11-04T05:32:47", {}, "04/11/2026 05:32:47"),
    ("2026-03-04 09:05:01", {}, "04/03/2026 09:05:01"),
    ("2026-11-04 05:32", {}, "04/11/2026 05:32:00"),
    ("2026-11-04 05:32:47", {"seconds": False}, "04/11/2026 05:32"),
    (datetime(2026, 11, 4, 5, 32, 47), {"seconds": False}, "04/11/2026 05:32"),
    # sans heure : la date seule, pas de minuit inventé
    (date(2026, 11, 4), {}, "04/11/2026"),
    ("2026-11-04", {}, "04/11/2026"),
    ("", {}, ""),
    (None, {}, ""),
    ("2026-11-04 25:00:00", {}, "2026-11-04 25:00:00"),
    ("n/a", {}, "n/a"),
])
def test_format_datetime_num(value, kwargs, expected):
    assert format_datetime_num(value, **kwargs) == expected


def test_no_timezone_conversion():
    """Aucune conversion : une heure aware est affichée telle quelle (UTC reste UTC, +01:00 reste +01:00)."""
    assert format_datetime_num(datetime(2026, 11, 4, 5, 32, 47, tzinfo=timezone.utc)) == "04/11/2026 05:32:47"
    paris = timezone(timedelta(hours=1))
    assert format_datetime_num(datetime(2026, 11, 4, 23, 30, 0, tzinfo=paris)) == "04/11/2026 23:30:00"


def test_admin_pdf_format_date_fr_delegates():
    """Nom historique conservé (factures / contrats) : même sortie JJ/MM/AAAA."""
    from services.admin_pdf import _format_date_fr
    assert _format_date_fr(date(2026, 3, 31)) == "31/03/2026"
    assert _format_date_fr("2026-03-31") == "31/03/2026"
    assert _format_date_fr("") == ""
    assert _format_date_fr(None) == ""


def test_date_format_module_is_not_the_chatbot_formatter():
    """Garde-fou de nommage : le formateur chatbot (texte) reste distinct et inchangé."""
    from services.base_chat_utils import _format_date_fr as chat_fmt
    assert chat_fmt("2026-02-09") == "9 février 2026"
    assert format_date_num("2026-02-09") == "09/02/2026"


# ═══════════════════════════════════════════════════════════════════════
# 2. Filtres Jinja + gabarits admin
# ═══════════════════════════════════════════════════════════════════════

def _render(name: str, **ctx) -> str:
    from config.templates import env
    return env.get_template(name).render(**ctx)


def test_jinja_filters_registered():
    from config.templates import env
    assert env.filters["date_num"] is format_date_num
    assert env.filters["datetime_num"] is format_datetime_num


def _facture():
    return {
        "id": 7, "numero": "FIA-202603-0001", "sponsor_nom": "Sponsor Test", "sponsor_id": 1,
        "date_emission": date(2026, 3, 4), "date_echeance": date(2026, 4, 3),
        "periode_debut": date(2026, 3, 1), "periode_fin": date(2026, 3, 31),
        "montant_ht": 650.0, "montant_tva": 0.0, "montant_ttc": 650.0, "statut": "envoyee", "notes": None,
    }


def _contrat():
    return {
        "id": 3, "numero": "CTR-202604-0001", "sponsor_nom": "Sponsor Test", "sponsor_id": 1,
        "product_codes": "LOTOIA_EXCLU", "date_debut": date(2026, 4, 1), "date_fin": date(2026, 6, 30),
        "montant_mensuel_ht": 650.0, "mode_depassement": "CPC", "statut": "actif", "engagement_mois": 3,
        "plafond_mensuel": None, "pool_impressions": 10000, "conditions_particulieres": "",
    }


def test_factures_list_dates_num():
    html = _render("admin/factures.html", active="factures", factures=[_facture()])
    assert "<td>04/03/2026</td>" in html
    assert "01/03/2026 — 31/03/2026" in html
    assert "2026-03-04" not in html and "2026-03-01" not in html and "2026-03-31" not in html


def test_facture_detail_dates_num():
    html = _render("admin/facture_detail.html", active="factures", facture=_facture(), lignes=[])
    assert '<span class="kpi-value">04/03/2026</span>' in html
    assert '<span class="kpi-value">03/04/2026</span>' in html
    assert "<b>01/03/2026</b> au <b>31/03/2026</b>" in html
    assert not _ISO_ANY.search(html)


def test_contrats_list_dates_num():
    html = _render("admin/contrats.html", active="contrats", contrats=[_contrat()], pool_data=None)
    assert "<td>01/04/2026</td>" in html and "<td>30/06/2026</td>" in html
    assert "2026-04-01" not in html and "2026-06-30" not in html


def test_contrat_detail_dates_num():
    html = _render("admin/contrat_detail.html", active="contrats", contrat=_contrat(), impressions_data=None)
    assert "<b>01/04/2026</b> au <b>30/06/2026</b>" in html
    assert "2026-04-01" not in html


def test_contrat_form_values_stay_iso():
    """Les value= des <input type="date"> doivent rester en ISO (exigé par le navigateur)."""
    html = _render("admin/contrat_form.html", active="contrats", contrat=_contrat(),
                   sponsors=[{"id": 1, "nom": "Sponsor Test"}], error=None)
    assert 'value="2026-04-01"' in html and 'value="2026-06-30"' in html
    assert 'value="01/04/2026"' not in html


@pytest.mark.parametrize("rel", ["ui/templates/admin/contrat_form.html", "ui/templates/admin/facture_form.html"])
def test_form_templates_never_use_date_filter(rel):
    assert "date_num" not in _read(rel)


# ═══════════════════════════════════════════════════════════════════════
# 3. PDF admin + cockpit
# ═══════════════════════════════════════════════════════════════════════

def test_sponsor_report_pdf_day_and_custom_period():
    from services.admin_pdf import generate_sponsor_report_pdf
    buf = generate_sponsor_report_pdf(
        {"impressions": 3, "clicks": 0, "videos": 0, "ctr": "0.00%", "sessions": 1},
        [{"day": "2026-03-04", "event_type": "sponsor-popup-shown", "page": "/loto",
          "lang": "fr", "device": "desktop", "country": "FR", "cnt": 3}],
        "2026-01-01 — 2026-02-01",
    )
    text = _pdf_text(buf)
    assert "04/03/2026" in text
    assert "01/01/2026" in text and "01/02/2026" in text
    assert not _ISO_ANY.search(text)


def test_sponsor_report_pdf_text_period_unchanged():
    from services.admin_pdf import generate_sponsor_report_pdf
    text = _pdf_text(generate_sponsor_report_pdf({}, [], "7 derniers jours"))
    assert "7 derniers jours" in text


def test_realtime_report_pdf_datetime_num():
    from services.admin_pdf import generate_realtime_report_pdf
    buf = generate_realtime_report_pdf(
        {"total": 1, "hour": 1, "types": 1}, {"page_view": 1},
        [{"created_at": "2026-03-04 05:32:47", "event_type": "page_view", "page": "/loto",
          "lang": "fr", "device": "desktop", "country": "FR"}],
        "7 derniers jours",
    )
    text = _pdf_text(buf)
    assert "04/03/2026 05:32:47" in text
    assert "2026-03-04" not in text


def test_cockpit_pdf_footer_date_num():
    import services.cockpit_pdf_generator as cpg
    canvas_obj = MagicMock()
    doc_obj = MagicMock()
    doc_obj.page = 2
    with patch.object(cpg, "date") as mdate:
        mdate.today.return_value = date(2026, 3, 4)
        cpg._footer(canvas_obj, doc_obj)
    assert canvas_obj.drawRightString.call_args[0][2] == "04/03/2026 · p. 2"


# ═══════════════════════════════════════════════════════════════════════
# 4. Routes PDF méta Loto + EM
# ═══════════════════════════════════════════════════════════════════════

_static_patch = patch("fastapi.staticfiles.StaticFiles.__init__", return_value=None)
_static_call = patch("fastapi.staticfiles.StaticFiles.__call__", return_value=None)
_db_env = patch.dict(os.environ, {"DB_PASSWORD": "fake", "DB_USER": "test", "DB_NAME": "testdb"})
_ip_counter = [140]


def _get_client():
    with _db_env, _static_patch, _static_call:
        import importlib
        import main as main_mod
        importlib.reload(main_mod)
        return TestClient(main_mod.app, raise_server_exceptions=False)


def _headers():
    _ip_counter[0] += 1
    return {"X-Forwarded-For": f"10.66.0.{_ip_counter[0]}"}


@pytest.mark.usefixtures("db_unavailable")  # middleware ip_ban : base indisponible simulée (garde-fou conftest)
@pytest.mark.parametrize("fetched,expected", [("2026-11-02", "02/11/2026"), (None, None)])
def test_meta_pdf_loto_passes_ddmmyyyy(fetched, expected):
    client = _get_client()
    gen = MagicMock(return_value=io.BytesIO(b"%PDF-1.4 test"))
    with patch("routes.api_pdf._fetch_last_draw_date_loto", AsyncMock(return_value=fetched)), \
         patch("routes.api_pdf.generate_meta_pdf", gen):
        resp = client.post("/api/meta-pdf", json={"lang": "fr"}, headers=_headers())
    assert resp.status_code == 200, resp.text
    assert gen.call_args.kwargs["last_draw_date"] == expected


@pytest.mark.usefixtures("db_unavailable")  # middleware ip_ban : base indisponible simulée (garde-fou conftest)
@pytest.mark.parametrize("fetched,expected", [("2026-10-30", "30/10/2026"), (None, None)])
def test_meta_pdf_em_passes_ddmmyyyy(fetched, expected):
    client = _get_client()
    gen = MagicMock(return_value=io.BytesIO(b"%PDF-1.4 test"))
    with patch("routes.em_analyse._fetch_last_draw_date_em", AsyncMock(return_value=fetched)), \
         patch("services.em_pdf_generator.generate_em_meta_pdf", gen):
        resp = client.post("/api/euromillions/meta-pdf", json={"lang": "en"}, headers=_headers())
    assert resp.status_code == 200, resp.text
    assert gen.call_args.kwargs["last_draw_date"] == expected


def _fake_get_connection(row):
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=row)

    @asynccontextmanager
    async def _cm():
        conn = AsyncMock()
        conn.cursor = AsyncMock(return_value=cursor)
        yield conn
    return _cm


def test_fetch_last_draw_date_still_iso_for_sitemap():
    """routes/sitemap.py:148-149 réutilise ces fonctions pour <lastmod> : elles restent ISO."""
    from routes.api_pdf import _fetch_last_draw_date_loto
    from routes.em_analyse import _fetch_last_draw_date_em
    # Boucle dédiée, jamais installée comme boucle courante : asyncio.run() ferait set_event_loop(None)
    # et casserait les tests suivants qui appellent asyncio.get_event_loop() (test_v121_*, test_v74_*).
    loop = asyncio.new_event_loop()
    try:
        with patch("engine.db.get_connection", _fake_get_connection({"date_de_tirage": date(2026, 11, 2)})):
            assert loop.run_until_complete(_fetch_last_draw_date_loto()) == "2026-11-02"
            assert loop.run_until_complete(_fetch_last_draw_date_em()) == "2026-11-02"
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════════════
# 5. E-mail d'alerte
# ═══════════════════════════════════════════════════════════════════════

def test_alert_email_timestamp_ddmmyyyy_utc():
    from services.alerting import Alert, _send_email_sync
    alert = Alert("critical", "cpu", 0.95, 0.90, "CPU critique")
    smtp = MagicMock()
    smtp.__enter__ = MagicMock(return_value=smtp)
    smtp.__exit__ = MagicMock(return_value=False)
    with patch("services.alerting._SMTP_HOST", "smtp.test.com"), \
         patch("services.alerting._SMTP_PORT", 465), \
         patch("services.alerting._SMTP_USER", "user@test.com"), \
         patch("services.alerting._SMTP_PASS", "pass123"), \
         patch("smtplib.SMTP_SSL", return_value=smtp):
        _send_email_sync(alert)
    msg = smtp.send_message.call_args[0][0]
    body = msg.get_payload()[0].get_payload(decode=True).decode("utf-8")
    assert re.search(r"^Timestamp : \d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2} UTC$", body, re.MULTILINE), body
    assert not re.search(r"Timestamp : \d{4}-", body)


# ═══════════════════════════════════════════════════════════════════════
# 6. Sources JS / gabarits (statiques) + exécution node
# ═══════════════════════════════════════════════════════════════════════

def test_em_statistiques_last_drawn_formatted():
    src = _read("ui/templates/em/statistiques.html")
    assert "s.derniere_sortie || s.last_appearance || '-'" not in src
    assert src.count("fmtDateNum(s.derniere_sortie || s.last_appearance) || '-'") == 2
    assert "function fmtDateNum(" in src


@pytest.mark.parametrize("rel,raw", [
    ("ui/static/simulateur.js", "heat.last_draw || 'N/A'"),
    ("ui/static/simulateur-em.js", "heat.last_draw || 'N/A'"),
])
def test_simulators_tooltip_formatted(rel, raw):
    src = _read(rel)
    assert raw not in src
    assert "formatDateNum(heat.last_draw)" in src
    assert "function formatDateNum(" in src


def test_monitoring_labels_no_mm_dd():
    src = _read("ui/templates/admin/monitoring.html")
    assert "t.slice(5, 13)" not in src
    assert "return fmtDayHour(t);" in src
    assert "charts.botsTimeline.data.labels = buckets.map(fmtDayHour);" in src
    assert "if (currentPeriod === '24h') return t.slice(11, 16);" in src  # 24 h inchangé (D7)


def test_em_generateur_formatter_no_tolocale():
    fn = _js_function(_read("ui/templates/em/generateur.html"), "formatDateFREM")
    assert "toLocaleDateString" not in fn and "new Date(" not in fn and "date_locale" not in fn


@pytest.mark.parametrize("rel", ["ui/static/app.js", "ui/static/app-em.js"])
def test_next_draw_date_no_toisostring(rel):
    fn = _js_function(_read(rel), "getNextDrawDate")
    assert "nextDate.toISOString" not in fn  # l'appel (le commentaire H1 cite le nom de la méthode)
    assert "getFullYear()" in fn and "getMonth()" in fn and "getDate()" in fn


def test_admin_js_fmtday_wiring():
    src = _read("ui/static/admin.js")
    assert "function fmtDay(" in src
    assert "escHtml(r.day)" not in src
    assert src.count("escHtml(fmtDay(r.day))") == 2
    assert "labels: labels.map(fmtDay)" in src
    assert "return fmtDay(r.day);" in src
    assert "' — ' + fmtDay(dateStr)" in src
    assert "'/admin/api/calendar-perf/draw/' + perfState.game + '/' + dateStr" in src  # fetch : ISO conservé


_JS_HELPER_CASES = [
    ("ui/static/simulateur.js", "formatDateNum", "2026-03-04", "04/03/2026"),
    ("ui/static/simulateur.js", "formatDateNum", "", ""),
    ("ui/static/simulateur-em.js", "formatDateNum", "2026-12-01", "01/12/2026"),
    ("ui/templates/em/statistiques.html", "fmtDateNum", "2026-09-01", "01/09/2026"),
    ("ui/templates/em/generateur.html", "formatDateFREM", "2019-11-06", "06/11/2019"),
    ("ui/templates/em/generateur.html", "formatDateFREM", "---", "---"),
    ("ui/static/admin.js", "fmtDay", "2026-11-04", "04/11/2026"),
    ("ui/static/admin.js", "fmtDay", "total", "total"),
    ("ui/templates/admin/monitoring.html", "fmtDayHour", "2026-11-04 06:00", "04/11 06h"),
    ("ui/templates/admin/monitoring.html", "fmtDayHour", "2026-11-04", "04/11"),
]


@pytest.mark.skipif(_NODE is None, reason="node absent (CI) — exécuté au pré-push local")
@pytest.mark.parametrize("rel,name,arg,expected", _JS_HELPER_CASES)
def test_js_helpers_runtime(tmp_path, rel, name, arg, expected):
    harness = _js_function(_read(rel), name) + f"\nprocess.stdout.write(String({name}({json.dumps(arg)})));\n"
    script = tmp_path / "helper.js"
    script.write_text(harness, encoding="utf-8")
    out = subprocess.run([_NODE, str(script)], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert out.stdout == expected


@pytest.mark.skipif(_NODE is None, reason="node absent (CI) — exécuté au pré-push local")
@pytest.mark.parametrize("rel,expected", [
    ("ui/static/app.js", "2026-11-09"),      # dimanche 00:30 → lundi (l'ancien code donnait 2026-11-08)
    ("ui/static/app-em.js", "2026-11-10"),   # dimanche 00:30 → mardi (l'ancien code donnait 2026-11-09)
])
def test_h1_next_draw_date_after_midnight_paris(tmp_path, rel, expected):
    """H1 : horloge simulée dimanche 08/11/2026 00:30 heure de Paris (UTC+1)."""
    harness = (
        "const RealDate = Date;\n"
        "const FIXED = new RealDate(2026, 10, 8, 0, 30, 0).getTime();\n"
        "if (new RealDate(FIXED).getTimezoneOffset() !== -60) { process.stdout.write('TZ_KO'); process.exit(0); }\n"
        "global.Date = class extends RealDate {\n"
        "  constructor(...a) { if (a.length === 0) { super(FIXED); } else { super(...a); } }\n"
        "  static now() { return FIXED; }\n"
        "};\n"
        + _js_function(_read(rel), "getNextDrawDate")
        + "\nprocess.stdout.write(getNextDrawDate());\n"
    )
    script = tmp_path / "h1.js"
    script.write_text(harness, encoding="utf-8")
    out = subprocess.run([_NODE, str(script)], capture_output=True, text=True, timeout=30,
                         env={**os.environ, "TZ": "Europe/Paris"})
    assert out.returncode == 0, out.stderr
    if out.stdout == "TZ_KO":
        pytest.skip("TZ=Europe/Paris non appliqué par node sur cette machine")
    assert out.stdout == expected


# ═══════════════════════════════════════════════════════════════════════
# 7. Cache-busters ?v=
# ═══════════════════════════════════════════════════════════════════════

def test_cache_busters_bumped():
    assert "/static/admin.js?v=23" in _read("ui/templates/admin/_base.html")
    assert "/ui/static/simulateur.js?v=8" in _read("ui/simulateur.html")
    assert "/ui/static/app.js?v=14" in _read("ui/loto.html")


@pytest.mark.parametrize("js,version", [("simulateur-em.js", "9"), ("app-em.js", "11")])
def test_em_cache_busters_aligned(js, version):
    """Défaut (config/templates.py) et surcharge FR (routes/em_pages.py) identiques."""
    pattern = re.escape("/ui/static/" + js) + r"\?v=(\d+)"
    found = set(re.findall(pattern, _read("config/templates.py"))) | set(re.findall(pattern, _read("routes/em_pages.py")))
    assert found == {version}, found


# ═══════════════════════════════════════════════════════════════════════
# 8. en.po + rendu /en/euromillions/hybride
# ═══════════════════════════════════════════════════════════════════════

def _en_catalog():
    from babel.messages.pofile import read_po
    with open(os.path.join(_ROOT, "translations", "en", "LC_MESSAGES", "messages.po"), "rb") as f:
        return read_po(f)


_HYBRIDE_EXAMPLES = [
    ('"Combien de fois le 22 est sorti en 2024 ?"', '"How many times has 22 been drawn in 2024?"'),
    ('"Quel est le numéro le plus sorti depuis 2019 ?"', '"What is the most drawn number since 2019?"'),
    ('"Quels numéros ne sont pas sortis depuis plus de 20 tirages ?"',
     '"Which numbers haven\'t been drawn for over 20 draws?"'),
    ('"Quel était le résultat du tirage du 14 janvier 2025 ?"',
     '"What was the result of the draw on 14 January 2025?"'),
    ('"Combien de tirages ont eu lieu en 2024 ?"', '"How many draws took place in 2024?"'),
    ('"Quel tirage a eu la somme la plus élevée ?"', '"Which draw had the highest sum?"'),
    ('"Montre-moi les 5 derniers tirages."', '"Show me the last 5 draws."'),
    ('"C\'est quoi un numéro chaud ?"', '"What is a hot number?"'),
    ('"Dans quels pays peut-on jouer à l\'EuroMillions ?"', '"In which countries can you play EuroMillions?"'),
]

_EN_EXACT = [
    ("30 mars 2026", "30 March 2026"),
    ("27 avril 2026", "27 April 2026"),
    ("Rendez-vous le 15 mars à 15h00", "See you on 15 March at 15:00"),
    ("Horaires : 7j/7 de 8h à 2h du matin", "Available 7 days a week, 08:00 to 02:00"),
] + _HYBRIDE_EXAMPLES
_EN_CONTAINS = [
    ("Depuis le lancement de l'EuroMillions le 15 mars", "Since the EuroMillions launch on 15 March, "),
    ("Le lancement public d'EuroMillions approche", "<strong>15 March at 15:00</strong>!"),
    ("<strong>LotoIA s'agrandit !</strong>", "<strong>15 March at 15:00</strong>."),
]


@pytest.mark.parametrize("msgid,msgstr", _EN_EXACT)
def test_en_po_exact_msgstr(msgid, msgstr):
    msg = _en_catalog().get(msgid)
    assert msg is not None, msgid
    assert msg.string == msgstr
    assert not msg.fuzzy


@pytest.mark.parametrize("prefix,fragment", _EN_CONTAINS)
def test_en_po_body_msgstr(prefix, fragment):
    msgs = [m for m in _en_catalog() if isinstance(m.id, str) and m.id.startswith(prefix)]
    assert len(msgs) == 1, prefix
    assert fragment in msgs[0].string
    assert not msgs[0].fuzzy


def test_en_po_no_us_dates_or_ampm():
    bad = re.compile(r"March 15|March 30,|April 27,|3:00 PM|\b8am\b|\b\d{1,2}(:\d{2})? ?(AM|PM)\b"
                     r"|\b(January|February|March|April|May|June|July|August|September|October|November|December)"
                     r" \d{1,2}(st|nd|rd|th)?, \d{4}")
    hits = [(m.id, m.string) for m in _en_catalog() if isinstance(m.string, str) and bad.search(m.string)]
    assert not hits, hits


def test_en_hybride_page_has_no_french_example():
    """/en/euromillions/hybride : les 9 exemples sont traduits (D11 + D13).

    Méthode : en.po compilé EN MÉMOIRE (babel read_po → write_mo) puis rendu réel du gabarit
    em/hybride.html en EN avec ce catalogue — indépendant d'un .mo local périmé (non suivi par git,
    compilé au build par Dockerfile:17).
    """
    from babel.messages.mofile import write_mo
    from config import templates as tpl_mod

    buf = io.BytesIO()
    write_mo(buf, _en_catalog())
    buf.seek(0)
    en_trans = gettext.GNUTranslations(buf)
    real = tpl_mod.get_translations

    req = MagicMock()
    req.url.path = "/en/euromillions/hybride"
    req.query_params = {}
    req.cookies = {}
    req.headers = {}
    with patch.object(tpl_mod, "get_translations", lambda lang: en_trans if lang == "en" else real(lang)):
        resp = tpl_mod.render_template(
            "em/hybride.html", req, lang="en", page_key="hybride_page",
            body_class="subpage em-page", include_nav_scroll=True, hero_icon="\U0001f916",
            hero_title="HYBRIDE", hero_subtitle="HYBRIDE", em_db_total=729,
        )
    html = resp.body.decode("utf-8")
    assert 'lang="en"' in html
    for fr, en in _HYBRIDE_EXAMPLES:
        # le gabarit échappe " et ' (autoescape) : on compare le cœur de la phrase, sans guillemets ni apostrophe
        fr_core = max(re.split(r"[\"']", fr.strip('"')), key=len)
        en_core = max(re.split(r"[\"']", en.strip('"')), key=len)
        assert fr_core not in html, fr
        assert en_core in html, en
