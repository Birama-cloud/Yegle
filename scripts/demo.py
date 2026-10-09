"""Fait passer des phrases d'exemple dans la chaîne complète, en mode hors ligne.

  python -m scripts.demo            affiche l'analyse et l'orientation, n'enregistre rien
  python -m scripts.demo --save     enregistre aussi les signalements (pour peupler le tableau de bord)
"""
import sys

from app.assistant import Assistant
from app.storage import Storage

EXAMPLES = [
    ["Il y a une grosse fuite d'eau dans ma rue depuis ce matin", "À Grand-Yoff, près du marché"],
    ["Le lampadaire devant l'école est en panne à Ouakam"],
    ["Un câble électrique est tombé par terre à la Médina, c'est dangereux"],
    ["Les ordures ne sont pas ramassées depuis une semaine à Pikine"],
    ["Il y a un gros trou sur la route à Pikine", "Je ne sais pas"],
    ["Les égouts débordent aux Parcelles Assainies"],
    ["Bonjour, quel temps fait-il ?"],
]


def main() -> None:
    save = "--save" in sys.argv
    assistant = Assistant(llm=None, storage=Storage() if save else Storage(":memory:"))
    assistant.llm = None    # mode hors ligne, même si une clé est configurée
    for messages in EXAMPLES:
        draft, turn = None, None
        for text in messages:
            turn = assistant.analyze(draft, text=text)
            draft = turn.draft
            print(f"Citoyen   : {text}\nAssistant : {turn.message}")
        if turn.kind == "confirm":
            print(f"            {turn.decision['justification']}")
            done = assistant.submit(draft)
            print(f"Assistant : {done.message}   [statut {done.report['status']}]")
        print("-" * 78)


if __name__ == "__main__":
    main()
