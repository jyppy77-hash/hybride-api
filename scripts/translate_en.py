"""
One-shot script to fill all empty/fuzzy translations in EN .po file.
Run: py -3 scripts/translate_en.py
"""
import re, pathlib

PO_PATH = pathlib.Path(__file__).resolve().parent.parent / "translations" / "en" / "LC_MESSAGES" / "messages.po"

# ── Translation dictionary: French msgid → English msgstr ──────────────────
# Keys are the FULL msgid text (concatenated if multiline).
# Existing translated entries are NOT touched.

TRANSLATIONS = {
    # === _base.html ===
    "Choisir la langue": "Choose language",

    # === _footer.html (new links) ===
    "Méthodologie": "Methodology",
    "IA et EuroMillions": "AI and EuroMillions",
    "Chatbot HYBRIDE": "HYBRIDE Chatbot",
    "À propos": "About",

    # === a-propos.html ===
    "À propos de LotoIA | LotoIA EuroMillions":
        "About LotoIA | LotoIA EuroMillions",
    "Découvrez LotoIA : mission, technologie HYBRIDE, données officielles EuroMillions et Loto, jeu responsable. Plateforme gratuite d'analyse statistique.":
        "Discover LotoIA: mission, HYBRIDE technology, official EuroMillions and Loto data, responsible gambling. Free statistical analysis platform.",
    "Qui sommes-nous, notre mission et notre engagement pour le jeu responsable.":
        "Who we are, our mission and our commitment to responsible gambling.",
    "Mission, technologie et engagement pour le jeu responsable.":
        "Mission, technology and commitment to responsible gambling.",
    "Plateforme d'analyse statistique du Loto et de l'EuroMillions basée sur le moteur algorithmique HYBRIDE":
        "Statistical analysis platform for the Loto and EuroMillions powered by the HYBRIDE algorithmic engine",
    "Qui sommes-nous ?": "Who are we?",
    "<strong>LotoIA</strong> est une plateforme française indépendante dédiée à l'analyse statistique des tirages du Loto et de l'EuroMillions. Créée par <strong>JyppY</strong>, développeur passionné par la data science et les probabilités, LotoIA est née d'une conviction simple : les joueurs méritent des outils transparents, honnêtes et gratuits.":
        "<strong>LotoIA</strong> is an independent French platform dedicated to the statistical analysis of Loto and EuroMillions draws. Created by <strong>JyppY</strong>, a developer passionate about data science and probability, LotoIA was born from a simple conviction: players deserve transparent, honest and free tools.",
    "Nous ne sommes <strong>pas affiliés à la Française des Jeux</strong> ni à aucun opérateur de loterie européen. Nous ne vendons ni grilles, ni abonnements, ni « systèmes gagnants ». LotoIA est un outil d'analyse purement informatif et pédagogique.":
        "We are <strong>not affiliated with la Française des Jeux</strong> nor with any European lottery operator. We do not sell grids, subscriptions or \"winning systems\". LotoIA is a purely informational and educational analysis tool.",
    "Notre mission": "Our mission",
    "LotoIA poursuit trois objectifs :": "LotoIA pursues three objectives:",
    "<strong>Rendre les statistiques accessibles</strong> — Transformer des données brutes (tirages officiels Loto et EuroMillions) en analyses visuelles et compréhensibles par tous.":
        "<strong>Making statistics accessible</strong> — Transforming raw data (official Loto and EuroMillions draws) into visual analyses understandable by everyone.",
    "<strong>Lutter contre la désinformation</strong> — Trop de sites prétendent « prédire » les résultats ou vendent des méthodes miracles. Nous rappelons systématiquement que le Loto et l'EuroMillions sont des jeux de hasard pur et que <strong>personne ne peut prédire les résultats</strong>.":
        "<strong>Fighting misinformation</strong> — Too many sites claim to \"predict\" results or sell miracle methods. We consistently remind users that the Loto and EuroMillions are pure games of chance and that <strong>nobody can predict the results</strong>.",
    "<strong>Promouvoir le jeu responsable</strong> — Chaque page de notre site rappelle les risques liés au jeu et fournit les coordonnées des organismes d'aide.":
        "<strong>Promoting responsible gambling</strong> — Every page on our site highlights the risks associated with gambling and provides contact details for support organisations.",
    "Notre technologie": "Our technology",
    "Le moteur HYBRIDE":
        "The HYBRIDE engine",
    "Au cœur de LotoIA se trouve le moteur HYBRIDE, un algorithme d'analyse statistique qui combine 5 composantes : analyse fréquentielle, calcul des retards, pondération temporelle, scoring multicritère et sélection optimale. Sa méthodologie est entièrement documentée et transparente.":
        "At the heart of LotoIA lies the HYBRIDE engine, a statistical analysis algorithm combining 5 components: frequency analysis, gap calculation, temporal weighting, multi-criteria scoring and optimal selection. Its methodology is fully documented and transparent.",
    "L'IA Grounded": "Grounded AI",
    "Notre chatbot intelligent est alimenté par <strong>Gemini</strong> (Google DeepMind) en mode « Grounded » : il est connecté en temps réel à nos bases de données de tirages officiels. Résultat : <strong>zéro hallucination</strong>. Chaque réponse est ancrée sur des données réelles et vérifiables.":
        "Our intelligent chatbot is powered by <strong>Gemini</strong> (Google DeepMind) in \"Grounded\" mode: it is connected in real time to our official draw databases. Result: <strong>zero hallucination</strong>. Every answer is grounded in real, verifiable data.",
    "Infrastructure": "Infrastructure",
    "LotoIA est hébergé sur <strong>Google Cloud Run</strong> avec une base de données <strong>Cloud SQL</strong>. Cette architecture garantit la disponibilité, la sécurité et la mise à jour automatique des données après chaque tirage officiel.":
        "LotoIA is hosted on <strong>Google Cloud Run</strong> with a <strong>Cloud SQL</strong> database. This architecture ensures availability, security and automatic data updates after each official draw.",
    "Nos données": "Our data",
    "EuroMillions": "EuroMillions",
    "Notre base couvre <strong>729+ tirages officiels EuroMillions</strong> depuis 2019. L'EuroMillions se joue dans 9 pays européens avec 5 numéros (1-50) et 2 étoiles (1-12). Les tirages ont lieu les mardis et vendredis.":
        "Our database covers <strong>729+ official EuroMillions draws</strong> since 2019. EuroMillions is played in 9 European countries with 5 numbers (1-50) and 2 stars (1-12). Draws take place on Tuesdays and Fridays.",
    "Loto France": "Loto France",
    "Notre base couvre <strong>986+ tirages officiels du Loto français</strong> depuis novembre 2019. Le Loto se joue avec 5 numéros (1-49) et 1 numéro Chance (1-10). Les tirages ont lieu les lundis, mercredis et samedis.":
        "Our database covers <strong>986+ official French Loto draws</strong> since November 2019. The Loto is played with 5 numbers (1-49) and 1 Lucky number (1-10). Draws take place on Mondays, Wednesdays and Saturdays.",
    "Toutes les données proviennent des sources officielles. Elles sont mises à jour automatiquement après chaque tirage. Aucune donnée n'est inventée ou approximée.":
        "All data comes from official sources. It is updated automatically after each draw. No data is fabricated or approximated.",
    "Notre engagement pour le jeu responsable":
        "Our commitment to responsible gambling",
    "Le jeu responsable est au cœur de notre démarche. Concrètement :":
        "Responsible gambling is at the heart of our approach. In practice:",
    "Chaque page de LotoIA affiche un <strong>avertissement sur les risques du jeu</strong>":
        "Every page on LotoIA displays a <strong>warning about the risks of gambling</strong>",
    "Nous ne promettons <strong>jamais de gains</strong> et rappelons que le Loto et l'EuroMillions sont des jeux de hasard pur":
        "We <strong>never promise winnings</strong> and remind users that the Loto and EuroMillions are pure games of chance",
    "Les coordonnées des <strong>organismes d'aide</strong> sont visibles sur chaque page":
        "Contact details for <strong>support organisations</strong> are visible on every page",
    "Nous rappelons l'<strong>interdiction de jeu aux mineurs</strong>":
        "We emphasise the <strong>prohibition of gambling for minors</strong>",
    "Nous n'incitons jamais à jouer plus ou à augmenter ses mises":
        "We never encourage playing more or increasing stakes",
    "Si vous ou un proche avez des difficultés avec le jeu, contactez <a href=\"%(url)s\" target=\"_blank\" rel=\"noopener\">%(name)s</a>.":
        "If you or someone close to you is struggling with gambling, contact <a href=\"%(url)s\" target=\"_blank\" rel=\"noopener\">%(name)s</a>.",
    "Ce que LotoIA n'est pas": "What LotoIA is not",
    "LotoIA <strong>n'est pas un site de jeu</strong> — nous ne vendons pas de grilles et ne permettons pas de jouer":
        "LotoIA <strong>is not a gambling site</strong> — we do not sell grids and do not allow you to play",
    "LotoIA <strong>n'est pas un outil de pronostic</strong> — nous analysons des données historiques, nous ne prédisons pas l'avenir":
        "LotoIA <strong>is not a prediction tool</strong> — we analyse historical data, we do not predict the future",
    "LotoIA <strong>n'est pas affilié à la FDJ</strong> ni à aucun opérateur — nous sommes un projet indépendant":
        "LotoIA <strong>is not affiliated with the FDJ</strong> or any operator — we are an independent project",
    "LotoIA <strong>n'est pas payant</strong> — toutes les fonctionnalités sont gratuites, sans inscription":
        "LotoIA <strong>is not a paid service</strong> — all features are free, with no registration required",
    "Nous contacter": "Contact us",
    "Pour toute question, suggestion ou partenariat :":
        "For any questions, suggestions or partnerships:",
    "Email : <strong>contact@lotoia.fr</strong>":
        "Email: <strong>contact@lotoia.fr</strong>",
    "Partenariats : <strong>partenariats@lotoia.fr</strong>":
        "Partnerships: <strong>partenariats@lotoia.fr</strong>",
    "Explorer les statistiques EuroMillions":
        "Explore EuroMillions statistics",
    "Découvrez les fréquences, tendances et analyses des numéros et étoiles.":
        "Discover the frequencies, trends and analyses of numbers and stars.",

    # === euromillions-ia.html ===
    "EuroMillions et Intelligence Artificielle — Analyse IA des Tirages | LotoIA":
        "EuroMillions and Artificial Intelligence — AI Draw Analysis | LotoIA",
    "L'intelligence artificielle peut-elle aider à analyser l'EuroMillions ? Découvrez ce que l'IA fait réellement, le moteur HYBRIDE et les limites scientifiques.":
        "Can artificial intelligence help analyse EuroMillions? Discover what AI actually does, the HYBRIDE engine and the scientific limitations.",
    "EuroMillions et Intelligence Artificielle | LotoIA":
        "EuroMillions and Artificial Intelligence | LotoIA",
    "L'IA peut-elle analyser l'EuroMillions ? Moteur HYBRIDE, recherche scientifique et limites mathématiques.":
        "Can AI analyse EuroMillions? HYBRIDE engine, scientific research and mathematical limitations.",
    "Ce que l'IA peut réellement faire pour l'analyse de l'EuroMillions. Modélisation statistique et exploration de données.":
        "What AI can actually do for EuroMillions analysis. Statistical modelling and data exploration.",
    "EuroMillions et Intelligence Artificielle — Ce que dit la science":
        "EuroMillions and Artificial Intelligence — What science says",
    "Analyse complète du rôle de l'intelligence artificielle dans l'analyse des tirages EuroMillions":
        "Comprehensive analysis of the role of artificial intelligence in EuroMillions draw analysis",
    "EuroMillions et IA": "EuroMillions and AI",
    "L'intelligence artificielle peut-elle prédire les résultats EuroMillions ?":
        "Can artificial intelligence predict EuroMillions results?",
    "Non. L'EuroMillions est un jeu de hasard pur où chaque tirage est indépendant. Aucune IA, aucun algorithme ne peut prédire les résultats. L'IA peut en revanche analyser les fréquences historiques et détecter des biais cognitifs chez les joueurs.":
        "No. EuroMillions is a pure game of chance where each draw is independent. No AI, no algorithm can predict the results. AI can, however, analyse historical frequencies and detect cognitive biases in players.",
    "Comment LotoIA utilise l'IA pour l'EuroMillions ?":
        "How does LotoIA use AI for EuroMillions?",
    "Le moteur HYBRIDE combine 5 algorithmes : analyse fréquentielle, calcul des retards, pondération temporelle (méthodologie 5 ans + 2), scoring multicritère et sélection optimale. Il analyse %(total)s+ tirages officiels EuroMillions pour proposer des grilles statistiquement équilibrées.":
        "The HYBRIDE engine combines 5 algorithms: frequency analysis, gap calculation, temporal weighting (\"5 years + 2\" methodology), multi-criteria scoring and optimal selection. It analyses %(total)s+ official EuroMillions draws to produce statistically balanced grids.",
    "Quelle est la différence entre LotoIA et ChatGPT pour l'EuroMillions ?":
        "What is the difference between LotoIA and ChatGPT for EuroMillions?",
    "ChatGPT est un modèle de langage génératif qui n'a pas accès aux données réelles des tirages. Il invente des numéros sans fondement statistique. LotoIA utilise une IA Grounded connectée aux %(total)s+ tirages officiels EuroMillions, sans hallucination.":
        "ChatGPT is a generative language model with no access to real draw data. It invents numbers with no statistical basis. LotoIA uses a Grounded AI connected to %(total)s+ official EuroMillions draws, with zero hallucination.",
    "Les « systèmes gagnants » EuroMillions fonctionnent-ils ?":
        "Do EuroMillions \"winning systems\" actually work?",
    "Non. Tout système prétendant garantir des gains à l'EuroMillions est une arnaque. La probabilité de gagner le jackpot est de 1 sur 139 838 160, identique pour chaque combinaison, à chaque tirage.":
        "No. Any system claiming to guarantee EuroMillions winnings is a scam. The probability of winning the jackpot is 1 in 139,838,160, identical for every combination, at every draw.",
    "Pourquoi LotoIA est gratuit ?":
        "Why is LotoIA free?",
    "LotoIA est un projet indépendant dont la mission est de rendre les statistiques accessibles. Toutes les fonctionnalités sont gratuites, sans inscription ni paiement : exploration de grilles, analyse, statistiques et chatbot IA.":
        "LotoIA is an independent project whose mission is to make statistics accessible. All features are free, with no registration or payment: grid exploration, analysis, statistics and AI chatbot.",
    "L'IA de LotoIA va-t-elle s'améliorer ?":
        "Will LotoIA's AI improve?",
    "Oui. Le moteur HYBRIDE est régulièrement mis à jour : nouveaux tirages intégrés automatiquement, algorithmes affinés et nouvelles fonctionnalités d'analyse. L'objectif est de fournir l'analyse statistique la plus complète et transparente possible.":
        "Yes. The HYBRIDE engine is regularly updated: new draws integrated automatically, refined algorithms and new analysis features. The goal is to provide the most comprehensive and transparent statistical analysis possible.",
    "L'EuroMillions fascine des millions de joueurs à travers l'Europe chaque semaine. Avec l'essor de l'intelligence artificielle, une question revient sans cesse : <strong>peut-on utiliser l'IA pour gagner à l'EuroMillions ?</strong> La réponse courte est non. Mais la réponse complète est bien plus intéressante.":
        "EuroMillions fascinates millions of players across Europe every week. With the rise of artificial intelligence, one question keeps coming back: <strong>can AI be used to win at EuroMillions?</strong> The short answer is no. But the full answer is far more interesting.",
    "Cet article fait le point sur ce que l'intelligence artificielle peut — et ne peut pas — faire pour les amateurs d'EuroMillions, en s'appuyant sur la science, les mathématiques et l'expérience concrète du <a href=\"%(moteur_url)s\">moteur HYBRIDE</a> développé par LotoIA.":
        "This article takes stock of what artificial intelligence can — and cannot — do for EuroMillions enthusiasts, drawing on science, mathematics and the practical experience of the <a href=\"%(moteur_url)s\">HYBRIDE engine</a> developed by LotoIA.",
    "L'IA peut-elle prédire l'EuroMillions ?":
        "Can AI predict EuroMillions?",
    "<strong>Non, et voici pourquoi.</strong> L'EuroMillions est un jeu de hasard pur. Chaque tirage est un événement statistiquement indépendant : les boules n'ont pas de mémoire. Le fait qu'un numéro soit sorti trois fois de suite ne change absolument rien à sa probabilité de sortir au prochain tirage.":
        "<strong>No, and here is why.</strong> EuroMillions is a pure game of chance. Each draw is a statistically independent event: the balls have no memory. The fact that a number has been drawn three times in a row changes absolutely nothing about its probability of being drawn in the next draw.",
    "La probabilité de trouver les 5 bons numéros parmi 50 et les 2 bonnes étoiles parmi 12 est exactement de <strong>1 sur 139 838 160</strong>. Cette probabilité est identique pour la combinaison 1-2-3-4-5 + étoiles 1-2 que pour 7-14-23-38-47 + étoiles 5-11. Aucun algorithme, aussi sophistiqué soit-il, ne peut améliorer ces probabilités fondamentales.":
        "The probability of finding the 5 correct numbers out of 50 and the 2 correct stars out of 12 is exactly <strong>1 in 139,838,160</strong>. This probability is identical for the combination 1-2-3-4-5 + stars 1-2 as for 7-14-23-38-47 + stars 5-11. No algorithm, however sophisticated, can improve these fundamental probabilities.",
    "La différence fondamentale": "The fundamental difference",
    "Prédiction": "Prediction",
    "prétendre deviner les numéros du prochain tirage — <em>mathématiquement impossible</em>.":
        "claiming to guess the numbers of the next draw — <em>mathematically impossible</em>.",
    "Analyse statistique": "Statistical analysis",
    "étudier les tirages passés pour comprendre les fréquences, détecter les biais cognitifs des joueurs et proposer des combinaisons équilibrées — <em>c'est ce que fait LotoIA</em>.":
        "studying past draws to understand frequencies, detect cognitive biases in players and propose balanced combinations — <em>this is what LotoIA does</em>.",
    "Le machine learning et le deep learning excellent quand il existe des <strong>patterns exploitables</strong> dans les données : reconnaissance d'images, traduction, prévisions météo. Le tirage de l'EuroMillions, par construction, est conçu pour être <strong>parfaitement aléatoire</strong>. Il n'y a pas de pattern à exploiter, pas de signal dans le bruit.":
        "Machine learning and deep learning excel when there are <strong>exploitable patterns</strong> in the data: image recognition, translation, weather forecasting. The EuroMillions draw, by design, is intended to be <strong>perfectly random</strong>. There is no pattern to exploit, no signal in the noise.",
    "Ce que l'IA peut réellement faire pour les joueurs":
        "What AI can actually do for players",
    "Si l'IA ne peut pas prédire l'EuroMillions, elle peut en revanche apporter une vraie valeur aux joueurs dans plusieurs domaines :":
        "While AI cannot predict EuroMillions, it can bring real value to players in several areas:",
    "Analyse des fréquences historiques":
        "Historical frequency analysis",
    "En analysant les <strong>%(total)s+ tirages officiels EuroMillions</strong>, l'IA identifie quels numéros (1-50) et quelles étoiles (1-12) sont sortis le plus souvent (« chauds ») et lesquels sont en retard (« froids »). Ces statistiques sont factuelles et vérifiables. Elles ne prédisent pas l'avenir, mais elles décrivent précisément le passé. Consultez nos <a href=\"%(stats_url)s\">statistiques détaillées</a>.":
        "By analysing the <strong>%(total)s+ official EuroMillions draws</strong>, AI identifies which numbers (1-50) and which stars (1-12) have been drawn most often (\"hot\") and which are overdue (\"cold\"). These statistics are factual and verifiable. They do not predict the future, but they precisely describe the past. View our <a href=\"%(stats_url)s\">detailed statistics</a>.",
    "Détection des biais cognitifs": "Detecting cognitive biases",
    "Les joueurs ont des biais inconscients : ils jouent trop les dates de naissance (numéros 1-31), évitent les extrêmes (1 et 50), et choisissent des suites « esthétiques ». L'IA peut mettre en évidence ces biais et aider à composer des grilles plus <strong>diversifiées</strong>, ce qui réduit le risque de partager un éventuel gain avec d'autres joueurs ayant les mêmes numéros.":
        "Players have unconscious biases: they over-play birth dates (numbers 1-31), avoid extremes (1 and 50), and choose \"aesthetic\" sequences. AI can highlight these biases and help compose more <strong>diversified</strong> grids, which reduces the risk of sharing any potential winnings with other players who chose the same numbers.",
    "Optimisation pour éviter le partage de gains":
        "Optimisation to avoid sharing winnings",
    "Toutes les combinaisons ont la même probabilité de sortir, mais toutes n'ont pas la même probabilité d'être <strong>jouées par d'autres</strong>. La combinaison 1-2-3-4-5 est jouée par des milliers de personnes chaque tirage. Une combinaison statistiquement « originale » vous garantit, en cas de gain, un jackpot moins partagé.":
        "All combinations have the same probability of being drawn, but not all have the same probability of being <strong>played by others</strong>. The combination 1-2-3-4-5 is played by thousands of people every draw. A statistically \"original\" combination guarantees, in the event of a win, a less shared jackpot.",
    "Analyse de conformité d'une grille":
        "Grid conformity analysis",
    "Notre <a href=\"%(sim_url)s\">simulateur d'analyse de grille</a> évalue votre sélection selon des critères objectifs : équilibre pair/impair, répartition bas/haut (1-25 vs 26-50), dispersion, somme totale et présence de suites. Les étoiles (1-12) sont évaluées séparément. Ce n'est pas de la prédiction, c'est de l'audit statistique.":
        "Our <a href=\"%(sim_url)s\">grid analysis simulator</a> evaluates your selection against objective criteria: odd/even balance, low/high distribution (1-25 vs 26-50), dispersion, total sum and presence of consecutive numbers. Stars (1-12) are evaluated separately. This is not prediction — it is statistical auditing.",
    "Comment fonctionne le moteur HYBRIDE de LotoIA":
        "How the LotoIA HYBRIDE engine works",
    "Le <a href=\"%(moteur_url)s\">moteur HYBRIDE</a> est le cœur algorithmique de LotoIA. Son approche se résume en une phrase : <strong>« Analyser, pas prédire »</strong>.":
        "The <a href=\"%(moteur_url)s\">HYBRIDE engine</a> is the algorithmic core of LotoIA. Its approach can be summed up in one phrase: <strong>\"Analyse, don't predict\"</strong>.",
    "Les 5 algorithmes du moteur": "The engine's 5 algorithms",
    "<strong>Analyse fréquentielle</strong> — Calcul des fréquences d'apparition de chaque numéro (1-50) et de chaque étoile (1-12) sur l'historique complet des tirages.":
        "<strong>Frequency analysis</strong> — Calculation of the appearance frequency of each number (1-50) and each star (1-12) over the complete draw history.",
    "<strong>Calcul des retards</strong> — Nombre de tirages depuis la dernière apparition de chaque numéro et de chaque étoile.":
        "<strong>Gap calculation</strong> — Number of draws since the last appearance of each number and each star.",
    "<strong>Pondération temporelle</strong> — Application de coefficients privilégiant les 2 dernières années (<a href=\"%(methodo_url)s\">méthodologie « 5 ans + 2 »</a>).":
        "<strong>Temporal weighting</strong> — Applying coefficients favouring the last 2 years (<a href=\"%(methodo_url)s\">\"5 years + 2\" methodology</a>).",
    "<strong>Scoring multicritère</strong> — Évaluation de chaque grille selon l'équilibre pair/impair, la répartition bas/haut, la dispersion, la somme totale et la détection de patterns. Les étoiles sont évaluées séparément.":
        "<strong>Multi-criteria scoring</strong> — Evaluation of each grid based on odd/even balance, low/high distribution, dispersion, total sum and pattern detection. Stars are evaluated separately.",
    "<strong>Sélection optimale</strong> — Classement des grilles par niveau de convergence statistique décroissant.":
        "<strong>Optimal selection</strong> — Ranking grids by decreasing statistical convergence level.",
    "La méthodologie « 5 ans + 2 »":
        "The \"5 years + 2\" methodology",
    "Le moteur combine deux horizons temporels : <strong>5 ans</strong> d'historique pour la stabilité statistique, avec une <strong>pondération renforcée sur les 2 dernières années</strong> pour capter les tendances récentes. Cette approche équilibre profondeur et réactivité.":
        "The engine combines two time horizons: <strong>5 years</strong> of history for statistical stability, with <strong>reinforced weighting on the last 2 years</strong> to capture recent trends. This approach balances depth and responsiveness.",
    "L'assistant IA conversationnel":
        "The conversational AI assistant",
    "LotoIA intègre un chatbot alimenté par <strong>Gemini</strong> (Google DeepMind) en mode « Grounded » : l'IA est connectée en temps réel à la base de données des tirages. Chaque réponse est ancrée sur des données vérifiées, sans hallucination. Vous pouvez lui poser des questions sur les statistiques, les fréquences ou demander une analyse personnalisée.":
        "LotoIA includes a chatbot powered by <strong>Gemini</strong> (Google DeepMind) in \"Grounded\" mode: the AI is connected in real time to the draw database. Every answer is grounded in verified data, with zero hallucination. You can ask it questions about statistics, frequencies or request a personalised analysis.",
    "L'état de la recherche — Études et exemples concrets":
        "The state of research — Studies and real-world examples",
    "L'expérience des étudiants de Lecce":
        "The Lecce students' experiment",
    "En 2023, des étudiants en mathématiques de l'Université du Salento (Lecce, Italie) ont fait les gros titres en remportant environ 43 000 euros au loto italien grâce à un algorithme basé sur les « numéros en retard ». Leur approche exploitait une particularité du système italien (ruote régionales). <strong>Attention</strong> : cette stratégie n'est pas transposable à l'EuroMillions, dont le mécanisme de tirage est différent et parfaitement aléatoire.":
        "In 2023, mathematics students from the University of Salento (Lecce, Italy) made headlines by winning approximately €43,000 in the Italian lottery using an algorithm based on \"overdue numbers\". Their approach exploited a peculiarity of the Italian system (regional wheels). <strong>Warning</strong>: this strategy cannot be applied to EuroMillions, whose draw mechanism is different and perfectly random.",
    "Les limites mathématiques": "The mathematical limitations",
    "Le théorème central limite et la loi des grands nombres garantissent que, sur un nombre suffisant de tirages, chaque numéro convergera vers la même fréquence. Les écarts observés à court terme sont du bruit statistique, pas un signal exploitable. C'est la raison fondamentale pour laquelle aucune méthode ne peut battre le hasard sur le long terme.":
        "The central limit theorem and the law of large numbers guarantee that, over a sufficient number of draws, each number will converge towards the same frequency. Short-term deviations are statistical noise, not an exploitable signal. This is the fundamental reason why no method can beat chance in the long run.",
    "Les « systèmes gagnants » sont des arnaques":
        "\"Winning systems\" are scams",
    "Internet regorge de sites vendant des « systèmes infaillibles » ou des « logiciels de prédiction ». <strong>Tous sont des arnaques</strong>. Si un système permettait réellement de gagner à l'EuroMillions, son inventeur serait milliardaire et ne le vendrait pas 29,99 euros.":
        "The internet is full of sites selling \"foolproof systems\" or \"prediction software\". <strong>They are all scams</strong>. If a system could actually win the EuroMillions, its inventor would be a billionaire and wouldn't be selling it for €29.99.",
    "La position des opérateurs":
        "The operators' position",
    "Les opérateurs européens de loterie sont catégoriques : chaque tirage est indépendant, les machines sont certifiées et auditées, et aucune méthode ne peut influencer le résultat. Les tirages de l'EuroMillions sont supervisés par des huissiers de justice. LotoIA partage cette position : nous analysons, nous ne prédisons pas.":
        "European lottery operators are categorical: each draw is independent, the machines are certified and audited, and no method can influence the result. EuroMillions draws are supervised by bailiffs. LotoIA shares this position: we analyse, we do not predict.",
    "LotoIA vs les autres approches":
        "LotoIA vs other approaches",
    "Vs les simulateurs aléatoires classiques":
        "Vs standard random simulators",
    "Un simulateur aléatoire simple produit des numéros sans aucune analyse. C'est honnête, mais c'est aussi aveugle. LotoIA génère des grilles qui sont <strong>à la fois aléatoires et statistiquement équilibrées</strong> : bonne répartition pair/impair, bonne dispersion, numéros et étoiles diversifiés. Le résultat est une grille qui a autant de chances d'être tirée qu'une autre, mais moins de chances d'être partagée en cas de correspondance.":
        "A simple random simulator produces numbers without any analysis. It is honest, but also blind. LotoIA generates grids that are <strong>both random and statistically balanced</strong>: good odd/even distribution, good dispersion, diversified numbers and stars. The result is a grid that has as much chance of being drawn as any other, but less chance of being shared in the event of a match.",
    "Vs ChatGPT et les IA génératives":
        "Vs ChatGPT and generative AI",
    "ChatGPT, Claude ou Gemini (en mode libre) sont des modèles de langage. Quand vous leur demandez des numéros d'EuroMillions, ils <strong>inventent</strong> — littéralement. Ils n'ont pas accès aux données réelles des tirages et produisent des réponses plausibles mais sans fondement statistique. LotoIA utilise une IA <strong>« Grounded »</strong> (ancrée) : chaque analyse est calculée à partir des %(total)s+ tirages officiels stockés dans notre base de données Cloud SQL.":
        "ChatGPT, Claude or Gemini (in free mode) are language models. When you ask them for EuroMillions numbers, they <strong>invent</strong> — literally. They have no access to real draw data and produce plausible but statistically unfounded answers. LotoIA uses a <strong>\"Grounded\"</strong> AI: every analysis is calculated from the %(total)s+ official draws stored in our Cloud SQL database.",
    "L'avantage d'une plateforme spécialisée":
        "The advantage of a specialised platform",
    "LotoIA est un outil dédié, construit pour l'analyse des tirages EuroMillions et Loto. Notre base couvre %(total)s+ tirages officiels EuroMillions, mis à jour après chaque tirage (mardis et vendredis). Le <a href=\"%(moteur_url)s\">moteur HYBRIDE</a> a été conçu spécifiquement pour ce domaine, avec une <a href=\"%(methodo_url)s\">méthodologie documentée</a> et transparente. C'est cette spécialisation qui fait la différence.":
        "LotoIA is a dedicated tool, built for analysing EuroMillions and Loto draws. Our database covers %(total)s+ official EuroMillions draws, updated after each draw (Tuesdays and Fridays). The <a href=\"%(moteur_url)s\">HYBRIDE engine</a> was specifically designed for this domain, with a <a href=\"%(methodo_url)s\">documented methodology</a> that is fully transparent. It is this specialisation that makes the difference.",
    # IA FAQ section
    "Non. L'EuroMillions est un jeu de hasard pur où chaque tirage est indépendant. Aucune IA ne peut prédire les résultats. En revanche, l'IA peut analyser les fréquences historiques et aider à composer des grilles statistiquement équilibrées.":
        "No. EuroMillions is a pure game of chance where each draw is independent. No AI can predict the results. However, AI can analyse historical frequencies and help compose statistically balanced grids.",
    "Le moteur HYBRIDE combine 5 algorithmes (analyse fréquentielle, retards, pondération temporelle, scoring multicritère et sélection optimale) appliqués aux %(total)s+ tirages officiels EuroMillions. Découvrez les détails sur la page <a href=\"%(moteur_url)s\">Moteur HYBRIDE</a>.":
        "The HYBRIDE engine combines 5 algorithms (frequency analysis, gaps, temporal weighting, multi-criteria scoring and optimal selection) applied to %(total)s+ official EuroMillions draws. Discover the details on the <a href=\"%(moteur_url)s\">HYBRIDE Engine</a> page.",
    "ChatGPT invente des numéros sans accès aux données réelles. LotoIA utilise une IA « Grounded » connectée aux tirages officiels EuroMillions : zéro hallucination, uniquement des analyses factuelles.":
        "ChatGPT invents numbers with no access to real data. LotoIA uses a \"Grounded\" AI connected to official EuroMillions draws: zero hallucination, only factual analyses.",
    "Non. Tout système prétendant garantir des gains à l'EuroMillions est une arnaque. La probabilité de gagner le jackpot est de 1 sur 139 838 160, identique pour chaque combinaison.":
        "No. Any system claiming to guarantee EuroMillions winnings is a scam. The probability of winning the jackpot is 1 in 139,838,160, identical for every combination.",
    "LotoIA est un projet indépendant dont la mission est de rendre les statistiques accessibles. Toutes les fonctionnalités sont gratuites, sans inscription : <a href=\"%(gen_url)s\">exploration de grilles</a>, <a href=\"%(sim_url)s\">analyse de grille</a>, <a href=\"%(stats_url)s\">statistiques</a> et chatbot IA.":
        "LotoIA is an independent project whose mission is to make statistics accessible. All features are free, with no registration: <a href=\"%(gen_url)s\">grid exploration</a>, <a href=\"%(sim_url)s\">grid analysis</a>, <a href=\"%(stats_url)s\">statistics</a> and AI chatbot.",
    # IA shared elements
    "Jeu responsable": "Responsible gambling",
    "L'EuroMillions est un jeu de hasard. Jouer comporte des risques : endettement, isolement, dépendance. Ne jouez jamais plus que ce que vous pouvez vous permettre de perdre.":
        "EuroMillions is a game of chance. Gambling carries risks: debt, isolation, addiction. Never gamble more than you can afford to lose.",
    "Explorer des grilles EuroMillions":
        "Explore EuroMillions grids",
    "Utilisez le moteur HYBRIDE pour générer des grilles statistiquement optimisées.":
        "Use the HYBRIDE engine to generate statistically optimised grids.",
    "Lancer l'exploration": "Start exploring",

    # === hybride.html ===
    "HYBRIDE — Chatbot IA Grounded pour l'EuroMillions | LotoIA":
        "HYBRIDE — Grounded AI Chatbot for EuroMillions | LotoIA",
    "HYBRIDE est l'assistant IA de LotoIA, connecté en temps réel aux %(total)s+ tirages officiels EuroMillions. Posez vos questions sur les numéros, les étoiles, les tirages et les statistiques.":
        "HYBRIDE is LotoIA's AI assistant, connected in real time to %(total)s+ official EuroMillions draws. Ask your questions about numbers, stars, draws and statistics.",
    "HYBRIDE — Chatbot IA Grounded EuroMillions | LotoIA":
        "HYBRIDE — Grounded AI Chatbot EuroMillions | LotoIA",
    "Assistant IA connecté en temps réel aux %(total)s+ tirages officiels EuroMillions. Zéro hallucination, uniquement des analyses factuelles.":
        "AI assistant connected in real time to %(total)s+ official EuroMillions draws. Zero hallucination, only factual analyses.",
    "Assistant IA connecté aux tirages officiels EuroMillions. Zéro hallucination, uniquement des analyses factuelles.":
        "AI assistant connected to official EuroMillions draws. Zero hallucination, only factual analyses.",
    "Assistant IA conversationnel connecté en temps réel aux tirages officiels EuroMillions. Analyse factuelle, zéro hallucination.":
        "Conversational AI assistant connected in real time to official EuroMillions draws. Factual analysis, zero hallucination.",
    "Connexion temps réel aux %(total)s+ tirages officiels EuroMillions":
        "Real-time connection to %(total)s+ official EuroMillions draws",
    "Analyse de fréquences par numéro (1-50) et par étoile (1-12)":
        "Frequency analysis by number (1-50) and by star (1-12)",
    "Recherche de tirages par date":
        "Draw search by date",
    "Statistiques numéros et étoiles chauds et froids":
        "Hot and cold numbers and stars statistics",
    "Anti-hallucination par vérification systématique":
        "Anti-hallucination through systematic verification",
    "HYBRIDE — Chatbot IA": "HYBRIDE — AI Chatbot",
    "Comment fonctionne le chatbot HYBRIDE pour l'EuroMillions ?":
        "How does the HYBRIDE chatbot work for EuroMillions?",
    "HYBRIDE utilise une architecture Grounded (RAG) : il interroge la base de données des %(total)s+ tirages officiels EuroMillions en temps réel, puis Gemini (Google DeepMind) formule une réponse factuelle à partir des données récupérées. Zéro hallucination.":
        "HYBRIDE uses a Grounded (RAG) architecture: it queries the database of %(total)s+ official EuroMillions draws in real time, then Gemini (Google DeepMind) formulates a factual answer from the retrieved data. Zero hallucination.",
    "Le chatbot peut-il prédire les résultats EuroMillions ?":
        "Can the chatbot predict EuroMillions results?",
    "Non. L'EuroMillions est un jeu de hasard pur et personne — aucune IA, aucun algorithme — ne peut prédire les résultats. HYBRIDE analyse les données passées pour fournir des statistiques factuelles, il ne prédit pas l'avenir.":
        "No. EuroMillions is a pure game of chance and nobody — no AI, no algorithm — can predict the results. HYBRIDE analyses past data to provide factual statistics; it does not predict the future.",
    "En quoi HYBRIDE est différent de ChatGPT pour l'EuroMillions ?":
        "How is HYBRIDE different from ChatGPT for EuroMillions?",
    "ChatGPT est un modèle de langage généraliste sans accès aux données réelles des tirages. HYBRIDE est une IA Grounded connectée aux %(total)s+ tirages officiels EuroMillions stockés dans Cloud SQL. Chaque réponse est vérifiée, pas inventée.":
        "ChatGPT is a generalist language model with no access to real draw data. HYBRIDE is a Grounded AI connected to %(total)s+ official EuroMillions draws stored in Cloud SQL. Every answer is verified, not invented.",
    "Le chatbot est-il disponible dans ma langue ?":
        "Is the chatbot available in my language?",
    "HYBRIDE est disponible en 6 langues : français, anglais, espagnol, portugais, allemand et néerlandais. L'interface et les réponses s'adaptent automatiquement à la langue de la page.":
        "HYBRIDE is available in 6 languages: French, English, Spanish, Portuguese, German and Dutch. The interface and responses automatically adapt to the language of the page.",
    # hybride article body
    "<strong>HYBRIDE</strong> est le chatbot IA intégré à LotoIA. Il est connecté en temps réel aux <strong>%(total)s+ tirages officiels</strong> de l'EuroMillions. Contrairement à ChatGPT ou d'autres IA génératives, HYBRIDE ne devine pas : il interroge les données réelles et vous répond avec des <strong>faits vérifiables</strong>.":
        "<strong>HYBRIDE</strong> is the AI chatbot integrated into LotoIA. It is connected in real time to <strong>%(total)s+ official draws</strong> from the EuroMillions. Unlike ChatGPT or other generative AIs, HYBRIDE does not guess: it queries real data and responds with <strong>verifiable facts</strong>.",
    "Vous pouvez lui poser des questions sur les numéros (1-50), les étoiles (1-12), les tirages, les fréquences ou le fonctionnement du moteur. Il est disponible gratuitement sur toutes les pages EuroMillions de LotoIA — cliquez sur l'icône en bas à droite pour essayer.":
        "You can ask it questions about numbers (1-50), stars (1-12), draws, frequencies or how the engine works. It is available free of charge on all EuroMillions pages on LotoIA — click the icon at the bottom right to try it.",
    "Qu'est-ce qu'une IA « Grounded » ?":
        "What is a \"Grounded\" AI?",
    "Le terme <strong>« Grounded »</strong> (ancré) désigne une IA dont les réponses sont fondées sur des données vérifiées, et non sur l'imagination ou des probabilités linguistiques.":
        "The term <strong>\"Grounded\"</strong> refers to an AI whose answers are based on verified data, rather than on imagination or linguistic probabilities.",
    "La différence fondamentale avec les modèles de langage classiques (ChatGPT, Gemini en mode libre, Claude) est cruciale :":
        "The fundamental difference with standard language models (ChatGPT, Gemini in free mode, Claude) is crucial:",
    "Un <strong>LLM classique</strong> génère une réponse qui « semble correcte » à partir de ses connaissances d'entraînement. Il peut inventer des faits, confondre des données ou produire des réponses plausibles mais fausses — c'est ce qu'on appelle l'<strong>hallucination</strong>.":
        "A <strong>standard LLM</strong> generates an answer that \"looks correct\" from its training knowledge. It can invent facts, confuse data or produce plausible but incorrect answers — this is what is called <strong>hallucination</strong>.",
    "Une <strong>IA Grounded</strong> comme HYBRIDE interroge d'abord sa base de données, récupère les faits pertinents, puis formule sa réponse à partir de ces données vérifiées. Pas de place pour l'invention.":
        "A <strong>Grounded AI</strong> like HYBRIDE first queries its database, retrieves the relevant facts, then formulates its answer from this verified data. No room for invention.",
    "L'analogie simple": "The simple analogy",
    "un ami qui répond de mémoire. Souvent pertinent, parfois complètement faux, et vous ne pouvez pas vérifier.":
        "a friend answering from memory. Often relevant, sometimes completely wrong, and you cannot verify.",
    "un bibliothécaire qui va chercher dans les archives avant de répondre. Plus lent d'une seconde, mais toujours factuel.":
        "a librarian who searches the archives before answering. One second slower, but always factual.",
    "En termes techniques, HYBRIDE utilise une architecture appelée <strong>RAG</strong> (Retrieval-Augmented Generation) : le modèle « récupère » d'abord les données pertinentes dans la base, puis « augmente » sa réponse avec ces données vérifiées. Le résultat : <strong>zéro hallucination</strong> sur les questions EuroMillions.":
        "In technical terms, HYBRIDE uses an architecture called <strong>RAG</strong> (Retrieval-Augmented Generation): the model first \"retrieves\" relevant data from the database, then \"augments\" its answer with this verified data. The result: <strong>zero hallucination</strong> on EuroMillions questions.",
    "Comment HYBRIDE accède aux données en temps réel":
        "How HYBRIDE accesses data in real time",
    "HYBRIDE n'est pas un chatbot décoratif. Il est connecté à la même base de données que le <a href=\"%(moteur_url)s\">moteur d'exploration</a> et les <a href=\"%(stats_url)s\">statistiques</a> de LotoIA :":
        "HYBRIDE is not a decorative chatbot. It is connected to the same database as the <a href=\"%(moteur_url)s\">exploration engine</a> and <a href=\"%(stats_url)s\">statistics</a> on LotoIA:",
    "<strong>%(total)s+ tirages officiels EuroMillions</strong> (plusieurs années d'historique)":
        "<strong>%(total)s+ official EuroMillions draws</strong> (several years of history)",
    "<strong>Synchronisation automatique</strong> après chaque tirage officiel (mardi et vendredi)":
        "<strong>Automatic synchronisation</strong> after each official draw (Tuesday and Friday)",
    "Base hébergée sur <strong>Google Cloud SQL</strong> pour la fiabilité et la rapidité":
        "Database hosted on <strong>Google Cloud SQL</strong> for reliability and speed",
    "Le parcours d'une question": "The journey of a question",
    "<strong>Vous posez votre question</strong> dans le chatbot (texte libre)":
        "<strong>You ask your question</strong> in the chatbot (free text)",
    "<strong>HYBRIDE analyse votre intention</strong> et identifie les données nécessaires":
        "<strong>HYBRIDE analyses your intent</strong> and identifies the required data",
    "<strong>Il interroge la base de données</strong> Cloud SQL en temps réel":
        "<strong>It queries the database</strong> Cloud SQL in real time",
    "<strong>Gemini (Google DeepMind)</strong> formule une réponse claire à partir des données récupérées":
        "<strong>Gemini (Google DeepMind)</strong> formulates a clear answer from the retrieved data",
    "<strong>Vérification anti-hallucination</strong> : la réponse est ancrée exclusivement sur les données EuroMillions":
        "<strong>Anti-hallucination verification</strong>: the answer is grounded exclusively on EuroMillions data",
    "<strong>Vous recevez une réponse factuelle</strong>, généralement en moins de 3 secondes":
        "<strong>You receive a factual answer</strong>, typically in under 3 seconds",
    "Les données utilisées par HYBRIDE sont <strong>exactement les mêmes</strong> que celles affichées dans la page <a href=\"%(stats_url)s\">Statistiques</a>. Pas de base alternative, pas de données approximatives.":
        "The data used by HYBRIDE is <strong>exactly the same</strong> as that displayed on the <a href=\"%(stats_url)s\">Statistics</a> page. No alternative database, no approximate data.",
    "Ce que vous pouvez demander à HYBRIDE":
        "What you can ask HYBRIDE",
    "Questions sur les numéros et les étoiles":
        "Questions about numbers and stars",
    "HYBRIDE connaît l'historique complet de chaque numéro (1 à 50) et chaque étoile (1 à 12).":
        "HYBRIDE knows the complete history of every number (1 to 50) and every star (1 to 12).",
    "\"Combien de fois le 22 est sorti en 2024 ?\"":
        "\"How many times has 22 been drawn in 2024?\"",
    "\"Quel est le numéro le plus sorti depuis 2019 ?\"":
        "\"What is the most drawn number since 2019?\"",
    "\"Quelle étoile sort le plus souvent ?\"":
        "\"Which star is drawn most often?\"",
    "\"Quels numéros ne sont pas sortis depuis plus de 20 tirages ?\"":
        "\"Which numbers haven't been drawn for over 20 draws?\"",
    "Questions sur les tirages": "Questions about draws",
    "Retrouvez n'importe quel tirage par date ou explorez l'historique complet.":
        "Find any draw by date or explore the complete history.",
    "\"Quel était le résultat du tirage du 14 janvier 2025 ?\"":
        "\"What was the result of the draw on 14 January 2025?\"",
    "\"Combien de tirages ont eu lieu en 2024 ?\"":
        "\"How many draws took place in 2024?\"",
    "\"Quel tirage a eu la somme la plus élevée ?\"":
        "\"Which draw had the highest sum?\"",
    "\"Montre-moi les 5 derniers tirages.\"":
        "\"Show me the last 5 draws.\"",
    "Questions sur les statistiques": "Questions about statistics",
    "HYBRIDE calcule les statistiques à la volée à partir de la base complète.":
        "HYBRIDE calculates statistics on the fly from the complete database.",
    "\"Quels sont les 5 numéros les plus chauds en ce moment ?\"":
        "\"What are the 5 hottest numbers right now?\"",
    "\"Quelle est la fréquence moyenne de sortie du numéro 42 ?\"":
        "\"What is the average draw frequency of number 42?\"",
    "\"Y a-t-il des paires de numéros qui sortent souvent ensemble ?\"":
        "\"Are there pairs of numbers that are often drawn together?\"",
    "\"Quelle étoile est la plus en retard ?\"":
        "\"Which star has the biggest gap?\"",
    "Questions pédagogiques": "Educational questions",
    "HYBRIDE explique aussi le fonctionnement de la plateforme et les concepts statistiques.":
        "HYBRIDE also explains how the platform works and statistical concepts.",
    "\"Comment fonctionne le moteur HYBRIDE ?\"":
        "\"How does the HYBRIDE engine work?\"",
    "\"C'est quoi un numéro chaud ?\"":
        "\"What is a hot number?\"",
    "\"L'EuroMillions est-il vraiment aléatoire ?\"":
        "\"Is EuroMillions truly random?\"",
    "\"Dans quels pays peut-on jouer à l'EuroMillions ?\"":
        "\"In which countries can you play EuroMillions?\"",
    "Ce que HYBRIDE ne fait PAS": "What HYBRIDE does NOT do",
    "HYBRIDE est un assistant d'<strong>analyse</strong>, pas un oracle. Voici ce qu'il refuse de faire :":
        "HYBRIDE is an <strong>analysis</strong> assistant, not an oracle. Here is what it refuses to do:",
    "Il <strong>ne prédit PAS</strong> les résultats futurs — l'EuroMillions est un jeu de hasard pur":
        "It does <strong>NOT predict</strong> future results — EuroMillions is a pure game of chance",
    "Il <strong>ne promet PAS</strong> de gains — aucune méthode ne peut garantir un gain à l'EuroMillions":
        "It does <strong>NOT promise</strong> winnings — no method can guarantee a win at EuroMillions",
    "Il <strong>ne donne PAS</strong> de « numéros magiques » ou de « combinaisons gagnantes »":
        "It does <strong>NOT give</strong> \"magic numbers\" or \"winning combinations\"",
    "Il <strong>refuse les questions hors-sujet</strong> (politique, médecine, cuisine…)":
        "It <strong>refuses off-topic questions</strong> (politics, medicine, cooking…)",
    "Il <strong>rappelle systématiquement</strong> que l'EuroMillions est un jeu de hasard et que jouer comporte des risques":
        "It <strong>systematically reminds</strong> users that EuroMillions is a game of chance and that gambling carries risks",
    "Cette honnêteté n'est pas une limitation — c'est une <strong>force</strong>. Dans un univers où les sites de « prédictions » pullulent, HYBRIDE choisit la transparence et l'intégrité. Pour en savoir plus, consultez notre article <a href=\"%(ia_url)s\">EuroMillions et Intelligence Artificielle</a>.":
        "This honesty is not a limitation — it is a <strong>strength</strong>. In a world where \"prediction\" sites abound, HYBRIDE chooses transparency and integrity. To learn more, read our article <a href=\"%(ia_url)s\">EuroMillions and Artificial Intelligence</a>.",
    "HYBRIDE vs ChatGPT — Le comparatif":
        "HYBRIDE vs ChatGPT — The comparison",
    "Pourquoi ne pas simplement utiliser ChatGPT pour analyser l'EuroMillions ? Voici la différence concrète :":
        "Why not simply use ChatGPT to analyse EuroMillions? Here is the concrete difference:",
    "Critère": "Criterion",
    "Données EuroMillions réelles": "Real EuroMillions data",
    "%(total)s+ tirages officiels": "%(total)s+ official draws",
    "Aucune base de données": "No database",
    "Mise à jour": "Update",
    "Après chaque tirage": "After each draw",
    "Knowledge cutoff figé": "Fixed knowledge cutoff",
    "Anti-hallucination": "Anti-hallucination",
    "Vérification systématique": "Systematic verification",
    "Peut inventer des données": "May invent data",
    "Spécialisé EuroMillions": "EuroMillions specialist",
    "100%% dédié": "100%% dedicated",
    "Généraliste": "Generalist",
    "Gratuit": "Free",
    "100%% gratuit — sans inscription": "100% free — no registration",
    "Freemium": "Freemium",
    "Personnalité": "Personality",
    "Mascotte ludique et pédagogique": "Fun and educational mascot",
    "Générique": "Generic",
    "Quand vous demandez à ChatGPT <em>« Quel numéro sort le plus à l'EuroMillions ? »</em>, il génère une réponse plausible basée sur des connaissances générales — souvent inexacte ou datée. Quand vous posez la même question à HYBRIDE, il interroge la base de données en temps réel et vous donne la <strong>vraie réponse</strong>, à jour du dernier tirage.":
        "When you ask ChatGPT <em>\"Which number is drawn the most in EuroMillions?\"</em>, it generates a plausible answer based on general knowledge — often inaccurate or outdated. When you ask the same question to HYBRIDE, it queries the database in real time and gives you the <strong>real answer</strong>, up to date with the latest draw.",
    "La personnalité HYBRIDE": "The HYBRIDE personality",
    "HYBRIDE n'est pas un chatbot froid et technique. Il a été conçu pour être <strong>accessible, pédagogique et sympathique</strong> :":
        "HYBRIDE is not a cold, technical chatbot. It was designed to be <strong>accessible, educational and friendly</strong>:",
    "<strong>Ton conversationnel</strong> — Il s'adresse à vous comme un assistant bienveillant, pas comme un rapport statistique":
        "<strong>Conversational tone</strong> — It addresses you like a helpful assistant, not like a statistical report",
    "<strong>Mise en forme claire</strong> — Il utilise des listes et des mises en forme pour rendre les données lisibles et agréables":
        "<strong>Clear formatting</strong> — It uses lists and formatting to make data readable and pleasant",
    "<strong>Jeu responsable</strong> — Il rappelle régulièrement que l'EuroMillions est un jeu de hasard et oriente vers les organismes d'aide si nécessaire":
        "<strong>Responsible gambling</strong> — It regularly reminds users that EuroMillions is a game of chance and directs them to support organisations when needed",
    "<strong>Pédagogie</strong> — Il explique les concepts (numéros chauds, convergence, écart-type) dans un langage accessible":
        "<strong>Education</strong> — It explains concepts (hot numbers, convergence, standard deviation) in accessible language",
    "<strong>Multilingue</strong> — Il répond en 6 langues et s'adapte automatiquement à la langue de la page":
        "<strong>Multilingual</strong> — It responds in 6 languages and automatically adapts to the page language",
    "Sa philosophie : <strong>rendre les statistiques EuroMillions compréhensibles pour tous</strong>, du joueur occasionnel au passionné de data.":
        "Its philosophy: <strong>making EuroMillions statistics understandable for everyone</strong>, from the occasional player to the data enthusiast.",
    "Essayez HYBRIDE maintenant": "Try HYBRIDE now",
    "Le chatbot est disponible sur toutes les pages EuroMillions de LotoIA. Cliquez sur l'icône en bas à droite pour commencer une conversation.":
        "The chatbot is available on all EuroMillions pages on LotoIA. Click the icon at the bottom right to start a conversation.",
    "Auditer ma grille": "Audit my grid",
    "Questions fréquentes sur HYBRIDE":
        "Frequently asked questions about HYBRIDE",
    # hybride FAQ (article versions with <strong> tags)
    "HYBRIDE utilise une architecture <strong>Grounded (RAG)</strong> : il interroge la base de données des %(total)s+ tirages officiels EuroMillions en temps réel, puis <strong>Gemini</strong> (Google DeepMind) formule une réponse factuelle à partir des données récupérées. Si HYBRIDE ne trouve pas l'information dans la base, il le dit — plutôt que d'inventer.":
        "HYBRIDE uses a <strong>Grounded (RAG)</strong> architecture: it queries the database of %(total)s+ official EuroMillions draws in real time, then <strong>Gemini</strong> (Google DeepMind) formulates a factual answer from the retrieved data. If HYBRIDE cannot find the information in the database, it says so — rather than inventing.",
    "<strong>Non.</strong> L'EuroMillions est un jeu de hasard pur et <strong>personne</strong> — aucune IA, aucun algorithme, aucun « système » — ne peut prédire les résultats. HYBRIDE analyse les données passées pour vous donner des statistiques factuelles. Il ne prédit pas l'avenir, et il le dit clairement.":
        "<strong>No.</strong> EuroMillions is a pure game of chance and <strong>nobody</strong> — no AI, no algorithm, no \"system\" — can predict the results. HYBRIDE analyses past data to give you factual statistics. It does not predict the future, and it says so clearly.",
    "ChatGPT est un modèle de langage <strong>généraliste</strong> sans accès aux données réelles des tirages. HYBRIDE est une IA <strong>Grounded</strong> connectée aux %(total)s+ tirages officiels EuroMillions stockés dans Cloud SQL. Chaque réponse est vérifiée, pas inventée.":
        "ChatGPT is a <strong>generalist</strong> language model with no access to real draw data. HYBRIDE is a <strong>Grounded</strong> AI connected to %(total)s+ official EuroMillions draws stored in Cloud SQL. Every answer is verified, not invented.",
    "HYBRIDE est disponible en <strong>6 langues</strong> : français, anglais, espagnol, portugais, allemand et néerlandais. L'interface et les réponses s'adaptent automatiquement à la langue de la page que vous consultez.":
        "HYBRIDE is available in <strong>6 languages</strong>: French, English, Spanish, Portuguese, German and Dutch. The interface and responses automatically adapt to the language of the page you are viewing.",

    # === methodologie.html ===
    "Méthodologie « 5 ans + 2 » EuroMillions — Analyse Statistique | LotoIA":
        "\"5 Years + 2\" Methodology EuroMillions — Statistical Analysis | LotoIA",
    "Découvrez la méthodologie « 5 ans + 2 » appliquée à l'EuroMillions : analyse fréquentielle sur 5 ans, pondération des 2 dernières années. Approche data-driven.":
        "Discover the \"5 years + 2\" methodology applied to EuroMillions: frequency analysis over 5 years, weighting of the last 2 years. A data-driven approach.",
    "Méthodologie « 5 ans + 2 » EuroMillions | LotoIA":
        "\"5 Years + 2\" Methodology EuroMillions | LotoIA",
    "Approche statistique hybride combinant analyse long terme et tendances récentes pour l'EuroMillions.":
        "Hybrid statistical approach combining long-term analysis and recent trends for EuroMillions.",
    "Approche statistique hybride pour l'analyse des tirages EuroMillions.":
        "Hybrid statistical approach for analysing EuroMillions draws.",
    "Méthodologie « 5 ans + 2 » : Analyse Statistique Avancée EuroMillions":
        "\"5 Years + 2\" Methodology: Advanced EuroMillions Statistical Analysis",
    "Documentation technique de la méthodologie d'analyse statistique appliquée aux tirages EuroMillions":
        "Technical documentation of the statistical analysis methodology applied to EuroMillions draws",
    "Méthodes statistiques appliquées aux données de loterie EuroMillions":
        "Statistical methods applied to EuroMillions lottery data",
    "Principe fondamental": "Fundamental principle",
    "La méthodologie <strong>« 5 ans + 2 »</strong> est le cœur du moteur HYBRIDE appliqué à l'EuroMillions. Elle combine deux horizons temporels pour équilibrer stabilité statistique et réactivité aux tendances.":
        "The <strong>\"5 years + 2\"</strong> methodology is the core of the HYBRIDE engine applied to EuroMillions. It combines two time horizons to balance statistical stability and responsiveness to trends.",
    "Analyse de fréquence sur l'ensemble de l'historique disponible (2019-2026)":
        "Frequency analysis over the entire available history (2019-2026)",
    "Pondération renforcée sur les 2 dernières années pour capter les tendances récentes":
        "Reinforced weighting on the last 2 years to capture recent trends",
    "Sources de données": "Data sources",
    "hébergée sur Google Cloud": "hosted on Google Cloud",
    "Historique": "History",
    "729+ tirages officiels EuroMillions depuis février 2004":
        "729+ official EuroMillions draws since February 2004",
    "Tirages les mardis et vendredis": "Draws on Tuesdays and Fridays",
    "Synchronisation après chaque tirage officiel": "Synchronisation after each official draw",
    "Intégrité": "Integrity",
    "Vérification systématique des données sources": "Systematic verification of source data",
    "Métriques calculées": "Calculated metrics",
    "Fréquences": "Frequencies",
    "Pour chaque numéro (1-50) et chaque étoile (1-12), calcul du nombre d'apparitions sur la période analysée.":
        "For each number (1-50) and each star (1-12), calculation of the number of appearances over the analysed period.",
    "Retards": "Gaps",
    "Nombre de tirages depuis la dernière apparition de chaque numéro et de chaque étoile.":
        "Number of draws since the last appearance of each number and each star.",
    "Analyse de conformité": "Conformity analysis",
    "Évaluation multicritère basée sur :": "Multi-criteria evaluation based on:",
    "Équilibre pair/impair (ratio optimal : 2-3 pairs)":
        "Odd/even balance (optimal ratio: 2-3 even)",
    "Répartition bas/haut (numéros 1-25 vs 26-50)":
        "Low/high distribution (numbers 1-25 vs 26-50)",
    "Dispersion (écart entre min et max)":
        "Dispersion (spread between min and max)",
    "Somme totale (plage optimale : ~125)":
        "Total sum (optimal range: ~125)",
    "Détection de suites consécutives":
        "Consecutive sequence detection",
    "Étoiles évaluées séparément (1-12)":
        "Stars evaluated separately (1-12)",
    "Pondération temporelle": "Temporal weighting",
    "Le moteur HYBRIDE applique un système de pondération en deux couches :":
        "The HYBRIDE engine applies a two-layer weighting system:",
    "Couche 1 — Base long terme": "Layer 1 — Long-term base",
    "L'historique complet des tirages EuroMillions est analysé pour établir les fréquences de référence. Cette base assure la stabilité statistique et identifie les tendances profondes.":
        "The complete EuroMillions draw history is analysed to establish reference frequencies. This base ensures statistical stability and identifies deep trends.",
    "Couche 2 — Boost récent": "Layer 2 — Recent boost",
    "Les tirages des 2 dernières années reçoivent un coefficient de pondération plus élevé. Cela permet de capter les éventuelles inflexions de tendance sans perdre la perspective historique.":
        "Draws from the last 2 years receive a higher weighting coefficient. This captures potential trend shifts without losing historical perspective.",
    "Ce double horizon est la raison du nom <strong>« 5 ans + 2 »</strong> : 5 ans de profondeur historique, avec un poids renforcé sur les 2 dernières années.":
        "This dual horizon is the reason for the name <strong>\"5 years + 2\"</strong>: 5 years of historical depth, with reinforced weighting on the last 2 years.",
    "Processus de génération": "Generation process",
    "Le moteur HYBRIDE suit un pipeline en 5 étapes pour chaque grille générée :":
        "The HYBRIDE engine follows a 5-step pipeline for each generated grid:",
    "Collecte": "Collection",
    "Extraction des tirages officiels depuis la base de données":
        "Extraction of official draws from the database",
    "Calcul": "Calculation",
    "Fréquences, retards et pondérations temporelles pour les numéros (1-50) et les étoiles (1-12)":
        "Frequencies, gaps and temporal weightings for numbers (1-50) and stars (1-12)",
    "Génération": "Generation",
    "Sélection probabiliste de combinaisons candidates (5 numéros + 2 étoiles)":
        "Probabilistic selection of candidate combinations (5 numbers + 2 stars)",
    "Scoring": "Scoring",
    "Évaluation multicritère de chaque combinaison candidate":
        "Multi-criteria evaluation of each candidate combination",
    "Sélection": "Selection",
    "Classement par score de conformité et retour des meilleures grilles":
        "Ranking by conformity score and returning the best grids",
    "Limites scientifiques": "Scientific limitations",
    "Avertissement": "Warning",
    "L'EuroMillions est un jeu de hasard. Chaque tirage est statistiquement indépendant. Aucune méthode ne peut prédire les résultats futurs.":
        "EuroMillions is a game of chance. Each draw is statistically independent. No method can predict future results.",
    "La méthodologie « 5 ans + 2 » propose des grilles <em>statistiquement guidées</em>, pas des prédictions.":
        "The \"5 years + 2\" methodology offers <em>statistically guided</em> grids, not predictions.",
    "Probabilité de gain au rang 1 : 1 sur 139 838 160":
        "Probability of winning the jackpot: 1 in 139,838,160",
    "Stack technique": "Tech stack",
    "Moteur": "Engine",
    "Région": "Region",
    "Google Cloud — Union européenne": "Google Cloud — European Union",
    "Utilisez la méthodologie « 5 ans + 2 » pour générer des grilles statistiquement guidées.":
        "Use the \"5 years + 2\" methodology to generate statistically guided grids.",

    # === moteur.html ===
    "Moteur HYBRIDE EuroMillions — Analyse Statistique | LotoIA":
        "HYBRIDE Engine EuroMillions — Statistical Analysis | LotoIA",
    "HYBRIDE : moteur d'analyse statistique hybride pour l'EuroMillions. Architecture cloud-native, 5 algorithmes combinés, API REST temps réel.":
        "HYBRIDE: hybrid statistical analysis engine for EuroMillions. Cloud-native architecture, 5 combined algorithms, real-time REST API.",
    "Moteur HYBRIDE EuroMillions | LotoIA":
        "HYBRIDE Engine EuroMillions | LotoIA",
    "Architecture technique du moteur d'analyse statistique EuroMillions.":
        "Technical architecture of the EuroMillions statistical analysis engine.",
    "Moteur d'analyse statistique hybride pour l'EuroMillions basé sur l'historique des tirages officiels":
        "Hybrid statistical analysis engine for EuroMillions based on official draw history",
    "Analyse fréquentielle sur 5 ans": "Frequency analysis over 5 years",
    "Pondération tendances récentes": "Recent trend weighting",
    "Analyse de conformité multicritère": "Multi-criteria conformity analysis",
    "Génération de grilles optimisées (5+2)": "Optimised grid generation (5+2)",
    "API REST temps réel": "Real-time REST API",
    "Navigateur web moderne": "Modern web browser",
    "Aucun (cloud-based)": "None (cloud-based)",
    "Vue d'ensemble": "Overview",
    "<strong>HYBRIDE</strong> est le moteur de calcul au cœur de la plateforme LotoIA. Il combine plusieurs approches analytiques pour générer des grilles EuroMillions statistiquement optimisées.":
        "<strong>HYBRIDE</strong> is the computational engine at the heart of the LotoIA platform. It combines several analytical approaches to generate statistically optimised EuroMillions grids.",
    "Type": "Type",
    "Moteur hybride (statistiques + heuristiques)":
        "Hybrid engine (statistics + heuristics)",
    "Format": "Format",
    "5 numéros (1-50) + 2 étoiles (1-12)":
        "5 numbers (1-50) + 2 stars (1-12)",
    "« 5 ans + 2 »": "\"5 years + 2\"",
    "Base de données": "Database",
    "Architecture technique": "Technical architecture",
    "Backend API": "Backend API",
    "REST API avec documentation OpenAPI":
        "REST API with OpenAPI documentation",
    "Authentification": "Authentication",
    "Endpoints publics (lecture seule)": "Public endpoints (read-only)",
    "Compression": "Compression",
    "GZip middleware pour optimisation": "GZip middleware for optimisation",
    "Infrastructure Cloud": "Cloud Infrastructure",
    "haute disponibilité": "high availability",
    "Cache headers optimisés pour assets statiques":
        "Optimised cache headers for static assets",
    "Algorithmes": "Algorithms",
    "1. Analyse fréquentielle": "1. Frequency analysis",
    "Calcul des fréquences d'apparition de chaque numéro (1-50) et de chaque étoile (1-12) sur l'historique complet des tirages EuroMillions.":
        "Calculation of the appearance frequency of each number (1-50) and each star (1-12) over the complete EuroMillions draw history.",
    "2. Calcul des retards": "2. Gap calculation",
    "Détermination du nombre de tirages depuis la dernière apparition de chaque numéro et de chaque étoile.":
        "Determination of the number of draws since the last appearance of each number and each star.",
    "3. Pondération temporelle": "3. Temporal weighting",
    "Application de coefficients de pondération privilégiant les 2 dernières années (méthodologie « 5 ans + 2 »).":
        "Application of weighting coefficients favouring the last 2 years (\"5 years + 2\" methodology).",
    "4. Scoring multicritère": "4. Multi-criteria scoring",
    "Évaluation de chaque grille candidate selon :":
        "Evaluation of each candidate grid based on:",
    "Équilibre pair/impair": "Odd/even balance",
    "Répartition bas/haut": "Low/high distribution",
    "Dispersion (écart min-max)": "Dispersion (min-max spread)",
    "Somme totale": "Total sum",
    "Détection de patterns (suites)": "Pattern detection (sequences)",
    "5. Sélection optimale": "5. Optimal selection",
    "Filtrage et classement des grilles par niveau de convergence décroissant.":
        "Filtering and ranking grids by decreasing convergence level.",
    "Endpoints API": "API Endpoints",
    "Modes de génération": "Generation modes",
    "Mode": "Mode",
    "Description": "Description",
    "Privilégie les numéros fréquents (chauds)":
        "Favours frequent (hot) numbers",
    "Équilibre entre fréquences et retards":
        "Balance between frequencies and gaps",
    "Pondération forte sur les tendances récentes":
        "Strong weighting on recent trends",
    "Le moteur HYBRIDE est un outil d'analyse statistique.":
        "The HYBRIDE engine is a statistical analysis tool.",
    "Il ne prédit pas les résultats futurs des tirages. L'EuroMillions reste un jeu de hasard où chaque tirage est indépendant. Probabilité de gagner le jackpot : 1 sur 139 838 160.":
        "It does not predict future draw results. EuroMillions remains a game of chance where each draw is independent. Probability of winning the jackpot: 1 in 139,838,160.",
    "LotoIA n'est pas un opérateur de jeu et ne vend aucune grille.":
        "LotoIA is not a gambling operator and does not sell any grids.",

    # === Existing pages: fuzzy fixes ===
    "de l'EuroMillions": "of the EuroMillions",
    "Analyse statistique, pas prédiction":
        "Statistical analysis, not prediction",
    "Moteur HYBRIDE - Analyse statistique de l'EuroMillions":
        "HYBRIDE Engine - EuroMillions Statistical Analysis",
    "Chat en ligne disponible": "Online chat available",
    "Analyse instantanée": "Instant analysis",
    "LotoIA - Analyse statistique EuroMillions":
        "LotoIA - EuroMillions Statistical Analysis",
    "Outil d analyse statistique descriptive pour grilles EuroMillions":
        "Descriptive statistical analysis tool for EuroMillions grids",
    "Historique des tirages et statistiques EuroMillions":
        "EuroMillions draw history and statistics",
    "Jeu de données statistiques complet des tirages EuroMillions. Numéros gagnants (5 boules + 2 étoiles), fréquences de sortie, écarts entre apparitions, analyse des probabilités et tendances. Données issues des résultats officiels, analysées par l'algorithme HYBRIDE.":
        "Complete EuroMillions draw statistical dataset. Winning numbers (5 balls + 2 stars), appearance frequencies, gaps between appearances, probability analysis and trends. Data sourced from official results, analysed by the HYBRIDE algorithm.",
    "Algorithme statistique HYBRIDE":
        "HYBRIDE statistical algorithm",
    "Fréquence de sortie": "Appearance frequency",
    "Date de tirage": "Draw date",
    "Tirage du ": "Draw of ",
    "Numéro ": "Number ",
    "Étoile ": "Star ",
    "Étoiles (1-12)": "Stars (1-12)",
    "Aucune donnée disponible.": "No data available.",
    "Numéro :": "Number:",
    "Analyser": "Analyse",
    "Étoile :": "Star:",
    "Feuille de route technique — Module EuroMillions":
        "Technical roadmap — EuroMillions Module",

    # === statistiques.html ===
    "statistiques euromillions, data science, analyse de probabilités, historique des tirages, fréquences, étoiles, Europe":
        "euromillions statistics, data science, probability analysis, draw history, frequencies, stars, Europe",
}


def parse_po(text):
    """Parse .po file into entries. Each entry is a dict with keys:
    comments, msgid, msgstr, flags (list), is_obsolete, raw_lines
    """
    entries = []
    current = {"comments": [], "msgid_lines": [], "msgstr_lines": [],
               "flags": [], "phase": "comments", "is_obsolete": False}

    for line in text.splitlines(True):
        stripped = line.rstrip("\n")

        if stripped.startswith("#~"):
            current["is_obsolete"] = True
            current["comments"].append(line)
            continue

        if stripped.startswith("#,"):
            flags = [f.strip() for f in stripped[2:].split(",")]
            current["flags"] = flags
            current["comments"].append(line)
            continue

        if stripped.startswith("#"):
            if current["phase"] == "msgstr" and current["msgid_lines"]:
                # New entry
                entries.append(current)
                current = {"comments": [], "msgid_lines": [], "msgstr_lines": [],
                           "flags": [], "phase": "comments", "is_obsolete": False}
            current["comments"].append(line)
            continue

        if stripped.startswith("msgid "):
            if current["phase"] == "msgstr" and current["msgid_lines"]:
                entries.append(current)
                current = {"comments": current.get("pending_comments", []),
                           "msgid_lines": [], "msgstr_lines": [],
                           "flags": [], "phase": "comments", "is_obsolete": False}
            current["phase"] = "msgid"
            current["msgid_lines"].append(stripped)
            continue

        if stripped.startswith("msgstr "):
            current["phase"] = "msgstr"
            current["msgstr_lines"].append(stripped)
            continue

        if stripped.startswith('"') and stripped.endswith('"'):
            if current["phase"] == "msgid":
                current["msgid_lines"].append(stripped)
            elif current["phase"] == "msgstr":
                current["msgstr_lines"].append(stripped)
            continue

        if stripped == "":
            if current["msgid_lines"]:
                entries.append(current)
                current = {"comments": [], "msgid_lines": [], "msgstr_lines": [],
                           "flags": [], "phase": "comments", "is_obsolete": False}
            continue

    if current["msgid_lines"]:
        entries.append(current)

    return entries


def extract_string(lines):
    """Extract the actual string from msgid/msgstr lines."""
    parts = []
    for line in lines:
        if line.startswith("msgid ") or line.startswith("msgstr "):
            # Extract the quoted part
            idx = line.index('"')
            s = line[idx+1:-1]  # Remove surrounding quotes
        elif line.startswith('"') and line.endswith('"'):
            s = line[1:-1]
        else:
            continue
        parts.append(s)
    return "".join(parts)


def make_msgstr_lines(text):
    """Create msgstr lines from a translated string."""
    if not text:
        return ['msgstr ""']

    # If short enough, single line
    if len(text) < 70:
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return [f'msgstr "{escaped}"']

    # Multi-line: split at spaces near 70 chars
    lines = ['msgstr ""']
    remaining = text
    while remaining:
        if len(remaining) <= 70:
            lines.append(f'"{remaining}"')
            break
        # Find a good split point
        split_at = 70
        while split_at > 30 and remaining[split_at] != ' ':
            split_at -= 1
        if split_at <= 30:
            split_at = 70
        chunk = remaining[:split_at+1]
        remaining = remaining[split_at+1:]
        lines.append(f'"{chunk}"')
    return lines


def rebuild_po(entries, header_text):
    """Rebuild .po file from entries."""
    lines = [header_text.rstrip("\n")]
    lines.append("")

    for entry in entries:
        if entry["is_obsolete"]:
            for c in entry["comments"]:
                lines.append(c.rstrip("\n"))
            lines.append("")
            continue

        for c in entry["comments"]:
            lines.append(c.rstrip("\n"))

        for ml in entry["msgid_lines"]:
            lines.append(ml)

        for ms in entry["msgstr_lines"]:
            lines.append(ms)

        lines.append("")

    return "\n".join(lines) + "\n"


def main():
    text = PO_PATH.read_text(encoding="utf-8")

    # Split header from rest
    # Header is the first msgid ""/msgstr "" block
    header_end = text.find("\n\nmsgid") if "\n\nmsgid" in text else text.find("\n\n#:")
    if header_end < 0:
        header_end = 0
    header_text = text[:header_end]
    rest = text[header_end:]

    entries = parse_po(rest)

    translated = 0
    fuzzy_fixed = 0

    for entry in entries:
        if entry["is_obsolete"]:
            continue

        msgid = extract_string(entry["msgid_lines"])
        msgstr = extract_string(entry["msgstr_lines"])

        if not msgid:  # Skip header
            continue

        needs_translation = (msgstr == "" or "fuzzy" in entry["flags"])

        if needs_translation and msgid in TRANSLATIONS:
            new_tr = TRANSLATIONS[msgid]
            entry["msgstr_lines"] = make_msgstr_lines(new_tr)

            # Remove fuzzy flag
            if "fuzzy" in entry["flags"]:
                entry["flags"].remove("fuzzy")
                fuzzy_fixed += 1
                # Rebuild flag comment
                new_comments = []
                for c in entry["comments"]:
                    if c.rstrip("\n").startswith("#,"):
                        if entry["flags"]:
                            new_comments.append("#, " + ", ".join(entry["flags"]) + "\n")
                        # else: drop the flag line entirely
                    else:
                        new_comments.append(c)
                entry["comments"] = new_comments

            if msgstr == "":
                translated += 1

    # Write result
    output = rebuild_po(entries, header_text)
    PO_PATH.write_text(output, encoding="utf-8")

    print(f"Translations applied: {translated} new, {fuzzy_fixed} fuzzy fixed")
    print(f"Total entries processed: {len([e for e in entries if not e['is_obsolete']])}")


if __name__ == "__main__":
    main()
