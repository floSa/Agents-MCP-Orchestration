"""Tests de `usine.etat` : l'état partagé (stock + suivi).

L'état est la mémoire commune ; ces tests vérifient ses invariants (copies en lecture,
consommation/ajout, suivi).
"""
from __future__ import annotations

from usine.etat import Etat


class _ConfigFactice:
    """Mini-config juste pour `Etat.depuis_config`."""

    stock_initial = {"roue": 3, "batterie": 2, "chassis": 1}


def test_depuis_config_copie_le_stock_initial():
    config = _ConfigFactice()
    etat = Etat.depuis_config(config)
    assert etat.stock == {"roue": 3, "batterie": 2, "chassis": 1}
    # C'est bien une copie : modifier l'état ne touche pas la config.
    etat.ajouter("roue", 10)
    assert config.stock_initial["roue"] == 3


def test_interroger_stock_renvoie_une_copie():
    etat = Etat(stock={"roue": 2})
    vue = etat.interroger_stock()
    vue["roue"] = 999  # modifier la copie ne doit pas affecter l'état réel
    assert etat.stock["roue"] == 2


def test_ajouter_cumule_et_renvoie_le_total():
    etat = Etat(stock={"roue": 1})
    assert etat.ajouter("roue", 4) == 5
    assert etat.ajouter("batterie", 2) == 2  # pièce absente au départ
    assert etat.stock == {"roue": 5, "batterie": 2}


def test_consommer_retire_les_pieces_de_la_recette():
    etat = Etat(stock={"roue": 4, "batterie": 3, "chassis": 2})
    etat.consommer({"roue": 4, "batterie": 3, "chassis": 2})
    assert etat.stock == {"roue": 0, "batterie": 0, "chassis": 0}


def test_consommer_peut_rendre_negatif():
    # L'état ne se protège pas : c'est l'Assembleur qui vérifie le stock AVANT d'assembler.
    etat = Etat(stock={"roue": 1})
    etat.consommer({"roue": 2})
    assert etat.stock["roue"] == -1


def test_maj_suivi():
    etat = Etat()
    assert etat.maj_suivi("moto#1", "livrée") == "livrée"
    assert etat.suivi == {"moto#1": "livrée"}


def test_snapshot_est_une_photo_independante():
    etat = Etat(stock={"roue": 1}, suivi={"moto#1": "livrée"})
    photo = etat.snapshot()
    etat.ajouter("roue", 5)  # modifie l'état après la photo
    assert photo == {"stock": {"roue": 1}, "suivi": {"moto#1": "livrée"}}
