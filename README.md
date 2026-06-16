# MCP-Orchestration — Usine d'agents

Tutoriel d'orchestration multi-agents + MCP sur un fil rouge concret : une usine qui fabrique
des machines a la commande. On y voit, sur un seul exemple, les cas de figure de l'orchestration :
orchestrateur, sous-agents, boucles, reutilisation d'agents, profondeur (un agent qui appelle un
agent), etat partage, et outils exposes via MCP (FastMCP).

A lire d'abord : [`docs/architecture.md`](docs/architecture.md) (avec le schema). C'est la
specification complete. Pour réutiliser ce squelette sur un autre sujet, voir
[`docs/adapter-a-votre-projet.md`](docs/adapter-a-votre-projet.md).

---

## Parcours d'apprentissage (ordre conseillé)

1. **Survol** — ce README, puis [`docs/architecture.md`](docs/architecture.md) et son schéma.
2. **Voir tourner** — `uv run python -m usine.main "2 motos + 2 voitures"` : lire le journal
   indenté par profondeur (qui appelle qui).
3. **Le moteur** — [`usine/agent.py`](usine/agent.py) (la boucle ReAct) et
   [`usine/trace.py`](usine/trace.py). Générique, valable pour tout projet.
4. **La logique métier** — [`usine/cerveau.py`](usine/cerveau.py), classe `CerveauFake` :
   une politique déterministe par agent. C'est le cœur pédagogique.
5. **Les outils et l'état** — [`usine/mcp_servers.py`](usine/mcp_servers.py) et
   [`usine/etat.py`](usine/etat.py).
6. **Le câblage** — [`usine/orchestration.py`](usine/orchestration.py) : comment l'arbre d'agents
   est assemblé.
7. **Les tests comme doc** — [`tests/test_cerveau_fake.py`](tests/test_cerveau_fake.py) décrit, pas
   à pas, le comportement de chaque agent.
8. **Adapter à votre projet** — [`docs/adapter-a-votre-projet.md`](docs/adapter-a-votre-projet.md).

Chaque module Python porte en tête un repère : `MOTEUR GÉNÉRIQUE` (réutilisable tel quel) vs
`EXEMPLE MÉTIER` (à réécrire pour votre domaine).

---

## Ce que ca fait

On passe une commande (ex. `2 motos + 2 voitures`). Le Chef d'usine (orchestrateur) :

1. demande a l'Assembleur d'assembler chaque machine ;
2. si des pieces manquent, demande au Fabricant de les produire ;
3. le Fabricant commande au Fournisseur (qui livre 1 a 5 pieces au hasard), et recommande
   jusqu'a obtenir la quantite voulue, puis met le stock a jour ;
4. le Chef relance l'Assembleur, qui assemble et livre.

Chaque action (quel agent, quel outil, quels arguments, quel resultat, a quelle profondeur) est
journalisee et affichee dans une interface Streamlit pour se balader dans l'arbre d'agents.

---

## Arborescence

```
MCP-Orchestration/
├── README.md
├── docs/
│   ├── architecture.md            <- LA spec (agents, MCP, outils, flux, regles)
│   ├── adapter-a-votre-projet.md  <- guide : reutiliser ce squelette ailleurs
│   └── schema_architecture.svg
├── usine/                     <- le package Python
│   ├── config.py              <- recettes + configuration LLM
│   ├── etat.py                <- etat partage : stock + suivi_commande
│   ├── trace.py               <- journal d'evenements (pour Streamlit)
│   ├── cerveau.py             <- le "cerveau" : mode fake (deterministe) ou ollama (Gemma)
│   ├── agent.py               <- classe Agent + boucle ReAct generique
│   ├── mcp_servers.py         <- les MCP (FastMCP) : atelier, fabrication, fournisseur
│   ├── orchestration.py       <- assemble les agents et lance une commande
│   ├── main.py                <- lancement en ligne de commande
│   └── streamlit_app.py       <- interface de suivi
├── tests/                     <- suite pytest (un fichier par module)
├── pyproject.toml             <- dependances (uv)
├── Dockerfile
├── docker-compose.yml         <- Ollama + l'app Streamlit
├── .env.example               <- variables de configuration
├── .github/workflows/         <- CI (pytest)
└── LICENSE                    <- MIT
```

---

## Lancer en local (sans Docker)

Prerequis : [uv](https://docs.astral.sh/uv/).

```bash
uv sync                       # cree l'env et installe les dependances

# 1) Demo en ligne de commande, SANS LLM (cerveau deterministe) :
uv run python -m usine.main "2 motos + 2 voitures"

# 2) Interface de suivi :
uv run streamlit run usine/streamlit_app.py
```

Par defaut, `LLM_PROVIDER=fake` : tout tourne sans modele, de facon deterministe — pratique pour
explorer l'architecture. Pour brancher Gemma E4B via Ollama :

```bash
cp .env.example .env          # puis mettre LLM_PROVIDER=ollama
ollama pull gemma3n:e4b       # recuperer le modele
uv run python -m usine.main "2 motos + 2 voitures"
```

---

## Tests

```bash
uv sync --group dev   # installe pytest
uv run pytest
```

La suite couvre l'analyse de commande, l'état partagé, la trace, la politique de chaque agent
(`CerveauFake`), le `CerveauOllama` (sans serveur, appel réseau simulé) et un scénario complet
de bout en bout, reproductible grâce à `SEED`. Les tests valent aussi comme documentation
exécutable du comportement attendu.

> Note : si le venv est sur un montage réseau Windows (`\\?\UNC\...`, ex. projet WSL ouvert
> depuis Windows), pytest saute le test de bout en bout car le chargement de la DLL pywin32 y
> échoue ; il s'exécute normalement ailleurs (CI Linux). Préfixez vos commandes uv par
> `UV_LINK_MODE=copy` dans ce cas.

---

## Lancer avec Docker

```bash
docker compose up --build
```

- `ollama` : sert le modele local.
- `app` : l'interface Streamlit, exposee sur http://localhost:8501

La premiere fois, telecharger le modele dans le conteneur Ollama :

```bash
docker compose exec ollama ollama pull gemma3n:e4b
```

---

## Modes du "cerveau"

| `LLM_PROVIDER` | Effet |
|---|---|
| `fake` (defaut) | Cerveau deterministe qui applique les regles. Aucune dependance, reproductible — pratique pour comprendre et tester l'arbre d'agents. |
| `ollama` | Les agents decident via Gemma E4B (Ollama). |

Les outils sont des stubs (ils renvoient un jeton), sauf `fournir_pieces` qui tire un nombre
aleatoire entre 1 et 5 — c'est ce qui cree la boucle du Fabricant.
