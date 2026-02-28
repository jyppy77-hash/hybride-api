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
        "grid_generated_one": " grille g\u00e9n\u00e9r\u00e9e",
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
        "popup_gen_title_one": "Simulation de 1 grille optimis\u00e9e EM",

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
        "history_appeared_one": "\U0001f4dc Cette combinaison est deja sortie <strong>1 fois</strong>",
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

        # ── chatbot widget ──
        "chatbot_welcome": "Bienvenue ! Je suis HYBRIDE, l\u2019assistant IA de LotoIA \u2014 module EuroMillions. Pose-moi tes questions sur l\u2019EuroMillions, les statistiques ou le moteur HYBRIDE \uD83C\uDF1F",
        "chatbot_placeholder": "Pose ta question EuroMillions...",
        "chatbot_bubble_label": "Ouvrir le chatbot HYBRIDE EuroMillions",
        "chatbot_clear_title": "Nouvelle conversation",
        "chatbot_close_label": "Fermer",
        "chatbot_send_label": "Envoyer",

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
        "grid_generated_one": " grid generated",
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
        "popup_gen_title_one": "Simulating 1 optimised EM grid",

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
        "history_appeared_one": "\U0001f4dc This combination has appeared <strong>1 time</strong>",
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

        # ── chatbot widget ──
        "chatbot_welcome": "Welcome! I\u2019m HYBRIDE, the LotoIA AI assistant \u2014 EuroMillions module. Ask me anything about EuroMillions, statistics or the HYBRIDE engine \uD83C\uDF1F",
        "chatbot_placeholder": "Ask your EuroMillions question...",
        "chatbot_bubble_label": "Open HYBRIDE EuroMillions chatbot",
        "chatbot_clear_title": "New conversation",
        "chatbot_close_label": "Close",
        "chatbot_send_label": "Send",

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
        "grids_generated": " combinaciones generadas",
        "grid_generated_one": " combinación generada",
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
        "popup_gen_title": "Simulación de {n} combinaciones optimizada{s} EM",
        "popup_gen_title_one": "Simulación de 1 combinación optimizada EM",

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
        "history_appeared": "\U0001f4dc Esta combinación ya ha salido <strong>{n} veces</strong>",
        "history_appeared_one": "\U0001f4dc Esta combinación ya ha salido <strong>1 vez</strong>",
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
        "log_success": "\u2713 {n} combinaciones generada{s} con éxito",
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
        "log75_success": "\u2713 {n} combinaciones generada{s} con éxito",
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
        "wrapper_gen_title": "Simulación de {n} combinaciones optimizada{s} EM",
        "wrapper_sim_title": "Analizando su combinación EM",

        # ── chatbot widget ──
        "chatbot_welcome": "¡Bienvenido! Soy HYBRIDE, el asistente IA de LotoIA \u2014 módulo EuroMillions. Pregúntame lo que quieras sobre EuroMillions, estadísticas o el motor HYBRIDE \uD83C\uDF1F",
        "chatbot_placeholder": "Haz tu pregunta EuroMillions...",
        "chatbot_bubble_label": "Abrir el chatbot HYBRIDE EuroMillions",
        "chatbot_clear_title": "Nueva conversación",
        "chatbot_close_label": "Cerrar",
        "chatbot_send_label": "Enviar",

        # ── rating-popup ──
        "rating_prompt": "¿Tu opinión sobre LotoIA?",
        "rating_close": "Cerrar",
        "rating_thanks": "¡Gracias!",
    },

    "pt": {
        # ── Locale ──
        "locale": "pt-PT",

        # ── app-em — errors / API ──
        "api_error": "Erro de API",
        "http_error": "Erro HTTP ",
        "error_generating": "Erro ao gerar as combinações.",
        "unable_generate": "Não foi possível gerar as combinações. ",
        "select_date": "Por favor, selecione uma data de sorteio.",
        "draw_days_only": "O EuroMillions só é sorteado às terças e sextas-feiras.",
        "no_draw_msg": "Não há sorteio EuroMillions neste dia. Próximo sorteio: ",

        # ── app-em — display ──
        "draws_suffix": " sorteios analisados",
        "data_depth_from": "de ",
        "data_depth_to": " a ",
        "grids_for": "Combinações EuroMillions para ",
        "grids_generated": " combinações geradas",
        "grid_generated_one": " combinação gerada",
        "result_title": "Análise do sorteio",

        # ── app-em — grid cards ──
        "profile_balanced": "Perfil equilibrado",
        "profile_hot": "Perfil quente",
        "profile_mixed": "Perfil misto",
        "grid_label": "Combinação",
        "profile_label": "Perfil",
        "pitch_loading": "HYBRIDE EM analisa a tua combinação\u2026",

        # ── app-em — footer ──
        "reminder_title": "Aviso importante:",
        "reminder_text": "Estas combinações são geradas a partir de estatísticas históricas. O EuroMillions é um jogo de sorte e nenhum método garante ganhos.",
        "play_responsible": "Joga com responsabilidade: ",
        "gambling_url": "https://www.jogoresponsavel.pt",
        "gambling_name": "Jogo Responsável",

        # ── app-em — popup title template ──
        "popup_gen_title": "Simulação de {n} combinações otimizada{s} EM",
        "popup_gen_title_one": "Simulação de 1 combinação otimizada EM",

        # ── simulateur-em ──
        "based_on_draws": "Baseado em {n} sorteios oficiais EuroMillions",
        "heat_title_freq": "Frequência: ",
        "heat_title_last": " | Último: ",
        "analyzing_grid": "A analisar a sua combinação EuroMillions",
        "generating_one": "A simular uma combinação otimizada EM...",

        # convergence
        "convergence_strong": "Convergência forte",
        "convergence_moderate": "Convergência moderada",
        "convergence_intermediate": "Convergência intermédia",
        "convergence_partial": "Convergência parcial",

        # detail labels
        "detail_even_odd": "Par / Ímpar",
        "detail_low_high": "Baixo / Alto",
        "detail_sum": "Soma",
        "detail_spread": "Dispersão",
        "detail_runs": "Sequências",
        "detail_compliance": "Conformidade",

        # history
        "history_appeared": "\U0001f4dc Esta combinação já saiu <strong>{n} vezes</strong>",
        "history_appeared_one": "\U0001f4dc Esta combinação já saiu <strong>1 vez</strong>",
        "history_never": "\U0001f50e Esta combinação nunca apareceu no histórico.",
        "history_best": "\U0001f9e0 Melhor correspondência: <strong>{n} número{s} idêntico{s}</strong>",

        # ── sponsor-popup-em ──
        "sponsor1_desc": "Restauro artesanal de fotografias",
        "sponsor1_badge": "Impulsionado por",
        "sponsor2_name": "A sua marca aqui",
        "sponsor2_desc": "Audiência ampla \u2022 tráfego qualificado",
        "sponsor2_badge": "Com o apoio de",
        "console_title": "MOTOR HYBRIDE EM",
        "system_ready": "Sistema pronto",
        "sponsors_header": "Parceiros",
        "timer_label": "segundos",
        "cancel_btn": "Cancelar",
        "popup_default_title": "HYBRIDE EM - Análise em curso...",

        # console logs (sponsor-popup-em)
        "log_init": "> A inicializar HYBRIDE_EM_V1...",
        "log_connection": "\u2713 Ligação ao motor OK (142ms)",
        "log_loading_db": "> A carregar base de dados EuroMillions...",
        "log_draws_loaded": " sorteios EuroMillions carregados (387ms)",
        "log_freq": "\U0001f4ca A analisar frequências 5 números + 2 estrelas... ",
        "log_european": "\U0001f30d A cruzar dados europeus... ",
        "log_star_optim": "\u2b50 A otimizar estrelas... ",
        "log_balance": "\u2696\ufe0f A equilibrar par/ímpar... ",
        "log_spread_multi": "\U0001f4cf A calcular dispersão multipaís... ",
        "log_constraints": "\u23f3 A aplicar restrições suaves... ",
        "log_gen_grids": "\u23f3 A simular combinações otimizadas EM... ",
        "log_validating": "\u23f3 A validar pontuações finais... ",
        "log_success": "\u2713 {n} combinações gerada{s} com sucesso",
        "log_preparing": "> A preparar visualização dos resultados...",
        "log_ready": "\u2713 Pronto a apresentar",

        # ── sponsor-popup75-em ──
        "sponsor_header_single": "Parceiro",
        "video_cta": "\U0001f4fa Este espaço de vídeo está disponível para a sua marca",
        "meta_window_badge": "Janela META ANÁLISE EM",
        "popup75_default": "HYBRIDE EM - A calcular...",

        # console logs 75
        "log75_init": "> A inicializar HYBRIDE EM...",
        "log75_connection": "\u2713 Ligação ao motor OK (142ms)",
        "log75_loading_db": "> A carregar base de dados EuroMillions...",
        "log75_draws": " sorteios EuroMillions analisados",
        "log75_draws_full": " sorteios EuroMillions analisados (base completa)",
        "log75_freq_balls": "\u23f3 A calcular frequências de bolas (1-50)... ",
        "log75_freq_stars": "\u23f3 A calcular frequências de estrelas (1-12)... ",
        "log75_hot": "\u23f3 A detetar padrões quentes... ",
        "log75_balance": "\u23f3 A equilibrar par/ímpar... ",
        "log75_geo": "\u23f3 A calcular dispersão geográfica... ",
        "log75_constraints": "\u23f3 A aplicar restrições suaves... ",
        "log75_gen": "\u23f3 A simular combinações otimizadas EM... ",
        "log75_validating": "\u23f3 A validar pontuações finais... ",
        "log75_success": "\u2713 {n} combinações gerada{s} com sucesso",
        "log75_preparing": "> A preparar visualização dos resultados...",
        "log75_ready": "\u2713 Pronto a apresentar",

        # meta final logs
        "meta_log_analysing": "A analisar 75 combinações EM...",
        "meta_log_charts": "A criar gráficos...",
        "meta_log_pdf": "Relatório PDF EM...",
        "meta_log_validation": "Validação final...",
        "meta_log_ready": "Análise pronta.",

        # meta result popup
        "meta_result_title": "Resultado META ANÁLISE EM",
        "meta_result_subtitle": "Análise baseada em 75 combinações EuroMillions simuladas",
        "meta_graph_balls": "Top 5 Bolas - Convergência estatística",
        "meta_graph_stars": "Top 3 Estrelas - Convergência estatística",
        "meta_src_gemini": "\U0001f9e0 Análise enriquecida Gemini",
        "meta_src_local": "\u26a0\ufe0f Análise local (Gemini indisponível)",
        "meta_close": "Fechar",
        "meta_download": "Descarregar relatório META EM",
        "meta_chart_na": "Gráfico não disponível",
        "meta_pending": "Análise avançada ainda em curso...",
        "meta_fallback_text": "Resultado temporariamente indisponível.",
        "meta_fallback_retry": "Por favor, tente novamente dentro de instantes.",
        "meta_75_grids": "75 combinações",
        "meta_sponsor_space": "Espaço disponível",
        "meta_popup_title": "META ANÁLISE EM - A processar 75 combinações",

        # PDF labor illusion steps
        "meta_anim_step1": "A analisar os ciclos de sorteio...",
        "meta_anim_step2": "A calcular a convergência estatística...",
        "meta_anim_step3": "A modelar as probabilidades...",
        "meta_anim_step4": "A compilar o relatório PDF...",

        # wrapper titles
        "wrapper_gen_title": "Simulação de {n} combinações otimizada{s} EM",
        "wrapper_sim_title": "A analisar a sua combinação EM",

        # ── chatbot widget ──
        "chatbot_welcome": "Bem-vindo! Sou o HYBRIDE, o assistente IA do LotoIA \u2014 módulo EuroMillions. Pergunta-me o que quiseres sobre o EuroMillions, estatísticas ou o motor HYBRIDE \uD83C\uDF1F",
        "chatbot_placeholder": "Faz a tua pergunta sobre EuroMillions...",
        "chatbot_bubble_label": "Abrir o chatbot HYBRIDE EuroMillions",
        "chatbot_clear_title": "Nova conversa",
        "chatbot_close_label": "Fechar",
        "chatbot_send_label": "Enviar",

        # ── rating-popup ──
        "rating_prompt": "A tua opinião sobre o LotoIA?",
        "rating_close": "Fechar",
        "rating_thanks": "Obrigado!",
    },

    "de": {
        # ── Locale ──
        "locale": "de-DE",

        # ── app-em — errors / API ──
        "api_error": "API-Fehler",
        "http_error": "HTTP-Fehler ",
        "error_generating": "Fehler beim Generieren der Kombinationen.",
        "unable_generate": "Kombinationen konnten nicht generiert werden. ",
        "select_date": "Bitte wählen Sie ein Ziehungsdatum.",
        "draw_days_only": "EuroMillions wird nur dienstags und freitags gezogen.",
        "no_draw_msg": "Keine EuroMillions-Ziehung an diesem Tag. Nächste Ziehung: ",

        # ── app-em — display ──
        "draws_suffix": " Ziehungen analysiert",
        "data_depth_from": "von ",
        "data_depth_to": " bis ",
        "grids_for": "EuroMillions-Kombinationen für den ",
        "grids_generated": " Kombinationen generiert",
        "grid_generated_one": " Kombination generiert",
        "result_title": "Ziehungsanalyse",

        # ── app-em — grid cards ──
        "profile_balanced": "Ausgewogenes Profil",
        "profile_hot": "Heißes Profil",
        "profile_mixed": "Gemischtes Profil",
        "grid_label": "Kombination",
        "profile_label": "Profil",
        "pitch_loading": "HYBRIDE EM analysiert deine Kombination\u2026",

        # ── app-em — footer ──
        "reminder_title": "Wichtiger Hinweis:",
        "reminder_text": "Diese Kombinationen werden aus historischen Statistiken generiert. EuroMillions ist ein Glücksspiel und keine Methode garantiert Gewinne.",
        "play_responsible": "Spielen Sie verantwortungsvoll: ",
        "gambling_url": "https://www.spielerschutz.de",
        "gambling_name": "Spielerschutz",

        # ── app-em — popup title template ──
        "popup_gen_title": "Simulation von {n} optimierten EM-Kombination{s}",
        "popup_gen_title_one": "Simulation von 1 optimierten EM-Kombination",

        # ── simulateur-em ──
        "based_on_draws": "Basierend auf {n} offiziellen EuroMillions-Ziehungen",
        "heat_title_freq": "Häufigkeit: ",
        "heat_title_last": " | Letzte: ",
        "analyzing_grid": "Ihre EuroMillions-Kombination wird analysiert",
        "generating_one": "Eine optimierte EM-Kombination wird simuliert...",

        # convergence
        "convergence_strong": "Starke Konvergenz",
        "convergence_moderate": "Moderate Konvergenz",
        "convergence_intermediate": "Mittlere Konvergenz",
        "convergence_partial": "Teilweise Konvergenz",

        # detail labels
        "detail_even_odd": "Gerade / Ungerade",
        "detail_low_high": "Niedrig / Hoch",
        "detail_sum": "Summe",
        "detail_spread": "Streuung",
        "detail_runs": "Folgen",
        "detail_compliance": "Konformität",

        # history
        "history_appeared": "\U0001f4dc Diese Kombination ist bereits <strong>{n} Mal</strong> gezogen worden",
        "history_appeared_one": "\U0001f4dc Diese Kombination ist bereits <strong>1 Mal</strong> gezogen worden",
        "history_never": "\U0001f50e Diese Kombination ist noch nie in der Ziehungshistorie aufgetaucht.",
        "history_best": "\U0001f9e0 Beste Übereinstimmung: <strong>{n} identische Zahl{s}</strong>",

        # ── sponsor-popup-em ──
        "sponsor1_desc": "Handwerkliche Fotorestaurierung",
        "sponsor1_badge": "Unterstützt von",
        "sponsor2_name": "Ihre Marke hier",
        "sponsor2_desc": "Große Reichweite \u2022 qualifizierter Traffic",
        "sponsor2_badge": "Mit Unterstützung von",
        "console_title": "HYBRIDE-ENGINE EM",
        "system_ready": "System bereit",
        "sponsors_header": "Partner",
        "timer_label": "Sekunden",
        "cancel_btn": "Abbrechen",
        "popup_default_title": "HYBRIDE EM - Analyse läuft...",

        # console logs (sponsor-popup-em)
        "log_init": "> Initialisierung HYBRIDE_EM_V1...",
        "log_connection": "\u2713 Verbindung zur Engine OK (142ms)",
        "log_loading_db": "> Lade EuroMillions-Datenbank...",
        "log_draws_loaded": " EuroMillions-Ziehungen geladen (387ms)",
        "log_freq": "\U0001f4ca Analysiere Häufigkeiten 5 Zahlen + 2 Sterne... ",
        "log_european": "\U0001f30d Abgleich europäischer Daten... ",
        "log_star_optim": "\u2b50 Optimiere Sterne... ",
        "log_balance": "\u2696\ufe0f Ausgleich gerade/ungerade... ",
        "log_spread_multi": "\U0001f4cf Berechne Streuung länderübergreifend... ",
        "log_constraints": "\u23f3 Wende Soft-Constraints an... ",
        "log_gen_grids": "\u23f3 Simuliere optimierte EM-Kombinationen... ",
        "log_validating": "\u23f3 Validiere Endergebnisse... ",
        "log_success": "\u2713 {n} Kombination{s} erfolgreich generiert",
        "log_preparing": "> Bereite Ergebnisanzeige vor...",
        "log_ready": "\u2713 Bereit zur Anzeige",

        # ── sponsor-popup75-em ──
        "sponsor_header_single": "Partner",
        "video_cta": "\U0001f4fa Dieser Videoplatz steht für Ihre Marke zur Verfügung",
        "meta_window_badge": "META-ANALYSE EM Fenster",
        "popup75_default": "HYBRIDE EM - Berechnung...",

        # console logs 75
        "log75_init": "> Initialisierung HYBRIDE EM...",
        "log75_connection": "\u2713 Verbindung zur Engine OK (142ms)",
        "log75_loading_db": "> Lade EuroMillions-Datenbank...",
        "log75_draws": " EuroMillions-Ziehungen analysiert",
        "log75_draws_full": " EuroMillions-Ziehungen analysiert (vollständige Datenbank)",
        "log75_freq_balls": "\u23f3 Berechne Kugelhäufigkeiten (1-50)... ",
        "log75_freq_stars": "\u23f3 Berechne Sternhäufigkeiten (1-12)... ",
        "log75_hot": "\u23f3 Erkenne heiße Muster... ",
        "log75_balance": "\u23f3 Ausgleich gerade/ungerade... ",
        "log75_geo": "\u23f3 Berechne geografische Streuung... ",
        "log75_constraints": "\u23f3 Wende Soft-Constraints an... ",
        "log75_gen": "\u23f3 Simuliere optimierte EM-Kombinationen... ",
        "log75_validating": "\u23f3 Validiere Endergebnisse... ",
        "log75_success": "\u2713 {n} Kombination{s} erfolgreich generiert",
        "log75_preparing": "> Bereite Ergebnisanzeige vor...",
        "log75_ready": "\u2713 Bereit zur Anzeige",

        # meta final logs
        "meta_log_analysing": "Analysiere 75 EM-Kombinationen...",
        "meta_log_charts": "Erstelle Diagramme...",
        "meta_log_pdf": "PDF-Bericht EM...",
        "meta_log_validation": "Abschlussvalidierung...",
        "meta_log_ready": "Analyse bereit.",

        # meta result popup
        "meta_result_title": "Ergebnis META-ANALYSE EM",
        "meta_result_subtitle": "Analyse basierend auf 75 simulierten EuroMillions-Kombinationen",
        "meta_graph_balls": "Top 5 Kugeln - Statistische Konvergenz",
        "meta_graph_stars": "Top 3 Sterne - Statistische Konvergenz",
        "meta_src_gemini": "\U0001f9e0 Gemini-erweiterte Analyse",
        "meta_src_local": "\u26a0\ufe0f Lokale Analyse (Gemini nicht verfügbar)",
        "meta_close": "Schließen",
        "meta_download": "META-EM-Bericht herunterladen",
        "meta_chart_na": "Diagramm nicht verfügbar",
        "meta_pending": "Erweiterte Analyse noch in Bearbeitung...",
        "meta_fallback_text": "Ergebnis vorübergehend nicht verfügbar.",
        "meta_fallback_retry": "Bitte versuchen Sie es in einigen Augenblicken erneut.",
        "meta_75_grids": "75 Kombinationen",
        "meta_sponsor_space": "Platz verfügbar",
        "meta_popup_title": "META-ANALYSE EM - Verarbeitung von 75 Kombinationen",

        # PDF labor illusion steps
        "meta_anim_step1": "Analysiere Ziehungszyklen...",
        "meta_anim_step2": "Berechne statistische Konvergenz...",
        "meta_anim_step3": "Modelliere Wahrscheinlichkeiten...",
        "meta_anim_step4": "Erstelle PDF-Bericht...",

        # wrapper titles
        "wrapper_gen_title": "Simulation von {n} optimierten EM-Kombination{s}",
        "wrapper_sim_title": "Ihre EM-Kombination wird analysiert",

        # ── chatbot widget ──
        "chatbot_welcome": "Willkommen! Ich bin HYBRIDE, der KI-Assistent von LotoIA \u2014 EuroMillions-Modul. Frag mich alles über EuroMillions, Statistiken oder die HYBRIDE-Engine \uD83C\uDF1F",
        "chatbot_placeholder": "Stelle deine EuroMillions-Frage...",
        "chatbot_bubble_label": "HYBRIDE EuroMillions Chatbot öffnen",
        "chatbot_clear_title": "Neues Gespräch",
        "chatbot_close_label": "Schließen",
        "chatbot_send_label": "Senden",

        # ── rating-popup ──
        "rating_prompt": "Deine Meinung zu LotoIA?",
        "rating_close": "Schließen",
        "rating_thanks": "Danke!",
    },
}


def get_js_labels(lang: str) -> dict[str, str]:
    """Return the JS i18n dict for the given language."""
    return _LABELS.get(lang, _LABELS["fr"])
