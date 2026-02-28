"""
JS i18n labels for EuroMillions frontend.
P3/5 — single source of truth for all JS-rendered strings.
Injected as window.LotoIA_i18n via Jinja2.
"""

from __future__ import annotations

_LABELS: dict[str, dict[str, str]] = {
    "fr": {
        # ── Locale ──
        "locale": "fr-FR",

        # ── app-em — errors / API ──
        "api_error": "Erreur API",
        "http_error": "Erreur HTTP ",
        "error_generating": "Erreur lors de la g\u00e9n\u00e9ration des grilles.",
        "unable_generate": "Impossible de g\u00e9n\u00e9rer les grilles. ",
        "select_date": "Veuillez s\u00e9lectionner une date de tirage.",
        "draw_days_only": "L'EuroMillions est tir\u00e9 uniquement les mardis et vendredis.",
        "no_draw_msg": "Pas de tirage EuroMillions ce jour. Prochain tirage : ",

        # ── app-em — display ──
        "draws_suffix": " tirages analyses",
        "data_depth_from": "de ",
        "data_depth_to": " a ",
        "grids_for": "Grilles EuroMillions pour le ",
        "grids_generated": " grille(s) g\u00e9n\u00e9r\u00e9e(s)",
        "result_title": "Analyse du tirage",

        # ── app-em — grid cards ──
        "profile_balanced": "Profil \u00e9quilibr\u00e9",
        "profile_hot": "Profil chaud",
        "profile_mixed": "Profil mixte",
        "grid_label": "Grille",
        "profile_label": "Profil",
        "pitch_loading": "HYBRIDE EM analyse ta grille\u2026",

        # ── app-em — footer ──
        "reminder_title": "Rappel important :",
        "reminder_text": "Ces grilles sont g\u00e9n\u00e9r\u00e9es \u00e0 partir de statistiques historiques. L'EuroMillions est un jeu de hasard et aucune m\u00e9thode ne garantit de gains.",
        "play_responsible": "Jouez responsable : ",
        "gambling_url": "https://www.joueurs-info-service.fr",
        "gambling_name": "Joueurs Info Service",

        # ── app-em — popup title template ──
        "popup_gen_title": "Simulation de {n} grille{s} optimis\u00e9e{s} EM",

        # ── simulateur-em ──
        "based_on_draws": "Base sur {n} tirages officiels EuroMillions",
        "heat_title_freq": "Fr\u00e9quence: ",
        "heat_title_last": " | Dernier: ",
        "analyzing_grid": "Analyse de votre grille EuroMillions en cours",
        "generating_one": "Simulation d'une grille optimis\u00e9e EM...",

        # convergence
        "convergence_strong": "Forte convergence",
        "convergence_moderate": "Convergence moderee",
        "convergence_intermediate": "Convergence intermediaire",
        "convergence_partial": "Convergence partielle",

        # detail labels
        "detail_even_odd": "Pair / Impair",
        "detail_low_high": "Bas / Haut",
        "detail_sum": "Somme",
        "detail_spread": "Dispersion",
        "detail_runs": "Suites",
        "detail_compliance": "Conformit\u00e9",

        # history
        "history_appeared": "\U0001f4dc Cette combinaison est deja sortie <strong>{n} fois</strong>",
        "history_never": "\U0001f50e Cette combinaison n'est jamais apparue dans l'historique.",
        "history_best": "\U0001f9e0 Meilleure correspondance : <strong>{n} num\u00e9ro{s} identique{s}</strong>",

        # ── sponsor-popup-em ──
        "sponsor1_desc": "Restauration photo artisanale",
        "sponsor1_badge": "Propuls\u00e9 par",
        "sponsor2_name": "Votre marque ici",
        "sponsor2_desc": "Audience forte \u2022 trafic qualifi\u00e9",
        "sponsor2_badge": "Avec le soutien de",
        "console_title": "MOTEUR HYBRIDE EM",
        "system_ready": "Syst\u00e8me pr\u00eat",
        "sponsors_header": "Partenaires",
        "timer_label": "secondes",
        "cancel_btn": "Annuler",
        "popup_default_title": "HYBRIDE EM - Analyse en cours...",

        # console logs (sponsor-popup-em)
        "log_init": "> Initialisation HYBRIDE_EM_V1...",
        "log_connection": "\u2713 Connexion moteur OK (142ms)",
        "log_loading_db": "> Chargement base de donn\u00e9es EuroMillions...",
        "log_draws_loaded": " tirages EuroMillions charg\u00e9s (387ms)",
        "log_freq": "\U0001f4ca Analyse fr\u00e9quences 5 num\u00e9ros + 2 \u00e9toiles... ",
        "log_european": "\U0001f30d Croisement donn\u00e9es europ\u00e9ennes... ",
        "log_star_optim": "\u2b50 Optimisation \u00e9toiles... ",
        "log_balance": "\u2696\ufe0f \u00c9quilibrage pair/impair... ",
        "log_spread_multi": "\U0001f4cf Calcul dispersion multi-pays... ",
        "log_constraints": "\u23f3 Application contraintes soft... ",
        "log_gen_grids": "\u23f3 Simulation grilles optimis\u00e9es EM... ",
        "log_validating": "\u23f3 Validation scores finaux... ",
        "log_success": "\u2713 {n} grille{s} g\u00e9n\u00e9r\u00e9e{s} avec succ\u00e8s",
        "log_preparing": "> Pr\u00e9paration affichage r\u00e9sultats...",
        "log_ready": "\u2713 Pr\u00eat \u00e0 afficher",

        # ── sponsor-popup75-em ──
        "sponsor_header_single": "Partenaire",
        "video_cta": "\U0001f4fa Cet espace vid\u00e9o est disponible pour votre marque",
        "meta_window_badge": "Fen\u00eatre META ANALYSE EM",
        "popup75_default": "HYBRIDE EM - Calcul en cours...",

        # console logs 75
        "log75_init": "> Initialisation HYBRIDE EM...",
        "log75_connection": "\u2713 Connexion moteur OK (142ms)",
        "log75_loading_db": "> Chargement base de donn\u00e9es EuroMillions...",
        "log75_draws": " tirages EuroMillions analys\u00e9s",
        "log75_draws_full": " tirages EuroMillions analys\u00e9s (base compl\u00e8te)",
        "log75_freq_balls": "\u23f3 Calcul fr\u00e9quences boules (1-50)... ",
        "log75_freq_stars": "\u23f3 Calcul fr\u00e9quences \u00e9toiles (1-12)... ",
        "log75_hot": "\u23f3 D\u00e9tection patterns chauds... ",
        "log75_balance": "\u23f3 \u00c9quilibrage pair/impair... ",
        "log75_geo": "\u23f3 Calcul dispersion g\u00e9ographique... ",
        "log75_constraints": "\u23f3 Application contraintes soft... ",
        "log75_gen": "\u23f3 Simulation grilles optimis\u00e9es EM... ",
        "log75_validating": "\u23f3 Validation scores finaux... ",
        "log75_success": "\u2713 {n} grille{s} g\u00e9n\u00e9r\u00e9e{s} avec succ\u00e8s",
        "log75_preparing": "> Pr\u00e9paration affichage r\u00e9sultats...",
        "log75_ready": "\u2713 Pr\u00eat \u00e0 afficher",

        # meta final logs
        "meta_log_analysing": "Analyse 75 grilles EM...",
        "meta_log_charts": "Cr\u00e9ation graphiques...",
        "meta_log_pdf": "Rapport PDF EM...",
        "meta_log_validation": "Validation finale...",
        "meta_log_ready": "Analyse pr\u00eate.",

        # meta result popup
        "meta_result_title": "R\u00e9sultat META ANALYSE EM",
        "meta_result_subtitle": "Analyse bas\u00e9e sur 75 grilles EuroMillions simul\u00e9es",
        "meta_graph_balls": "Top 5 Boules - Convergence statistique",
        "meta_graph_stars": "Top 3 \u00c9toiles - Convergence statistique",
        "meta_src_gemini": "\U0001f9e0 Analyse Gemini enrichie",
        "meta_src_local": "\u26a0\ufe0f Analyse locale (Gemini indisponible)",
        "meta_close": "Fermer",
        "meta_download": "T\u00e9l\u00e9charger le rapport META EM",
        "meta_chart_na": "Graphique non disponible",
        "meta_pending": "Analyse avanc\u00e9e encore en cours...",
        "meta_fallback_text": "R\u00e9sultat temporairement indisponible.",
        "meta_fallback_retry": "Veuillez r\u00e9essayer dans quelques instants.",
        "meta_75_grids": "75 grilles",
        "meta_sponsor_space": "Espace disponible",
        "meta_popup_title": "META ANALYSE EM - Traitement 75 grilles",

        # PDF labor illusion steps
        "meta_anim_step1": "Analyse des cycles de sortie...",
        "meta_anim_step2": "Calcul de convergence statistique...",
        "meta_anim_step3": "Mod\u00e9lisation des probabilit\u00e9s...",
        "meta_anim_step4": "Compilation du rapport PDF...",

        # wrapper titles
        "wrapper_gen_title": "Simulation de {n} grille{s} optimis\u00e9e{s} EM",
        "wrapper_sim_title": "Analyse de votre grille EM en cours",

        # ── rating-popup ──
        "rating_prompt": "Votre avis sur LotoIA ?",
        "rating_close": "Fermer",
        "rating_thanks": "Merci !",
    },

    "en": {
        # ── Locale ──
        "locale": "en-GB",

        # ── app-em — errors / API ──
        "api_error": "API Error",
        "http_error": "HTTP Error ",
        "error_generating": "Error generating grids.",
        "unable_generate": "Unable to generate grids. ",
        "select_date": "Please select a draw date.",
        "draw_days_only": "EuroMillions draws take place on Tuesdays and Fridays only.",
        "no_draw_msg": "No EuroMillions draw on this day. Next draw: ",

        # ── app-em — display ──
        "draws_suffix": " draws analysed",
        "data_depth_from": "from ",
        "data_depth_to": " to ",
        "grids_for": "EuroMillions grids for ",
        "grids_generated": " grid(s) generated",
        "result_title": "Draw analysis",

        # ── app-em — grid cards ──
        "profile_balanced": "Balanced profile",
        "profile_hot": "Hot profile",
        "profile_mixed": "Mixed profile",
        "grid_label": "Grid",
        "profile_label": "Profile",
        "pitch_loading": "HYBRIDE EM is analysing your grid\u2026",

        # ── app-em — footer ──
        "reminder_title": "Important reminder:",
        "reminder_text": "These grids are generated from historical statistics. EuroMillions is a game of chance and no method guarantees winnings.",
        "play_responsible": "Play responsibly: ",
        "gambling_url": "https://www.begambleaware.org",
        "gambling_name": "BeGambleAware.org",

        # ── app-em — popup title template ──
        "popup_gen_title": "Simulating {n} optimised EM grid{s}",

        # ── simulateur-em ──
        "based_on_draws": "Based on {n} official EuroMillions draws",
        "heat_title_freq": "Frequency: ",
        "heat_title_last": " | Last: ",
        "analyzing_grid": "Analysing your EuroMillions grid",
        "generating_one": "Simulating an optimised EM grid...",

        # convergence
        "convergence_strong": "Strong convergence",
        "convergence_moderate": "Moderate convergence",
        "convergence_intermediate": "Intermediate convergence",
        "convergence_partial": "Partial convergence",

        # detail labels
        "detail_even_odd": "Even / Odd",
        "detail_low_high": "Low / High",
        "detail_sum": "Sum",
        "detail_spread": "Spread",
        "detail_runs": "Runs",
        "detail_compliance": "Compliance",

        # history
        "history_appeared": "\U0001f4dc This combination has appeared <strong>{n} time{s}</strong>",
        "history_never": "\U0001f50e This combination has never appeared in the draw history.",
        "history_best": "\U0001f9e0 Best match: <strong>{n} identical number{s}</strong>",

        # ── sponsor-popup-em ──
        "sponsor1_desc": "Artisan photo restoration",
        "sponsor1_badge": "Powered by",
        "sponsor2_name": "Your brand here",
        "sponsor2_desc": "High audience \u2022 qualified traffic",
        "sponsor2_badge": "Supported by",
        "console_title": "HYBRID ENGINE EM",
        "system_ready": "System ready",
        "sponsors_header": "Partners",
        "timer_label": "seconds",
        "cancel_btn": "Cancel",
        "popup_default_title": "HYBRIDE EM - Analysis in progress...",

        # console logs (sponsor-popup-em)
        "log_init": "> Initialising HYBRIDE_EM_V1...",
        "log_connection": "\u2713 Engine connection OK (142ms)",
        "log_loading_db": "> Loading EuroMillions database...",
        "log_draws_loaded": " EuroMillions draws loaded (387ms)",
        "log_freq": "\U0001f4ca Analysing frequencies 5 numbers + 2 stars... ",
        "log_european": "\U0001f30d Cross-referencing European data... ",
        "log_star_optim": "\u2b50 Optimising stars... ",
        "log_balance": "\u2696\ufe0f Balancing odd/even... ",
        "log_spread_multi": "\U0001f4cf Computing multi-country spread... ",
        "log_constraints": "\u23f3 Applying soft constraints... ",
        "log_gen_grids": "\u23f3 Simulating optimised EM grids... ",
        "log_validating": "\u23f3 Validating final scores... ",
        "log_success": "\u2713 {n} grid{s} generated successfully",
        "log_preparing": "> Preparing results display...",
        "log_ready": "\u2713 Ready to display",

        # ── sponsor-popup75-em ──
        "sponsor_header_single": "Partner",
        "video_cta": "\U0001f4fa This video space is available for your brand",
        "meta_window_badge": "META ANALYSIS EM Window",
        "popup75_default": "HYBRIDE EM - Computing...",

        # console logs 75
        "log75_init": "> Initialising HYBRIDE EM...",
        "log75_connection": "\u2713 Engine connection OK (142ms)",
        "log75_loading_db": "> Loading EuroMillions database...",
        "log75_draws": " EuroMillions draws analysed",
        "log75_draws_full": " EuroMillions draws analysed (complete database)",
        "log75_freq_balls": "\u23f3 Computing ball frequencies (1-50)... ",
        "log75_freq_stars": "\u23f3 Computing star frequencies (1-12)... ",
        "log75_hot": "\u23f3 Detecting hot patterns... ",
        "log75_balance": "\u23f3 Balancing odd/even... ",
        "log75_geo": "\u23f3 Computing geographic spread... ",
        "log75_constraints": "\u23f3 Applying soft constraints... ",
        "log75_gen": "\u23f3 Simulating optimised EM grids... ",
        "log75_validating": "\u23f3 Validating final scores... ",
        "log75_success": "\u2713 {n} grid{s} generated successfully",
        "log75_preparing": "> Preparing results display...",
        "log75_ready": "\u2713 Ready to display",

        # meta final logs
        "meta_log_analysing": "Analysing 75 EM grids...",
        "meta_log_charts": "Creating charts...",
        "meta_log_pdf": "PDF report EM...",
        "meta_log_validation": "Final validation...",
        "meta_log_ready": "Analysis ready.",

        # meta result popup
        "meta_result_title": "META ANALYSIS EM Result",
        "meta_result_subtitle": "Analysis based on 75 simulated EuroMillions grids",
        "meta_graph_balls": "Top 5 Balls - Statistical convergence",
        "meta_graph_stars": "Top 3 Stars - Statistical convergence",
        "meta_src_gemini": "\U0001f9e0 Gemini enriched analysis",
        "meta_src_local": "\u26a0\ufe0f Local analysis (Gemini unavailable)",
        "meta_close": "Close",
        "meta_download": "Download META EM report",
        "meta_chart_na": "Chart not available",
        "meta_pending": "Advanced analysis still in progress...",
        "meta_fallback_text": "Result temporarily unavailable.",
        "meta_fallback_retry": "Please try again in a few moments.",
        "meta_75_grids": "75 grids",
        "meta_sponsor_space": "Space available",
        "meta_popup_title": "META ANALYSIS EM - Processing 75 grids",

        # PDF labor illusion steps
        "meta_anim_step1": "Analysing draw cycles...",
        "meta_anim_step2": "Computing statistical convergence...",
        "meta_anim_step3": "Modelling probabilities...",
        "meta_anim_step4": "Compiling PDF report...",

        # wrapper titles
        "wrapper_gen_title": "Simulating {n} optimised EM grid{s}",
        "wrapper_sim_title": "Analysing your EM grid",

        # ── rating-popup ──
        "rating_prompt": "Rate LotoIA?",
        "rating_close": "Close",
        "rating_thanks": "Thanks!",
    },

    "es": {
        # ── Locale ──
        "locale": "es-ES",

        # ── app-em — errors / API ──
        "api_error": "Error de API",
        "http_error": "Error HTTP ",
        "error_generating": "Error al generar las combinaciones.",
        "unable_generate": "No se pueden generar las combinaciones. ",
        "select_date": "Por favor, seleccione una fecha de sorteo.",
        "draw_days_only": "EuroMillions solo se sortea los martes y viernes.",
        "no_draw_msg": "No hay sorteo de EuroMillions este día. Próximo sorteo: ",

        # ── app-em — display ──
        "draws_suffix": " sorteos analizados",
        "data_depth_from": "del ",
        "data_depth_to": " al ",
        "grids_for": "Combinaciones EuroMillions para el ",
        "grids_generated": " combinación(es) generada(s)",
        "result_title": "Análisis del sorteo",

        # ── app-em — grid cards ──
        "profile_balanced": "Perfil equilibrado",
        "profile_hot": "Perfil caliente",
        "profile_mixed": "Perfil mixto",
        "grid_label": "Combinación",
        "profile_label": "Perfil",
        "pitch_loading": "HYBRIDE EM analiza tu combinación\u2026",

        # ── app-em — footer ──
        "reminder_title": "Aviso importante:",
        "reminder_text": "Estas combinaciones se generan a partir de estadísticas históricas. EuroMillions es un juego de azar y ningún método garantiza ganancias.",
        "play_responsible": "Juega con responsabilidad: ",
        "gambling_url": "https://www.jugarbien.es",
        "gambling_name": "Jugar Bien",

        # ── app-em — popup title template ──
        "popup_gen_title": "Simulación de {n} combinación(es) optimizada{s} EM",

        # ── simulateur-em ──
        "based_on_draws": "Basado en {n} sorteos oficiales de EuroMillions",
        "heat_title_freq": "Frecuencia: ",
        "heat_title_last": " | Último: ",
        "analyzing_grid": "Analizando su combinación EuroMillions",
        "generating_one": "Simulando una combinación optimizada EM...",

        # convergence
        "convergence_strong": "Convergencia fuerte",
        "convergence_moderate": "Convergencia moderada",
        "convergence_intermediate": "Convergencia intermedia",
        "convergence_partial": "Convergencia parcial",

        # detail labels
        "detail_even_odd": "Par / Impar",
        "detail_low_high": "Bajo / Alto",
        "detail_sum": "Suma",
        "detail_spread": "Dispersión",
        "detail_runs": "Secuencias",
        "detail_compliance": "Conformidad",

        # history
        "history_appeared": "\U0001f4dc Esta combinación ya ha salido <strong>{n} vez/veces</strong>",
        "history_never": "\U0001f50e Esta combinación nunca ha aparecido en el historial.",
        "history_best": "\U0001f9e0 Mejor coincidencia: <strong>{n} número{s} idéntico{s}</strong>",

        # ── sponsor-popup-em ──
        "sponsor1_desc": "Restauración artesanal de fotografías",
        "sponsor1_badge": "Impulsado por",
        "sponsor2_name": "Su marca aquí",
        "sponsor2_desc": "Audiencia amplia \u2022 tráfico cualificado",
        "sponsor2_badge": "Con el apoyo de",
        "console_title": "MOTOR HYBRIDE EM",
        "system_ready": "Sistema listo",
        "sponsors_header": "Colaboradores",
        "timer_label": "segundos",
        "cancel_btn": "Cancelar",
        "popup_default_title": "HYBRIDE EM - Análisis en curso...",

        # console logs (sponsor-popup-em)
        "log_init": "> Inicializando HYBRIDE_EM_V1...",
        "log_connection": "\u2713 Conexión al motor OK (142ms)",
        "log_loading_db": "> Cargando base de datos EuroMillions...",
        "log_draws_loaded": " sorteos EuroMillions cargados (387ms)",
        "log_freq": "\U0001f4ca Analizando frecuencias 5 números + 2 estrellas... ",
        "log_european": "\U0001f30d Cruzando datos europeos... ",
        "log_star_optim": "\u2b50 Optimizando estrellas... ",
        "log_balance": "\u2696\ufe0f Equilibrando par/impar... ",
        "log_spread_multi": "\U0001f4cf Calculando dispersión multipaís... ",
        "log_constraints": "\u23f3 Aplicando restricciones blandas... ",
        "log_gen_grids": "\u23f3 Simulando combinaciones optimizadas EM... ",
        "log_validating": "\u23f3 Validando puntuaciones finales... ",
        "log_success": "\u2713 {n} combinación(es) generada{s} con éxito",
        "log_preparing": "> Preparando visualización de resultados...",
        "log_ready": "\u2713 Listo para mostrar",

        # ── sponsor-popup75-em ──
        "sponsor_header_single": "Colaborador",
        "video_cta": "\U0001f4fa Este espacio de vídeo está disponible para su marca",
        "meta_window_badge": "Ventana META ANÁLISIS EM",
        "popup75_default": "HYBRIDE EM - Calculando...",

        # console logs 75
        "log75_init": "> Inicializando HYBRIDE EM...",
        "log75_connection": "\u2713 Conexión al motor OK (142ms)",
        "log75_loading_db": "> Cargando base de datos EuroMillions...",
        "log75_draws": " sorteos EuroMillions analizados",
        "log75_draws_full": " sorteos EuroMillions analizados (base completa)",
        "log75_freq_balls": "\u23f3 Calculando frecuencias de bolas (1-50)... ",
        "log75_freq_stars": "\u23f3 Calculando frecuencias de estrellas (1-12)... ",
        "log75_hot": "\u23f3 Detectando patrones calientes... ",
        "log75_balance": "\u23f3 Equilibrando par/impar... ",
        "log75_geo": "\u23f3 Calculando dispersión geográfica... ",
        "log75_constraints": "\u23f3 Aplicando restricciones blandas... ",
        "log75_gen": "\u23f3 Simulando combinaciones optimizadas EM... ",
        "log75_validating": "\u23f3 Validando puntuaciones finales... ",
        "log75_success": "\u2713 {n} combinación(es) generada{s} con éxito",
        "log75_preparing": "> Preparando visualización de resultados...",
        "log75_ready": "\u2713 Listo para mostrar",

        # meta final logs
        "meta_log_analysing": "Analizando 75 combinaciones EM...",
        "meta_log_charts": "Creando gráficos...",
        "meta_log_pdf": "Informe PDF EM...",
        "meta_log_validation": "Validación final...",
        "meta_log_ready": "Análisis listo.",

        # meta result popup
        "meta_result_title": "Resultado META ANÁLISIS EM",
        "meta_result_subtitle": "Análisis basado en 75 combinaciones EuroMillions simuladas",
        "meta_graph_balls": "Top 5 Bolas - Convergencia estadística",
        "meta_graph_stars": "Top 3 Estrellas - Convergencia estadística",
        "meta_src_gemini": "\U0001f9e0 Análisis enriquecido Gemini",
        "meta_src_local": "\u26a0\ufe0f Análisis local (Gemini no disponible)",
        "meta_close": "Cerrar",
        "meta_download": "Descargar informe META EM",
        "meta_chart_na": "Gráfico no disponible",
        "meta_pending": "Análisis avanzado aún en curso...",
        "meta_fallback_text": "Resultado temporalmente no disponible.",
        "meta_fallback_retry": "Por favor, inténtelo de nuevo en unos instantes.",
        "meta_75_grids": "75 combinaciones",
        "meta_sponsor_space": "Espacio disponible",
        "meta_popup_title": "META ANÁLISIS EM - Procesando 75 combinaciones",

        # PDF labor illusion steps
        "meta_anim_step1": "Analizando los ciclos de sorteo...",
        "meta_anim_step2": "Calculando la convergencia estadística...",
        "meta_anim_step3": "Modelizando las probabilidades...",
        "meta_anim_step4": "Compilando el informe PDF...",

        # wrapper titles
        "wrapper_gen_title": "Simulación de {n} combinación(es) optimizada{s} EM",
        "wrapper_sim_title": "Analizando su combinación EM",

        # ── rating-popup ──
        "rating_prompt": "¿Tu opinión sobre LotoIA?",
        "rating_close": "Cerrar",
        "rating_thanks": "¡Gracias!",
    },
}


def get_js_labels(lang: str) -> dict[str, str]:
    """Return the JS i18n dict for the given language."""
    return _LABELS.get(lang, _LABELS["fr"])
