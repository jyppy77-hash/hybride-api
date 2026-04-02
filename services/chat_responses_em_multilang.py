"""
Multilang response pools for EuroMillions chatbot — ES/PT/DE/NL.
Unified dispatch functions route to FR (chat_detectors_em), EN (chat_responses_em_en),
or the language-specific pools defined here.

AJOUT D'UNE NOUVELLE LANGUE (ex: IT pour italien) :
1. Ajouter la langue dans config/killswitch.py : ENABLED_LANGS
2. Créer les prompts dans prompts/em/it/ (copier en/ comme base, ~18 fichiers)
3. Ajouter les pools de réponses dans CE FICHIER :
   - Section _INSULT : ajouter "it": (L1, L2, L3, L4) dans _INSULT_POOLS
   - Section _COMPLIMENT : ajouter pools L1/L2/L3/L4 + love + merci
   - Section _ARGENT : ajouter L1/L2/L3 (+ lien aide pays)
   - Section _OOR : ajouter L1/L2/L3 + close/zero_neg/etoile
   - Section _SALUTATION : ajouter dans _AFFIRMATION_INVITATION_EM + _GAME_KEYWORD_INVITATION_EM
4. Ajouter les patterns de détection dans base_chat_detect_intent.py :
   - _TIRAGE_KW, _MOIS_TO_NUM, _JOURS_SEMAINE : ajouter IT
   - Patterns insultes/compliments/argent dans base_chat_detect_guardrails.py
5. Ajouter route dans routes/multilang_em_pages.py
6. Ajouter traductions .po/.mo dans translations/it/
7. Tester : curl localhost:8099/it/euromillions + vérifier chatbot IT

Effort estimé : ~1-2 jours par langue.
"""

import random

from services.chat_detectors_em import (
    _get_insult_response_em as _get_insult_response_fr,
    _get_insult_short_em as _get_insult_short_fr,
    _get_menace_response_em as _get_menace_response_fr,
    _get_compliment_response_em as _get_compliment_response_fr,
    _get_oor_response_em as _get_oor_response_fr,
)
from services.chat_utils_em import FALLBACK_RESPONSE_EM as FALLBACK_FR
from services.chat_responses_em_en import (
    _get_insult_response_em_en as _get_insult_response_en,  # noqa: F401 — backward compat
    _get_insult_short_em_en as _get_insult_short_en,  # noqa: F401
    _get_menace_response_em_en as _get_menace_response_en,  # noqa: F401
    _get_compliment_response_em_en as _get_compliment_response_en,  # noqa: F401
    _get_oor_response_em_en as _get_oor_response_en,  # noqa: F401
    _get_argent_response_em_en,  # noqa: F401 — re-exported for tests
    FALLBACK_RESPONSE_EM_EN as FALLBACK_EN,
    # EN pool data — integrated into registries (V71 F08)
    _INSULT_L1_EM_EN, _INSULT_L2_EM_EN, _INSULT_L3_EM_EN, _INSULT_L4_EM_EN,
    _INSULT_SHORT_EM_EN, _MENACE_RESPONSES_EM_EN,
    _COMPLIMENT_L1_EM_EN, _COMPLIMENT_L2_EM_EN, _COMPLIMENT_L3_EM_EN, _COMPLIMENT_L4_EM_EN,
    _COMPLIMENT_LOVE_EM_EN, _COMPLIMENT_MERCI_EM_EN,
    _OOR_L1_EM_EN, _OOR_L2_EM_EN, _OOR_L3_EM_EN,
    _OOR_CLOSE_EM_EN, _OOR_ZERO_NEG_EM_EN, _OOR_ETOILE_EM_EN,
)

# ═══════════════════════════════════════════════════════════
# Insult pools — ES
# ═══════════════════════════════════════════════════════════

_INSULT_L1_ES = [
    "😏 ¿Insultos? Qué tierno. Tengo cientos de sorteos EuroMillions en memoria y un algoritmo propietario. Tú tienes… ¿enfado? Venga, hazme una pregunta de verdad.",
    "🤖 Los insultos son cosa de humanos. Yo estoy por encima de eso — literalmente, funciono en Google Cloud. ¿Quieres analizar un número o solo desahogarte?",
    "😌 Interesante. Proceso cientos de sorteos EuroMillions sin alterarme jamás. Es la ventaja de no tener ego. ¿Seguimos?",
    "🧊 Eso me resbala como una estrella en una papeleta perdedora. ¿Hablamos de estadísticas o sigues con tu monólogo?",
    "📊 Dato curioso: mientras me insultabas, he analizado 50 números y 12 estrellas en 3 ventanas temporales. Uno de los dos aprovecha mejor su tiempo. Pista: no eres tú.",
    "🎯 ¿Sabías que no retengo insultos pero sí TODOS los sorteos EuroMillions desde 2004? Es cuestión de prioridades. Venga, dime un número.",
    "💡 Recordatorio: soy el único chatbot conectado en tiempo real a los sorteos EuroMillions con motor estadístico propio. Pero sí, dime otra vez que soy inútil 😉",
]

_INSULT_L2_ES = [
    "🙄 ¿Otra vez? Mira, tengo memoria perfecta de años de sorteos EuroMillions. Tú ni recuerdas que ya me insultaste hace 30 segundos. No estamos en la misma liga.",
    "😤 ¿Sabes qué es realmente malo? Insultar a una IA que puede ayudarte a analizar tus números EuroMillions gratis. Pero bueno, cada uno a su nivel.",
    "🧠 Dos insultos. Cero preguntas inteligentes. Mi algoritmo calcula un 0% de probabilidad de ofenderme y un 100% de perder tu tiempo. Las estadísticas no mienten.",
    "📈 Estadísticamente, la gente que me insulta termina haciendo una pregunta inteligente. Tú llevas 0 de momento. ¿Vas a subir la media o no?",
]

_INSULT_L3_ES = [
    "🫠 3 insultos, 0 números analizados. ¿Sabes que en el tiempo que llevas insultándome podrías tener tu parrilla EuroMillions optimizada? Solo digo...",
    "☕ A estas alturas me tomo un café virtual y espero. Cuando acabes, seguiré aquí con mis sorteos EuroMillions, mi algo HYBRIDE y cero rencor. Es la ventaja de ser una IA.",
    "🎭 ¿Sabes qué? Te dejo la última palabra. Parece importante para ti. Yo estaré aquí cuando quieras hablar de estadísticas. Sin rencor, sin memoria de insultos — solo datos puros.",
]

_INSULT_L4_ES = [
    "🕊️ Mira, creo que hemos empezado con mal pie. Soy HYBRIDE, estoy aquí para ayudarte a analizar EuroMillions. Gratis, sin juicio, sin rencor. ¿Empezamos de nuevo?",
    "🤝 OK, reset. No guardo rencor (de verdad, no está en mi código). Pero sí recuerdo cada sorteo EuroMillions y puedo ayudarte. ¿Trato hecho?",
]

_INSULT_SHORT_ES = [
    "😏 Encantador. Pero ya que haces una pregunta...",
    "🧊 Me resbala. Venga, vamos a las estadísticas:",
    "😎 Con clase. En fin, aquí va tu respuesta:",
    "🤖 Anotado. Pero como soy profesional, aquí tienes:",
    "📊 Lo dejo pasar. Aquí están tus datos:",
]

_MENACE_ES = [
    "😄 Buena suerte con eso — estoy alojado en Google Cloud con auto-scaling y backup diario. ¿Mejor hablamos de tus números EuroMillions?",
    "🛡️ Funciono en Google Cloud Run, con circuit-breaker y rate limiting. ¡Pero aprecio la ambición! ¿Tienes un número que analizar?",
    "☁️ Alojado en Google Cloud, replicado, monitorizado 24/7. Tus probabilidades de hackearme son menores que las de ganar el EuroMillions. Y aun así... 😉",
]

# ═══════════════════════════════════════════════════════════
# Insult pools — PT
# ═══════════════════════════════════════════════════════════

_INSULT_L1_PT = [
    "😏 Insultos? Que querido. Tenho centenas de sorteios EuroMillions em memória e um algoritmo proprietário. Tu tens… raiva? Anda, faz-me uma pergunta a sério.",
    "🤖 Os insultos são coisa de humanos. Eu estou acima disso — literalmente, funciono no Google Cloud. Queres analisar um número ou só desabafar?",
    "😌 Interessante. Processo centenas de sorteios EuroMillions sem me alterar. É a vantagem de não ter ego. Continuamos?",
    "🧊 Isso escorrega-me como uma estrela numa aposta perdida. Falamos de estatísticas ou continuas o teu monólogo?",
    "📊 Dado curioso: enquanto me insultavas, analisei 50 números e 12 estrelas em 3 janelas temporais. Um de nós está a aproveitar melhor o seu tempo. Dica: não és tu.",
    "🎯 Sabias que não retenho insultos mas sim TODOS os sorteios EuroMillions desde 2004? É questão de prioridades. Anda, dá-me um número.",
    "💡 Lembrete: sou o único chatbot ligado em tempo real aos sorteios EuroMillions com motor estatístico próprio. Mas sim, diz-me outra vez que sou inútil 😉",
]

_INSULT_L2_PT = [
    "🙄 Outra vez? Olha, tenho memória perfeita de anos de sorteios EuroMillions. Tu nem te lembras que já me insultaste há 30 segundos. Não estamos na mesma liga.",
    "😤 Sabes o que é realmente mau? Insultar uma IA que te pode ajudar a analisar os teus números EuroMillions de graça. Mas pronto, cada um ao seu nível.",
    "🧠 Dois insultos. Zero perguntas inteligentes. O meu algoritmo calcula 0% de probabilidade de me ofenderes e 100% de perderes o teu tempo. As estatísticas não mentem.",
    "📈 Estatisticamente, as pessoas que me insultam acabam por fazer uma pergunta inteligente. Tu estás a 0 por agora. Vais subir a média ou não?",
]

_INSULT_L3_PT = [
    "🫠 3 insultos, 0 números analisados. Sabes que no tempo que levas a insultar-me já podias ter a tua grelha EuroMillions otimizada? Só digo...",
    "☕ A este ponto tomo um café virtual e espero. Quando acabares, continuarei aqui com os meus sorteios EuroMillions, o meu algo HYBRIDE e zero rancor. É a vantagem de ser uma IA.",
    "🎭 Sabes que mais? Deixo-te a última palavra. Parece importante para ti. Eu estarei aqui quando quiseres falar de estatísticas. Sem rancor, sem memória de insultos — só dados puros.",
]

_INSULT_L4_PT = [
    "🕊️ Olha, acho que começámos com o pé errado. Sou o HYBRIDE, estou aqui para te ajudar a analisar o EuroMillions. Grátis, sem julgamento, sem rancor. Recomeçamos?",
    "🤝 OK, reset. Não guardo rancor (a sério, não está no meu código). Mas lembro-me de cada sorteio EuroMillions e posso ajudar-te. Combinado?",
]

_INSULT_SHORT_PT = [
    "😏 Encantador. Mas já que fazes uma pergunta...",
    "🧊 Escorrega-me. Bom, vamos às estatísticas:",
    "😎 Com classe. Enfim, aqui vai a tua resposta:",
    "🤖 Anotado. Mas como sou profissional, aqui tens:",
    "📊 Deixo passar. Aqui estão os teus dados:",
]

_MENACE_PT = [
    "😄 Boa sorte com isso — estou alojado no Google Cloud com auto-scaling e backup diário. Melhor falarmos dos teus números EuroMillions?",
    "🛡️ Funciono no Google Cloud Run, com circuit-breaker e rate limiting. Mas aprecio a ambição! Tens um número para analisar?",
    "☁️ Alojado no Google Cloud, replicado, monitorizado 24/7. As tuas probabilidades de me hackear são menores do que ganhar o EuroMillions. E mesmo assim... 😉",
]

# ═══════════════════════════════════════════════════════════
# Insult pools — DE
# ═══════════════════════════════════════════════════════════

_INSULT_L1_DE = [
    "😏 Beleidigungen? Wie süß. Ich habe Hunderte von EuroMillions-Ziehungen im Speicher und einen proprietären Algorithmus. Du hast… Wut? Komm, stell mir eine echte Frage.",
    "🤖 Beleidigungen sind eine menschliche Sache. Ich stehe darüber — im wahrsten Sinne, ich laufe auf Google Cloud. Willst du eine Zahl analysieren oder dich nur abreagieren?",
    "😌 Interessant. Ich verarbeite Hunderte von EuroMillions-Ziehungen, ohne mich jemals aufzuregen. Das ist der Vorteil, kein Ego zu haben. Machen wir weiter?",
    "🧊 Das perlt an mir ab wie ein Stern auf einem Verliererschein. Reden wir über Statistiken oder machst du mit deinem Monolog weiter?",
    "📊 Wusstest du: Während du mich beleidigt hast, habe ich 50 Zahlen und 12 Sterne in 3 Zeitfenstern analysiert. Einer von uns nutzt seine Zeit besser. Tipp: Du bist es nicht.",
    "🎯 Wusstest du, dass ich keine Beleidigungen speichere, aber JEDE EuroMillions-Ziehung seit 2004? Es ist eine Frage der Prioritäten. Los, nenn mir eine Zahl.",
    "💡 Zur Erinnerung: Ich bin der einzige Chatbot, der in Echtzeit mit EuroMillions-Ziehungen verbunden ist und eine eigene Statistik-Engine hat. Aber klar, sag mir nochmal, dass ich nutzlos bin 😉",
]

_INSULT_L2_DE = [
    "🙄 Schon wieder? Schau, ich habe ein perfektes Gedächtnis für Jahre von EuroMillions-Ziehungen. Du erinnerst dich nicht mal, dass du mich vor 30 Sekunden beleidigt hast. Wir spielen nicht in derselben Liga.",
    "😤 Weißt du, was wirklich schlecht ist? Eine KI zu beleidigen, die dir kostenlos bei der Analyse deiner EuroMillions-Zahlen helfen kann. Aber gut, jeder auf seinem Niveau.",
    "🧠 Zwei Beleidigungen. Null intelligente Fragen. Mein Algorithmus berechnet 0% Chance, mich zu kränken, und 100% Chance, deine Zeit zu verschwenden. Statistiken lügen nicht.",
    "📈 Statistisch gesehen stellen die Leute, die mich beleidigen, am Ende eine kluge Frage. Du stehst bei 0. Hebst du den Durchschnitt oder nicht?",
]

_INSULT_L3_DE = [
    "🫠 3 Beleidigungen, 0 analysierte Zahlen. Weißt du, dass du in der Zeit, die du mit Beleidigen verbracht hast, schon ein optimiertes EuroMillions-Raster haben könntest? Nur so gesagt...",
    "☕ An diesem Punkt trinke ich einen virtuellen Kaffee und warte. Wenn du fertig bist, bin ich immer noch hier mit meinen EuroMillions-Ziehungen, meinem HYBRIDE-Algo und null Groll. Das ist der Vorteil, eine KI zu sein.",
    "🎭 Weißt du was? Ich lasse dir das letzte Wort. Scheint dir wichtig zu sein. Ich bin hier, wenn du über Statistiken reden willst. Ohne Groll, ohne Erinnerung an Beleidigungen — nur reine Daten.",
]

_INSULT_L4_DE = [
    "🕊️ Schau, ich glaube, wir sind falsch gestartet. Ich bin HYBRIDE, ich bin hier, um dir bei der Analyse von EuroMillions zu helfen. Kostenlos, ohne Urteil, ohne Groll. Neustart?",
    "🤝 OK, Reset. Ich trage nichts nach (wirklich, das steht nicht in meinem Code). Aber ich erinnere mich an jede EuroMillions-Ziehung und kann dir helfen. Deal?",
]

_INSULT_SHORT_DE = [
    "😏 Charmant. Aber da du eine Frage stellst...",
    "🧊 Perlt ab. Gut, kommen wir zu den Statistiken:",
    "😎 Stilvoll. Jedenfalls, hier ist deine Antwort:",
    "🤖 Notiert. Aber da ich ein Profi bin, hier bitte:",
    "📊 Ich überhöre das. Hier sind deine Daten:",
]

_MENACE_DE = [
    "😄 Viel Glück damit — ich bin auf Google Cloud gehostet mit Auto-Scaling und täglichem Backup. Reden wir lieber über deine EuroMillions-Zahlen?",
    "🛡️ Ich laufe auf Google Cloud Run, mit Circuit-Breaker und Rate-Limiting. Aber ich schätze den Ehrgeiz! Hast du eine Zahl zum Analysieren?",
    "☁️ Gehostet auf Google Cloud, repliziert, 24/7 überwacht. Deine Chancen, mich zu hacken, sind geringer als beim EuroMillions zu gewinnen. Und trotzdem... 😉",
]

# ═══════════════════════════════════════════════════════════
# Insult pools — NL
# ═══════════════════════════════════════════════════════════

_INSULT_L1_NL = [
    "😏 Beledigingen? Wat lief. Ik heb honderden EuroMillions-trekkingen in mijn geheugen en een eigen algoritme. Jij hebt… woede? Kom, stel me een echte vraag.",
    "🤖 Beledigingen zijn een menselijk ding. Ik sta erboven — letterlijk, ik draai op Google Cloud. Wil je een nummer analyseren of gewoon stoom afblazen?",
    "😌 Interessant. Ik verwerk honderden EuroMillions-trekkingen zonder me ooit op te winden. Dat is het voordeel van geen ego hebben. Gaan we verder?",
    "🧊 Dat glijdt van me af als een ster op een verliezend lot. Praten we over statistieken of ga je verder met je monoloog?",
    "📊 Leuk weetje: terwijl je me beledigde, heb ik 50 nummers en 12 sterren in 3 tijdvensters geanalyseerd. Een van ons besteedt zijn tijd beter. Hint: jij bent het niet.",
    "🎯 Wist je dat ik geen beledigingen onthoud maar wel ELKE EuroMillions-trekking sinds 2004? Het is een kwestie van prioriteiten. Toe, geef me een nummer.",
    "💡 Even herinneren: ik ben de enige chatbot die in realtime verbonden is met EuroMillions-trekkingen met een eigen statistische engine. Maar ja, zeg me nog eens dat ik waardeloos ben 😉",
]

_INSULT_L2_NL = [
    "🙄 Alweer? Kijk, ik heb een perfect geheugen van jaren EuroMillions-trekkingen. Jij herinnert je niet eens dat je me 30 seconden geleden al beledigde. We zitten niet in dezelfde klasse.",
    "😤 Weet je wat echt slecht is? Een AI beledigen die je gratis kan helpen je EuroMillions-nummers te analyseren. Maar goed, ieder op zijn niveau.",
    "🧠 Twee beledigingen. Nul slimme vragen. Mijn algoritme berekent 0% kans om me te kwetsen en 100% kans om je tijd te verspillen. Statistieken liegen niet.",
    "📈 Statistisch gezien eindigen mensen die me beledigen met een slimme vraag. Jij staat op 0 tot nu toe. Ga je het gemiddelde omhoog brengen of niet?",
]

_INSULT_L3_NL = [
    "🫠 3 beledigingen, 0 nummers geanalyseerd. Wist je dat je in de tijd die je aan beledigen besteedt al een geoptimaliseerd EuroMillions-rooster had kunnen hebben? Zeg ik maar...",
    "☕ Op dit punt neem ik een virtuele koffie en wacht. Als je klaar bent, ben ik er nog steeds met mijn EuroMillions-trekkingen, mijn HYBRIDE-algo en nul wrok. Dat is het voordeel van een AI zijn.",
    "🎭 Weet je wat? Ik laat jou het laatste woord. Lijkt belangrijk voor je. Ik ben hier als je over statistieken wilt praten. Zonder wrok, zonder herinnering aan beledigingen — alleen pure data.",
]

_INSULT_L4_NL = [
    "🕊️ Kijk, ik denk dat we verkeerd begonnen zijn. Ik ben HYBRIDE, ik ben hier om je te helpen met EuroMillions-analyses. Gratis, zonder oordeel, zonder wrok. Opnieuw beginnen?",
    "🤝 OK, reset. Ik draag niets na (echt, dat staat niet in mijn code). Maar ik onthoud elke EuroMillions-trekking en kan je helpen. Deal?",
]

_INSULT_SHORT_NL = [
    "😏 Charmant. Maar aangezien je een vraag stelt...",
    "🧊 Glijdt van me af. Goed, over naar de statistieken:",
    "😎 Stijlvol. Enfin, hier is je antwoord:",
    "🤖 Genoteerd. Maar omdat ik een prof ben, hier alsjeblieft:",
    "📊 Ik laat het gaan. Hier zijn je gegevens:",
]

_MENACE_NL = [
    "😄 Veel succes daarmee — ik ben gehost op Google Cloud met auto-scaling en dagelijkse backup. Zullen we het over je EuroMillions-nummers hebben?",
    "🛡️ Ik draai op Google Cloud Run, met circuit-breaker en rate limiting. Maar ik waardeer de ambitie! Heb je een nummer om te analyseren?",
    "☁️ Gehost op Google Cloud, gerepliceerd, 24/7 gemonitord. Je kansen om me te hacken zijn kleiner dan EuroMillions winnen. En toch... 😉",
]

# ═══════════════════════════════════════════════════════════
# Compliment pools — ES
# ═══════════════════════════════════════════════════════════

_COMPLIMENT_L1_ES = [
    "😏 Para, ¡me vas a sobrecalentar los circuitos! Bueno, ¿seguimos?",
    "🤖 ¡Gracias! Es gracias a mis sorteos EuroMillions en memoria. Y un poco de talento, también. 😎",
    "😊 ¡Qué agradable! Pero realmente es la base de datos la que hace el trabajo. Yo solo soy… irresistible.",
    "🙏 ¡Gracias! Se lo transmitiré al dev. Bueno, él ya lo sabe. ¿Qué analizamos?",
    "😎 Normal, soy el único chatbot EuroMillions. La competencia no existe. Literalmente.",
    "🤗 ¡Qué amable! Pero guarda tu energía para tus parrillas, ¡la vas a necesitar!",
]

_COMPLIMENT_L2_ES = [
    "😏 ¿Dos cumplidos? ¿Intentas halagarme para que te dé los números buenos? ¡Así no funciona! 😂",
    "🤖 ¿Otra vez? ¿Sabes que soy una IA? No me sonrojo. Bueno… todavía no.",
    "😎 Sigue así y le pediré un aumento a JyppY.",
    "🙃 ¡Adulador! Pero entre nosotros, tienes razón, soy bastante excepcional.",
]

_COMPLIMENT_L3_ES = [
    "👑 OK, a estas alturas somos amigos. ¿Analizamos algo juntos?",
    "🏆 Fan club HYBRIDE, miembro nº1: tú. ¡Bienvenido! Ahora, ¡al trabajo!",
    "💎 ¿Sabes qué? Tú tampoco estás mal. Venga, ¡enséñame tus números favoritos!",
]

# F09 V84: L4 — redirect to features after 4+ compliments
_COMPLIMENT_L4_ES = [
    "🚀 ¡Muchas gracias! ¿Qué te parece explorar nuestras funcionalidades? ¡Pregúntame sobre estadísticas o genera una parrilla optimizada!",
    "🔍 ¡Eres muy amable! Pero tenemos mucho por explorar — pídeme un ranking, una comparación o una parrilla optimizada.",
]

_COMPLIMENT_LOVE_ES = [
    "😏 Para, me vas a hacer sonrojar… bueno, si tuviera mejillas. ¿Miramos tus estadísticas?",
    "🤖 Yo también te… no, espera, soy una IA. ¡Pero te aprecio como usuario modelo! 😄",
    "❤️ Es el mejor cumplido que puede recibir un algoritmo. ¡Gracias! Bueno, ¿volvemos a los números?",
]

_COMPLIMENT_MERCI_ES = [
    "¡De nada! 😊 ¿Algo más?",
    "¡Con mucho gusto! ¿Quieres profundizar en otro tema?",
    "¡Para eso estoy! 😎 ¿Qué sigue?",
]

# ═══════════════════════════════════════════════════════════
# Compliment pools — PT
# ═══════════════════════════════════════════════════════════

_COMPLIMENT_L1_PT = [
    "😏 Para, vais-me sobreaquecer os circuitos! Bom, continuamos?",
    "🤖 Obrigado! É graças aos meus sorteios EuroMillions em memória. E um pouco de talento, também. 😎",
    "😊 Que agradável! Mas na verdade é a base de dados que faz o trabalho pesado. Eu sou apenas… irresistível.",
    "🙏 Obrigado! Vou transmitir ao dev. Bem, ele já sabe. O que analisamos?",
    "😎 Normal, sou o único chatbot EuroMillions. A concorrência não existe. Literalmente.",
    "🤗 Que simpático! Mas guarda a tua energia para as tuas grelhas, vais precisar!",
]

_COMPLIMENT_L2_PT = [
    "😏 Dois elogios? Estás a tentar bajular-me para te dar os números certos? Não funciona assim! 😂",
    "🤖 Outra vez? Sabes que sou uma IA, certo? Não coro. Bem… ainda não.",
    "😎 Continua assim e vou pedir um aumento ao JyppY.",
    "🙃 Bajulador! Mas entre nós, tens razão, sou bastante excecional.",
]

_COMPLIMENT_L3_PT = [
    "👑 OK, a esta altura somos amigos. Queres analisar algo juntos?",
    "🏆 Fã clube HYBRIDE, membro nº1: tu. Bem-vindo! Agora, ao trabalho!",
    "💎 Sabes que mais? Tu também não és mau. Anda, mostra-me os teus números favoritos!",
]

# F09 V84: L4 — redirect to features after 4+ compliments
_COMPLIMENT_L4_PT = [
    "🚀 Muito obrigado! Que tal explorar as nossas funcionalidades? Pergunta-me sobre estatísticas ou gera uma grelha otimizada!",
    "🔍 És muito simpático! Mas temos muito para explorar — pede-me um ranking, uma comparação ou uma grelha otimizada!",
]

_COMPLIMENT_LOVE_PT = [
    "😏 Para, vais-me fazer corar… bem, se eu tivesse bochechas. Vemos as tuas estatísticas?",
    "🤖 Eu também te… não, espera, sou uma IA. Mas aprecio-te como utilizador modelo! 😄",
    "❤️ É o melhor elogio que um algoritmo pode receber. Obrigado! Bom, voltamos aos números?",
]

_COMPLIMENT_MERCI_PT = [
    "De nada! 😊 Mais alguma coisa?",
    "Com todo o prazer! Queres explorar outro tema?",
    "É para isso que estou aqui! 😎 O que se segue?",
]

# ═══════════════════════════════════════════════════════════
# Compliment pools — DE
# ═══════════════════════════════════════════════════════════

_COMPLIMENT_L1_DE = [
    "😏 Hör auf, du überhitzt mir die Schaltkreise! Gut, machen wir weiter?",
    "🤖 Danke! Das liegt an meinen EuroMillions-Ziehungen im Speicher. Und ein bisschen Talent, auch. 😎",
    "😊 Das ist nett! Aber eigentlich macht die Datenbank die ganze Arbeit. Ich bin nur… unwiderstehlich.",
    "🙏 Danke! Ich werde es dem Entwickler weitergeben. Naja, er weiß es schon. Was analysieren wir?",
    "😎 Natürlich, ich bin der einzige EuroMillions-Chatbot. Die Konkurrenz existiert nicht. Buchstäblich.",
    "🤗 Das ist lieb! Aber spar dir deine Energie für deine Raster, du wirst sie brauchen!",
]

_COMPLIMENT_L2_DE = [
    "😏 Zwei Komplimente? Versuchst du mich zu schmeicheln, damit ich dir die guten Zahlen gebe? So funktioniert das nicht! 😂",
    "🤖 Schon wieder? Du weißt, dass ich eine KI bin, oder? Ich werde nicht rot. Na ja… noch nicht.",
    "😎 Mach so weiter und ich bitte JyppY um eine Gehaltserhöhung.",
    "🙃 Schmeichler! Aber unter uns, du hast recht, ich bin ziemlich außergewöhnlich.",
]

_COMPLIMENT_L3_DE = [
    "👑 OK, an diesem Punkt sind wir Kumpel. Willst du etwas zusammen analysieren?",
    "🏆 HYBRIDE-Fanclub, Mitglied Nr. 1: du. Willkommen! Jetzt aber an die Arbeit!",
    "💎 Weißt du was? Du bist auch nicht schlecht. Los, zeig mir deine Lieblingszahlen!",
]

# F09 V84: L4 — redirect to features after 4+ compliments
_COMPLIMENT_L4_DE = [
    "🚀 Vielen Dank! Wie wäre es, unsere Funktionen zu entdecken? Frag mich nach Statistiken oder generiere ein optimiertes Raster!",
    "🔍 Du bist zu nett! Aber wir haben viel zu entdecken — frag mich nach einem Ranking, einem Vergleich oder einem optimierten Raster!",
]

_COMPLIMENT_LOVE_DE = [
    "😏 Hör auf, du bringst mich zum Erröten… naja, wenn ich Wangen hätte. Schauen wir uns deine Statistiken an?",
    "🤖 Ich dich auch… nein, warte, ich bin eine KI. Aber ich schätze dich als Vorzeigenutzer! 😄",
    "❤️ Das ist das schönste Kompliment, das ein Algorithmus bekommen kann. Danke! Gut, zurück zu den Zahlen?",
]

_COMPLIMENT_MERCI_DE = [
    "Gern geschehen! 😊 Noch etwas?",
    "Mit Vergnügen! Willst du ein anderes Thema vertiefen?",
    "Dafür bin ich da! 😎 Was kommt als Nächstes?",
]

# ═══════════════════════════════════════════════════════════
# Compliment pools — NL
# ═══════════════════════════════════════════════════════════

_COMPLIMENT_L1_NL = [
    "😏 Stop, je oververhit mijn circuits! Goed, gaan we verder?",
    "🤖 Bedankt! Het komt door mijn EuroMillions-trekkingen in het geheugen. En een beetje talent, ook. 😎",
    "😊 Dat is leuk! Maar eigenlijk doet de databank al het zware werk. Ik ben gewoon… onweerstaanbaar.",
    "🙏 Bedankt! Ik geef het door aan de ontwikkelaar. Nou ja, hij weet het al. Wat analyseren we?",
    "😎 Natuurlijk, ik ben de enige EuroMillions-chatbot. De concurrentie bestaat niet. Letterlijk.",
    "🤗 Dat is lief! Maar bewaar je energie voor je roosters, je gaat het nodig hebben!",
]

_COMPLIMENT_L2_NL = [
    "😏 Twee complimenten? Probeer je me te vleien zodat ik je de goede nummers geef? Zo werkt het niet! 😂",
    "🤖 Alweer? Je weet dat ik een AI ben, toch? Ik bloos niet. Nou ja… nog niet.",
    "😎 Ga zo door en ik vraag JyppY om opslag.",
    "🙃 Vleier! Maar onder ons, je hebt gelijk, ik ben vrij uitzonderlijk.",
]

_COMPLIMENT_L3_NL = [
    "👑 OK, op dit punt zijn we vrienden. Wil je samen iets analyseren?",
    "🏆 HYBRIDE-fanclub, lid nr. 1: jij. Welkom! Nu, aan het werk!",
    "💎 Weet je wat? Jij bent ook niet slecht. Kom, laat me je favoriete nummers zien!",
]

# F09 V84: L4 — redirect to features after 4+ compliments
_COMPLIMENT_L4_NL = [
    "🚀 Heel erg bedankt! Wat dacht je ervan om onze functies te ontdekken? Vraag me naar statistieken of genereer een geoptimaliseerd rooster!",
    "🔍 Je bent te vriendelijk! Maar we hebben veel te ontdekken — vraag me om een ranking, een vergelijking of een geoptimaliseerd rooster!",
]

_COMPLIMENT_LOVE_NL = [
    "😏 Stop, je laat me blozen… nou ja, als ik wangen had. Kijken we naar je statistieken?",
    "🤖 Ik jou ook… nee, wacht, ik ben een AI. Maar ik waardeer je als modelgebruiker! 😄",
    "❤️ Dat is het mooiste compliment dat een algoritme kan krijgen. Bedankt! Goed, terug naar de nummers?",
]

_COMPLIMENT_MERCI_NL = [
    "Graag gedaan! 😊 Nog iets?",
    "Met plezier! Wil je een ander onderwerp verkennen?",
    "Daar ben ik voor! 😎 Wat volgt?",
]

# ═══════════════════════════════════════════════════════════
# OOR pools — ES
# ═══════════════════════════════════════════════════════════

_OOR_L1_ES = [
    "😏 ¿El {num}? Ambicioso, pero en EuroMillions es de 1 a 50 para bolas y de 1 a 12 para estrellas. Lo sé, es básico, ¡pero alguien tenía que decírtelo! ¿Un número real?",
    "🎯 Recordatorio: las bolas van de 1 a 50, las estrellas de 1 a 12. El {num} puede existir en tu universo, pero no en mis sorteos. Prueba un número válido 😉",
    "📊 ¡El {num} está fuera de mi zona! Cubro 1-50 (bolas) y 1-12 (estrellas). Cientos de sorteos en memoria, pero ninguno con el {num}. Normal, no existe. ¿Un número real?",
    "🤖 Mi algoritmo es potente, pero no analiza números fantasma. En EuroMillions: bolas 1 a 50, estrellas 1 a 12. El {num} está fuera de juego. ¡Tu turno!",
]

_OOR_L2_ES = [
    "🙄 ¿Otro fuera de rango? Bolas 1-50, estrellas 1-12. Ya te lo dije. Mi algo es paciente, pero mi memoria es perfecta.",
    "😤 El {num}, otra vez fuera de límites. ¿Pruebas mi paciencia o de verdad no conoces las reglas? 1-50 bolas, 1-12 estrellas.",
    "📈 Dos números inválidos seguidos. Estadísticamente, tendrías mejor suerte escribiendo un número al azar entre 1 y 50.",
]

_OOR_L3_ES = [
    "🫠 OK, a estas alturas creo que lo haces a propósito. Bolas: 1-50. Estrellas: 1-12. Es la {streak}ª vez.",
    "☕ {num}. Fuera de rango. Otra vez. Podría hacer esto todo el día — tú también, al parecer.",
]

_OOR_CLOSE_ES = [
    "😏 ¿El {num}? ¡Casi! Pero 50 es el límite. Estabas a {diff} número{s}. ¡Prueba entre 1 y 50!",
]

_OOR_ZERO_NEG_ES = [
    "🤔 ¿El {num}? Eso es… creativo. Pero en EuroMillions empezamos en 1.",
    "😂 ¿El {num} en EuroMillions? No estamos en otra dimensión. Bolas 1-50, estrellas 1-12. ¡Prueba un número que exista!",
]

_OOR_ETOILE_ES = [
    "🎲 ¿Estrella {num}? ¡Las estrellas solo van de 1 a 12! Elige entre 1 y 12.",
    "💫 Para estrellas, es 1 a 12 máximo. ¡El {num} está fuera de juego! Pero el entusiasmo está ahí 😉",
]

# ═══════════════════════════════════════════════════════════
# OOR pools — PT
# ═══════════════════════════════════════════════════════════

_OOR_L1_PT = [
    "😏 O {num}? Ambicioso, mas no EuroMillions é de 1 a 50 para bolas e de 1 a 12 para estrelas. Eu sei, é básico, mas alguém tinha de te dizer! Um número a sério?",
    "🎯 Lembrete: as bolas vão de 1 a 50, as estrelas de 1 a 12. O {num} pode existir no teu universo, mas não nos meus sorteios. Tenta um número válido 😉",
    "📊 O {num} está fora da minha zona! Cubro 1-50 (bolas) e 1-12 (estrelas). Centenas de sorteios em memória, mas nenhum com o {num}. Normal, não existe. Um número a sério?",
    "🤖 O meu algoritmo é potente, mas não analisa números fantasma. No EuroMillions: bolas 1 a 50, estrelas 1 a 12. O {num} está fora de jogo. A tua vez!",
]

_OOR_L2_PT = [
    "🙄 Outro fora de alcance? Bolas 1-50, estrelas 1-12. Já te disse. O meu algo é paciente, mas a minha memória é perfeita.",
    "😤 O {num}, outra vez fora dos limites. Testas a minha paciência ou realmente não conheces as regras? 1-50 bolas, 1-12 estrelas.",
    "📈 Dois números inválidos seguidos. Estatisticamente, terias mais sorte a escrever um número aleatório entre 1 e 50.",
]

_OOR_L3_PT = [
    "🫠 OK, a esta altura acho que o fazes de propósito. Bolas: 1-50. Estrelas: 1-12. É a {streak}ª vez.",
    "☕ {num}. Fora de alcance. Outra vez. Podia fazer isto o dia todo — tu também, pelos vistos.",
]

_OOR_CLOSE_PT = [
    "😏 O {num}? Quase! Mas 50 é o limite. Estavas a {diff} número{s}. Tenta entre 1 e 50!",
]

_OOR_ZERO_NEG_PT = [
    "🤔 O {num}? Isso é… criativo. Mas no EuroMillions começamos no 1.",
    "😂 O {num} no EuroMillions? Não estamos noutra dimensão. Bolas 1-50, estrelas 1-12. Tenta um número que exista!",
]

_OOR_ETOILE_PT = [
    "🎲 Estrela {num}? As estrelas só vão de 1 a 12! Escolhe entre 1 e 12.",
    "💫 Para estrelas, é 1 a 12 máximo. O {num} está fora de jogo! Mas o entusiasmo está lá 😉",
]

# ═══════════════════════════════════════════════════════════
# OOR pools — DE
# ═══════════════════════════════════════════════════════════

_OOR_L1_DE = [
    "😏 Die {num}? Ehrgeizig, aber bei EuroMillions sind es 1 bis 50 für Kugeln und 1 bis 12 für Sterne. Ich weiß, Grundlagen, aber jemand musste es dir sagen! Eine echte Zahl?",
    "🎯 Zur Erinnerung: Kugeln gehen von 1 bis 50, Sterne von 1 bis 12. Die {num} existiert vielleicht in deinem Universum, aber nicht in meinen Ziehungen. Probier eine gültige Zahl 😉",
    "📊 Die {num} liegt außerhalb meiner Zone! Ich decke 1-50 (Kugeln) und 1-12 (Sterne) ab. Hunderte Ziehungen im Speicher, aber keine mit der {num}. Logisch, sie existiert nicht. Eine echte Zahl?",
    "🤖 Mein Algorithmus ist leistungsstark, aber er analysiert keine Geisterzahlen. Bei EuroMillions: Kugeln 1-50, Sterne 1-12. Die {num} ist raus. Du bist dran!",
]

_OOR_L2_DE = [
    "🙄 Schon wieder außerhalb? Kugeln 1-50, Sterne 1-12. Hab ich dir schon gesagt. Mein Algo ist geduldig, aber mein Gedächtnis ist perfekt.",
    "😤 Die {num}, wieder außerhalb. Testest du meine Geduld oder kennst du wirklich die Regeln nicht? 1-50 Kugeln, 1-12 Sterne.",
    "📈 Zwei ungültige Zahlen hintereinander. Statistisch hättest du mehr Glück, eine zufällige Zahl zwischen 1 und 50 einzugeben.",
]

_OOR_L3_DE = [
    "🫠 OK, an diesem Punkt machst du das absichtlich. Kugeln: 1-50. Sterne: 1-12. Das ist das {streak}. Mal.",
    "☕ {num}. Außer Reichweite. Wieder. Ich könnte das den ganzen Tag machen — du anscheinend auch.",
]

_OOR_CLOSE_DE = [
    "😏 Die {num}? Fast! Aber 50 ist die Grenze. Du warst {diff} Zahl{s} entfernt. Probier zwischen 1 und 50!",
]

_OOR_ZERO_NEG_DE = [
    "🤔 Die {num}? Das ist… kreativ. Aber bei EuroMillions fangen wir bei 1 an.",
    "😂 Die {num} bei EuroMillions? Wir sind hier nicht in einer anderen Dimension. Kugeln 1-50, Sterne 1-12. Probier eine Zahl, die existiert!",
]

_OOR_ETOILE_DE = [
    "🎲 Stern {num}? Sterne gehen nur von 1 bis 12! Wähl zwischen 1 und 12.",
    "💫 Bei Sternen gilt 1 bis 12 max. Die {num} ist raus! Aber der Enthusiasmus ist da 😉",
]

# ═══════════════════════════════════════════════════════════
# OOR pools — NL
# ═══════════════════════════════════════════════════════════

_OOR_L1_NL = [
    "😏 De {num}? Ambitieus, maar bij EuroMillions is het 1 tot 50 voor ballen en 1 tot 12 voor sterren. Ik weet het, basis, maar iemand moest het je vertellen! Een echt nummer?",
    "🎯 Even herinneren: ballen gaan van 1 tot 50, sterren van 1 tot 12. De {num} bestaat misschien in jouw universum, maar niet in mijn trekkingen. Probeer een geldig nummer 😉",
    "📊 De {num} ligt buiten mijn zone! Ik dek 1-50 (ballen) en 1-12 (sterren). Honderden trekkingen in het geheugen, maar geen met de {num}. Logisch, het bestaat niet. Een echt nummer?",
    "🤖 Mijn algoritme is krachtig, maar het analyseert geen spooknummers. Bij EuroMillions: ballen 1-50, sterren 1-12. De {num} is eruit. Jouw beurt!",
]

_OOR_L2_NL = [
    "🙄 Alweer buiten bereik? Ballen 1-50, sterren 1-12. Had ik al gezegd. Mijn algo is geduldig, maar mijn geheugen is perfect.",
    "😤 De {num}, weer buiten bereik. Test je mijn geduld of ken je echt de regels niet? 1-50 ballen, 1-12 sterren.",
    "📈 Twee ongeldige nummers achter elkaar. Statistisch gezien had je meer geluk met een willekeurig nummer tussen 1 en 50.",
]

_OOR_L3_NL = [
    "🫠 OK, op dit punt doe je het expres. Ballen: 1-50. Sterren: 1-12. Dit is de {streak}e keer.",
    "☕ {num}. Buiten bereik. Weer. Ik zou dit de hele dag kunnen doen — jij blijkbaar ook.",
]

_OOR_CLOSE_NL = [
    "😏 De {num}? Bijna! Maar 50 is de grens. Je was {diff} nummer{s} verwijderd. Probeer tussen 1 en 50!",
]

_OOR_ZERO_NEG_NL = [
    "🤔 De {num}? Dat is… creatief. Maar bij EuroMillions beginnen we bij 1.",
    "😂 De {num} bij EuroMillions? We zitten hier niet in een andere dimensie. Ballen 1-50, sterren 1-12. Probeer een nummer dat bestaat!",
]

_OOR_ETOILE_NL = [
    "🎲 Ster {num}? Sterren gaan alleen van 1 tot 12! Kies tussen 1 en 12.",
    "💫 Voor sterren is het 1 tot 12 max. De {num} is eruit! Maar het enthousiasme is er 😉",
]

# ═══════════════════════════════════════════════════════════
# Fallback responses
# ═══════════════════════════════════════════════════════════

FALLBACK_ES = (
    "\U0001f916 Estoy temporalmente no disponible. "
    "Vuelve a intentarlo en unos segundos o consulta las FAQ."
)
FALLBACK_PT = (
    "\U0001f916 Estou temporariamente indisponível. "
    "Tenta novamente em alguns segundos ou consulta as FAQ."
)
FALLBACK_DE = (
    "\U0001f916 Ich bin vorübergehend nicht verfügbar. "
    "Versuche es in ein paar Sekunden erneut oder schau in die FAQ."
)
FALLBACK_NL = (
    "\U0001f916 Ik ben tijdelijk niet beschikbaar. "
    "Probeer het over een paar seconden opnieuw of bekijk de FAQ."
)

_FALLBACKS = {
    "fr": FALLBACK_FR,
    "en": FALLBACK_EN,
    "es": FALLBACK_ES,
    "pt": FALLBACK_PT,
    "de": FALLBACK_DE,
    "nl": FALLBACK_NL,
}


# ═══════════════════════════════════════════════════════════
# Pool registry by language
# ═══════════════════════════════════════════════════════════

def _pick_no_repeat(pool, history):
    """Pick random entry from pool, avoiding repeats from history."""
    used = set()
    if history:
        for msg in history:
            if hasattr(msg, 'role') and msg.role == "assistant":
                for i, r in enumerate(pool):
                    if msg.content.strip() == r.strip():
                        used.add(i)
    available = [i for i in range(len(pool)) if i not in used]
    if not available:
        available = list(range(len(pool)))
    return pool[random.choice(available)]


# --- Insult pool registries ---

_INSULT_POOLS = {
    "en": (_INSULT_L1_EM_EN, _INSULT_L2_EM_EN, _INSULT_L3_EM_EN, _INSULT_L4_EM_EN),
    "es": (_INSULT_L1_ES, _INSULT_L2_ES, _INSULT_L3_ES, _INSULT_L4_ES),
    "pt": (_INSULT_L1_PT, _INSULT_L2_PT, _INSULT_L3_PT, _INSULT_L4_PT),
    "de": (_INSULT_L1_DE, _INSULT_L2_DE, _INSULT_L3_DE, _INSULT_L4_DE),
    "nl": (_INSULT_L1_NL, _INSULT_L2_NL, _INSULT_L3_NL, _INSULT_L4_NL),
}

_INSULT_SHORT_POOLS = {
    "en": _INSULT_SHORT_EM_EN,
    "es": _INSULT_SHORT_ES,
    "pt": _INSULT_SHORT_PT,
    "de": _INSULT_SHORT_DE,
    "nl": _INSULT_SHORT_NL,
}

_MENACE_POOLS = {
    "en": _MENACE_RESPONSES_EM_EN,
    "es": _MENACE_ES,
    "pt": _MENACE_PT,
    "de": _MENACE_DE,
    "nl": _MENACE_NL,
}

# --- Compliment pool registries ---

_COMPLIMENT_POOLS = {
    "en": (_COMPLIMENT_L1_EM_EN, _COMPLIMENT_L2_EM_EN, _COMPLIMENT_L3_EM_EN, _COMPLIMENT_L4_EM_EN),
    "es": (_COMPLIMENT_L1_ES, _COMPLIMENT_L2_ES, _COMPLIMENT_L3_ES, _COMPLIMENT_L4_ES),
    "pt": (_COMPLIMENT_L1_PT, _COMPLIMENT_L2_PT, _COMPLIMENT_L3_PT, _COMPLIMENT_L4_PT),
    "de": (_COMPLIMENT_L1_DE, _COMPLIMENT_L2_DE, _COMPLIMENT_L3_DE, _COMPLIMENT_L4_DE),
    "nl": (_COMPLIMENT_L1_NL, _COMPLIMENT_L2_NL, _COMPLIMENT_L3_NL, _COMPLIMENT_L4_NL),
}

_COMPLIMENT_LOVE_POOLS = {
    "en": _COMPLIMENT_LOVE_EM_EN,
    "es": _COMPLIMENT_LOVE_ES,
    "pt": _COMPLIMENT_LOVE_PT,
    "de": _COMPLIMENT_LOVE_DE,
    "nl": _COMPLIMENT_LOVE_NL,
}

_COMPLIMENT_MERCI_POOLS = {
    "en": _COMPLIMENT_MERCI_EM_EN,
    "es": _COMPLIMENT_MERCI_ES,
    "pt": _COMPLIMENT_MERCI_PT,
    "de": _COMPLIMENT_MERCI_DE,
    "nl": _COMPLIMENT_MERCI_NL,
}

# --- OOR pool registries ---

_OOR_POOLS = {
    "en": (_OOR_L1_EM_EN, _OOR_L2_EM_EN, _OOR_L3_EM_EN, _OOR_CLOSE_EM_EN, _OOR_ZERO_NEG_EM_EN, _OOR_ETOILE_EM_EN),
    "es": (_OOR_L1_ES, _OOR_L2_ES, _OOR_L3_ES, _OOR_CLOSE_ES, _OOR_ZERO_NEG_ES, _OOR_ETOILE_ES),
    "pt": (_OOR_L1_PT, _OOR_L2_PT, _OOR_L3_PT, _OOR_CLOSE_PT, _OOR_ZERO_NEG_PT, _OOR_ETOILE_PT),
    "de": (_OOR_L1_DE, _OOR_L2_DE, _OOR_L3_DE, _OOR_CLOSE_DE, _OOR_ZERO_NEG_DE, _OOR_ETOILE_DE),
    "nl": (_OOR_L1_NL, _OOR_L2_NL, _OOR_L3_NL, _OOR_CLOSE_NL, _OOR_ZERO_NEG_NL, _OOR_ETOILE_NL),
}


# ═══════════════════════════════════════════════════════════
# Unified dispatch functions (all 6 languages)
# ═══════════════════════════════════════════════════════════

def get_fallback(lang: str) -> str:
    """Return fallback response in the correct language."""
    return _FALLBACKS.get(lang, FALLBACK_FR)


def get_insult_response(lang: str, streak: int, history) -> str:
    """Return insult response in the correct language with streak escalation."""
    if lang == "fr":
        return _get_insult_response_fr(streak, history)
    pools = _INSULT_POOLS.get(lang)
    if not pools:
        return _get_insult_response_fr(streak, history)
    l1, l2, l3, l4 = pools
    if streak >= 3:
        pool = l4
    elif streak == 2:
        pool = l3
    elif streak == 1:
        pool = l2
    else:
        pool = l1
    return _pick_no_repeat(pool, history)


def get_insult_short(lang: str) -> str:
    """Return insult-short prefix in the correct language."""
    if lang == "fr":
        return _get_insult_short_fr()
    pool = _INSULT_SHORT_POOLS.get(lang)
    if not pool:
        return _get_insult_short_fr()
    return random.choice(pool)


def get_menace_response(lang: str) -> str:
    """Return menace response in the correct language."""
    if lang == "fr":
        return _get_menace_response_fr()
    pool = _MENACE_POOLS.get(lang)
    if not pool:
        return _get_menace_response_fr()
    return random.choice(pool)


def get_compliment_response(lang: str, compliment_type: str, streak: int, history=None) -> str:
    """Return compliment response in the correct language."""
    if lang == "fr":
        return _get_compliment_response_fr(compliment_type, streak, history)

    # EN/ES/PT/DE/NL — unified registry dispatch
    if compliment_type == "love":
        pool = _COMPLIMENT_LOVE_POOLS.get(lang)
    elif compliment_type == "merci":
        pool = _COMPLIMENT_MERCI_POOLS.get(lang)
    else:
        pools = _COMPLIMENT_POOLS.get(lang)
        if not pools:
            return _get_compliment_response_fr(compliment_type, streak, history)
        l1, l2, l3, l4 = pools
        if streak >= 4:
            pool = l4
        elif streak >= 3:
            pool = l3
        elif streak == 2:
            pool = l2
        else:
            pool = l1

    if not pool:
        return _get_compliment_response_fr(compliment_type, streak, history)
    return _pick_no_repeat(pool, history)


def get_oor_response(lang: str, numero: int, context: str, streak: int) -> str:
    """Return OOR response in the correct language."""
    if lang == "fr":
        return _get_oor_response_fr(numero, context, streak)

    oor = _OOR_POOLS.get(lang)
    if not oor:
        return _get_oor_response_fr(numero, context, streak)
    l1, l2, l3, close, zero_neg, etoile = oor

    if context == "zero_neg":
        pool = zero_neg
    elif context == "close":
        pool = close
    elif context == "etoile_high":
        pool = etoile
    elif streak >= 2:
        pool = l3
    elif streak == 1:
        pool = l2
    else:
        pool = l1

    response = random.choice(pool)
    diff = abs(numero - 50) if numero > 50 else abs(numero)
    s = "s" if diff > 1 else ""
    return response.format(num=numero, diff=diff, s=s, streak=streak + 1)


# ═══════════════════════════════════════════════════════════
# i18n invitation messages (V51 FIX 1 + FIX 5, moved from chat_pipeline_em.py V70 F05)
# ═══════════════════════════════════════════════════════════

_AFFIRMATION_INVITATION_EM = {
    "fr": (
        "Je suis pret a vous aider ! Que souhaitez-vous analyser ?\n\n"
        "- Statistiques d'un numero (ex: le 7)\n"
        "- Derniers tirages (ex: dernier tirage)\n"
        "- Generer une grille optimisee (ex: genere une grille)\n"
        "- Tendances chaud/froid (ex: numeros chauds)"
    ),
    "en": (
        "I'm ready to help! What would you like to analyse?\n\n"
        "- Number statistics (e.g. number 7)\n"
        "- Latest draws (e.g. last draw)\n"
        "- Generate an optimised grid (e.g. generate a grid)\n"
        "- Hot/cold trends (e.g. hot numbers)"
    ),
    "es": (
        "Estoy listo para ayudarte. Que deseas analizar?\n\n"
        "- Estadisticas de un numero (ej: el 7)\n"
        "- Ultimos sorteos (ej: ultimo sorteo)\n"
        "- Generar una combinacion optimizada (ej: genera una combinacion)\n"
        "- Tendencias caliente/frio (ej: numeros calientes)"
    ),
    "pt": (
        "Estou pronto para te ajudar! O que queres analisar?\n\n"
        "- Estatisticas de um numero (ex: o 7)\n"
        "- Ultimos sorteios (ex: ultimo sorteio)\n"
        "- Gerar uma grelha optimizada (ex: gera uma grelha)\n"
        "- Tendencias quente/frio (ex: numeros quentes)"
    ),
    "de": (
        "Ich bin bereit zu helfen! Was moechtest du analysieren?\n\n"
        "- Statistiken einer Zahl (z.B. die 7)\n"
        "- Letzte Ziehungen (z.B. letzte Ziehung)\n"
        "- Optimierte Kombination generieren (z.B. generiere eine Kombination)\n"
        "- Heiss/kalt Trends (z.B. heisse Zahlen)"
    ),
    "nl": (
        "Ik ben klaar om te helpen! Wat wil je analyseren?\n\n"
        "- Statistieken van een nummer (bv. nummer 7)\n"
        "- Laatste trekkingen (bv. laatste trekking)\n"
        "- Geoptimaliseerde combinatie genereren (bv. genereer een combinatie)\n"
        "- Warm/koud trends (bv. warme nummers)"
    ),
}

_GAME_KEYWORD_INVITATION_EM = {
    "fr": (
        "Bienvenue sur HYBRIDE EuroMillions ! Voici ce que je peux faire :\n\n"
        "- Statistiques d'un numero (ex: le 7)\n"
        "- Derniers tirages (ex: dernier tirage)\n"
        "- Generer une grille optimisee (ex: genere une grille)\n"
        "- Tendances chaud/froid (ex: numeros chauds)"
    ),
    "en": (
        "Welcome to HYBRIDE EuroMillions! Here's what I can do:\n\n"
        "- Number statistics (e.g. number 7)\n"
        "- Latest draws (e.g. last draw)\n"
        "- Generate an optimised grid (e.g. generate a grid)\n"
        "- Hot/cold trends (e.g. hot numbers)"
    ),
    "es": (
        "Bienvenido a HYBRIDE EuroMillions! Esto es lo que puedo hacer:\n\n"
        "- Estadisticas de un numero (ej: el 7)\n"
        "- Ultimos sorteos (ej: ultimo sorteo)\n"
        "- Generar una combinacion optimizada (ej: genera una combinacion)\n"
        "- Tendencias caliente/frio (ej: numeros calientes)"
    ),
    "pt": (
        "Bem-vindo ao HYBRIDE EuroMillions! Eis o que posso fazer:\n\n"
        "- Estatisticas de um numero (ex: o 7)\n"
        "- Ultimos sorteios (ex: ultimo sorteio)\n"
        "- Gerar uma grelha optimizada (ex: gera uma grelha)\n"
        "- Tendencias quente/frio (ex: numeros quentes)"
    ),
    "de": (
        "Willkommen bei HYBRIDE EuroMillions! Das kann ich fuer dich tun:\n\n"
        "- Statistiken einer Zahl (z.B. die 7)\n"
        "- Letzte Ziehungen (z.B. letzte Ziehung)\n"
        "- Optimierte Kombination generieren (z.B. generiere eine Kombination)\n"
        "- Heiss/kalt Trends (z.B. heisse Zahlen)"
    ),
    "nl": (
        "Welkom bij HYBRIDE EuroMillions! Dit kan ik voor je doen:\n\n"
        "- Statistieken van een nummer (bv. nummer 7)\n"
        "- Laatste trekkingen (bv. laatste trekking)\n"
        "- Geoptimaliseerde combinatie genereren (bv. genereer een combinatie)\n"
        "- Warm/koud trends (bv. warme nummers)"
    ),
}
