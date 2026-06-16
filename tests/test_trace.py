"""Tests de `usine.trace` : le journal d'événements (structure + export JSONL)."""
from __future__ import annotations

import json

from usine.trace import Trace


def test_log_numerote_et_structure_les_evenements():
    trace = Trace()
    e1 = trace.log(0, "Chef d'usine", "objectif", detail={"commande": "1 moto"})
    e2 = trace.log(1, "Assembleur", "outil", "lire_recette", {"args": {"vehicule": "moto"}})

    assert e1["ordre"] == 1
    assert e2["ordre"] == 2
    assert e1["profondeur"] == 0 and e2["profondeur"] == 1
    assert e2["agent"] == "Assembleur"
    assert e2["type"] == "outil"
    assert e2["nom"] == "lire_recette"
    assert len(trace.journal) == 2


def test_to_jsonl_round_trip(tmp_path):
    trace = Trace()
    trace.log(0, "Chef d'usine", "objectif", detail={"commande": "1 moto"})
    trace.log(1, "Assembleur", "fin", detail={"statut": "livré"})

    chemin = tmp_path / "trace.jsonl"
    trace.to_jsonl(str(chemin))

    lignes = chemin.read_text(encoding="utf-8").splitlines()
    assert len(lignes) == 2
    relu = [json.loads(ligne) for ligne in lignes]
    assert relu == trace.journal
