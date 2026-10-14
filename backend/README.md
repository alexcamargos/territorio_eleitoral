# Território Eleitoral — Backend

> **Camada de dados, pipeline de processamento (ETL), modelagem geoespacial (PostGIS), análises estatísticas determinísticas e API REST de alta performance.**

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL 17 + PostGIS 3.5](https://img.shields.io/badge/PostGIS-3.5%20%7C%20PG%2017-336791.svg?logo=postgresql&logoColor=white)](https://postgis.net)
[![SQLAlchemy Core 2.0](https://img.shields.io/badge/SQLAlchemy-Core%202.0-red.svg?logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org)
[![Pandera](https://img.shields.io/badge/Schema%20Validation-Pandera-orange.svg)](https://pandera.readthedocs.io)
[![Astral uv](https://img.shields.io/badge/Package%20Manager-Astral%20uv-DE5FE9.svg?logo=uv&logoColor=white)](https://astral.sh/uv)
[![Pytest](https://img.shields.io/badge/Testes-Pytest%20%2B%20pytest--mock-success.svg?logo=pytest&logoColor=white)](https://pytest.org)
[![Ruff](https://img.shields.io/badge/Linter-Ruff%20(Google%20Docstrings)-yellow.svg?logo=ruff&logoColor=white)](https://astral.sh/ruff)

---

## Sumário

1. [Visão Geral e Propósito](#visão-geral-e-propósito)
2. [Arquitetura Interna do Backend](#arquitetura-interna-do-backend)
3. [Estrutura de Pastas e Módulos](#estrutura-de-pastas-e-módulos)
4. [A Fábrica (Pipeline ETL)](#1-a-fábrica-pipeline-etl)
   - [De-Para Canônico TSE ↔ IBGE (Crosswalk)](#de-para-canônico-tse--ibge-crosswalk)
   - [Validação com Pandera e Resiliência HTTP](#validação-com-pandera-e-resiliência-http)
   - [Adaptadores de Fontes de Dados](#adaptadores-de-fontes-de-dados)
   - [Auditoria e Verificação de Aceitação](#auditoria-e-verificação-de-aceitação)
5. [A Memória (Banco de Dados e PostGIS)](#2-a-memória-banco-de-dados-e-postgis)
   - [Modelagem Relacional e Espacial](#modelagem-relacional-e-espacial)
   - [Níveis de Detalhe Topológicos (LOD 0, 1 e 2)](#níveis-de-detalhe-topológicos-lod-0-1-e-2)
   - [Views Materializadas e Otimização de Consultas](#views-materializadas-e-otimização-de-consultas)
6. [O Cérebro (API FastAPI e Motor Analítico)](#3-o-cérebro-api-fastapi-e-motor-analítico)
   - [Arquitetura da API e Cache HTTP 304](#arquitetura-da-api-e-cache-http-304)
   - [Vector Tiles MVT Dinâmicos](#vector-tiles-mvt-dinâmicos)
   - [Motor Estatístico Determinístico (Zero LLM)](#motor-estatístico-determinístico-zero-llm)
   - [Catálogo de Endpoints REST](#catálogo-de-endpoints-rest)
7. [CLI `territorio` (Interface de Linha de Comando)](#cli-territorio-interface-de-linha-de-comando)
8. [Configuração e Variáveis de Ambiente](#configuração-e-variáveis-de-ambiente)
9. [Desenvolvimento Local e Padrões de Engenharia](#desenvolvimento-local-e-padrões-de-engenharia)
   - [Instalação e Sincronização via `uv`](#instalação-e-sincronização-via-uv)
   - [Qualidade de Código com `ruff`](#qualidade-de-código-com-ruff)
   - [Estratégia de Testes (`pytest` + `pytest-mock`)](#estratégia-de-testes-pytest--pytest-mock)
10. [Containerização e Docker](#containerização-e-docker)
11. [Regras Inegociáveis do Backend](#regras-inegociáveis-do-backend)
12. [Documentação de Referência](#documentação-de-referência)

---

## Visão Geral e Propósito

Este subdiretório contém o código-fonte, a infraestrutura de migração, os dados de referência e a suíte de testes do **Backend do Território Eleitoral**.

Enquanto a [documentação raiz](../README.md) apresenta o produto em escala macro (incluindo interface, jornada do usuário e visualizações do frontend), este documento funciona como o **manual definitivo de engenharia do backend**, orientando desenvolvedores e agentes sobre como os dados brutos governamentais são extraídos, validados, consolidados espacialmente e disponibilizados em alta velocidade para o frontend.

---

## Arquitetura Interna do Backend

O backend implementa 3 das 4 caixas da arquitetura do sistema:

```mermaid
flowchart TD
    subgraph S1["Fontes Externas"]
        TSE_IN["TSE Dados Abertos<br/>CSV por Município/Zona"]
        IBGE_IN["IBGE Malha & APIs<br/>SHP/GeoJSON + SIDRA"]
        CGU_IN["Portal da Transparência<br/>API Bolsa Família / BPC"]
        STN_IN["Tesouro SICONFI / CAPAG<br/>API & CKAN"]
        MAN_IN["Índices Manuais<br/>Firjan, IPEA, PNUD"]
    end

    subgraph Box1["1. A Fábrica (ETL — territorio.etl)"]
        HTTP["HTTP Client Resiliente<br/>Streaming + SHA-256 Cache"]
        XWALK["Crosswalk Engine<br/>Regras X1-X6: TSE ↔ IBGE"]
        SCHEMAS["Pandera Validators<br/>Fronteira Estrita de Tipos"]
        TRANS["Transformadores<br/>Votos, Indicadores, Geometria"]
        LOAD["Bulk Loader<br/>PostgreSQL COPY"]
        VERIFY["Auditor de Qualidade<br/>Checagens E1-E5, I1-I4, G1-G3"]
    end

    subgraph Box2["2. A Memória (Banco — territorio.db)"]
        PG[("PostgreSQL 17 + PostGIS 3.5")]
        TAB["Tabelas Fato & Dimensão<br/>municipality, election, indicator_value"]
        GEOM["Tabelas Geoespaciais<br/>municipality_geom (LODs), uf_geom"]
        MVS["Views Materializadas<br/>mv_municipality_result, mv_bloc_share, mv_indicator_current"]
    end

    subgraph Box3["3. O Cérebro (API & Analytics)"]
        FASTAPI["FastAPI 0.115+<br/>Injeção de Repositório SQL"]
        MVT["Serviço MVT<br/>ST_AsMVT + LRU Cache"]
        STATS["Motor Estatístico<br/>Pearson, Spearman, Regressão O(N)"]
        DEC["Decis Ponderados<br/>Razão ∑ Votos / ∑ Válidos"]
        INS["Gerador de Insights<br/>100% Determinístico (Zero LLM)"]
    end

    S1 --> HTTP
    HTTP --> SCHEMAS
    SCHEMAS --> XWALK
    XWALK --> TRANS
    TRANS --> LOAD
    LOAD --> PG
    PG --- TAB
    PG --- GEOM
    PG --- MVS
    VERIFY -.->|"Auditoria pós-carga"| PG
    PG -->|"SQLAlchemy Core"| FASTAPI
    MVS --> FASTAPI
    GEOM --> MVT
    FASTAPI --> STATS
    STATS --> DEC
    DEC --> INS
```

| Caixa | Módulos Python | Responsabilidade |
|---|---|---|
| **1. A Fábrica** | `territorio.etl.*` | Download com cache e hash SHA-256, De-Para TSE↔IBGE, simplificação geométrica em 3 LODs, validação com Pandera e carga em lote no PostGIS. |
| **2. A Memória** | `territorio.db.*` | DDL, migrações Alembic, tabelas espaciais e relacionais, views materializadas pré-computadas e índices GiST. |
| **3. O Cérebro** | `territorio.api.*` & `territorio.analytics.*` | Endpoints REST assíncronos, Mapbox Vector Tiles binários (`.pbf`), cálculos estatísticos e geração de textos de insight determinísticos. |

---

## Estrutura de Pastas e Módulos

```text
backend/
├── alembic.ini                   # Configuração das migrações de banco
├── Dockerfile                    # Multi-stage build (targets: base, dev, prod)
├── pyproject.toml                # Dependências uv, scripts de CLI, ruff e pytest
├── uv.lock                       # Lockfile determinístico de dependências
├── .env.example                  # Modelo de variáveis de ambiente
├── data/
│   ├── reference/                # VERSIONADO NO GIT: tabelas de verdade do sistema
│   │   ├── indicators.yaml       # Catálogo oficial de indicadores (temas, fontes, polaridades)
│   │   ├── offices.yaml          # Definição canônica de cargos e sistemas eleitorais
│   │   ├── party_ideology.yaml   # Classificação ideológica (Bolognesi et al., 2023)
│   │   ├── de_para_tse_ibge.csv  # Mapeamento canônico 1:1 dos 5.571 municípios
│   │   └── de_para_overrides.csv # Exceções históricas e fusões (ex.: Boa Esperança do Norte)
│   ├── raw/                      # NÃO VERSIONADO: cache local de downloads com SHA-256
│   │   ├── http_json/            # Respostas de APIs cacheadas (IBGE, CGU, Tesouro)
│   │   ├── ibge_geo/             # Shapefiles brutos da malha municipal IBGE 2025
│   │   └── tse/                  # Arquivos compactados de votação do TSE
│   ├── manual/                   # NÃO VERSIONADO: planilhas de fontes sem API (Firjan, IPS, IVS, IDHM)
│   └── reports/                  # Relatórios de qualidade gerados pelo verify (JSON + Markdown)
├── src/territorio/
│   ├── __init__.py               # Versão do pacote (__version__ = "0.1.0")
│   ├── config.py                 # Configurações tipadas via pydantic-settings
│   ├── domain.py                 # Enums de domínio (Office, Bloc, Theme, Level) e dataclasses
│   ├── logging.py                # Configuração estruturada de logs do sistema
│   ├── cli.py                    # CLI Typer (territorio db, crosswalk, etl)
│   ├── db/
│   │   ├── engine.py             # Criação da Engine SQLAlchemy Core e helpers de migração
│   │   ├── tables.py             # Definição formal das tabelas SQLAlchemy Core
│   │   └── migrations/           # Scripts versionados de migração do Alembic
│   ├── etl/
│   │   ├── http.py               # Cliente HTTP com retry exponencial e verificação de SHA-256
│   │   ├── provenance.py         # Registro de proveniência na tabela etl_run
│   │   ├── reference.py          # Carregador dos YAMLs de referência
│   │   ├── crosswalk.py          # Motor de validação e construção do De-Para TSE↔IBGE
│   │   ├── schemas.py            # Esquemas Pandera de validação de dados
│   │   ├── pipeline.py           # Orquestrador do pipeline de dados
│   │   ├── load.py               # Carga em lote no PostGIS (COPY e upsert)
│   │   ├── verify.py             # Suíte de auditoria pós-ETL (regras E1-E5, I1-I4, G1-G3)
│   │   ├── sources/              # Adaptadores para fontes oficiais específicas
│   │   │   ├── tse.py            # Extração de comparecimento, votos de partido e candidatos
│   │   │   ├── ibge_geo.py       # Malha 2025 com simplificação em 3 LODs
│   │   │   ├── ibge_sidra.py     # API SIDRA (PIB, VAB e Censo 2022)
│   │   │   ├── ibge_pesquisas.py # API IBGE Cidades (salários, saneamento, religião)
│   │   │   ├── transparencia.py  # API CGU (Bolsa Família e BPC)
│   │   │   ├── siconfi.py        # Balanços orçamentários do Tesouro Nacional
│   │   │   ├── ckan.py           # Rating CAPAG via portal CKAN do Tesouro
│   │   │   └── manual_file.py    # Leitura de planilhas manuais (Firjan, IPS, IVS, IDHM)
│   │   └── transform/            # Transformadores de limpeza e agregação
│   │       ├── geometry.py       # Correção topológica, simplificação e união de UFs
│   │       ├── votes.py          # Agregação de votos por bloco e cálculo de comparecimento
│   │       └── indicators.py     # Normalização e cálculo de indicadores derivados
│   ├── analytics/
│   │   ├── stats.py              # Motor estatístico (Pearson, Spearman, regressão, decis)
│   │   ├── insights.py           # Geração determinística de manchetes e cards de insight
│   │   └── formatting.py         # Formatação localizada pt-BR de números, moedas e percentuais
│   └── api/
│       ├── main.py               # Factory da aplicação FastAPI e middlewares CORS
│       ├── deps.py               # Injeção de dependência do SqlDataRepository
│       ├── errors.py             # Handlers centrais de exceção em envelopes padronizados
│       ├── cache.py              # Mecanismo de ETag e resposta HTTP 304 Not Modified
│       ├── schemas.py            # Modelos Pydantic de entrada e saída da API REST
│       ├── repository.py         # Repositório de leitura otimizado em SQLAlchemy Core
│       └── routers/
│           ├── meta.py           # /api/v1/meta e /api/v1/health
│           ├── elections.py      # /api/v1/elections/map e /api/v1/elections/summary
│           ├── indicators.py     # /api/v1/indicators/map
│           ├── analysis.py       # /api/v1/analysis (endpoint bivariado unificado)
│           ├── municipalities.py # /api/v1/municipalities/{cd_ibge} e autocomplete
│           └── tiles.py          # /tiles/municipalities/{z}/{x}/{y}.pbf (MVT binário)
└── tests/                        # Suíte pytest completa
    ├── conftest.py               # Fixtures compartilhadas e mocks de banco
    ├── test_config.py            # Testes de carregamento de configurações
    ├── test_domain.py            # Testes de enums e estruturas de domínio
    ├── analytics/                # Testes das formulações estatísticas e gerador de insights
    ├── api/                      # Testes de rotas FastAPI, cache ETag e contratos REST
    └── etl/                      # Testes unitários de adaptadores, crosswalk e schemas
```

---

## 1. A Fábrica (Pipeline ETL)

A camada de ETL é responsável por transformar dados brutos e heterogêneos de fontes oficiais em tabelas limpas, tipadas e indexadas.

### De-Para Canônico TSE ↔ IBGE (Crosswalk)
O TSE e o IBGE utilizam códigos territoriais distintos. O código canônico adotado pelo projeto é o **`cd_ibge` (7 dígitos, `int`)**.
O módulo [`crosswalk.py`](src/territorio/etl/crosswalk.py) implementa um mecanismo estrito de De-Para validado contra as **Regras X1 a X6**:

- **X1 (Exaustividade IBGE):** Exatamente todos os 5.571 municípios do IBGE devem estar mapeados.
- **X2 (Unicidade 1:1):** Cada código TSE mapeia para exatamente um código IBGE e vice-versa.
- **X3 (Validação de UF):** A UF atribuída ao município pelo TSE deve coincidir com a UF do IBGE.
- **X4 (Inclusão de Novos Municípios):** Cobertura obrigatória de Boa Esperança do Norte/MT (`cd_ibge=5101837`, instalado formalmente em 2025).
- **X5 (Divergências Conhecidas):** Municípios com discrepâncias históricas de nomenclatura são resolvidos via `data/reference/de_para_overrides.csv`.
- **X6 (Auditoria Fonética/Nomes):** Alertas preventivos para variações ortográficas entre os cadastros.

### Validação com Pandera e Resiliência HTTP
- **Validação de Fronteira:** Antes de qualquer dado ser persistido, ele deve passar pela validação de esquema do Pandera ([`schemas.py`](src/territorio/etl/schemas.py)). Se colunas obrigatórias faltarem ou valores estiverem fora dos limites físicos esperados, o pipeline aborta com erro explícito (*fail fast*).
- **Cliente HTTP Resiliente ([`http.py`](src/territorio/etl/http.py)):** Implementa streaming de arquivos massivos, *token-bucket rate limiting* para APIs governamentais sensíveis (ex.: CGU limitado a 80 req/min) e cálculo de integridade criptográfica **SHA-256**.
- **Registro de Proveniência ([`provenance.py`](src/territorio/etl/provenance.py)):** Toda execução de ingestão registra em `etl_run` a data de coleta, a URL exata da fonte, o tamanho em bytes e o hash de verificação.

### Adaptadores de Fontes de Dados
Localizados em [`src/territorio/etl/sources/`](src/territorio/etl/sources/):
- **`tse.py`:** Processamento dos arquivos consolidados `*_BRASIL.csv` de comparecimento (`turnout`), votação partidária (`party_vote`) e nominal majoritária (`candidate_vote`) para 1º e 2º turnos e todos os 6 cargos.
- **`ibge_geo.py`:** Leitura da Malha Municipal 2025 via `pyogrio` e `shapely`, aplicando correção de geometrias inválidas via `make_valid`.
- **`ibge_sidra.py`:** Extração via API REST do SIDRA (PIB total, PIB per capita e composição setorial do VAB).
- **`ibge_pesquisas.py`:** Coleta automatizada da API IBGE Cidades (renda domiciliar, salários médios, saneamento, IDEB e taxa de mortalidade).
- **`transparencia.py`:** Coleta paginada da API da CGU para execução de despesas municipais do Bolsa Família e BPC.
- **`siconfi.py` & `ckan.py`:** Coleta de balanços orçamentários declarados no SICONFI (receitas próprias vs. FPM) e notas de Capacidade de Pagamento (CAPAG).
- **`manual_file.py`:** Normalização de planilhas de índices de mercado colocados em `data/manual/` (Firjan IFDM/IFGF, IPS Brasil, IPEA IVS e Atlas Brasil IDHM).

### Auditoria e Verificação de Aceitação
O comando `territorio etl verify` executa a auditoria automática definida em [`verify.py`](src/territorio/etl/verify.py):
- **E1 a E5 (Eleições):** 5.571 municípios presentes no turnout, votos válidos = nominais + legenda, soma dos blocos = total de válidos, consistência de comparecimento + abstenção = eleitorado apto.
- **I1 a I4 (Indicadores):** Cobertura municipal mínima para cada indicador verificado, ausência de duplicidade de chaves `(cd_ibge, indicator_code, year)`, motivos de ausência válidos (`missing_reason`).
- **G1 a G3 (Geometria):** 5.571 polígonos presentes nos LODs 0, 1 e 2, sem sobreposições topológicas e com contornos válidos de UFs.

---

## 2. A Memória (Banco de Dados e PostGIS)

A persistência do sistema é suportada pelo **PostgreSQL 17** com extensão geoespacial **PostGIS 3.5**.
A camada de acesso a dados utiliza **SQLAlchemy Core 2.0** (sem abstração ORM no caminho crítico de consulta) com o driver binário de alta performance **`psycopg` (versão 3)**.

### Modelagem Relacional e Espacial
As tabelas principais definidas em [`src/territorio/db/tables.py`](src/territorio/db/tables.py) são:

- `municipality`: Cadastro dos 5.571 municípios brasileiros.
  - Chave primária canônica: `cd_ibge` (`INTEGER`).
  - Coluna gerada: `cd_ibge6` (`cd_ibge / 10`).
  - Coordenadas do centróide em `label_point` (`Geometry(POINT, 4326)`).
- `municipality_geom`: Geometrias municipais simplificadas.
  - Chave primária composta: `(cd_ibge, lod)`.
  - Geometria em Web Mercator: `geom` (`Geometry(MULTIPOLYGON, 3857)`), com índice espacial `GIST(geom)`.
- `uf_geom`: Geometrias agregadas das 27 Unidades da Federação.
- `election`: Dimensão de eleições cadastradas (ano, turno, cargo, sistema e abrangência).
- `election_turnout`: Fato de comparecimento por município, eleição e cargo.
- `party_vote`: Votação nominal e de legenda por partido em cada município.
- `candidate_vote`: Detalhamento dos candidatos mais votados em disputas majoritárias.
- `indicator_metadata`: Catálogo de metadados dos indicadores socioeconômicos e fiscais.
- `indicator_value`: Fato de indicadores municipais, com ano de referência e justificativa de ausência (`missing_reason` quando valor é `NULL`).
- `etl_run`: Auditoria de execuções do ETL com integridade SHA-256.

### Níveis de Detalhe Topológicos (LOD 0, 1 e 2)
Para conciliar fidelidade cartográfica com performance web instantânea, as geometrias são processadas em 3 níveis de detalhe:
- **LOD 0 (Visão Nacional / Zoom 0 a 5):** Alta simplificação topológica (~0.015° de tolerância), viabilizando transferência ultrarrápida do mapa do Brasil inteiro.
- **LOD 1 (Visão Regional e Estadual / Zoom 6 a 8):** Simplificação intermediária (~0.005° de tolerância).
- **LOD 2 (Visão Local e Zoom Alto / Zoom ≥ 9):** Geometria com máxima precisão (~0.001° de tolerância).

### Views Materializadas e Otimização de Consultas
Para viabilizar tempos de resposta abaixo de 50 ms nas consultas de mapa e análise, o banco mantém views materializadas indexadas:
- `mv_municipality_result`: Consolida o vencedor municipal, total de votos válidos e margem percentual de vitória para cada eleição e cargo.
- `mv_bloc_share`: Pré-calcula a porcentagem de votos dos blocos de Esquerda, Centro e Direita por município.
- `mv_indicator_current`: Isola o registro mais recente de cada indicador por município, eliminando subconsultas custosas em tempo de execução.

---

## 3. O Cérebro (API FastAPI e Motor Analítico)

A API REST é construída sobre o **FastAPI**, servindo dados serializados com **orjson** para o frontend.

### Arquitetura da API e Cache HTTP 304
- **Controle de Versão do Dataset (`X-Dataset-Version`):** Cada execução do pipeline ETL atualiza o identificador de versão do banco.
- **Cache Condicional via `ETag`:** Todos os endpoints de leitura geram cabeçalhos `ETag` baseados na versão dos dados e nos parâmetros da requisição. Requisições subsequentes com `If-None-Match` recebem `304 Not Modified` instantâneo sem consulta ao banco, economizando largura de banda e tempo de CPU.
- **Tratamento Padronizado de Erros:** Exceções disparam respostas JSON consistentes com a especificação RFC 7807 (`code`, `message`, `details`).

### Vector Tiles MVT Dinâmicos
O endpoint `/tiles/municipalities/{z}/{x}/{y}.pbf` gera Mapbox Vector Tiles binários diretamente no PostgreSQL através da função `ST_AsMVT()`.
O servidor mantém um cache LRU em memória para blocos frequentemente solicitados, garantindo que o mapa carregue instantaneamente mesmo sob múltiplas requisições simultâneas.

### Motor Estatístico Determinístico (Zero LLM)
Todo o cálculo analítico do projeto é executado de forma estritamente determinística no módulo [`src/territorio/analytics/`](src/territorio/analytics/):
- **Correlações Bivariadas ([`stats.py`](src/territorio/analytics/stats.py)):** Coeficiente de correlação linear de Pearson ($r$), coeficiente por postos de Spearman ($\rho$), respectivos $p$-valores de significância e coeficiente de determinação ($R^2$).
- **Regressão Linear $O(N)$:** Cálculo determinístico dos coeficientes de inclinação ($\alpha$) e intercepto ($\beta$) para traçar a linha de tendência no scatter plot.
- **Decis Ponderados por Votos Válidos:**
  Os municípios são classificados pelo indicador socioeconômico e divididos em 10 grupos de mesmo tamanho (D1 a D10).
  A taxa eleitoral do decil é calculada rigorosamente pela razão matemática:
  $$\text{Taxa do Bloco no Decil } k = \frac{\sum_{i \in D_k} \text{Votos do Bloco}_i}{\sum_{i \in D_k} \text{Votos Válidos}_i}$$
  Isso impede a distorção clássica da média simples de municípios, assegurando que cidades populosas e pequenos vilarejos tenham seu peso eleitoral devidamente ponderado.
- **Gerador de Insights Textuais ([`insights.py`](src/territorio/analytics/insights.py)):**
  Em conformidade estrita com o [ADR-003](../docs/13-decisoes-arquiteturais.md#adr-003--insights-100-determinísticos-zero-llm-no-caminho-dos-dados), **nenhum modelo de linguagem (LLM) é utilizado no caminho dos dados**. Os textos de síntese, destaques e conclusões são preenchidos por um motor de templates que avalia a força estatística das correlações e os extremos municipais.
- **Linguagem Ecológica:** Todos os textos gerados referem-se estritamente a **municípios**, nunca a "eleitores" ou "pessoas" (ex.: *"Municípios com maior PIB per capita apresentaram..."* em vez de *"Eleitores ricos votaram..."*), prevenindo formalmente a **falácia ecológica**.

### Catálogo de Endpoints REST

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/v1/health` | Healthcheck de liveness e readiness da aplicação. |
| `GET` | `/api/v1/meta` | Catálogo de metadados: eleições disponíveis, cargos, blocos e lista de indicadores. |
| `GET` | `/api/v1/elections/map` | Vetor compacto de resultados eleitorais para coloração do mapa por margem ou bloco. Suporta `level=municipality` ou `level=uf`. |
| `GET` | `/api/v1/elections/summary` | Resumo de votação nacional e estadual por partido e por bloco ideológico. |
| `GET` | `/api/v1/indicators/map` | Vetor numérico compacto dos valores de um indicador socioeconômico para coloração territorial. |
| `GET` | `/api/v1/analysis` | **Endpoint analítico unificado:** retorna correlações ($r$, $\rho$), parâmetros da reta de regressão, decis ponderados (D1–D10), pontos do scatter plot e cards de insight textuais em uma única requisição. |
| `GET` | `/api/v1/municipalities/{cd_ibge}` | Ficha cadastral e estatística completa do município (votações, partidos e indicadores). |
| `GET` | `/api/v1/municipalities/search` | Autocomplete de busca fonética e sem acento por nome de município ou UF. |
| `GET` | `/tiles/municipalities/{z}/{x}/{y}.pbf` | Tiles vetoriais binários Mapbox Vector Tile (MVT) dos contornos municipais e estaduais. |

---

## CLI `territorio` (Interface de Linha de Comando)

O backend disponibiliza uma CLI completa implementada com `typer`, invocada através de `uv run territorio`:

```text
territorio [OPTIONS] COMMAND [ARGS]...
```

### 1. Migrações de Banco de Dados (`territorio db`)
```powershell
# Aplica todas as migrações pendentes até a versão mais recente
uv run territorio db upgrade

# Aplica migrações até uma revisão específica do Alembic
uv run territorio db upgrade --revision 0001_initial

# Reverte todas as migrações até a base
uv run territorio db downgrade --revision base
```

### 2. Gestão do De-Para TSE ↔ IBGE (`territorio crosswalk`)
```powershell
# Reconstrói data/reference/de_para_tse_ibge.csv com base nas regras e overrides
uv run territorio crosswalk build

# Valida a integridade do De-Para contra as regras bloqueantes X1 a X6
uv run territorio crosswalk validate
```

### 3. Execução do Pipeline ETL (`territorio etl`)
```powershell
# Execução completa de todas as etapas (1 a 8)
uv run territorio etl run --all

# Execução de uma etapa individual:
# Opções: reference | territory | crosswalk | elections | indicators | derive | verify | publish
uv run territorio etl run --step territory
uv run territorio etl run --step elections --round 1
uv run territorio etl run --step indicators --only "IDHM,PIB_PC,BOLSA_FAMILIA_PC"

# Retoma o processamento ignorando etapas com sucesso anterior
uv run territorio etl run --all --resume

# Força novo download ignorando o cache local em disco
uv run territorio etl run --step indicators --force-refresh

# Executa a auditoria completa de aceitação e gera relatório em data/reports/
uv run territorio etl verify
```

---

## Configuração e Variáveis de Ambiente

As configurações são gerenciadas pela classe tipada `Settings` em [`src/territorio/config.py`](src/territorio/config.py) via `pydantic-settings`.
Para configurar o ambiente de desenvolvimento local, crie o arquivo `.env` a partir do modelo:

```powershell
Copy-Item .env.example .env
```

| Variável | Tipo | Padrão | Descrição |
|---|---|---|---|
| `DATABASE_URL` | `str` | `postgresql+psycopg://territorio:territorio@localhost:5432/territorio` | String de conexão SQLAlchemy utilizando o driver `psycopg` v3. |
| `DATA_DIR` | `Path` | `./data` | Diretório base para armazenamento de arquivos brutos, referências e relatórios. |
| `TRANSPARENCIA_API_KEY` | `str` | `""` | Chave de acesso à API do Portal da Transparência (CGU). |
| `TRANSPARENCIA_RATE_PER_MIN` | `int` | `80` | Limite de requisições por minuto para a API da CGU (*token-bucket*). |
| `HTTP_TIMEOUT_S` | `float` | `60.0` | Timeout padrão em segundos para chamadas HTTP do ETL. |
| `API_CORS_ORIGINS` | `str` | `http://localhost:5173` | Lista de origens CORS autorizadas separadas por vírgula. |
| `LOG_LEVEL` | `str` | `INFO` | Nível de log do sistema (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |

---

## Desenvolvimento Local e Padrões de Engenharia

O projeto adota padrões rigorosos de qualidade de software, tipagem estática e engenharia orientada a testes (TDD).

### Instalação e Sincronização via `uv`
Todas as dependências são gerenciadas pelo **Astral uv**. Nunca utilize `pip` diretamente.

```powershell
# Cria o ambiente virtual (.venv) e instala dependências do lockfile
uv sync

# Adiciona uma nova dependência de produção
uv add <pacote>

# Adiciona uma dependência de desenvolvimento
uv add --dev <pacote>
```

### Qualidade de Código com `ruff`
O código segue estritamente o **PEP 8** e o formato de documentação **Google Style Docstrings** (com seções `Args:`, `Returns:`, `Raises:`):

```powershell
# Executa a verificação de linter e tipagem de docstrings
uv run ruff check .

# Executa o formatador de código
uv run ruff format --check .

# Aplica correções automáticas de formatação e imports
uv run ruff check --fix .
uv run ruff format .
```

### Estratégia de Testes (`pytest` + `pytest-mock`)
- **Regra Inegociável:** É **estritamente proibido** o uso de `unittest`, classes `unittest.TestCase` ou `unittest.mock`. Todos os testes devem ser baseados em funções `pytest` com fixtures nativas e o fixture `mocker` do `pytest-mock`.
- **Separação de Testes:**
  - **Testes Unitários:** Executam sem dependência de banco de dados ativo (rápidos, isolados e executados em milissegundos).
  - **Testes de Integração:** Marcados com `@pytest.mark.integration`, exigem um banco PostgreSQL + PostGIS operacional.

```powershell
# Executa apenas a suíte de testes rápidos (unitários)
uv run pytest -m "not integration"

# Executa a suíte completa de testes incluindo integração
uv run pytest

# Executa testes com cobertura de código
uv run pytest --cov=territorio --cov-report=term-missing
```

---

## Containerização e Docker

O backend conta com um [`Dockerfile`](Dockerfile) multi-stage otimizado para os ambientes de desenvolvimento e produção:

```mermaid
flowchart LR
    BASE["base<br/>python:3.12-slim<br/>+ Astral uv binário"]
    DEV["dev<br/>uv sync completo<br/>hot reload com uvicorn"]
    PROD["prod<br/>--no-dev + usuário appuser<br/>healthcheck ativo + 2 workers"]

    BASE --> DEV
    BASE --> PROD
```

- **Target `dev`:** Utilizado no `docker compose up` para desenvolvimento integrado com volume montado e live-reload.
- **Target `prod`:** Execução com usuário sem privilégios (`appuser` UID 1000), dependências de desenvolvimento expurgadas e `HEALTHCHECK` automático em `/api/v1/health`.

Para construir e testar a imagem de produção localmente:
```powershell
docker build --target prod -t territorio-backend:latest .
docker run -p 8000:8000 --env-file .env territorio-backend:latest
```

---

## Regras Inegociáveis do Backend

Ao implementar qualquer alteração neste serviço, as seguintes regras são absolutas:

1. **`cd_ibge` (7 dígitos, `int`) é o identificador canônico:** Códigos do TSE (`cd_tse`) e códigos de 6 dígitos existem apenas na camada de ingestão e são convertidos imediatamente no De-Para.
2. **Nenhum join sem validação:** Todas as junções de DataFrames no Pandas devem utilizar `validate="one_to_one"` (ou `many_to_one`) e `indicator=True`, com asserção estrita de ausência de registros órfãos.
3. **Falhar alto, nunca silenciosamente:** Dados ausentes devem ser representados como `NULL` explícito no banco com justificativa em `missing_reason`. É proibido preencher dados faltantes com zero ou descartar linhas sem contabilidade e log.
4. **Zero LLM no caminho dos dados:** Toda estatística, correlação, decil e texto de insight é gerado determininisticamente por algoritmos científicos e templates de texto.
5. **Classificação ideológica exclusivamente declarativa:** Os blocos partidários vêm unicamente do arquivo versionado `data/reference/party_ideology.yaml`. É proibido classificar partidos diretamente no código Python.
6. **Linguagem ecológica:** Todo texto descritivo e insight analítico gerado pela API refere-se a **municípios**, nunca a pessoas ou eleitores, eliminando o risco da falácia ecológica.

---

## Documentação de Referência

Para detalhes aprofundados sobre cada subsistema, consulte a documentação técnica oficial:

- [**README Principal do Projeto**](../README.md) — Visão do produto, frontend e guia de execução da stack completa.
- [**AGENTS.md**](../AGENTS.md) — Regras de engenharia e convenções para desenvolvedores e agentes.
- [**docs/02-arquitetura.md**](../docs/02-arquitetura.md) — Arquitetura "As Quatro Caixas" e fluxo de dados.
- [**docs/03-fontes-de-dados.md**](../docs/03-fontes-de-dados.md) — Especificações de cada API pública governamental.
- [**docs/04-catalogo-de-indicadores.md**](../docs/04-catalogo-de-indicadores.md) — Catálogo detalhado de indicadores socioeconômicos e fiscais.
- [**docs/05-pipeline-etl.md**](../docs/05-pipeline-etl.md) — Especificação detalhada de cada etapa da Fábrica.
- [**docs/06-modelo-de-dados.md**](../docs/06-modelo-de-dados.md) — DDL, tabelas, views materializadas e índices do PostGIS.
- [**docs/07-metodologia.md**](../docs/07-metodologia.md) — Fórmulas estatísticas, regras eleitorais e classificação ideológica.
- [**docs/08-api.md**](../docs/08-api.md) — Contrato da API REST, esquemas MVT e estratégia de cache.
- [**docs/11-padroes-e-testes.md**](../docs/11-padroes-e-testes.md) — Padrões de código, formatação e suíte de testes.
- [**docs/13-decisoes-arquiteturais.md**](../docs/13-decisoes-arquiteturais.md) — Registro histórico de decisões de arquitetura (ADRs).
