"""Le « cerveau » des agents : c'est lui qui décide la prochaine action.

Deux implémentations interchangeables :

- `CerveauFake` : **déterministe**, applique les règles métier sans aucun LLM.
  C'est la référence : elle permet de faire tourner et de comprendre tout l'arbre d'agents
  sans dépendance. C'est ici qu'est encodée la logique de chaque agent.

- `CerveauOllama` : appelle **Gemma E4B** via Ollama et lui demande de choisir l'action
  (au format JSON). Expérimental — la qualité dépend du modèle et du prompt.

Interface commune : `await cerveau.decider(agent, objectif, historique, etat) -> Action`.

`historique` est la liste des actions déjà faites par CET agent durant CETTE tâche :
chaque entrée vaut `{"type", "nom", "args", "resultat"}`. Le cerveau s'en sert pour savoir
où il en est (les agents « sans mémoire » repartent d'un historique vide à chaque appel).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Action:
    """Décision du cerveau pour un tour de boucle."""

    type: str                       # "outil" | "deleguer" | "terminer"
    nom: str = ""                   # nom de l'outil ou de la délégation
    args: dict = field(default_factory=dict)
    resultat: Any = None            # rempli uniquement pour "terminer"


# --------------------------------------------------------------------------------------
# Petits utilitaires pour relire l'historique
# --------------------------------------------------------------------------------------
def _fait(historique: list[dict], nom: str) -> bool:
    return any(h["nom"] == nom for h in historique)


def _resultat(historique: list[dict], nom: str):
    for h in historique:
        if h["nom"] == nom:
            return h["resultat"]
    return None


def _filtrer(historique: list[dict], nom: str, **args_egaux) -> list[dict]:
    """Renvoie les entrées d'un nom donné dont les args correspondent."""
    resultat = []
    for h in historique:
        if h["nom"] != nom:
            continue
        if all(h["args"].get(cle) == valeur for cle, valeur in args_egaux.items()):
            resultat.append(h)
    return resultat


# ======================================================================================
# Cerveau déterministe (référence)
# ======================================================================================
class CerveauFake:
    """Encode la politique de chaque agent. Aucune dépendance, 100 % reproductible."""

    async def decider(self, agent, objectif, historique, etat) -> Action:
        nom = agent.nom
        if nom.startswith("Chef"):
            return self._chef(objectif, historique, etat)
        if nom == "Assembleur":
            return self._assembleur(objectif, historique, etat)
        if nom == "Fabricant":
            return self._fabricant(objectif, historique, etat)
        if nom == "Fournisseur":
            return self._fournisseur(objectif, historique, etat)
        raise ValueError(f"Aucune politique pour l'agent '{nom}'")

    # --- Chef d'usine (orchestrateur) ----------------------------------------
    def _chef(self, objectif, historique, etat) -> Action:
        commande = objectif["commande"]

        # 1) Lire la commande pour obtenir le plan (liste de machines).
        if not _fait(historique, "lire_commande"):
            return Action("outil", "lire_commande", {"commande": commande})
        plan = _resultat(historique, "lire_commande") or []

        # 2) Trouver la première machine pas encore livrée (le suivi est dans l'état partagé).
        courante = next((m for m in plan if etat.suivi.get(m["id"]) != "livrée"), None)

        # 3) Tout est livré → clôturer la commande.
        if courante is None:
            if not _fait(historique, "livrer_commande"):
                return Action("outil", "livrer_commande", {"machines": [m["id"] for m in plan]})
            return Action("terminer", resultat={
                "statut": "commande_livrée",
                "machines": [m["id"] for m in plan],
            })

        machine_id, vehicule = courante["id"], courante["vehicule"]
        assemblages = _filtrer(historique, "appeler_assembleur", machine_id=machine_id)
        fabrications = _filtrer(historique, "appeler_fabricant", machine_id=machine_id)

        # 4) Pas encore tenté d'assembler cette machine → déléguer à l'Assembleur.
        if not assemblages:
            return Action("deleguer", "appeler_assembleur", {"machine_id": machine_id, "vehicule": vehicule})

        dernier = assemblages[-1]["resultat"] or {}

        # 5a) L'Assembleur a livré → marquer la machine comme livrée (suivi).
        if dernier.get("statut") == "livré":
            return Action("outil", "suivi_commande", {"machine_id": machine_id, "statut": "livrée"})

        # 5b) Il manque des pièces.
        if not fabrications:
            # On n'a pas encore fabriqué → déléguer au Fabricant les pièces manquantes.
            return Action("deleguer", "appeler_fabricant", {
                "machine_id": machine_id,
                "manquants": dernier.get("manquants", {}),
            })
        # Pièces fabriquées → on relance l'Assembleur (cette fois le stock suffit).
        return Action("deleguer", "appeler_assembleur", {"machine_id": machine_id, "vehicule": vehicule})

    # --- Assembleur (sans mémoire) -------------------------------------------
    def _assembleur(self, objectif, historique, etat) -> Action:
        vehicule = objectif["vehicule"]

        if not _fait(historique, "lire_recette"):
            return Action("outil", "lire_recette", {"vehicule": vehicule})
        if not _fait(historique, "interroger_stock"):
            return Action("outil", "interroger_stock", {})

        recette = _resultat(historique, "lire_recette") or {}
        stock = _resultat(historique, "interroger_stock") or {}

        # Déficit = besoin − stock, pièce par pièce.
        manquants = {
            piece: besoin - stock.get(piece, 0)
            for piece, besoin in recette.items()
            if besoin > stock.get(piece, 0)
        }
        if manquants:
            # Il manque des pièces : on remonte la liste au Chef (sans appeler le Fabricant).
            return Action("terminer", resultat={
                "statut": "manquants", "vehicule": vehicule, "manquants": manquants,
            })

        # Tout est là : on assemble (consomme le stock) puis on livre.
        if not _fait(historique, "assembler_vehicule"):
            return Action("outil", "assembler_vehicule", {"vehicule": vehicule})
        if not _fait(historique, "livrer_vehicule"):
            return Action("outil", "livrer_vehicule", {"vehicule": vehicule})
        return Action("terminer", resultat={"statut": "livré", "vehicule": vehicule})

    # --- Fabricant (boucle, mémoire de boucle) -------------------------------
    def _fabricant(self, objectif, historique, etat) -> Action:
        manquants = objectif["manquants"]  # {piece: deficit}

        for piece, deficit in manquants.items():
            deja_ajoute = _filtrer(historique, "ajouter_au_stock", piece=piece)
            if deja_ajoute:
                continue  # cette pièce est terminée

            cherche = _filtrer(historique, "rechercher_fournisseur", piece=piece)
            livraisons = _filtrer(historique, "appeler_fournisseur", piece=piece)
            cumule = sum((h["resultat"] or {}).get("quantite", 0) for h in livraisons)

            if not cherche:
                return Action("outil", "rechercher_fournisseur", {"piece": piece})
            if cumule < deficit:
                # Pas encore assez reçu → on (re)commande au Fournisseur.
                return Action("deleguer", "appeler_fournisseur", {"piece": piece})
            # Assez reçu → on verse au stock la quantité cumulée.
            return Action("outil", "ajouter_au_stock", {"piece": piece, "quantite": cumule})

        # Toutes les pièces manquantes ont été produites et versées au stock.
        return Action("terminer", resultat={"statut": "en_stock", "produites": manquants})

    # --- Fournisseur (sans mémoire) ------------------------------------------
    def _fournisseur(self, objectif, historique, etat) -> Action:
        piece = objectif["piece"]
        if not _fait(historique, "fournir_pieces"):
            return Action("outil", "fournir_pieces", {"piece": piece})
        recu = _resultat(historique, "fournir_pieces") or {}
        return Action("terminer", resultat={"piece": piece, "quantite": recu.get("quantite", 0)})


# ======================================================================================
# Cerveau Ollama (Gemma E4B) — expérimental
# ======================================================================================
class CerveauOllama:
    """Demande au modèle local de choisir l'action, au format JSON.

    Remarque : avec un petit modèle, la fiabilité dépend du prompt. Le mode `fake` reste
    la référence ; ce cerveau est un point de départ pour brancher un vrai LLM.
    """

    def __init__(self, config):
        import httpx  # importé ici pour ne pas l'exiger en mode fake
        self.config = config
        self._httpx = httpx
        self.client = httpx.AsyncClient(timeout=120.0)

    async def decider(self, agent, objectif, historique, etat) -> Action:
        outils = agent.noms_outils()
        delegations = agent.noms_delegations()
        systeme = (
            f"Tu es l'agent « {agent.nom} ». {agent.role}\n"
            f"Outils MCP disponibles : {outils}\n"
            f"Sous-agents que tu peux appeler : {delegations}\n"
            "Choisis UNE action et réponds STRICTEMENT par un objet JSON :\n"
            '  {"action": "outil"|"deleguer"|"terminer", "nom": "...", '
            '"args": {...}, "resultat": ...}\n'
            "N'invente pas d'outil hors de la liste."
        )
        contexte = {
            "objectif": objectif,
            "historique": historique,
            "stock": etat.interroger_stock(),
            "suivi": etat.suivi,
        }
        reponse = await self.client.post(
            f"{self.config.ollama_url}/api/chat",
            json={
                "model": self.config.ollama_model,
                "messages": [
                    {"role": "system", "content": systeme},
                    {"role": "user", "content": json.dumps(contexte, ensure_ascii=False)},
                ],
                "stream": False,
                "format": "json",  # demande à Ollama de renvoyer du JSON
            },
        )
        contenu = reponse.json()["message"]["content"]
        donnees = json.loads(contenu)

        action = donnees.get("action")
        if action == "terminer":
            return Action("terminer", resultat=donnees.get("resultat"))
        if action == "deleguer":
            return Action("deleguer", donnees.get("nom", ""), donnees.get("args", {}) or {})
        return Action("outil", donnees.get("nom", ""), donnees.get("args", {}) or {})


def construire_cerveau(config):
    """Fabrique le cerveau selon la configuration (`LLM_PROVIDER`)."""
    if config.provider == "ollama":
        return CerveauOllama(config)
    return CerveauFake()
