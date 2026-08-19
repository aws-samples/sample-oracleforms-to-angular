🇫🇷 Français | 🇬🇧 [English](README.md)

# Modernisation Oracle Forms + Oracle APEX → Angular/.NET avec un pipeline de migration GenAI

Un **exemple** montrant comment moderniser des applications Oracle héritées — **Oracle Forms** et
**Oracle APEX** — vers une architecture moderne **Angular + .NET** sur AWS, à l'aide d'un
**pipeline de migration par IA générative** construit sur **Amazon Bedrock**. Le pipeline lit les
artefacts hérités, récupère leurs règles métier dans une **base de connaissances**, génère le code
cible et **valide l'équivalence comportementale** avant tout déploiement.

> **Il s'agit d'un exemple de code**, publié pour accompagner une démonstration ou un atelier. Ce
> n'est pas un logiciel de production et il est fourni sous la licence [MIT-0](LICENSE). Réviser,
> durcir et évaluer les coûts avant tout usage réel. Voir [Sécurité](#sécurité).

## Vue d'ensemble

Les organisations qui exploitent Oracle Forms et Oracle APEX font face à des pressions liées à la
fin de vie du produit, à la sécurité et à la rétention des compétences, mais la réécriture
manuelle de centaines d'écrans adossés à du PL/SQL est lente et risquée. Cet exemple présente une
approche **assistée par IA et fondée sur des preuves** :

- **Analyser** les modules Forms hérités (`.fmb`) et l'export APEX pour en récupérer la structure
  et la logique métier — sans IA, entièrement déterministe.
- **Indexer** les règles récupérées dans une **Amazon Bedrock Knowledge Base** (RAG) afin que les
  développeurs puissent poser des questions sur le système hérité en langage naturel.
- **Générer** le code Angular + .NET + OpenAPI moderne avec **Amazon Bedrock (Anthropic Claude)**,
  en préservant chaque règle récupérée.
- **Valider** le résultat avec des tests d'équivalence générés et un **mode shadow** en direct
  optionnel qui compare l'application moderne au système hérité sur des entrées identiques.

Les entrées héritées ici sont des **applications de substitution publiques, à licence permissive**
(voir [Les exemples d'applications héritées](#les-exemples-dapplications-héritées)) afin que
l'ensemble du pipeline soit reproductible par n'importe qui.

## Architecture

**Pipeline de migration GenAI**

[![GenAI migration pipeline](docs/architecture-pipeline.svg)](https://raw.githubusercontent.com/bennciz/oracleforms-to-angular/main/docs/architecture-pipeline.svg)

**Architecture cible « après »**

[![Target architecture](docs/architecture-target.svg)](https://raw.githubusercontent.com/bennciz/oracleforms-to-angular/main/docs/architecture-target.svg)

## Fonctionnement

| Étape | Service(s) | Description |
|-------|------------|-------------|
| **1 · Analyser** | AWS Lambda (conteneur) | Analyse les binaires Oracle Forms `.fmb` et l'export APEX en JSON ; construit un graphe de dépendances et récupère les règles métier. Python pur — sans IA, fonctionne partout. |
| **2 · Base de connaissances** | Amazon Bedrock Knowledge Bases · Amazon OpenSearch Serverless · Amazon Titan Text Embeddings v2 | Convertit les règles récupérées en un corpus Markdown — docs par formulaire, **règles métier (intention + PL/SQL)**, carte des dépendances et schéma (**pas** le `.fmb` brut) — les intègre avec Titan v2, et les indexe dans OpenSearch Serverless pour le RAG avec citations. Voir [ARCHITECTURE](ARCHITECTURE.fr.md#ce-qui-se-retrouve-réellement-dans-la-base-de-connaissances). |
| **3 · Générer** | Amazon Bedrock (Anthropic Claude) | Génère les composants Angular, une API .NET, une spécification OpenAPI et des tests — un fichier par appel afin d'éviter la troncature — chaque règle récupérée étant tracée dans la sortie. |
| **4 · Valider** | AWS Lambda · `pytest` généré | Exécute des tests d'équivalence comportementale. Un **mode shadow** optionnel soumet les mêmes entrées au système hérité et à l'API moderne, puis compare chaque décision. |

Les étapes sont orchestrées par **AWS Step Functions** (flux de travail STANDARD — les appels
Bedrock enchaînés avec réflexion étendue dépassent la limite de 5 minutes du mode Express).
Les artefacts et les rapports sont écrits dans **Amazon S3** ; **Amazon CloudWatch** assure
l'observabilité.

## Prérequis

- Un compte AWS avec accès aux modèles **Amazon Bedrock** (Anthropic Claude + Amazon Titan
  Embeddings) activés dans votre région.
- **AWS CLI v2**, **AWS CDK CLI** (`npm i -g aws-cdk`), **Docker**, **Node.js ≥ 18**,
  **Python ≥ 3.11**, **.NET SDK 8**.
- Une base de données Oracle pour les applications « avant »/« après ». Cet exemple cible
  **Oracle XE** (p. ex. l'image communautaire `gvenzl/oracle-xe:21-slim`) — **amenez la vôtre** ;
  aucun binaire Oracle n'est redistribué ici.

## Démarrage rapide

```bash
cp .env.example .env          # fill in your values
./scripts/deploy-all.sh       # (Windows: ./scripts/deploy-all.ps1)
```

`deploy-all` provisionne l'infrastructure, construit et pousse le conteneur de l'API .NET, câble
le proxy CloudFront `/api/*`, puis construit et déploie la SPA Angular. L'URL CloudFront est
affichée à la fin.

Pour exécuter le **pipeline de migration** sur les exemples d'entrées fournis, consultez
[`pipeline/README.fr.md`](pipeline/README.fr.md).

## Ce qui est déployé

Piles CDK dans [`infrastructure/cdk`](infrastructure/cdk) :

| Pile | Rôle |
|------|------|
| `NetworkStack` | VPC, sous-réseaux, groupes de sécurité, ALB |
| `SecurityStack` | Rôles IAM, secret AWS Secrets Manager pour les identifiants de la base de données |
| `StorageStack` | S3 (interface + artefacts), dépôt ECR, distribution CloudFront + proxy `/api/*` |
| `DatabaseStack` | Oracle XE sur EC2 (dev/bac à sable) + initialisation du schéma |
| `BedrockKBStack` | Bedrock Knowledge Base + collection/index Amazon OpenSearch Serverless |
| `PipelineStack` | Machine à états AWS Step Functions + étapes Lambda-conteneur |
| `ApiStack` | Service ECS Fargate (l'API .NET) derrière l'ALB |
| `ObservabilityStack` | Tableaux de bord/métriques Amazon CloudWatch |

## Les exemples d'applications héritées

Les entrées du pipeline se trouvent dans [`pipeline/sample-inputs/`](pipeline/sample-inputs) et
sont des applications de substitution publiques sous licence permissive — **aucune donnée client
ni code propriétaire** :

- **`forms/`** — une application Oracle Forms de commerce de détail (6 modules `.fmb` + DDL).
  Source : [oracle-retail-management-system](https://github.com/v7med7elmy-ai/oracle-retail-management-system)
  (MIT).
- **`apex/opportunities.sql`** — un exemple d'application Oracle APEX « Opportunity Tracking »
  (Oracle UPL v1.0).

Les propriétaires de schémas Oracle utilisés par l'exemple sont `apex_sample` (tables APEX) et
`app_data` (données applicatives). Voir [THIRD-PARTY-LICENSES](THIRD-PARTY-LICENSES).

## Structure du projet

```
pipeline/            The GenAI migration pipeline (the star of the sample)
  sample-inputs/     Public stand-in Oracle Forms + APEX apps (sanitized)
  stage1_parse/      Parse .fmb / APEX -> JSON + dependency graph  (no AI)
  stage2_kb/         Build corpus + provision Bedrock KB (RAG)
  stage3_generate/   Generate Angular/.NET/OpenAPI/tests via Bedrock
  stage4_validate/   Behavioural-equivalence pytest suites
  stage5_shadow/     Live legacy-vs-modern shadow-mode comparison
  run_pipeline.py    One-command orchestrator over sample inputs
app/
  angular_app/       Modern "after" SPA (Accounts + Reports screens)
  dotnet_api/        .NET 8 API (thin gateway over Oracle via Dapper)
infrastructure/
  cdk/               AWS CDK (Python) — all stacks above
  pipeline/          The same pipeline steps as AWS Lambda container images,
                     orchestrated by Step Functions (deployed by PipelineStack)
scripts/             deploy-all.sh / .ps1, cleanup.sh
docs/                Architecture diagrams
```

> **Deux vues du pipeline.** `pipeline/` est la version à exécuter et à lire — du Python simple que
> vous pouvez exécuter étape par étape sur `sample-inputs/` pour comprendre chaque étape.
> `infrastructure/pipeline/` regroupe les *mêmes* étapes sous forme d'images de conteneur AWS Lambda
> qu'AWS CDK déploie derrière AWS Step Functions (`PipelineStack`) pour l'exécution orchestrée
> native sur le cloud.

## Sécurité

- **Aucune information d'identification dans le code.** L'API .NET et le pipeline lisent les
  détails de connexion et les secrets depuis les variables d'environnement / **AWS Secrets
  Manager** (`.env` est ignoré par git ; voir `.env.example`).
- La SPA Angular est servie via **HTTPS par CloudFront** ; l'API est accessible **en même
  origine** via un reverse-proxy CloudFront `/api/*` (aucun contenu mixte, aucun CORS).
- Les rôles IAM de l'exemple sont définis pour un compte **hors production**. À réviser et
  restreindre avant tout usage réel.
- Aucune donnée de production n'est utilisée nulle part ; les entrées héritées sont des
  applications de substitution publiques.

Voir [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) pour signaler des problèmes
de sécurité.

## Coût

Cet exemple provisionne des ressources facturables : **Amazon OpenSearch Serverless** (le coût
continu le plus élevé), **Bedrock** (inférence à la pièce), **ECS Fargate**, **EC2** (Oracle XE),
**CloudFront** et **S3**. Exécutez [`scripts/cleanup.sh`](scripts/cleanup.sh) une fois que vous
avez terminé.

## Nettoyage

```bash
./scripts/cleanup.sh          # cdk destroy --all + empties the S3 buckets
```

## Dépannage

- **Bedrock « model identifier is invalid » / on-demand not supported** — utilisez un ARN de
  **profil d'inférence** (p. ex. `us.anthropic.claude-...`), et non un identifiant de modèle
  brut, et activez le modèle dans votre région.
- **OpenSearch Serverless 401 / délai dépassé lors de l'ingestion de la KB** — la collection est
  **accessible uniquement via un point de terminaison VPC** (l'accès public est désactivé).
  Vérifiez que le **point de terminaison VPC AOSS** (`KB_VPC_ENDPOINT_ID`) existe, qu'il figure
  dans le champ `SourceVPCEs` de la politique réseau de la collection, et que l'appelant (Lambda,
  script local, etc.) s'exécute dans le VPC ou transite par ce point de terminaison. Confirmez
  également que la politique d'accès aux données liste les bons principaux (le rôle IAM de la KB
  et l'identité de l'appelant). N'activez **pas** l'accès public comme solution de contournement.
- **Page blanche Angular (NG0908)** — assurez-vous que les options de construction dans
  `angular.json` incluent `"polyfills": ["zone.js"]`.
- **Erreurs de contenu mixte / CORS** — confirmez que CloudFront proxifie `/api/*` vers l'ALB
  et que la SPA utilise une URL de base d'API en même origine (vide).

## Licence

Cet exemple est sous licence **MIT-0**. Voir [LICENSE](LICENSE). Les composants tiers restent
sous leurs propres licences — voir [THIRD-PARTY-LICENSES](THIRD-PARTY-LICENSES).
