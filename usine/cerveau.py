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
# Cerveau Ollama (Gemma E4B)
# ======================================================================================
#
# Pourquoi un garde-fou déterministe ?
# ------------------------------------
# Un petit modèle local (4B) ne tient pas une boucle « ReAct » brute : observé en vrai sur
# « 1 moto », il répète 40 fois la même lecture, corrompt un nom d'outil
# (« appeler_fabri fabricant ») ou invente des pièces manquantes. On garde donc le LLM AU
# VOLANT — c'est lui qui choisit la prochaine action à chaque tour — mais on l'encadre :
#
#   1. prompt par agent (rôle + règles + liste EXACTE des actions + exemples ciblés) ;
#   2. situation DIGÉRÉE (arithmétique pré-calculée : déficit, cumul reçu, machine courante)
#      plutôt qu'un historique brut illisible — et contexte volontairement court ;
#   3. le modèle ne choisit QUE l'action et son nom ; les arguments (sommes, dictionnaires,
#      identifiants) sont fournis par la référence déterministe — un 4B ne les calcule pas ;
#   4. validation contre `CerveauFake` (la référence) : si le modèle dérape (nom inconnu,
#      répétition, mauvais aiguillage, arrêt prématuré), on RELANCE avec un indice, puis on
#      CORRIGE/FORCE l'action de référence — c'est le « corriger/forcer » attendu ;
#   5. la sortie BRUTE du modèle et chaque correction sont tracées (journal) pour le débogage.
#
# Conséquence : le déroulé reste celui du cerveau fake (donc le MÊME résultat final), mais on
# voit dans le journal ce que le modèle propose réellement à chaque étape et où il faut le
# corriger. C'est précisément l'objet pédagogique : observer un petit modèle piloter, et le
# fiabiliser.
#
# (Alternative envisagée : l'API tool-calling native d'Ollama. Elle fiabilise le FORMAT
#  des appels mais pas la LOGIQUE — répétitions, aiguillage, arrêt — qui sont ici le vrai
#  problème ; et gemma3n n'expose pas d'outils via son gabarit Ollama. On garde donc le
#  protocole JSON maison, plus lisible pour le tutoriel.)


# --- Règles, par agent, injectées dans le prompt système. -----------------------------
_REGLES = {
    "chef": (
        "Déroulé attendu :\n"
        "1. lire_commande pour obtenir la liste des machines.\n"
        "2. Pour la machine courante (la première non livrée), délègue à l'Assembleur"
        " (appeler_assembleur).\n"
        "3. Si l'Assembleur a renvoyé le statut 'manquants' ET que le Fabricant n'a pas"
        " encore été appelé pour cette machine, délègue au Fabricant (appeler_fabricant).\n"
        "4. Si le Fabricant a déjà produit les pièces, relance l'Assembleur"
        " (appeler_assembleur).\n"
        "5. Si l'Assembleur a renvoyé le statut 'livré', enregistre la livraison"
        " (suivi_commande).\n"
        "6. Quand toutes les machines sont livrées, appelle livrer_commande, puis termine."
    ),
    "assembleur": (
        "Déroulé attendu :\n"
        "1. lire_recette du véhicule.\n"
        "2. interroger_stock.\n"
        "3. Regarde le champ 'manque' de la situation : s'il liste des pièces"
        " (besoin > stock), termine (l'usine fera produire ces pièces).\n"
        "4. Si 'manque' vaut {} (rien ne manque), assembler_vehicule puis livrer_vehicule,"
        " puis termine.\n"
        "('manque' = null signifie : pas encore calculé, continue les lectures.)"
    ),
    "fabricant": (
        "Déroulé attendu, pièce par pièce (voir 'progression'), pour 'piece_courante' :\n"
        "1. rechercher_fournisseur si 'recherche' est faux.\n"
        "2. appeler_fournisseur tant que 'cumule_recu' < 'besoin'.\n"
        "3. Quand 'cumule_recu' >= 'besoin', ajouter_au_stock pour verser la pièce.\n"
        "4. Quand toutes les pièces sont versées (piece_courante = null), termine."
    ),
    "fournisseur": (
        "Déroulé attendu : appelle fournir_pieces une seule fois, puis termine."
    ),
}

# --- Exemples ciblés (few-shot), par agent. -------------------------------------------
_EXEMPLES = {
    "chef": (
        'Exemples : {"action": "outil", "nom": "lire_commande"} ; '
        '{"action": "deleguer", "nom": "appeler_assembleur"} ; '
        '{"action": "deleguer", "nom": "appeler_fabricant"} ; '
        '{"action": "outil", "nom": "suivi_commande"} ; {"action": "terminer"}'
    ),
    "assembleur": (
        'Exemples : {"action": "outil", "nom": "lire_recette"} ; '
        '{"action": "outil", "nom": "interroger_stock"} ; '
        '{"action": "outil", "nom": "assembler_vehicule"} ; {"action": "terminer"}'
    ),
    "fabricant": (
        'Exemples : {"action": "outil", "nom": "rechercher_fournisseur"} ; '
        '{"action": "deleguer", "nom": "appeler_fournisseur"} ; '
        '{"action": "outil", "nom": "ajouter_au_stock"} ; {"action": "terminer"}'
    ),
    "fournisseur": (
        'Exemples : {"action": "outil", "nom": "fournir_pieces"} ; {"action": "terminer"}'
    ),
}


class CerveauOllama:
    """Pilote les agents avec Gemma E4B (Ollama), encadré par une référence déterministe.

    Le modèle choisit la prochaine action ; `CerveauFake` valide et, en cas de dérapage,
    corrige/force. Voir l'explication détaillée en tête de section.
    """

    def __init__(self, config):
        import httpx  # importé ici pour ne pas l'exiger en mode fake
        self.config = config
        self.client = httpx.AsyncClient(timeout=120.0)
        self.oracle = CerveauFake()      # référence : valide et corrige les choix du modèle
        self.max_relances = 2            # relances guidées avant de forcer l'action de référence

    # --- prompt système, taillé pour l'agent courant -------------------------
    def _cle_agent(self, agent) -> str:
        nom = agent.nom
        if nom.startswith("Chef"):
            return "chef"
        if nom == "Assembleur":
            return "assembleur"
        if nom == "Fabricant":
            return "fabricant"
        if nom == "Fournisseur":
            return "fournisseur"
        return "chef"

    def _actions_agent(self, agent) -> str:
        """Liste EXACTE des actions de cet agent (et d'elles seules)."""
        lignes = []
        for nom in agent.noms_outils():
            lignes.append(f'- {{"action": "outil", "nom": "{nom}"}} : {agent.catalogue.get(nom, "")}')
        for nom in agent.noms_delegations():
            lignes.append(f'- {{"action": "deleguer", "nom": "{nom}"}} : {agent.catalogue.get(nom, "")}')
        lignes.append('- {"action": "terminer"} : la tâche de cet agent est finie.')
        return "\n".join(lignes)

    def _prompt_systeme(self, agent) -> str:
        cle = self._cle_agent(agent)
        return (
            f"Tu es l'agent « {agent.nom} ». {agent.role}\n\n"
            f"{_REGLES[cle]}\n\n"
            "Actions possibles (n'en choisis AUCUNE autre) :\n"
            f"{self._actions_agent(agent)}\n\n"
            "Tu choisis UNE seule action à la fois, selon la situation fournie.\n"
            'Réponds STRICTEMENT par un objet JSON : {"action": "outil|deleguer|terminer",'
            ' "nom": "<nom exact>"}.\n'
            "Les ARGUMENTS sont calculés automatiquement : ne fournis QUE \"action\" et \"nom\".\n"
            "Ne répète jamais une étape déjà faite. Quand il n'y a plus rien à faire, réponds"
            ' {"action": "terminer"}.\n'
            f"{_EXEMPLES[cle]}"
        )

    # --- situation digérée, taillée pour l'agent courant ---------------------
    def _contexte_digere(self, agent, objectif, historique, etat) -> dict:
        cle = self._cle_agent(agent)
        if cle == "chef":
            return self._ctx_chef(objectif, historique, etat)
        if cle == "assembleur":
            return self._ctx_assembleur(objectif, historique)
        if cle == "fabricant":
            return self._ctx_fabricant(objectif, historique)
        return self._ctx_fournisseur(objectif, historique)

    def _ctx_chef(self, objectif, historique, etat) -> dict:
        plan = _resultat(historique, "lire_commande") or []
        machines = [
            {"id": m["id"], "vehicule": m["vehicule"], "statut": etat.suivi.get(m["id"], "à faire")}
            for m in plan
        ]
        courante = next((m for m in plan if etat.suivi.get(m["id"]) != "livrée"), None)
        dernier_retour, fabricant_appele = None, False
        if courante:
            assemblages = _filtrer(historique, "appeler_assembleur", machine_id=courante["id"])
            fabricant_appele = bool(_filtrer(historique, "appeler_fabricant", machine_id=courante["id"]))
            if assemblages:
                dernier_retour = assemblages[-1]["resultat"]
        return {
            "commande": objectif.get("commande"),
            "machines": machines,
            "machine_courante": courante["id"] if courante else None,
            "dernier_retour_assembleur": dernier_retour,
            "fabricant_deja_appele_pour_courante": fabricant_appele,
            "lire_commande_fait": _fait(historique, "lire_commande"),
        }

    def _ctx_assembleur(self, objectif, historique) -> dict:
        vehicule = objectif["vehicule"]
        recette = _resultat(historique, "lire_recette")
        stock = _resultat(historique, "interroger_stock")
        manque = None
        if recette and stock is not None:
            manque = {
                piece: besoin - stock.get(piece, 0)
                for piece, besoin in recette.items()
                if besoin > stock.get(piece, 0)
            }
        return {
            "vehicule": vehicule,
            "recette": recette,
            "stock": stock,
            "manque": manque,
            "etapes_faites": [h["nom"] for h in historique],
        }

    def _ctx_fabricant(self, objectif, historique) -> dict:
        manquants = objectif["manquants"]
        progression = {}
        for piece, besoin in manquants.items():
            livraisons = _filtrer(historique, "appeler_fournisseur", piece=piece)
            progression[piece] = {
                "besoin": besoin,
                "recherche": bool(_filtrer(historique, "rechercher_fournisseur", piece=piece)),
                "cumule_recu": sum((h["resultat"] or {}).get("quantite", 0) for h in livraisons),
                "verse_au_stock": bool(_filtrer(historique, "ajouter_au_stock", piece=piece)),
            }
        courante = next((p for p in manquants if not progression[p]["verse_au_stock"]), None)
        return {"manquants": manquants, "progression": progression, "piece_courante": courante}

    def _ctx_fournisseur(self, objectif, historique) -> dict:
        return {
            "piece": objectif["piece"],
            "fournir_pieces_fait": _fait(historique, "fournir_pieces"),
        }

    # --- boucle de décision : proposer (LLM) → valider/corriger (référence) ---
    async def decider(self, agent, objectif, historique, etat) -> Action:
        # Action de référence (déterministe) : sert à valider, à corriger, et à fournir les args.
        action_ref = await self.oracle.decider(agent, objectif, historique, etat)
        profondeur = getattr(agent, "profondeur", 0)

        messages = [
            {"role": "system", "content": self._prompt_systeme(agent)},
            {"role": "user", "content":
                "Situation actuelle :\n"
                + json.dumps(self._contexte_digere(agent, objectif, historique, etat),
                             ensure_ascii=False, indent=2)
                + "\n\nQuelle est la prochaine action ?"},
        ]

        noms_valides = agent.noms_outils() + agent.noms_delegations()
        raison = "réponse illisible"
        for tentative in range(1 + self.max_relances):
            brut = await self._appeler(messages)
            # Trace de la sortie BRUTE du modèle (débogage).
            agent.trace.log(profondeur, agent.nom, "cerveau", "",
                            {"tentative": tentative + 1, "brut": brut})
            donnees = _extraire_json(brut)
            if donnees is None:
                raison = "JSON illisible"
            elif _accord(donnees, action_ref, noms_valides):
                return action_ref  # le modèle a choisi la bonne action ; args fournis par la référence
            else:
                raison = (f"proposé action={donnees.get('action')!r} nom={donnees.get('nom')!r}, "
                          f"attendu action={action_ref.type!r} nom={action_ref.nom!r}")
            messages.append({"role": "user", "content": _indice_correctif(agent, historique)})

        # Garde-fou : le modèle a dérapé malgré les relances → on force l'action de référence.
        agent.trace.log(profondeur, agent.nom, "garde-fou", action_ref.nom or action_ref.type,
                        {"raison": raison})
        return action_ref

    async def _appeler(self, messages) -> str:
        reponse = await self.client.post(
            f"{self.config.ollama_url}/api/chat",
            json={
                "model": self.config.ollama_model,
                "messages": messages,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
            },
        )
        reponse.raise_for_status()
        return reponse.json()["message"]["content"]


def _extraire_json(texte: str):
    """Décode un objet JSON, en tolérant d'éventuels caractères autour."""
    if not texte:
        return None
    try:
        return json.loads(texte)
    except (ValueError, TypeError):
        pass
    debut, fin = texte.find("{"), texte.rfind("}")
    if 0 <= debut < fin:
        try:
            return json.loads(texte[debut:fin + 1])
        except (ValueError, TypeError):
            return None
    return None


def _accord(donnees: dict, action_ref: Action, noms_valides: list[str]) -> bool:
    """Le choix du modèle correspond-il à l'action de référence ?

    On ne compare que l'action visée (les arguments sont fournis par la référence). On
    tolère une étourderie fréquente du petit modèle : mettre le nom de l'outil dans le
    champ « action » (ex. {"action": "suivi_commande", "nom": "suivi_commande"}). On
    récupère donc son intention en cherchant un nom d'action valide dans les deux champs.
    Pour « terminer », il faut que le modèle dise « terminer » sans viser d'outil.
    """
    action = str(donnees.get("action") or "").strip()
    nom = str(donnees.get("nom") or "").strip()
    intention = nom if nom in noms_valides else (action if action in noms_valides else None)
    if action_ref.type == "terminer":
        return intention is None and action.lower() == "terminer"
    return intention == action_ref.nom


def _indice_correctif(agent, historique: list[dict]) -> str:
    """Message de relance : rappelle l'état sans révéler la réponse attendue."""
    faites = [h["nom"] for h in historique] or ["aucune"]
    noms = agent.noms_outils() + agent.noms_delegations()
    return (
        "Ta réponse ne convient pas. "
        f"Étapes déjà faites : {faites}. "
        f"Actions valides : {noms}. "
        "Choisis la PROCHAINE action utile non encore faite (ou termine si tout est fait). "
        'Réponds uniquement par le JSON {"action": ..., "nom": ...}.'
    )


def construire_cerveau(config):
    """Fabrique le cerveau selon la configuration (`LLM_PROVIDER`)."""
    if config.provider == "ollama":
        return CerveauOllama(config)
    return CerveauFake()
