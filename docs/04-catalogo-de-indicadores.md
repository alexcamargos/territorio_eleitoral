# 04 — Catálogo Canônico de Indicadores Socioeconômicos e Fiscais

> **Especificação dos indicadores integrados ao MVP, dimensões temáticas, metadados canônicos e rampas cromáticas auditáveis.**

---

## 1. Princípios de Seleção dos Indicadores

Para responder à pergunta central do projeto sem sobrecarregar o usuário com centenas de métricas redundantes, os indicadores do MVP foram selecionados segundo quatro critérios objetivos:
1. **Relevância explicativa:** Indicadores com histórico consolidado na literatura de comportamento eleitoral brasileiro (ex.: dependência de transferência de renda, peso do agronegócio, receita fiscal própria).
2. **Exaustividade territorial:** Disponibilidade de dados para os 5.571 municípios, evitando indicadores com buracos estatísticos superiores a 1% da federação.
3. **Oficialidade e auditabilidade:** Fontes públicas com metodologia aberta e atualizada (IBGE, CGU, Tesouro Nacional, Firjan, IPS).
4. **Segurança de apresentação visual:** Todos os indicadores usam rampas perceptuais seguras para daltonismo e **isentos de vermelho e azul**, reservando essas cores estritamente para os blocos políticos ([ADR-006](13-decisoes-arquiteturais.md#adr-006--separação-cromática-estrita-entre-espectro-político-e-indicadores)).

---

## 2. Estrutura Canônica de Metadados

A fonte da verdade de cada indicador em tempo de execução reside no arquivo versionado `backend/data/reference/indicators.yaml`. Cada indicador obedece à seguinte estrutura de especificação:

```yaml
id: "bolsa_familia_coverage_pct"
name: "Cobertura do Bolsa Família"
category: "social"
description: "Percentual da população municipal beneficiada por repasses do Bolsa Família."
unit: "%"
decimals: 1
polarity: "negative"          # Maior valor indica maior vulnerabilidade social
color_ramp: "YlOrPu"          # Amarelo -> Laranja -> Roxo (Rampa segura para daltonismo)
source_name: "CGU / Ministério do Desenvolvimento Social"
ref_year: 2024
priority: "N1"                # Nível 1 (Carregado na inicialização rápida)
```

---

## 3. Matriz de Indicadores do MVP

### 3.1 Dimensão Social e Demográfica (`category: "social"`)

| ID | Nome Amigável | Unidade | Fonte Oficial | Ano Ref. | Rampa Cromática | Descrição |
|---|---|---|---|---|---|---|
| `bolsa_familia_coverage_pct` | Cobertura do Bolsa Família | `%` | CGU / MDS | 2024 | `YlOrPu` | Percentual da população municipal atendida pelo programa de transferência de renda. |
| `bpc_rate_per_1000` | Taxa de Beneficiários do BPC | `por 1.000 hab` | CGU / MDS | 2024 | `YlOrPu` | Beneficiários do Benefício de Prestação Continuada (idosos e PCDs vulneráveis) por mil habitantes. |
| `idhm_longevity` | IDHM Longevidade | `índice (0-1)` | PNUD / IPEA | 2010/2020 | `SequentialTeal` | Esperança de vida ao nascer no município. |
| `idhm_education` | IDHM Educação | `índice (0-1)` | PNUD / IPEA | 2010/2020 | `SequentialTeal` | Escolaridade média da população adulta e frequência escolar de jovens. |
| `populacao_censo` | População Residente | `habitantes` | Censo IBGE | 2022 | `SequentialTeal` | Total de residentes apurado pelo Censo Demográfico oficial. |

### 3.2 Dimensão Econômica e Produtiva (`category: "economic"`)

| ID | Nome Amigável | Unidade | Fonte Oficial | Ano Ref. | Rampa Cromática | Descrição |
|---|---|---|---|---|---|---|
| `pib_per_capita` | PIB per Capita | `R$ / hab` | IBGE SIDRA | 2021/2022 | `SequentialEmerald` | Produto Interno Bruto a preços correntes dividido pela população residente. |
| `vab_agro_pct` | Participação da Agropecuária | `% do PIB` | IBGE SIDRA | 2021/2022 | `SequentialEmerald` | Proporção do Valor Adicionado Bruto da agropecuária na economia local. |
| `vab_servicos_pct` | Participação de Serviços | `% do PIB` | IBGE SIDRA | 2021/2022 | `SequentialEmerald` | Proporção do VAB gerado pelos setores de comércio e serviços. |
| `vab_industria_pct` | Participação da Indústria | `% do PIB` | IBGE SIDRA | 2021/2022 | `SequentialEmerald` | Proporção do VAB proveniente de indústrias de transformação e extrativas. |

### 3.3 Dimensão de Gestão Fiscal e Finanças Públicas (`category: "fiscal"`)

| ID | Nome Amigável | Unidade | Fonte Oficial | Ano Ref. | Rampa Cromática | Descrição |
|---|---|---|---|---|---|---|
| `fpm_dependency_pct` | Dependência do FPM | `%` | Tesouro / SICONFI | 2024 | `YlOrPu` | Proporção dos repasses constitucionais do FPM sobre a Receita Corrente Total da prefeitura. |
| `receita_propria_per_capita` | Arrecadação Própria | `R$ / hab` | Tesouro / SICONFI | 2024 | `SequentialTeal` | Receitas tributárias diretas do município (IPTU + ISS + ITBI) divididas pela população. |
| `capag_grade` | Nota CAPAG do Tesouro | `conceito (A/B/C)` | Tesouro Nacional | 2024 | `OrdinalTeal` | Capacidade de Pagamento avaliada pelo Ministério da Fazenda para contratação de crédito. |

### 3.4 Dimensão de Índices Compostos de Mercado (`category: "composite"`)

| ID | Nome Amigável | Unidade | Fonte Oficial | Ano Ref. | Rampa Cromática | Descrição |
|---|---|---|---|---|---|---|
| `ifdm_firjan_geral` | IFDM Firjan Geral | `índice (0-1)` | Sistema Firjan | 2020 | `SequentialTeal` | Índice de desenvolvimento municipal sintetizando Emprego & Renda, Saúde e Educação. |
| `ips_brasil_geral` | IPS Brasil Geral | `índice (0-100)` | IPS Brasil / Imazon | 2024 | `SequentialTeal` | Índice de Progresso Social medindo necessidades humanas básicas, bem-estar e oportunidades. |

---

## 4. Como os Indicadores Alimentam a Análise no Frontend

1. **Recoloração do Mapa:** Cada município recebe o valor normalizado do indicador via `setFeatureState` e o MapLibre interpola as cores segundo a paleta registrada no catálogo (ex.: escala de 7 tons de `YlOrPu`).
2. **Eixo X no Scatter Plot:** Os valores contínuos são mapeados para a escala linear horizontal do D3, enquanto o percentual de votos do bloco político ocupa o Eixo Y.
3. **Quebras de Decis (D1 a D10):** Os municípios são divididos em 10 quantis ordenados pelo valor do indicador. Os laços de desempate (*ties*) são resolvidos ordenando por `cd_ibge` ascendente, assegurando determinismo total.
