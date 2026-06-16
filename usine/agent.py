"""La classe Agent et sa boucle « ReAct ».

Un **agent** = un cerveau (LLM ou fake) + une boucle + une boîte à outils :
- `clients_par_outil` : pour chaque nom d'outil, le client FastMCP du MCP qui l'expose.
- `delegations`       : pour chaque nom de délégation, une coroutine qui lance un sous-agent.

La boucle est toujours la même : *demander au cerveau la prochaine action → l'exécuter →
observer → recommencer*, jusqu'à ce que le cerveau décide de `terminer`. C'est l'AGENT qui
boucle ; il se sert du cerveau pour décider.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    # Imports « pour les types » uniquement : jamais chargés à l'exécution (pas de dépendance ajoutée).
    from fastmcp import Client

    from usine.etat import Etat
    from usine.trace import Trace

# Une délégation est une coroutine `(args, profondeur) -> résultat` qui lance un sous-agent.
Delegation = Callable[[dict, int], Awaitable[Any]]

# Garde-fou : nombre maximum d'itérations d'un agent (évite toute boucle infinie).
MAX_ITERATIONS = 100


class Agent:
    def __init__(
        self,
        nom: str,
        role: str,
        clients_par_outil: dict[str, "Client"],
        delegations: dict[str, Delegation],
        cerveau: Any,                       # un objet exposant `await decider(agent, objectif, historique, etat)`
        trace: "Trace",
        etat: "Etat",
        catalogue: dict[str, str] | None = None,
    ) -> None:
        self.nom = nom
        self.role = role
        self.clients_par_outil = clients_par_outil   # {nom_outil: Client FastMCP}
        self.delegations = delegations               # {nom: async (args, profondeur) -> resultat}
        self.cerveau = cerveau
        self.trace = trace
        self.etat = etat
        # Catalogue : {nom_outil: "description (args: ...)"} — sert au cerveau LLM pour
        # comprendre quels arguments passer. Ignoré par le cerveau déterministe.
        self.catalogue: dict[str, str] = catalogue or {}
        self.memoire: dict = {}                      # mémoire persistante (utilisée par le Chef)

    # Outils visibles par le cerveau (utile pour le mode Ollama).
    def noms_outils(self) -> list[str]:
        return list(self.clients_par_outil)

    def noms_delegations(self) -> list[str]:
        return list(self.delegations)

    async def executer(self, objectif, profondeur: int = 0):
        """Exécute la tâche `objectif` et renvoie le résultat final."""
        self.trace.log(profondeur, self.nom, "objectif", detail=objectif)
        historique: list[dict] = []

        for _ in range(MAX_ITERATIONS):
            action = await self.cerveau.decider(self, objectif, historique, self.etat)

            if action.type == "terminer":
                self.trace.log(profondeur, self.nom, "fin", detail=action.resultat)
                return action.resultat

            if action.type == "outil":
                resultat = await self._appeler_outil(action.nom, action.args, profondeur)
            elif action.type == "deleguer":
                resultat = await self._deleguer(action.nom, action.args, profondeur)
            else:
                raise ValueError(f"Type d'action inconnu : {action.type}")

            historique.append({
                "type": action.type, "nom": action.nom,
                "args": action.args, "resultat": resultat,
            })

        raise RuntimeError(f"{self.nom} : trop d'itérations (boucle non terminée).")

    # --- exécution d'un outil via son MCP ------------------------------------
    async def _appeler_outil(self, nom, args, profondeur):
        client = self.clients_par_outil.get(nom)
        if client is None:
            raise KeyError(f"{self.nom} : outil inconnu « {nom} »")
        self.trace.log(profondeur, self.nom, "outil", nom, {"args": args})
        reponse = await client.call_tool(nom, args)
        valeur = _valeur_resultat(reponse)
        self.trace.log(profondeur, self.nom, "observation", nom, {"resultat": valeur})
        return valeur

    # --- appel d'un sous-agent (profondeur + 1) ------------------------------
    async def _deleguer(self, nom, args, profondeur):
        coroutine = self.delegations.get(nom)
        if coroutine is None:
            raise KeyError(f"{self.nom} : délégation inconnue « {nom} »")
        self.trace.log(profondeur, self.nom, "delegation", nom, {"args": args})
        resultat = await coroutine(args, profondeur + 1)
        self.trace.log(profondeur, self.nom, "retour", nom, {"resultat": resultat})
        return resultat


def _valeur_resultat(reponse):
    """Extrait la valeur Python d'un résultat d'outil FastMCP.

    FastMCP renvoie un objet `CallToolResult` : on privilégie `.data` (sortie structurée),
    sinon on tente de décoder le texte du premier bloc de contenu.
    """
    data = getattr(reponse, "data", None)
    if data is not None:
        return data
    contenu = getattr(reponse, "content", None)
    if contenu:
        texte = getattr(contenu[0], "text", None)
        if texte is not None:
            try:
                return json.loads(texte)
            except (ValueError, TypeError):
                return texte
    return None
