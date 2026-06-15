# MCP-Orchestration — Usine d'agents 🏭

Tutoriel d'**orchestration multi-agents + MCP** sur un fil rouge concret : **une usine qui
fabrique des machines à la commande**. On y voit, sur un seul exemple, *tous les cas de figure* :
orchestrateur, sous-agents, **boucles**, **réutilisation** d'agents, **profondeur** (agent qui
appelle un agent), **état partagé**, et **outils** exposés via **MCP** (FastMCP).

👉 **Lis d'abord [`docs/architecture.md`](docs/architecture.md)** (avec le schéma). C'est la
spécification complète.

---

## Ce que ça fait

On passe une commande (ex. `2 motos + 2 voitures`). Le **Chef d'usine** (orchestrateur) :

1. demande à l'**Assembleur** d'assembler chaque machine ;
2. si des pièces manquent, demande au **Fabricant** de les produire ;
3. le **Fabricant** commande en boucle au **Fournisseur** (qui livre 1 à 5 pièces au hasard)
   jusqu'à avoir assez, puis remet à jour le stock ;
4. le Chef relance l'Assembleur, qui assemble et livre.

Chaque action (quel agent, quel outil, quels arguments, quel résultat, à quelle profondeur) est
**journalisée** et affichée dans une **interface Streamlit** pour *se balader* dans l'arbre d'agents.

---

## Arborescence

```
MCP-Orchestration/
├── README.md                  ← vous êtes ici
├── docs/
│   ├── architecture.md        ← LA spec (agents, MCP, outils, flux, règles)
│   └── schema_architecture.svg
├── usine/                     ← le package Python
│   ├── config.py              ← recettes + configuration LLM
│   ├── etat.py                ← état partagé : stock + suivi_commande
│   ├── trace.py               ← journal d'événements (pour Streamlit)
│   ├── cerveau.py             ← le « cerveau » : mode `fake` (déterministe) ou `ollama` (Gemma)
│   ├── agent.py               ← classe Agent + boucle ReAct générique
│   ├── mcp_servers.py         ← les MCP (FastMCP) : atelier, fabrication, fournisseur
│   ├── orchestration.py       ← assemble les agents et lance une commande
│   ├── main.py                ← lancement en ligne de commande
│   └── streamlit_app.py       ← interface de suivi
├── pyproject.toml             ← dépendances (uv)
├── Dockerfile
├── docker-compose.yml         ← Ollama + l'app Streamlit
└── .env.example               ← variables de configuration
```

---

## Lancer en local (sans Docker)

Prérequis : [uv](https://docs.astral.sh/uv/).

```bash
uv sync                       # crée l'env et installe les dépendances

# 1) Démo en ligne de commande, SANS LLM (cerveau déterministe) :
uv run python -m usine.main "2 motos + 2 voitures"

# 2) Interface de suivi :
uv run streamlit run usine/streamlit_app.py
```

Par défaut, `LLM_PROVIDER=fake` : tout tourne **sans modèle**, de façon déterministe — parfait pour
explorer l'architecture. Pour brancher **Gemma E4B** via Ollama :

```bash
cp .env.example .env          # puis mettre LLM_PROVIDER=ollama
ollama pull gemma3n:e4b       # récupérer le modèle
uv run python -m usine.main "2 motos + 2 voitures"
```

---

## Lancer avec Docker

```bash
docker compose up --build
```

- `ollama` : sert le modèle local.
- `app` : l'interface Streamlit, exposée sur http://localhost:8501

La première fois, télécharger le modèle dans le conteneur Ollama :

```bash
docker compose exec ollama ollama pull gemma3n:e4b
```

---

## Modes du « cerveau »

| `LLM_PROVIDER` | Effet |
|---|---|
| `fake` (défaut) | Cerveau **déterministe** qui applique les règles. Aucune dépendance, reproductible — idéal pour comprendre et tester l'arbre d'agents. |
| `ollama` | Les agents décident via **Gemma E4B** (Ollama). |

Les **outils** sont des *stubs* (ils renvoient un jeton), sauf `fournir_pieces` qui tire un nombre
aléatoire entre 1 et 5 — c'est ce qui crée la boucle du Fabricant.
