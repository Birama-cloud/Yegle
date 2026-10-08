"""Phrases dites au citoyen. Elles sont fixes : le modèle d'IA ne rédige jamais
l'annonce d'une transmission, pour ne rien affirmer que le système n'a pas fait.

ATTENTION : les phrases en wolof doivent être relues par un locuteur avant la démonstration.
"""

MESSAGES = {
    "ask_problem": {
        "fr": "Quel problème voulez-vous signaler ?",
        "wo": "Ban jafe-jafe nga bëgg yëgle ?",
        "en": "What problem would you like to report?",
    },
    "not_report": {
        "fr": "Je sers à signaler un problème dans l'espace public : eau, électricité, route, éclairage, "
              "déchets ou assainissement. Quel problème voulez-vous signaler ?",
        "wo": "Man, jafe-jafe yi am ci mbedd mi laa jëmu : ndox, courant, yoon, lampadaire, mbalit. "
              "Ban jafe-jafe nga bëgg yëgle ?",
        "en": "I help report problems in public spaces: water, electricity, roads, street lighting, waste "
              "or sanitation. What problem would you like to report?",
    },
    "ask_location": {
        "fr": "Où se trouve le problème exactement ? Dites-moi le quartier ou la commune.",
        "wo": "Fan la jafe-jafe bi nekk ? Wax ma gox bi walla commune bi.",
        "en": "Where exactly is the problem? Tell me the neighbourhood or the commune.",
    },
    "ask_commune": {
        "fr": "Dans quelle commune ou quel quartier précisément ?",
        "wo": "Ci ban commune walla ban gox la nekk ?",
        "en": "In which commune or neighbourhood exactly?",
    },
    "summary_known": {
        "fr": "Votre signalement : {description}. Lieu : {place}. Il sera orienté vers {org}. "
              "Voulez-vous l'envoyer ?",
        "wo": "Sa yëgle : {description}. Béréb bi : {place}. Dinañu ko yónnee {org}. Ndax ma yónnee ko ?",
        "en": "Your report: {description}. Location: {place}. It will be sent to {org}. Do you want to send it?",
    },
    "summary_review": {
        "fr": "Votre signalement : {description}. Lieu : {place}. Notre équipe vérifiera quel service doit "
              "le traiter. Voulez-vous l'envoyer ?",
        "wo": "Sa yëgle : {description}. Béréb bi : {place}. Sunu équipe dina seet kan moo ko war a toppatoo. "
              "Ndax ma yónnee ko ?",
        "en": "Your report: {description}. Location: {place}. Our team will check which service should "
              "handle it. Do you want to send it?",
    },
    "done_routed": {
        "fr": "Votre signalement est enregistré et placé dans la file de {org}. Votre référence : {ref}.",
        "wo": "Sa yëgle bindu na te yónnee nañu ko {org}. Sa référence : {ref}.",
        "en": "Your report is saved and placed in the queue of {org}. Your reference: {ref}.",
    },
    "done_review": {
        "fr": "Votre signalement est enregistré. Notre équipe va vérifier quel service doit le traiter. "
              "Votre référence : {ref}.",
        "wo": "Sa yëgle bindu na. Sunu équipe dina seet kan moo ko war a toppatoo. Sa référence : {ref}.",
        "en": "Your report is saved. Our team will check which service should handle it. Your reference: {ref}.",
    },
    "emergency": {
        "fr": "En cas de danger immédiat, appelez aussi les sapeurs-pompiers au 18.",
        "wo": "Su amee musiba, wootel it sapeurs-pompiers yi ci 18.",
        "en": "If there is immediate danger, also call the fire brigade on 18.",
    },
    "correct": {
        "fr": "D'accord. Dites-moi ce qu'il faut corriger.",
        "wo": "Baax na. Wax ma li ma war a soppi.",
        "en": "All right. Tell me what needs to be corrected.",
    },
    "cancelled": {
        "fr": "Signalement annulé. Rien n'a été envoyé.",
        "wo": "Yëgle bi neenal nañu ko. Dara yónneesul.",
        "en": "Report cancelled. Nothing was sent.",
    },
    "unknown_place": {
        "fr": "lieu non précisé",
        "wo": "béréb bi xamuñu ko",
        "en": "location not specified",
    },
    "not_heard": {
        "fr": "Je n'ai pas bien entendu. Pouvez-vous répéter, ou écrire votre message ?",
        "wo": "Dégguma bu baax. Mën nga ko waxaat, walla nga bind ko ?",
        "en": "I didn't catch that. Could you repeat, or type your message?",
    },
    "error": {
        "fr": "Le service est momentanément indisponible. Réessayez dans un instant.",
        "wo": "Service bi dafa jàpp ab diir. Jéemaatal ci kanam tuuti.",
        "en": "The service is temporarily unavailable. Please try again in a moment.",
    },
    "quota": {
        "fr": "Le service a atteint sa limite d'utilisation pour le moment. Réessayez un peu plus tard.",
        "wo": "Service bi dafa jot ci dayo bi mu mën a def léegi. Jéemaatal ci kanam.",
        "en": "The service has reached its usage limit for now. Please try again later.",
    },
}


def msg(key: str, lang: str, **values) -> str:
    text = MESSAGES[key].get(lang) or MESSAGES[key]["fr"]
    return text.format(**values) if values else text
