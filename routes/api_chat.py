import os
import re
import logging
import httpx
from datetime import date, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import json as json_mod

from schemas import HybrideChatRequest, HybrideChatResponse, PitchGrillesRequest
from services.prompt_loader import load_prompt
from services.gemini import GEMINI_MODEL_URL
from rate_limit import limiter
from services.stats_service import (
    get_numero_stats, analyze_grille_for_chat,
    get_classement_numeros, get_comparaison_numeros, get_numeros_par_categorie,
    prepare_grilles_pitch_context,
)
import db_cloudsql

logger = logging.getLogger(__name__)

router = APIRouter()

FALLBACK_RESPONSE = (
    "\U0001f916 Je suis momentan\u00e9ment indisponible. "
    "R\u00e9essaie dans quelques secondes ou consulte la FAQ !"
)

META_KEYWORDS = ["meta", "algorithme", "moteur", "pond\u00e9ration", "ponderation"]


def _detect_mode(message: str, page: str) -> str:
    lower = message.lower()
    for kw in META_KEYWORDS:
        if kw in lower:
            return "meta"
    if page in ("simulateur", "loto", "statistiques"):
        return "analyse"
    return "decouverte"


def _detect_prochain_tirage(message: str) -> bool:
    """Detecte si l'utilisateur demande la date du prochain tirage."""
    lower = message.lower()
    return bool(re.search(
        r'(?:prochain|prochaine|quand|date)\s+.*(?:tirage|loto|draw)'
        r'|(?:tirage|loto)\s+.*(?:prochain|prochaine|quand|date)'
        r'|c.est\s+quand\s+(?:le\s+)?(?:prochain\s+)?(?:tirage|loto)'
        r'|(?:il\s+(?:y\s+a|est)\s+(?:un\s+)?tirage\s+quand)'
        r'|(?:quand\s+(?:est|a)\s+lieu)'
        r'|(?:prochain\s+(?:tirage|loto))',
        lower
    ))


# Jours de tirage FDJ : lundi (0), mercredi (2), samedi (5)
_JOURS_TIRAGE = [0, 2, 5]

_JOURS_FR = {
    0: "lundi", 1: "mardi", 2: "mercredi", 3: "jeudi",
    4: "vendredi", 5: "samedi", 6: "dimanche",
}


def _get_prochain_tirage() -> str | None:
    """
    Calcule la date du prochain tirage a partir de la date du jour
    et des jours de tirage FDJ (lundi, mercredi, samedi).
    Returns: contexte formate ou None si erreur.
    """
    try:
        today = date.today()

        # Chercher le prochain jour de tirage (y compris aujourd'hui)
        for delta in range(7):
            candidate = today + timedelta(days=delta)
            if candidate.weekday() in _JOURS_TIRAGE:
                next_draw = candidate
                break

        jour_fr = _JOURS_FR[next_draw.weekday()]
        date_str = next_draw.strftime("%d/%m/%Y")

        if next_draw == today:
            quand = "ce soir"
        elif next_draw == today + timedelta(days=1):
            quand = "demain soir"
        else:
            quand = f"{jour_fr} prochain"

        # Dernier tirage en BDD
        try:
            conn = db_cloudsql.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT MAX(date_de_tirage) as last FROM tirages")
                row = cursor.fetchone()
                last_draw = str(row['last']) if row and row['last'] else None
            finally:
                conn.close()
        except Exception:
            last_draw = None

        lines = [f"[PROCHAIN TIRAGE]"]
        lines.append(f"Date du prochain tirage : {jour_fr} {date_str} ({quand})")
        lines.append(f"Jours de tirage FDJ : lundi, mercredi et samedi")
        if last_draw:
            lines.append(f"Dernier tirage en base : {last_draw}")

        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"[HYBRIDE CHAT] Erreur calcul prochain tirage: {e}")
        return None


def _detect_numero(message: str):
    """
    Detecte si l'utilisateur pose une question sur un numero specifique.
    Returns: (numero: int, type_num: str) ou (None, None)
    """
    lower = message.lower()

    # Pattern chance : "numero chance X", "chance X"
    m = re.search(r'(?:num[eé]ro\s+)?chance\s+(\d{1,2})', lower)
    if m:
        num = int(m.group(1))
        if 1 <= num <= 10:
            return num, "chance"

    # Patterns principal :
    patterns = [
        r'(?:le\s+)?num[eé]ro\s+(\d{1,2})(?:\s|$|[?.!,])',
        r'(?:fr[eé]quence|[eé]cart|retard|sortie?|chaud|froid)\s+(?:du\s+)?(\d{1,2})(?:\s|$|[?.!,])',
        r'\ble\s+(\d{1,2})\s+(?:est|il|a\s|sort|[eé]tai)',
        r'\ble\s+(\d{1,2})\s*[?.!]',
        r'(?:combien|quand|sorti).*\ble\s+(\d{1,2})(?:\s|$|[?.!,])',
        r'\bdu\s+(\d{1,2})\s*[?.!]',
        r'\bboule\s+(\d{1,2})(?:\s|$|[?.!,])',
    ]

    for pattern in patterns:
        m = re.search(pattern, lower)
        if m:
            num = int(m.group(1))
            if 1 <= num <= 49:
                return num, "principal"

    return None, None


def _format_stats_context(stats: dict) -> str:
    """
    Formate les stats d'un numero en bloc de contexte pour Gemini.
    """
    type_label = "principal" if stats["type"] == "principal" else "chance"
    cat = stats["categorie"].upper()
    classement_sur = stats.get("classement_sur", 49)

    return (
        f"[DONN\u00c9ES TEMPS R\u00c9EL - Num\u00e9ro {type_label} {stats['numero']}]\n"
        f"Fr\u00e9quence totale : {stats['frequence_totale']} apparitions "
        f"sur {stats['total_tirages']} tirages ({stats['pourcentage_apparition']})\n"
        f"Derni\u00e8re sortie : {stats['derniere_sortie']}\n"
        f"\u00c9cart actuel : {stats['ecart_actuel']} tirages\n"
        f"\u00c9cart moyen : {stats['ecart_moyen']} tirages\n"
        f"Classement fr\u00e9quence : {stats['classement']}e sur {classement_sur}\n"
        f"Cat\u00e9gorie : {cat}\n"
        f"P\u00e9riode analys\u00e9e : {stats['periode']}"
    )


def _detect_grille(message: str):
    """
    Detecte si l'utilisateur fournit une grille de 5 numeros (+ chance optionnel).
    Returns: (numeros: list[int], chance: int|None) ou (None, None)
    """
    text = message.lower()

    # Extraire le numero chance d'abord (et le retirer du texte)
    chance = None
    chance_patterns = [
        r'chance\s*[:\s]*(\d{1,2})',
        r'n[°o]?\s*chance\s*[:\s]*(\d{1,2})',
        r'\+\s*(\d{1,2})\s*$',
    ]
    for pat in chance_patterns:
        m = re.search(pat, text)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 10:
                chance = val
                text = text[:m.start()] + text[m.end():]
                break

    # Extraire tous les nombres du message (1-2 chiffres)
    all_numbers = [int(x) for x in re.findall(r'\b(\d{1,2})\b', text)]

    # Filtrer : garder uniquement ceux entre 1 et 49
    valid_nums = [n for n in all_numbers if 1 <= n <= 49]

    # Eliminer les doublons en preservant l'ordre
    seen = set()
    unique_nums = []
    for n in valid_nums:
        if n not in seen:
            seen.add(n)
            unique_nums.append(n)

    # Il faut exactement 5 numeros uniques
    if len(unique_nums) != 5:
        return None, None

    return unique_nums, chance


def _format_grille_context(result: dict) -> str:
    """
    Formate l'analyse de grille en bloc de contexte pour Gemini.
    """
    nums = result["numeros"]
    chance = result["chance"]
    a = result["analyse"]
    h = result["historique"]

    # En-tete
    nums_str = " ".join(str(n) for n in nums)
    chance_str = f" (chance: {chance})" if chance else ""
    lines = [f"[ANALYSE DE GRILLE - {nums_str}{chance_str}]"]

    # Metriques
    ok = lambda b: "\u2713" if b else "\u2717"
    lines.append(f"Somme : {a['somme']} (id\u00e9al : 100-140) {ok(a['somme_ok'])}")
    lines.append(f"Pairs : {a['pairs']} / Impairs : {a['impairs']} {ok(a['equilibre_pair_impair'])}")
    lines.append(f"Bas (1-24) : {a['bas']} / Hauts (25-49) : {a['hauts']} {ok(a['equilibre_bas_haut'])}")
    lines.append(f"Dispersion : {a['dispersion']} (id\u00e9al : >= 15) {ok(a['dispersion_ok'])}")
    lines.append(f"Cons\u00e9cutifs : {a['consecutifs']} {ok(a['consecutifs'] <= 2)}")

    # Chaud/froid
    if a['numeros_chauds']:
        lines.append(f"Num\u00e9ros chauds : {', '.join(str(n) for n in a['numeros_chauds'])}")
    if a['numeros_froids']:
        lines.append(f"Num\u00e9ros froids : {', '.join(str(n) for n in a['numeros_froids'])}")
    if a['numeros_neutres']:
        lines.append(f"Num\u00e9ros neutres : {', '.join(str(n) for n in a['numeros_neutres'])}")

    lines.append(f"Conformit\u00e9 : {a['conformite_pct']}%")
    lines.append(f"Badges : {', '.join(a['badges'])}")

    # Historique
    if h['deja_sortie']:
        lines.append(f"Historique : combinaison d\u00e9j\u00e0 sortie le {', '.join(h['exact_dates'])}")
    else:
        mc = h['meilleure_correspondance']
        if mc['nb_numeros_communs'] > 0:
            communs = ', '.join(str(n) for n in mc['numeros_communs'])
            lines.append(
                f"Historique : jamais sortie. Meilleure correspondance : "
                f"{mc['nb_numeros_communs']} num\u00e9ros communs le {mc['date']} ({communs})"
            )
        else:
            lines.append("Historique : combinaison jamais sortie")

    return "\n".join(lines)


def _detect_requete_complexe(message: str):
    """
    Detecte les requetes complexes : classements, comparaisons, categories.
    Returns: dict d'intention ou None.
    """
    lower = message.lower()

    # --- Comparaison : "compare le 7 et le 23", "7 vs 23", "difference entre 7 et 23" ---
    comp_patterns = [
        r'compar\w*\s+(?:le\s+)?(\d{1,2})\s+(?:et|avec|vs\.?)\s+(?:le\s+)?(\d{1,2})',
        r'(\d{1,2})\s+vs\.?\s+(\d{1,2})',
        r'diff[eé]rence\s+entre\s+(?:le\s+)?(\d{1,2})\s+et\s+(?:le\s+)?(\d{1,2})',
        r'entre\s+(?:le\s+)?(\d{1,2})\s+et\s+(?:le\s+)?(\d{1,2})\s.*(?:lequel|qui)',
    ]
    for pat in comp_patterns:
        m = re.search(pat, lower)
        if m:
            n1, n2 = int(m.group(1)), int(m.group(2))
            is_chance = "chance" in lower
            if is_chance and 1 <= n1 <= 10 and 1 <= n2 <= 10:
                return {"type": "comparaison", "num1": n1, "num2": n2, "num_type": "chance"}
            if 1 <= n1 <= 49 and 1 <= n2 <= 49 and n1 != n2:
                return {"type": "comparaison", "num1": n1, "num2": n2, "num_type": "principal"}

    # --- Categorie chaud/froid ---
    if re.search(r'(?:quels?|les?|num[eé]ros?)\s+.*chauds?', lower) or \
       re.search(r'chauds?\s+(?:en ce moment|actuellement)', lower) or \
       re.search(r'(?:num[eé]ros?|lesquels)\s+(?:sont|en)\s+tendance', lower):
        num_type = "chance" if "chance" in lower else "principal"
        return {"type": "categorie", "categorie": "chaud", "num_type": num_type}

    if re.search(r'(?:quels?|les?|num[eé]ros?)\s+.*froids?', lower) or \
       re.search(r'froids?\s+(?:en ce moment|actuellement)', lower) or \
       re.search(r'num[eé]ros?\s+(?:en\s+retard|qui\s+sort\w*\s+(?:pas|plus|jamais))', lower):
        num_type = "chance" if "chance" in lower else "principal"
        return {"type": "categorie", "categorie": "froid", "num_type": num_type}

    # --- Classement : top/plus frequents/retards ---
    # Extraire le limit (top N)
    limit_match = re.search(r'top\s+(\d{1,2})', lower)
    limit = int(limit_match.group(1)) if limit_match else 5
    limit = min(limit, 15)

    num_type = "chance" if "chance" in lower else "principal"

    # Plus frequents / plus sortis
    if re.search(r'(?:plus|les?\s+plus)\s+(?:fr[eé]quent|sorti|courant|pr[eé]sent)', lower) or \
       re.search(r'(?:top|meilleur|premier)\s+\d{0,2}\s*(?:num[eé]ro|boule|chance)?', lower) or \
       re.search(r'num[eé]ros?\s+(?:les?\s+)?plus\s+(?:sorti|fr[eé]quent)', lower) or \
       re.search(r'(?:quels?|quel)\s+(?:est|sont)\s+(?:le|les)\s+num[eé]ro', lower):
        return {"type": "classement", "tri": "frequence_desc", "limit": limit, "num_type": num_type}

    # Moins frequents / moins sortis
    if re.search(r'(?:moins|les?\s+moins)\s+(?:fr[eé]quent|sorti|courant)', lower) or \
       re.search(r'(?:flop|dernier|pire)\s+\d{0,2}', lower):
        return {"type": "classement", "tri": "frequence_asc", "limit": limit, "num_type": num_type}

    # Plus gros ecarts / retards
    if re.search(r'(?:plus\s+(?:gros|grand|long)|plus\s+en)\s+(?:[eé]cart|retard)', lower) or \
       re.search(r'(?:[eé]cart|retard)\s+(?:les?\s+)?plus\s+(?:gros|grand|long|important)', lower) or \
       re.search(r'(?:plus\s+(?:long|grand)temps?)\s+(?:sans\s+)?sort', lower):
        return {"type": "classement", "tri": "ecart_desc", "limit": limit, "num_type": num_type}

    # Plus petits ecarts (sortis recemment)
    if re.search(r'(?:plus\s+(?:petit|court))\s+(?:[eé]cart|retard)', lower) or \
       re.search(r'(?:sorti|apparu)\s+(?:le\s+plus\s+)?r[eé]cemment', lower):
        return {"type": "classement", "tri": "ecart_asc", "limit": limit, "num_type": num_type}

    return None


def _format_complex_context(intent: dict, data) -> str:
    """
    Formate le resultat d'une requete complexe en contexte pour Gemini.
    """
    if intent["type"] == "classement":
        tri_labels = {
            "frequence_desc": "les plus fr\u00e9quents",
            "frequence_asc": "les moins fr\u00e9quents",
            "ecart_desc": "les plus en retard",
            "ecart_asc": "sortis le plus r\u00e9cemment",
        }
        label = tri_labels.get(intent["tri"], intent["tri"])
        limit = intent["limit"]
        type_label = "chance" if intent["num_type"] == "chance" else "principaux"

        lines = [f"[CLASSEMENT - Top {limit} num\u00e9ros {type_label} {label}]"]
        for i, item in enumerate(data["items"], 1):
            cat = item["categorie"].upper()
            lines.append(
                f"{i}. Num\u00e9ro {item['numero']} : "
                f"{item['frequence']} apparitions "
                f"(\u00e9cart actuel : {item['ecart_actuel']}) — {cat}"
            )
        lines.append(
            f"Total tirages analys\u00e9s : {data['total_tirages']} | "
            f"P\u00e9riode : {data['periode']}"
        )
        return "\n".join(lines)

    elif intent["type"] == "comparaison":
        s1 = data["num1"]
        s2 = data["num2"]
        diff = data["diff_frequence"]
        sign = "+" if diff > 0 else ""

        lines = [f"[COMPARAISON - Num\u00e9ro {s1['numero']} vs Num\u00e9ro {s2['numero']}]"]
        lines.append(
            f"Num\u00e9ro {s1['numero']} : {s1['frequence_totale']} apparitions "
            f"({s1['pourcentage_apparition']}) | \u00c9cart : {s1['ecart_actuel']} | "
            f"Cat\u00e9gorie : {s1['categorie'].upper()}"
        )
        lines.append(
            f"Num\u00e9ro {s2['numero']} : {s2['frequence_totale']} apparitions "
            f"({s2['pourcentage_apparition']}) | \u00c9cart : {s2['ecart_actuel']} | "
            f"Cat\u00e9gorie : {s2['categorie'].upper()}"
        )
        if diff != 0:
            favori = data["favori_frequence"]
            lines.append(
                f"Diff\u00e9rence de fr\u00e9quence : {sign}{diff} apparitions "
                f"en faveur du {favori}"
            )
        else:
            lines.append("Fr\u00e9quences identiques")
        return "\n".join(lines)

    elif intent["type"] == "categorie":
        cat = data["categorie"].upper()
        nums_list = [str(item["numero"]) for item in data["numeros"]]

        lines = [f"[NUM\u00c9ROS {cat}S - {data['count']} num\u00e9ros sur {data['periode_analyse']}]"]
        lines.append(f"Num\u00e9ros : {', '.join(nums_list)}")
        lines.append(f"Bas\u00e9 sur les tirages des {data['periode_analyse']}")
        return "\n".join(lines)

    return ""


# =========================
# HYBRIDE Chatbot — Gemini 2.0 Flash
# =========================

@router.post("/api/hybride-chat")
@limiter.limit("10/minute")
async def api_hybride_chat(request: Request, payload: HybrideChatRequest):
    """Endpoint chatbot HYBRIDE — conversation via Gemini 2.0 Flash."""

    mode = _detect_mode(payload.message, payload.page)

    # Charger le prompt systeme
    system_prompt = load_prompt("CHATBOT")
    if not system_prompt:
        logger.error("[HYBRIDE CHAT] Prompt systeme introuvable")
        return HybrideChatResponse(
            response=FALLBACK_RESPONSE, source="fallback", mode=mode
        )

    # Cle API
    gem_api_key = os.environ.get("GEM_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not gem_api_key:
        logger.warning("[HYBRIDE CHAT] GEM_API_KEY non configuree — fallback")
        return HybrideChatResponse(
            response=FALLBACK_RESPONSE, source="fallback", mode=mode
        )

    # Construire les contents (historique + message actuel)
    contents = []

    # Historique (max 20 derniers messages) + garde anti-doublon
    history = (payload.history or [])[-20:]
    if history and history[-1].role == "user" and history[-1].content == payload.message:
        history = history[:-1]

    for msg in history:
        role = "user" if msg.role == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg.content}]})

    # Detection : Prochain tirage → Grille (Phase 2) → Complexe (Phase 3) → Numero (Phase 1)
    enrichment_context = ""

    # Phase 0 : prochain tirage
    if _detect_prochain_tirage(payload.message):
        try:
            tirage_ctx = _get_prochain_tirage()
            if tirage_ctx:
                enrichment_context = tirage_ctx
                logger.info("[HYBRIDE CHAT] Prochain tirage injecte")
        except Exception as e:
            logger.warning(f"[HYBRIDE CHAT] Erreur prochain tirage: {e}")

    # Phase 2 : detection de grille (5 numeros)
    grille_nums, grille_chance = _detect_grille(payload.message)
    if grille_nums is not None:
        try:
            grille_result = analyze_grille_for_chat(grille_nums, grille_chance)
            if grille_result:
                enrichment_context = _format_grille_context(grille_result)
                logger.info(f"[HYBRIDE CHAT] Grille analysee: {grille_nums} chance={grille_chance}")
        except Exception as e:
            logger.warning(f"[HYBRIDE CHAT] Erreur analyse grille: {e}")

    # Phase 3 : requete complexe (classement, comparaison, categorie)
    if not enrichment_context:
        intent = _detect_requete_complexe(payload.message)
        if intent:
            try:
                if intent["type"] == "classement":
                    data = get_classement_numeros(intent["num_type"], intent["tri"], intent["limit"])
                elif intent["type"] == "comparaison":
                    data = get_comparaison_numeros(intent["num1"], intent["num2"], intent["num_type"])
                elif intent["type"] == "categorie":
                    data = get_numeros_par_categorie(intent["categorie"], intent["num_type"])
                else:
                    data = None

                if data:
                    enrichment_context = _format_complex_context(intent, data)
                    logger.info(f"[HYBRIDE CHAT] Requete complexe: {intent['type']}")
            except Exception as e:
                logger.warning(f"[HYBRIDE CHAT] Erreur requete complexe: {e}")

    # Phase 1 : detection de numero simple
    if not enrichment_context:
        numero, type_num = _detect_numero(payload.message)
        if numero is not None:
            try:
                stats = get_numero_stats(numero, type_num)
                if stats:
                    enrichment_context = _format_stats_context(stats)
                    logger.info(f"[HYBRIDE CHAT] Stats BDD injectees: numero={numero}, type={type_num}")
            except Exception as e:
                logger.warning(f"[HYBRIDE CHAT] Erreur stats BDD (numero={numero}): {e}")

    # Message utilisateur avec contexte de page + donnees BDD
    if enrichment_context:
        user_text = f"[Page: {payload.page}]\n\n{enrichment_context}\n\n[Question utilisateur] {payload.message}"
    else:
        user_text = f"[Page: {payload.page}] {payload.message}"
    contents.append({"role": "user", "parts": [{"text": user_text}]})

    try:
        client = request.app.state.httpx_client
        response = await client.post(
            GEMINI_MODEL_URL,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": gem_api_key,
            },
            json={
                "system_instruction": {
                    "parts": [{"text": system_prompt}]
                },
                "contents": contents,
                "generationConfig": {
                    "temperature": 0.8,
                    "maxOutputTokens": 300,
                },
            },
            timeout=15.0,
        )

        if response.status_code == 200:
            data = response.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    text = parts[0].get("text", "").strip()
                    if text:
                        logger.info(
                            f"[HYBRIDE CHAT] OK (page={payload.page}, mode={mode})"
                        )
                        return HybrideChatResponse(
                            response=text, source="gemini", mode=mode
                        )

        logger.warning(
            f"[HYBRIDE CHAT] Reponse Gemini invalide: {response.status_code}"
        )
        return HybrideChatResponse(
            response=FALLBACK_RESPONSE, source="fallback", mode=mode
        )

    except httpx.TimeoutException:
        logger.warning("[HYBRIDE CHAT] Timeout Gemini (15s) — fallback")
        return HybrideChatResponse(
            response=FALLBACK_RESPONSE, source="fallback", mode=mode
        )
    except Exception as e:
        logger.error(f"[HYBRIDE CHAT] Erreur Gemini: {e}")
        return HybrideChatResponse(
            response=FALLBACK_RESPONSE, source="fallback", mode=mode
        )


# =========================
# PITCH GRILLES — Gemini
# =========================

@router.post("/api/pitch-grilles")
@limiter.limit("10/minute")
async def api_pitch_grilles(request: Request, payload: PitchGrillesRequest):
    """Genere des pitchs HYBRIDE personnalises pour chaque grille via Gemini."""

    # Validation
    if not payload.grilles or len(payload.grilles) > 5:
        return JSONResponse(status_code=400, content={
            "success": False, "data": None, "error": "Entre 1 et 5 grilles requises"
        })

    for i, g in enumerate(payload.grilles):
        if len(g.numeros) != 5:
            return JSONResponse(status_code=400, content={
                "success": False, "data": None, "error": f"Grille {i+1}: 5 num\u00e9ros requis"
            })
        if len(set(g.numeros)) != 5:
            return JSONResponse(status_code=400, content={
                "success": False, "data": None, "error": f"Grille {i+1}: num\u00e9ros doivent \u00eatre uniques"
            })
        if not all(1 <= n <= 49 for n in g.numeros):
            return JSONResponse(status_code=400, content={
                "success": False, "data": None, "error": f"Grille {i+1}: num\u00e9ros entre 1 et 49"
            })
        if g.chance is not None and not 1 <= g.chance <= 10:
            return JSONResponse(status_code=400, content={
                "success": False, "data": None, "error": f"Grille {i+1}: chance entre 1 et 10"
            })

    # Preparer le contexte stats
    grilles_data = [{"numeros": g.numeros, "chance": g.chance} for g in payload.grilles]

    try:
        context = prepare_grilles_pitch_context(grilles_data)
    except Exception as e:
        logger.warning(f"[PITCH] Erreur contexte stats: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "data": None, "error": "Erreur donn\u00e9es statistiques"
        })

    if not context:
        return JSONResponse(status_code=500, content={
            "success": False, "data": None, "error": "Impossible de pr\u00e9parer le contexte"
        })

    # Charger le prompt
    system_prompt = load_prompt("PITCH_GRILLE")
    if not system_prompt:
        logger.error("[PITCH] Prompt pitch introuvable")
        return JSONResponse(status_code=500, content={
            "success": False, "data": None, "error": "Prompt pitch introuvable"
        })

    # Cle API
    gem_api_key = os.environ.get("GEM_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not gem_api_key:
        return JSONResponse(status_code=500, content={
            "success": False, "data": None, "error": "API Gemini non configur\u00e9e"
        })

    # Appel Gemini (1 seul appel pour toutes les grilles)
    try:
        client = request.app.state.httpx_client
        response = await client.post(
            GEMINI_MODEL_URL,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": gem_api_key,
            },
            json={
                "system_instruction": {
                    "parts": [{"text": system_prompt}]
                },
                "contents": [{
                    "role": "user",
                    "parts": [{"text": context}]
                }],
                "generationConfig": {
                    "temperature": 0.9,
                    "maxOutputTokens": 600,
                },
            },
            timeout=15.0,
        )

        if response.status_code != 200:
            logger.warning(f"[PITCH] Gemini HTTP {response.status_code}")
            return JSONResponse(status_code=502, content={
                "success": False, "data": None, "error": f"Gemini erreur HTTP {response.status_code}"
            })

        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return JSONResponse(status_code=502, content={
                "success": False, "data": None, "error": "Gemini: aucune r\u00e9ponse"
            })

        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
        if not text:
            return JSONResponse(status_code=502, content={
                "success": False, "data": None, "error": "Gemini: r\u00e9ponse vide"
            })

        # Parser le JSON (nettoyer si Gemini ajoute des backticks)
        clean = text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
            clean = clean.strip()

        try:
            result = json_mod.loads(clean)
            pitchs = result.get("pitchs", [])
        except (json_mod.JSONDecodeError, AttributeError):
            logger.warning(f"[PITCH] JSON invalide: {text[:200]}")
            return JSONResponse(status_code=502, content={
                "success": False, "data": None, "error": "Gemini: JSON mal form\u00e9"
            })

        logger.info(f"[PITCH] OK \u2014 {len(pitchs)} pitchs g\u00e9n\u00e9r\u00e9s")
        return {"success": True, "data": {"pitchs": pitchs}, "error": None}

    except httpx.TimeoutException:
        logger.warning("[PITCH] Timeout Gemini (15s)")
        return JSONResponse(status_code=503, content={
            "success": False, "data": None, "error": "Timeout Gemini"
        })
    except Exception as e:
        logger.error(f"[PITCH] Erreur: {e}")
        return JSONResponse(status_code=500, content={
            "success": False, "data": None, "error": "Erreur interne du serveur"
        })
