🇫🇷 Français | 🇬🇧 [English](README.md)

# Pipeline de migration GenAI

Analyse → Base de connaissances → Génération → Validation, sur les exemples d'applications
héritées fournis. Consultez [ARCHITECTURE.fr.md](../ARCHITECTURE.fr.md) du dépôt pour la
justification de la conception.

## Structure

```
sample-inputs/     Public stand-in legacy apps (Oracle Forms retail + APEX opportunities)
stage1_parse/      .fmb / APEX -> JSON + dependency graph   (deterministic, no AI)
stage2_kb/         Build corpus + provision Bedrock Knowledge Base (RAG)
stage3_generate/   Generate Angular / .NET / OpenAPI / tests via Amazon Bedrock
stage4_validate/   Behavioural-equivalence pytest suites (+ acceptance criteria)
stage5_shadow/     Optional: live legacy-vs-modern shadow comparison
run_pipeline.py    One-command orchestrator over the sample inputs
```

## Prérequis

- Python ≥ 3.11 avec `boto3` (`pip install boto3`) ; Graphviz `dot` pour l'image du graphe.
- Identifiants AWS avec accès à **Amazon Bedrock** (profil d'inférence Claude + Titan
  Embeddings) pour les étapes 2 à 4. L'étape 1 ne nécessite ni AWS ni IA.
- Copiez [`../.env.example`](../.env.example) vers `../.env` et renseignez les valeurs (région,
  identifiants KB, …).

## Exécution

**Étape 1 — analyse (hors ligne, sans AWS) :**

```bash
python stage1_parse/fmb_parser.py  sample-inputs/forms   -o stage1_parse/parsed
python stage1_parse/build_graph.py stage1_parse/parsed sample-inputs/forms/tables.SQL
python stage1_parse/apex_parser.py sample-inputs/apex/opportunities.sql -o stage1_parse/apex_parsed
```

Les sorties se trouvent dans `stage1_parse/parsed/`, `stage1_parse/graph/`,
`stage1_parse/apex_parsed/`. Des exemples de sorties sont inclus dans le dépôt afin que vous
puissiez les inspecter sans rien exécuter.

**Étape 2 — base de connaissances (provisionne des ressources AWS) :**

```bash
python stage2_kb/build_corpus.py       # -> corpus/*.md
python stage2_kb/provision_kb.py       # creates S3 + OpenSearch Serverless + Bedrock KB; prints KB_ID
python stage2_kb/ask_kb.py "what is the order line-total formula?"
```

Placez le `KB_ID` affiché dans votre `.env`.

**Étape 3 — génération (Amazon Bedrock) :**

```bash
python stage3_generate/generate.py         # retail Orders -> generated/
python stage3_generate/generate_apex.py    # APEX Account Details -> apex_generated/
```

**Étape 4 — validation :**

```bash
pytest stage4_validate/tests               # retail Orders equivalence
pytest stage4_validate/apex_tests          # APEX Account Details equivalence
```

**Étape 5 optionnelle — mode shadow** (nécessite un environnement hérité en cours d'exécution
+ l'API moderne) : consultez les scripts dans `stage5_shadow/`.

## Notes

- Amazon Bedrock exige un ARN de **profil d'inférence** (p. ex. `us.anthropic.claude-...`), et
  non un identifiant de modèle brut.
- La génération se fait **un fichier par appel de modèle** (source verbatim, pas JSON) afin
  d'éviter la troncature — voir [ARCHITECTURE.fr.md](../ARCHITECTURE.fr.md).
- Aucune information d'identification n'est codée en dur ; les scripts lisent les identifiants
  et les secrets depuis les variables d'environnement.
