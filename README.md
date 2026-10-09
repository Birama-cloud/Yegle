# Yëgle

**Dites le problème en wolof ou en français. Yëgle l'envoie au bon service.**

Yëgle (« faire savoir » en wolof) est un assistant vocal open source de signalement citoyen. Pas de formulaire, pas de catégorie à choisir, pas de carte : le citoyen parle, et le système s'occupe du reste.

*« Ndox mi mongui ballë ci mbedd mi, fii ci Grand-Yoff »* devient un signalement de fuite d'eau, localisé à Grand-Yoff et orienté vers le service de l'eau.

Projet réalisé pour le **Open Source × AI Hackathon 2026** de Galsen DEV, track *Civic Tech & services publics*.

## Le problème

Une fuite d'eau, un lampadaire en panne, des égouts qui débordent : le citoyen voit le problème, mais ne sait pas à qui s'adresser. Mairie, ONAS, SENELEC, SEN'EAU ? La plupart des plateformes de signalement lui demandent de remplir un formulaire, de choisir une catégorie et de placer un point sur une carte. Cela écarte ceux qui lisent peu ou qui s'expriment d'abord en wolof.

## La solution

1. Le citoyen appuie sur le micro et parle.
2. L'IA transcrit et extrait le problème, sa catégorie, le lieu et l'urgence.
3. Le lieu est rapproché d'un répertoire de communes. S'il manque, l'assistant pose une seule question.
4. Le moteur d'orientation croise la catégorie et la zone avec la base des organismes, et calcule une confiance.
5. Le citoyen entend un résumé et confirme.
6. Le signalement est enregistré et placé dans la file de l'organisme. Le citoyen reçoit une référence de suivi.

**En cas de doute, rien n'est envoyé au hasard.** Si la confiance est insuffisante, le signalement passe par une vérification humaine plutôt que d'arriver au mauvais service.

Un tableau de bord central permet de filtrer les signalements, de les suivre, de corriger l'organisme et de consulter tout l'historique.

## Utilisation de l'IA

L'IA a un rôle précis et limité : **écouter et comprendre**. Un seul appel au modèle transcrit le vocal, détecte la langue et renvoie une fiche structurée, contrôlée champ par champ avant usage.

L'IA ne choisit **jamais** l'organisme. Cette décision revient à un moteur de règles déterministe, alimenté par `data/organismes.yaml`, parce qu'une compétence administrative ne doit pas dépendre de la mémoire d'un modèle. De même, les phrases annonçant un envoi sont fixes : l'assistant ne peut pas affirmer une transmission qui n'a pas eu lieu.

| Rôle | Modèle ou outil | Type |
|---|---|---|
| Transcription du vocal et extraction (un seul appel) | Gemini, modèle réglé par `GEMINI_MODEL` | API |
| Voix de l'assistant en wolof | Gemini TTS, modèle réglé par `GEMINI_TTS_MODEL` | API |
| Voix de l'assistant en français et en anglais | gTTS | bibliothèque open source appelant un service en ligne |
| Secours si Gemini est saturé (facultatif) | OpenAI, `OPENAI_MODEL` et Whisper | API |
| Aide au développement | Claude (Anthropic) | assistant de programmation |

Sans clé d'API, l'application fonctionne en **mode hors ligne** : compréhension par mots-clés, par écrit uniquement. Ce mode sert de secours et permet de tester tout le parcours.

## Installation

Python 3.10 ou plus récent.

```
git clone https://github.com/Birama-cloud/Yegle.git
cd Yegle
python -m venv .venv
.venv\Scripts\activate           (Windows)
source .venv/bin/activate        (Linux, macOS)
pip install -r requirements-dev.txt     (application et outils de test ; requirements.txt seul pour l'application)
```

Copiez `.env.example` en `.env`, puis renseignez `GEMINI_API_KEY`, `DASHBOARD_PASSWORD` et `ADMIN_API_KEY`.

```
python -m scripts.check_setup    vérifie l'installation et la base de connaissances
pytest                           lance les tests (aucun appel extérieur)
```

## Utilisation

Toutes les commandes se lancent depuis la racine du projet.

```
streamlit run ui/Signaler.py     interface : signalement, suivi, tableau de bord
uvicorn api.main:app --reload    API REST, documentation interactive sur /docs
python -m scripts.demo           fait passer des phrases d'exemple dans la chaîne
python -m scripts.demo --save    idem, en enregistrant (pour peupler le tableau de bord)
```

## À faire avant la démonstration

1. **Vérifier les fiches organismes.** Les compétences de `data/organismes.yaml` sont des hypothèses de départ, livrées sans date de vérification. Tant qu'une fiche n'est pas vérifiée, ses signalements passent en vérification humaine. Pour chaque organisme : contrôler la compétence sur une source officielle, remplir `source_url` et `last_verified_at`.
2. **Faire relire le wolof** de `app/messages.py` par un locuteur.
3. **Contrôler les coordonnées** des communes : `python -m scripts.verifier_zones`.

## Ajouter un organisme

Aucune ligne de code à modifier : ajoutez une fiche dans `data/organismes.yaml` (domaines, zones couvertes, règles d'orientation, mode de transmission), puis lancez `python -m scripts.check_setup`. Les catégories (`data/categories.yaml`) et les zones (`data/zones.yaml`) se configurent de la même façon.

## Structure

```
config/settings.py        réglages (lus dans .env)
data/                     base de connaissances : organismes, catégories, zones
app/
  llm/client.py           appels Gemini, modèle de secours, bascule OpenAI
  understanding.py        compréhension du message et contrôle de la sortie du modèle
  zones.py                reconnaissance du lieu
  routing.py              moteur d'orientation institutionnelle
  assistant.py            orchestration du parcours
  storage.py              base SQLite et historiques
  transmission.py         envoi à l'organisme
  messages.py, voice.py   phrases de l'assistant et synthèse vocale
api/main.py               API REST
ui/                       pages Streamlit
scripts/                  vérification, démonstration, contrôle des zones
tests/                    tests automatiques
docs/ARCHITECTURE.md      architecture, modèle de données, API, sécurité, évolution
```

## Vie privée et sécurité

- L'enregistrement vocal n'est pas conservé ; seule la transcription l'est.
- Aucun nom ni numéro de téléphone n'est demandé.
- Le suivi public n'affiche que le statut, la catégorie, l'organisme et les dates.
- L'organisme est recalculé par le serveur à l'envoi ; une valeur venue du client est ignorée.
- La destination d'une transmission vient uniquement de la base de connaissances.
- Chaque décision d'orientation et chaque correction manuelle est tracée avec son auteur.

## Limites connues

- Périmètre : région de Dakar, 19 communes de la ville de Dakar reconnues précisément.
- Position GPS acceptée par l'API mais pas encore proposée dans l'interface.
- Un seul mot de passe pour le tableau de bord, sans compte par organisme.
- Transmission : file interne et webhook. L'e-mail n'est pas réalisé.
- Aucun organisme n'est partenaire à ce jour : c'est un prototype prêt à leur être proposé.

## Origine et dépendances

Le client d'appel au modèle (`app/llm/client.py`) et la synthèse vocale (`app/voice.py`) sont repris et adaptés de TEKTALMA, un prototype antérieur du même auteur (septembre 2026). Tout le reste a été écrit pour ce hackathon.

Dépendances principales : Streamlit, FastAPI, google-genai, PyYAML, httpx, gTTS, pytest.

## Équipe

- Birama TOGOLA
- *à compléter*

## Licence

MIT, voir `LICENSE`.
