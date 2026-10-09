# Refonte de l'interface de Yëgle

Tu vas refaire l'habillage visuel de l'application Streamlit de ce projet, d'après deux maquettes fournies en image dans ce dossier :

- `docs/maquettes/accueil-citoyen.png` : style sombre, pour les pages destinées au citoyen.
- `docs/maquettes/espace-services.png` : style clair, blanc et bleu marine, pour l'espace services.

Commence par ouvrir ces deux images et par lire les fichiers actuels du dossier `ui/` et `.streamlit/config.toml`. Ne te fie pas à ta mémoire du code : il a pu changer.

## Périmètre

À modifier : `ui/common.py`, `ui/Signaler.py`, `ui/pages/1_Suivre_mon_signalement.py`, `ui/pages/2_Tableau_de_bord.py`, `.streamlit/config.toml`.

À ne pas modifier : tout le dossier `app/`, `api/`, `config/`, `data/`, `tests/`. Seule l'apparence change. Le comportement doit rester identique : les trois étapes (décrire, vérifier, envoyé), les boutons Envoyer, Corriger et Annuler, le mode hors ligne sans micro, la mémorisation de la langue et de l'option voix, la connexion par mot de passe, les filtres, le changement de statut, la réorientation et les historiques.

Avant de coder, présente-moi ton plan en quelques lignes et attends mon accord.

## Deux styles, un seul produit

Les pages citoyen (Signaler, Suivre) sont sombres. L'espace services est clair. Les deux partagent le logo, la police et le bleu, pour qu'on reconnaisse la même application.

Police partout : Outfit, chargée depuis Google Fonts, avec `system-ui, sans-serif` en secours. Ne force pas cette police sur les icônes de Streamlit.

Difficulté à anticiper : le thème de `config.toml` est global. Je recommande un thème de base clair, adapté à l'espace services qui contient beaucoup de composants natifs (listes déroulantes, formulaires, onglets, carte), et de passer les pages citoyen en sombre par du CSS ciblé, puisqu'elles ont peu de composants natifs. Vérifie que chaque composant natif des pages sombres reste lisible : zone de saisie, choix de langue, interrupteur, boutons, champ de référence, messages d'information et d'erreur, lecteur audio.

## Style sombre : pages citoyen

Couleurs :

| Rôle | Valeur |
|---|---|
| Fond | `#070B1A` |
| Halo central | `rgba(88,101,255,.42)`, dégradé radial derrière le micro |
| Halo haut gauche | `rgba(0,214,201,.20)` |
| Halo bas droite | `rgba(178,92,255,.26)` |
| Texte principal | `#EEF2FF` |
| Texte secondaire | `#C3CBEA` (plus clair que sur la maquette, pour le contraste) |
| Dégradé de marque | `#19E3D0` vers `#8A8CFF` vers `#C77DFF` |
| Carte en verre | fond `rgba(255,255,255,.055)`, bordure `1px rgba(255,255,255,.10)`, rayon 20px |
| Pastille turquoise | fond `rgba(25,227,208,.10)`, bordure `rgba(25,227,208,.30)`, texte `#8FF3EA` |

Barre du haut : logo à gauche (carré arrondi en dégradé de marque avec une icône de micro, puis « Yëgle »), menu au centre dans une capsule en verre avec l'entrée active en blanc, lien « Espace services » à droite dans une capsule à bordure fine. Masque l'en-tête, la barre latérale et le pied de page de Streamlit, comme aujourd'hui.

Page Signaler, état d'accueil, de haut en bas et centré :

1. Pastille turquoise « Wolof, français et anglais ».
2. Titre sur deux lignes, très grand, gras : « Dites le problème. » en blanc, puis « Yëgle prévient le bon service. » avec le dégradé de marque appliqué au texte.
3. Sous-titre : « Fuite d'eau, coupure de courant, route abîmée, ordures. Pas de formulaire à remplir : parlez, on s'occupe du reste. »
4. Le micro : c'est l'élément central. Un grand cercle à fond bleu nuit, entouré d'un anneau en dégradé de marque et d'un halo lumineux, avec une icône de micro blanche. Des barres d'onde verticales en dégradé de chaque côté. Habille le bouton de `st.audio_input` pour obtenir ce rendu, comme le fait déjà le CSS actuel avec le bouton jaune. Pendant l'enregistrement, l'anneau passe au rouge avec une pulsation. Respecte `prefers-reduced-motion`.
5. Légende « Appuyez et parlez ».
6. Barre de saisie en verre « Ou écrivez votre message… ». Sur la maquette, le choix de langue (Auto, Wolof, Français, English) est dans la barre : dans Streamlit, place-le juste en dessous, avec l'interrupteur « Réponses à voix haute ».
7. En bas, quatre cartes en verre sur une ligne : un exemple, puis les trois étapes « Décrivez », « Vérifiez », « Suivez » avec une icône et une phrase chacune. La carte d'exemple contient la phrase « Ndox mi mongui ballë ci mbedd mi, fii ci Grand-Yoff », puis « Fuite d'eau », « Grand-Yoff » et « SEN'EAU » en étiquettes. Écris ce texte exactement ainsi, sans le corriger.

Sur téléphone, les quatre cartes passent en une colonne et le titre réduit. La page doit s'ouvrir en haut, sans défilement automatique vers le bas : garde le mécanisme actuel qui place la zone de saisie dans un conteneur tant que la conversation n'a pas commencé.

Page Signaler, conversation et récépissé : je n'ai pas de maquette. Décline le même style. Bulles du citoyen en dégradé bleu-violet alignées à droite, bulles de Yëgle en verre alignées à gauche. Le récépissé « Vérifiez votre signalement » et la carte de référence sont des cartes en verre, avec le service destinataire mis en évidence par une bordure en dégradé. Le bouton principal « Envoyer le signalement » est en dégradé turquoise vers bleu avec un texte foncé ; « Corriger » et « Annuler » sont à bordure fine.

Page Suivre : même style sombre. Champ de référence en verre, carte de résultat en verre, frise des étapes avec les points en dégradé pour les étapes franchies.

## Style clair : espace services

Couleurs :

| Rôle | Valeur |
|---|---|
| Fond de page | `#F4F7FC` |
| Bleu marine (texte, bloc organisme) | `#0B1F4B` |
| Bandeau du haut | dégradé `#0B1F4B` vers `#123A8C` vers `#1E5BD8` |
| Bleu d'action | `#1E5BD8` |
| Cartes | blanc, bordure `#DFE7F5`, rayon 20px, ombre légère |
| Texte secondaire | `#5B6B8C` |
| Ligne sélectionnée | fond `#EAF1FF`, trait bleu à gauche |
| Statut Orienté | fond `#E3ECFF`, texte `#123A8C` |
| Statut En vérification | fond `#FFF1CC`, texte `#7A4B00` |
| Statut En cours | fond `#DDF3FB`, texte `#075E7D` |
| Statut Résolu | fond `#DDF5E7`, texte `#0B6B3D` |
| Statut Rejeté | fond `#FBE4E2`, texte `#B3261E` |

Disposition :

1. Bandeau bleu marine en haut, sur toute la largeur, qui contient la barre de menu (texte blanc), le titre « Signalements », la date, et à droite l'alerte jaune clair sur les signalements à vérifier.
2. Quatre compteurs en cartes blanches qui chevauchent le bas du bandeau, chacun avec une icône dans un carré coloré : Signalements reçus, À vérifier, Chez les services, Résolus.
3. Deux colonnes. À gauche, une carte avec les filtres puis la liste. À droite, une carte de détail du signalement sélectionné.
4. Liste : colonnes Référence, Reçu, Statut, Catégorie avec icône, Lieu, Organisme, Confiance avec une petite barre. La barre est bleue, et jaune sous le seuil de confiance. « À déterminer » et « Non précisé » en gris.
5. Détail : référence et statut en tête, le message d'origine du citoyen dans un encadré gris clair, lieu reconnu et priorité dans deux petites cases, puis l'organisme recommandé dans un bloc bleu marine avec les trois barres de confiance (problème, lieu, organisme), l'historique, et en bas les actions « Changer le statut » (bouton bleu) et « Réorienter » (bouton à bordure).

Contraintes Streamlit à traiter franchement :

- Un tableau dessiné en HTML n'est pas cliquable. Garde une liste déroulante pour choisir la référence affichée dans le détail, placée en tête de la colonne de droite, et surligne la ligne correspondante dans la liste.
- Les formulaires de changement de statut et de réorientation restent de vrais formulaires Streamlit, dans la colonne de droite, sous le bloc organisme. Les historiques complets peuvent rester dans des onglets sous les deux colonnes.
- L'écran de connexion et l'écran « espace verrouillé » prennent le même style clair.

Les chiffres visibles sur la maquette sont inventés. Affiche les vraies données de la base.

## Qualité attendue

- Contraste suffisant pour tout le texte, dans les deux styles.
- Aucune information portée par la couleur seule : chaque statut garde son libellé.
- Focus clavier visible sur les boutons et les liens.
- Aucun défilement horizontal de la page sur téléphone. Le tableau peut défiler dans son propre cadre.
- Tout texte venant de la base ou du citoyen reste échappé avec `esc()` avant d'être inséré dans du HTML.

## Vérification

1. Lance `pytest` : les 36 tests doivent toujours passer.
2. Lance l'application et parcours-la : un signalement complet par écrit, la correction, l'annulation, le suivi par référence, la connexion à l'espace services, un changement de statut, une réorientation.
3. Montre-moi une capture de chaque écran, ou dis-moi clairement ce que tu n'as pas pu vérifier.
4. Ne fais aucun commit et aucun `git push` : je relirai d'abord.

Si un élément d'une maquette n'est pas réalisable proprement dans Streamlit, dis-le et propose la solution la plus proche, sans bricolage fragile.
