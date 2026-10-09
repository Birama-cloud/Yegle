"""Mesure la compréhension de Yëgle sur les cas de evaluation/cas.csv.

  python -m scripts.evaluer                 tous les cas (vocal quand un fichier audio est indiqué)
  python -m scripts.evaluer --mode texte    uniquement la colonne « texte »
  python -m scripts.evaluer --valeurs       affiche les catégories, zones et organismes acceptés

Chaque cas passe par la même chaîne que l'application : compréhension, lieu, orientation.
Rien n'est enregistré dans la base des signalements. Voir evaluation/LISEZMOI.md.
"""
import argparse
import csv
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from app import routing
from app.assistant import Assistant
from app.storage import Storage
from app.text import norm
from config import settings

DOSSIER = settings.BASE_DIR / "evaluation"
MIME = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".ogg": "audio/ogg",
        ".webm": "audio/webm"}
VERIFICATION = "VERIFICATION"
LANGUES = {"wo": "Wolof", "fr": "Français", "en": "Anglais"}


class CasInvalide(ValueError):
    pass


@dataclass
class Cas:
    ligne: int
    fichier: str
    langue: str
    texte: str
    categorie: str
    zone: str | None          # identifiant de zone, ou None si aucun lieu n'est dit
    organisme: str            # nom attendu, VERIFICATION, ou "" pour ne pas contrôler


@dataclass
class Resultat:
    ligne: int
    nom: str
    langue: str
    mode: str                 # vocal | texte
    entendu: str = ""
    categorie: str | None = None
    zone: str | None = None
    organisme: str = ""
    ok_categorie: bool = False
    ok_zone: bool = False
    ok_organisme: bool | None = None      # None : non contrôlé
    erreur: str = ""                      # panne technique : le cas n'est pas compté comme un échec de compréhension
    secondes: float = 0.0

    @property
    def tout_ok(self) -> bool:
        return self.ok_categorie and self.ok_zone and self.ok_organisme is not False


def lire_cas(chemin: Path, assistant: Assistant) -> list[Cas]:
    """Lit et contrôle le fichier des cas. Une valeur attendue inconnue arrête tout : mieux vaut
    une erreur claire qu'une mesure faussée par une faute de frappe."""
    contenu = chemin.read_text(encoding="utf-8-sig")
    separateur = ";" if contenu.splitlines()[0].count(";") >= contenu.splitlines()[0].count(",") else ","
    organismes = {norm(nom): nom for _, nom in assistant.organization_choices()}
    cas = []
    for numero, ligne in enumerate(csv.DictReader(contenu.splitlines(), delimiter=separateur), start=2):
        v = {k.strip().lower(): (x or "").strip() for k, x in ligne.items() if k}
        if not any(v.values()):
            continue
        ou = f"{chemin.name}, ligne {numero}"
        if not v.get("fichier") and not v.get("texte"):
            raise CasInvalide(f"{ou} : il faut un fichier audio ou un texte")
        if v.get("langue") not in LANGUES:
            raise CasInvalide(f"{ou} : langue « {v.get('langue')} » inconnue (wo, fr ou en)")
        if v.get("categorie") not in assistant.knowledge.categories:
            raise CasInvalide(f"{ou} : catégorie « {v.get('categorie')} » inconnue")
        zone = None
        if v.get("zone"):
            trouvee = assistant.gazetteer.get(v["zone"]) or assistant.gazetteer.resolve(v["zone"])[0]
            if trouvee is None:
                raise CasInvalide(f"{ou} : zone « {v['zone']} » inconnue")
            zone = trouvee.id
        organisme = v.get("organisme", "")
        if organisme and organisme.upper() != VERIFICATION:
            if norm(organisme) not in organismes:
                raise CasInvalide(f"{ou} : organisme « {organisme} » inconnu")
            organisme = organismes[norm(organisme)]
        elif organisme:
            organisme = VERIFICATION
        cas.append(Cas(numero, v.get("fichier", ""), v["langue"], v.get("texte", ""), v["categorie"], zone, organisme))
    if not cas:
        raise CasInvalide(f"{chemin.name} ne contient aucun cas")
    return cas


def evaluer_cas(assistant: Assistant, cas: Cas, mode: str, dossier_audio: Path) -> Resultat:
    vocal = mode != "texte" and bool(cas.fichier)
    r = Resultat(cas.ligne, cas.fichier or cas.texte[:60], cas.langue, "vocal" if vocal else "texte")
    if not vocal and not cas.texte:
        r.erreur = "pas de texte pour ce cas"
        return r
    debut = time.perf_counter()
    if vocal:
        chemin = dossier_audio / cas.fichier
        if not chemin.is_file():
            r.erreur = f"fichier audio introuvable : {cas.fichier}"
            return r
        if chemin.suffix.lower() not in MIME:
            r.erreur = f"format audio non pris en charge : {chemin.suffix}"
            return r
        if assistant.offline:
            r.erreur = "le vocal demande une clé GEMINI_API_KEY"
            return r
        tour = assistant.analyze(None, audio=chemin.read_bytes(), mime_type=MIME[chemin.suffix.lower()])
    else:
        tour = assistant.analyze(None, text=cas.texte)
    r.secondes = round(time.perf_counter() - debut, 1)
    if tour.kind == "error":
        r.erreur = "service indisponible ou quota atteint"
        return r

    brouillon = tour.draft
    r.entendu = tour.heard
    r.categorie = brouillon.get("category")
    r.zone = brouillon.get("zone_id")
    r.ok_categorie = r.categorie == cas.categorie
    r.ok_zone = r.zone == cas.zone
    if r.categorie:
        decision = routing.route(assistant.knowledge, r.categorie, brouillon.get("subcategory"),
                                 assistant.gazetteer.get(r.zone), brouillon.get("confidence_problem", 0.0))
        r.organisme = decision.organization.org_name if decision.ready else VERIFICATION
    else:
        r.organisme = VERIFICATION
    if cas.organisme:
        r.ok_organisme = norm(r.organisme) == norm(cas.organisme)
    return r


def synthese(resultats: list[Resultat]) -> dict:
    mesures = [r for r in resultats if not r.erreur]

    def taux(groupe, critere):
        groupe = [r for r in groupe if critere(r) is not None]
        reussis = sum(1 for r in groupe if critere(r))
        return {"reussis": reussis, "total": len(groupe),
                "taux": round(100 * reussis / len(groupe)) if groupe else None}

    def bloc(groupe):
        return {"categorie": taux(groupe, lambda r: r.ok_categorie), "zone": taux(groupe, lambda r: r.ok_zone),
                "organisme": taux(groupe, lambda r: r.ok_organisme), "tout": taux(groupe, lambda r: r.tout_ok)}

    durees = [r.secondes for r in mesures if r.secondes]
    return {
        "cas": len(resultats), "mesures": len(mesures), "pannes": len(resultats) - len(mesures),
        "vocaux": sum(r.mode == "vocal" for r in mesures), "ecrits": sum(r.mode == "texte" for r in mesures),
        "global": bloc(mesures),
        "par_langue": {l: bloc([r for r in mesures if r.langue == l])
                       for l in LANGUES if any(r.langue == l for r in mesures)},
        "secondes_moyennes": round(sum(durees) / len(durees), 1) if durees else None,
    }


def _ligne(nom: str, t: dict) -> str:
    if not t["total"]:
        return f"| {nom} | non contrôlé | |"
    return f"| {nom} | {t['reussis']} sur {t['total']} | {t['taux']} % |"


def rapport(resultats: list[Resultat], s: dict, cas: list[Cas], modele: str) -> str:
    attendus = {c.ligne: c for c in cas}
    lignes = [
        "# Évaluation de la compréhension", "",
        f"Mesure du {date.today().isoformat()}, produite par `python -m scripts.evaluer`.", "",
        f"- Compréhension : {modele}",
        f"- Cas mesurés : {s['mesures']}, dont {s['vocaux']} vocaux et {s['ecrits']} écrits",
    ]
    if s["pannes"]:
        lignes.append(f"- Cas non mesurés pour raison technique : {s['pannes']} (listés plus bas, exclus des taux)")
    if s["secondes_moyennes"]:
        lignes.append(f"- Temps de réponse moyen : {s['secondes_moyennes']} s")
    lignes += ["", "## Résultat", "", "| Critère | Réussis | Taux |", "|---|---|---|",
               _ligne("Catégorie du problème", s["global"]["categorie"]),
               _ligne("Lieu", s["global"]["zone"]),
               _ligne("Organisme", s["global"]["organisme"]),
               _ligne("Tout correct", s["global"]["tout"])]
    if len(s["par_langue"]) > 1:
        lignes += ["", "## Par langue", "", "| Langue | Cas | Tout correct |", "|---|---|---|"]
        for code, b in s["par_langue"].items():
            lignes.append(f"| {LANGUES[code]} | {b['tout']['total']} | {b['tout']['reussis']} sur "
                          f"{b['tout']['total']} ({b['tout']['taux']} %) |")
    echecs = [r for r in resultats if not r.erreur and not r.tout_ok]
    lignes += ["", "## Cas en échec", ""]
    if not echecs:
        lignes.append("Aucun.")
    else:
        lignes += ["| Cas | Entendu | Attendu | Obtenu |", "|---|---|---|---|"]
        for r in echecs:
            c = attendus[r.ligne]
            attendu = f"{c.categorie}, {c.zone or 'sans lieu'}" + (f", {c.organisme}" if c.organisme else "")
            obtenu = f"{r.categorie or 'non compris'}, {r.zone or 'sans lieu'}, {r.organisme}"
            cellule = lambda t: (t or "").replace("|", "/").replace("\n", " ")  # noqa: E731
            lignes.append(f"| {cellule(r.nom)} | {cellule(r.entendu)} | {cellule(attendu)} | {cellule(obtenu)} |")
    pannes = [r for r in resultats if r.erreur]
    if pannes:
        lignes += ["", "## Cas non mesurés", ""] + [f"- {r.nom} : {r.erreur}" for r in pannes]
    lignes += ["", "## Portée de cette mesure", "",
               f"Elle porte sur {s['mesures']} cas. Sous une trentaine de cas, le taux est une indication et non "
               "une preuve. Les valeurs attendues ont été fixées avant de lancer la mesure.", ""]
    return "\n".join(lignes)


def afficher_valeurs(assistant: Assistant) -> None:
    print("Catégories :", ", ".join(assistant.knowledge.category_ids()))
    print("\nZones :")
    for z in assistant.gazetteer.zones:
        print(f"  {z.id:32} {z.name}")
    print("\nOrganismes :", ", ".join(sorted({nom for _, nom in assistant.organization_choices()
                                             if not nom.startswith("Mairie de ")})))
    print("             Mairie de <commune>, ou VERIFICATION si le cas doit partir en vérification humaine")


def main(argv=None) -> int:
    parseur = argparse.ArgumentParser(description="Évalue la compréhension de Yëgle.")
    parseur.add_argument("--cas", type=Path, default=DOSSIER / "cas.csv")
    parseur.add_argument("--audio", type=Path, default=DOSSIER / "audio")
    parseur.add_argument("--mode", choices=["auto", "texte"], default="auto")
    parseur.add_argument("--pause", type=float, default=1.0, help="secondes entre deux appels au modèle")
    parseur.add_argument("--rapport", type=Path, default=settings.BASE_DIR / "docs" / "EVALUATION.md")
    parseur.add_argument("--valeurs", action="store_true", help="affiche les valeurs acceptées et s'arrête")
    args = parseur.parse_args(argv)

    assistant = Assistant(storage=Storage(":memory:"))     # rien n'est écrit dans la vraie base
    if args.valeurs:
        afficher_valeurs(assistant)
        return 0
    try:
        cas = lire_cas(args.cas, assistant)
    except (CasInvalide, OSError) as e:
        print(f"Erreur : {e}", file=sys.stderr)
        return 2

    modele = "mots-clés, mode hors ligne" if assistant.offline else f"Gemini ({settings.GEMINI_MODEL})"
    print(f"{len(cas)} cas, compréhension : {modele}\n")
    resultats = []
    for i, c in enumerate(cas):
        r = evaluer_cas(assistant, c, args.mode, args.audio)
        resultats.append(r)
        marque = "PANNE" if r.erreur else "OK   " if r.tout_ok else "ÉCHEC"
        detail = r.erreur or f"{r.categorie or 'non compris'}, {r.zone or 'sans lieu'}, {r.organisme}"
        print(f"  {marque} [{r.mode:5}] {r.nom[:44]:44} {detail}")
        if not assistant.offline and i < len(cas) - 1:
            time.sleep(args.pause)

    s = synthese(resultats)
    print()
    for nom, cle in (("Catégorie", "categorie"), ("Lieu", "zone"), ("Organisme", "organisme"), ("Tout correct", "tout")):
        t = s["global"][cle]
        print(f"  {nom:13} " + (f"{t['reussis']} sur {t['total']} ({t['taux']} %)" if t["total"] else "non contrôlé"))
    if s["pannes"]:
        print(f"  {s['pannes']} cas non mesurés pour raison technique")

    args.rapport.parent.mkdir(parents=True, exist_ok=True)
    args.rapport.write_text(rapport(resultats, s, cas, modele), encoding="utf-8")
    (DOSSIER / "resultats.json").write_text(
        json.dumps({"synthese": s, "resultats": [asdict(r) for r in resultats]}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"\nRapport écrit dans {args.rapport}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
