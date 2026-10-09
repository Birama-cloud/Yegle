# Évaluation de la compréhension

Ce dossier sert à mesurer, sur de vrais messages, si Yëgle comprend le problème, reconnaît le lieu et choisit le bon organisme.

## 1. Enregistrer les vocaux

- Un fichier par signalement, dans `evaluation/audio/` : formats wav, mp3, m4a, ogg ou webm.
- Des phrases naturelles, comme un habitant les dirait, avec le lieu ou sans.
- Plusieurs personnes si possible : hommes, femmes, accents et débits différents.
- Demandez l'accord de chaque personne enregistrée. Les fichiers audio restent sur votre ordinateur : ils sont exclus du dépôt par `.gitignore`.

## 2. Remplir `evaluation/cas.csv`

Une ligne par cas, colonnes séparées par des points-virgules. Le fichier s'ouvre dans Excel.

| Colonne | Contenu |
|---|---|
| `fichier` | Nom du fichier audio, par exemple `fuite-01.m4a`. Vide pour un cas écrit. |
| `langue` | `wo`, `fr` ou `en`. |
| `texte` | Ce qui est dit, écrit par vous. Obligatoire pour un cas écrit, conseillé pour un vocal. |
| `categorie` | La catégorie attendue. |
| `zone` | Le lieu attendu, ou vide si la personne ne dit pas de lieu. |
| `organisme` | L'organisme attendu, `VERIFICATION` si le cas doit partir en vérification humaine, ou vide pour ne pas le contrôler. |

Pour voir les valeurs acceptées :

```
python -m scripts.evaluer --valeurs
```

Remplissez les colonnes attendues avant de lancer l'évaluation, sans regarder ce que répond le système. Sinon la mesure ne vaut rien.

## 3. Lancer

```
python -m scripts.evaluer                 tous les cas, vocal quand un fichier est indiqué
python -m scripts.evaluer --mode texte    uniquement la colonne texte, sans passer par la voix
```

Le résultat s'affiche et un rapport est écrit dans `docs/EVALUATION.md`. Rien n'est enregistré dans la base des signalements.

Comparer les deux modes est instructif : si le texte est bien compris mais pas le vocal, l'erreur vient de la transcription.

## Lire le résultat honnêtement

- Sous une trentaine de cas, un pourcentage est une indication, pas une preuve.
- Indiquez toujours le nombre de cas et de locuteurs à côté du taux.
- Gardez les échecs dans le rapport : ils montrent les limites réelles et ce qu'il reste à améliorer.
