"""Tests du `CerveauFake` : la politique déterministe de chaque agent.

C'est le test le plus instructif du dépôt : pour chaque agent on donne un *historique*
(ce qu'il a déjà fait) et on vérifie la *prochaine action* décidée. Lus dans l'ordre, ces
tests décrivent pas à pas le comportement de chaque agent.

Chaque entrée d'historique a la forme `{"type", "nom", "args", "resultat"}` — exactement ce
que l'`Agent` y range après chaque action (voir usine/agent.py).
"""
from __future__ import annotations

import asyncio

import pytest

from usine.cerveau import CerveauFake
from usine.etat import Etat


def _evt(nom, resultat=None, **args):
    """Fabrique une entrée d'historique (le `type` n'est pas lu par les politiques)."""
    return {"type": "outil", "nom": nom, "args": args, "resultat": resultat}


CERVEAU = CerveauFake()


# ======================================================================================
# Assembleur (sans mémoire) : lit recette + stock, calcule le déficit
# ======================================================================================
def test_assembleur_commence_par_lire_la_recette():
    action = CERVEAU._assembleur({"vehicule": "moto"}, [], Etat())
    assert action.type == "outil" and action.nom == "lire_recette"


def test_assembleur_interroge_le_stock_apres_la_recette():
    historique = [_evt("lire_recette", {"roue": 2, "batterie": 1, "chassis": 1}, vehicule="moto")]
    action = CERVEAU._assembleur({"vehicule": "moto"}, historique, Etat())
    assert action.nom == "interroger_stock"


def test_assembleur_remonte_les_manquants_si_stock_insuffisant():
    historique = [
        _evt("lire_recette", {"roue": 2, "batterie": 1, "chassis": 1}, vehicule="moto"),
        _evt("interroger_stock", {"roue": 1, "batterie": 0, "chassis": 5}),
    ]
    action = CERVEAU._assembleur({"vehicule": "moto"}, historique, Etat())
    assert action.type == "terminer"
    # Déficit = besoin − stock, seulement pour ce qui manque (chassis est en surplus → absent).
    assert action.resultat == {
        "statut": "manquants",
        "vehicule": "moto",
        "manquants": {"roue": 1, "batterie": 1},
    }


def test_assembleur_assemble_puis_livre_si_stock_suffisant():
    recette = {"roue": 2, "batterie": 1, "chassis": 1}
    base = [
        _evt("lire_recette", recette, vehicule="moto"),
        _evt("interroger_stock", {"roue": 5, "batterie": 5, "chassis": 5}),
    ]
    # Étape 1 : assembler.
    a1 = CERVEAU._assembleur({"vehicule": "moto"}, base, Etat())
    assert a1.nom == "assembler_vehicule"
    # Étape 2 : livrer.
    a2 = CERVEAU._assembleur({"vehicule": "moto"}, base + [_evt("assembler_vehicule", "[moto assemblé]")], Etat())
    assert a2.nom == "livrer_vehicule"
    # Étape 3 : terminer "livré".
    a3 = CERVEAU._assembleur(
        {"vehicule": "moto"},
        base + [_evt("assembler_vehicule"), _evt("livrer_vehicule")],
        Etat(),
    )
    assert a3.type == "terminer"
    assert a3.resultat == {"statut": "livré", "vehicule": "moto"}


# ======================================================================================
# Fournisseur (sans mémoire) : un appel d'outil, puis renvoie la quantité reçue
# ======================================================================================
def test_fournisseur_appelle_loutil_puis_renvoie_la_quantite():
    a1 = CERVEAU._fournisseur({"piece": "roue"}, [], Etat())
    assert a1.nom == "fournir_pieces"

    historique = [_evt("fournir_pieces", {"piece": "roue", "quantite": 4})]
    a2 = CERVEAU._fournisseur({"piece": "roue"}, historique, Etat())
    assert a2.type == "terminer"
    assert a2.resultat == {"piece": "roue", "quantite": 4}


# ======================================================================================
# Fabricant (boucle) : commande jusqu'à atteindre le déficit, puis verse au stock
# ======================================================================================
def test_fabricant_cherche_dabord_un_fournisseur():
    action = CERVEAU._fabricant({"manquants": {"roue": 3}}, [], Etat())
    assert action.nom == "rechercher_fournisseur"
    assert action.args == {"piece": "roue"}


def test_fabricant_recommande_tant_que_le_cumul_est_insuffisant():
    historique = [
        _evt("rechercher_fournisseur", "[ok]", piece="roue"),
        _evt("appeler_fournisseur", {"piece": "roue", "quantite": 1}, piece="roue"),
    ]
    # Cumul = 1 < 3 → on recommande au Fournisseur.
    action = CERVEAU._fabricant({"manquants": {"roue": 3}}, historique, Etat())
    assert action.type == "deleguer" and action.nom == "appeler_fournisseur"


def test_fabricant_verse_le_cumul_au_stock_quand_le_deficit_est_atteint():
    historique = [
        _evt("rechercher_fournisseur", "[ok]", piece="roue"),
        _evt("appeler_fournisseur", {"piece": "roue", "quantite": 1}, piece="roue"),
        _evt("appeler_fournisseur", {"piece": "roue", "quantite": 5}, piece="roue"),
    ]
    # Cumul = 6 >= 3 → on verse TOUT le cumul (surplus inclus) au stock.
    action = CERVEAU._fabricant({"manquants": {"roue": 3}}, historique, Etat())
    assert action.nom == "ajouter_au_stock"
    assert action.args == {"piece": "roue", "quantite": 6}


def test_fabricant_enchaine_sur_la_piece_suivante():
    historique = [
        _evt("rechercher_fournisseur", "[ok]", piece="roue"),
        _evt("appeler_fournisseur", {"piece": "roue", "quantite": 5}, piece="roue"),
        _evt("ajouter_au_stock", {"roue": 5}, piece="roue"),
    ]
    # "roue" est terminée → on passe à "batterie".
    action = CERVEAU._fabricant({"manquants": {"roue": 3, "batterie": 2}}, historique, Etat())
    assert action.nom == "rechercher_fournisseur"
    assert action.args == {"piece": "batterie"}


def test_fabricant_termine_quand_toutes_les_pieces_sont_versees():
    historique = [
        _evt("rechercher_fournisseur", "[ok]", piece="roue"),
        _evt("appeler_fournisseur", {"piece": "roue", "quantite": 5}, piece="roue"),
        _evt("ajouter_au_stock", {"roue": 5}, piece="roue"),
    ]
    action = CERVEAU._fabricant({"manquants": {"roue": 3}}, historique, Etat())
    assert action.type == "terminer"
    assert action.resultat["statut"] == "en_stock"


# ======================================================================================
# Chef d'usine (orchestrateur, mémoire = suivi dans l'état partagé)
# ======================================================================================
PLAN = [{"id": "moto#1", "vehicule": "moto"}, {"id": "moto#2", "vehicule": "moto"}]


def test_chef_commence_par_lire_la_commande():
    action = CERVEAU._chef({"commande": "2 motos"}, [], Etat())
    assert action.nom == "lire_commande"


def test_chef_passe_la_machine_a_en_cours():
    # Cycle de vie : une machine "à faire" (défaut) passe d'abord "en cours".
    historique = [_evt("lire_commande", PLAN, commande="2 motos")]
    action = CERVEAU._chef({"commande": "2 motos"}, historique, Etat())
    assert action.nom == "suivi_commande"
    assert action.args == {"machine_id": "moto#1", "statut": "en cours"}


def test_chef_delegue_assemblage_quand_la_machine_est_en_cours():
    etat = Etat(suivi={"moto#1": "en cours"})
    historique = [_evt("lire_commande", PLAN, commande="2 motos")]
    action = CERVEAU._chef({"commande": "2 motos"}, historique, etat)
    assert action.type == "deleguer" and action.nom == "appeler_assembleur"
    assert action.args["machine_id"] == "moto#1"


def test_chef_marque_fini_quand_lassembleur_a_livre():
    etat = Etat(suivi={"moto#1": "en cours"})
    historique = [
        _evt("lire_commande", PLAN, commande="2 motos"),
        {"type": "deleguer", "nom": "appeler_assembleur",
         "args": {"machine_id": "moto#1", "vehicule": "moto"},
         "resultat": {"statut": "livré", "vehicule": "moto"}},
    ]
    action = CERVEAU._chef({"commande": "2 motos"}, historique, etat)
    assert action.nom == "suivi_commande"
    assert action.args == {"machine_id": "moto#1", "statut": "fini"}


def test_chef_appelle_le_fabricant_si_pieces_manquantes():
    etat = Etat(suivi={"moto#1": "en cours"})
    historique = [
        _evt("lire_commande", PLAN, commande="2 motos"),
        {"type": "deleguer", "nom": "appeler_assembleur",
         "args": {"machine_id": "moto#1", "vehicule": "moto"},
         "resultat": {"statut": "manquants", "manquants": {"roue": 2}}},
    ]
    action = CERVEAU._chef({"commande": "2 motos"}, historique, etat)
    assert action.type == "deleguer" and action.nom == "appeler_fabricant"
    assert action.args["manquants"] == {"roue": 2}


def test_chef_relance_lassembleur_apres_fabrication():
    etat = Etat(suivi={"moto#1": "en cours"})
    historique = [
        _evt("lire_commande", PLAN, commande="2 motos"),
        {"type": "deleguer", "nom": "appeler_assembleur",
         "args": {"machine_id": "moto#1", "vehicule": "moto"},
         "resultat": {"statut": "manquants", "manquants": {"roue": 2}}},
        {"type": "deleguer", "nom": "appeler_fabricant",
         "args": {"machine_id": "moto#1", "manquants": {"roue": 2}},
         "resultat": {"statut": "en_stock"}},
    ]
    action = CERVEAU._chef({"commande": "2 motos"}, historique, etat)
    assert action.type == "deleguer" and action.nom == "appeler_assembleur"
    assert action.args["machine_id"] == "moto#1"


def test_chef_cloture_quand_tout_est_fini():
    etat = Etat(suivi={"moto#1": "fini", "moto#2": "fini"})
    historique = [_evt("lire_commande", PLAN, commande="2 motos")]
    # Toutes finies → livrer_commande.
    a1 = CERVEAU._chef({"commande": "2 motos"}, historique, etat)
    assert a1.nom == "livrer_commande"
    assert a1.args["machines"] == ["moto#1", "moto#2"]
    # Puis terminer.
    a2 = CERVEAU._chef({"commande": "2 motos"}, historique + [_evt("livrer_commande", "[ok]")], etat)
    assert a2.type == "terminer"
    assert a2.resultat["statut"] == "commande_livrée"


# ======================================================================================
# Dispatch : decider() route vers la bonne politique selon le nom de l'agent
# ======================================================================================
class _AgentFactice:
    def __init__(self, nom):
        self.nom = nom


def test_decider_route_selon_le_nom_de_lagent():
    action = asyncio.run(
        CERVEAU.decider(_AgentFactice("Fournisseur"), {"piece": "roue"}, [], Etat())
    )
    assert action.nom == "fournir_pieces"


def test_decider_leve_si_agent_inconnu():
    with pytest.raises(ValueError):
        asyncio.run(CERVEAU.decider(_AgentFactice("Inconnu"), {}, [], Etat()))
