# 13 — Decisões Arquiteturais Consolidadas (ADRs)

> **Registro formal e aprofundado das decisões estruturantes de produto, engenharia e estatística aplicadas no Território Eleitoral, com histórico de contexto, justificativas, alternativas rejeitadas e consequências.**

---

## Índice dos Architecture Decision Records (ADRs)

| ADR | Título | Área | Status |
|---|---|---|---|
| [ADR-001](#adr-001--cd_ibge-7-dígitos-como-identificador-canônico-único-de-município) | `cd_ibge` (7 dígitos) como Identificador Canônico Único de Município | Engenharia de Dados | **Aceito** |
| [ADR-002](#adr-002--vector-tiles-mvt-no-postgis--recoloração-via-feature-state) | Vector Tiles (MVT) no PostGIS + Recoloração via `feature-state` em GPU | Arquitetura & Geo | **Aceito** |
| [ADR-003](#adr-003--insights-100-determinísticos-zero-llm-no-caminho-dos-dados) | Insights 100% Determinísticos (Zero LLM no Caminho dos Dados) | Inteligência & Analytics | **Aceito** |
| [ADR-004](#adr-004--cálculo-de-blocos-ideológicos-via-votacao_partido_munzona--bolognesi-et-al-2023) | Cálculo de Blocos via `votacao_partido_munzona` + Bolognesi et al. (2023) | Ciência Política | **Aceito** |
| [ADR-005](#adr-005--ponderação-por-votos-válidos-nos-decis-e-linguagem-ecológica-estrita) | Ponderação por Votos Válidos nos Decis e Linguagem Ecológica Estrita | Metodologia Estatística | **Aceito** |
| [ADR-006](#adr-006--separação-cromática-estrita-entre-espectro-político-e-indicadores) | Separação Cromática Estrita entre Espectro Político e Indicadores | Design System & UX | **Aceito** |
| [ADR-007](#adr-007--desacoplamento-da-fábrica-de-etl-do-backend-api-e-estratégia-de-deploy-cloud-free-tier) | Desacoplamento da Fábrica de ETL e Estratégia de Deploy Cloud Free-Tier | Infraestrutura & DevOps | **Aceito** |

---

## ADR-001 — `cd_ibge` (7 dígitos) como Identificador Canônico Único de Município

### Status
**Aceito** (Aplicado no MVP)

### Contexto do Problema
O sistema consome bases governamentais heterogêneas que utilizam convenções cadastrais distintas:
- O **TSE** emprega códigos eleitorais municipais próprios de até 5 dígitos (`cd_tse`), sem correspondência matemática direta com os códigos geográficos.
- A **API de Cidades do IBGE** utiliza códigos de 6 dígitos sem dígito verificador (`cd_ibge6`).
- As malhas territoriais digitais do **IBGE**, os censos populacionais e o **SICONFI/Tesouro** operam com o código padronizado de 7 dígitos (`cd_ibge`).
- Municípios homônimos (como "Bom Jesus", presente em cinco estados diferentes) causam desastres analíticos caso cruzados apenas por nome ou nome concatenado à sigla da UF.

### Decisão Tomada e Aplicada no MVP
O código do IBGE de 7 dígitos (`cd_ibge`, tipo `INTEGER`) foi instituído como a **única chave primária e estrangeira canônica de município em todo o sistema**:
1. Banco de dados relacional e espacial (PostGIS).
2. Contratos de payload da API REST e atributos de feição de Vector Tiles (`promoteId: "cd_ibge"`).
3. Estado global e seletores do frontend Preact.
4. Códigos do TSE (`cd_tse`) e IBGE de 6 dígitos existem exclusivamente na camada de ingestão da Fábrica (ETL), sendo convertidos imediatamente por meio de uma tabela de referência auditada (`data/reference/de_para_tse_ibge.csv`).
5. A operação de merge exige validação estrita 1:1 (`pd.merge(..., validate="one_to_one", indicator=True)`). Se um único município deixar de ser pareado, o pipeline lança exceção fatal e aborta a execução.

### Alternativas Rejeitadas
- **Joins por Nome do Município e UF em tempo de execução:** Rejeitado devido a pequenas variações de grafia (acentos, cedilhas, hífens) entre fontes que gerariam inconsistências silenciosas e perda de dados.
- **Uso do código do TSE como chave primária:** Rejeitado porque as bases de dados demográficas, geográficas e fiscais (IBGE, Tesouro, SUS) não conhecem a codificação do TSE.

### Consequências e Trade-offs
- **Positivas:** Eliminação completa de ambiguidades cadastrais; joins de alta performance no PostgreSQL indexados por inteiros; compatibilidade universal com qualquer camada geoespacial futura.
- **Trade-off:** Exige a manutenção contínua e versionada do arquivo de crosswalk no repositório.

---

## ADR-002 — Vector Tiles (MVT) no PostGIS + Recoloração via `feature-state` em GPU

### Status
**Aceito** (Aplicado no MVP)

### Contexto do Problema
O mapa da plataforma precisa renderizar os 5.571 municípios do Brasil com alta resolução, permitindo que o usuário alterne livremente entre cargos e indicadores. Enviar um arquivo GeoJSON tradicional com todas as coordenadas a cada clique consumiria de 20 a 50 MB de dados por requisição, gerando travamentos graves em navegadores móveis e violando a meta de tempo de recoloração do produto (< 300 ms).

### Decisão Tomada e Aplicada no MVP
Adotou-se uma arquitetura em duas camadas desassociadas:
1. **Geometrias Imutáveis em Vector Tiles:** O PostGIS gera Mapbox Vector Tiles binários compactos (`.pbf`) sob demanda através da função `ST_AsMVT(ST_AsMVTGeom(...))`, cacheados com cabeçalhos HTTP imutáveis no navegador.
2. **Separação de Dados Numéricos:** Os valores dos indicadores e votos trafegam separadamente em arrays JSON compactos (~60 KB).
3. **Recoloração em GPU via `feature-state`:** Ao trocar de indicador ou cargo, o frontend consome o JSON e aplica os novos valores diretamente na memória da placa de vídeo via `map.setFeatureState()`. As cores dos municípios são interpoladas por shaders WebGL em ~120 ms, sem rebaixar ou reprocessar as geometrias.

### Alternativas Rejeitadas
- **GeoJSON dinâmico por requisição:** Rejeitado pelo peso excessivo e bloqueio da thread principal do JavaScript.
- **Servidores de Tiles Externos (Martin / pg_tileserv):** Rejeitados no MVP para evitar a sobrecarga operacional de gerenciar um contêiner adicional e regras de rede extras no ambiente de desenvolvimento e deploy.
- **Tiles Rasterizados (PNG):** Rejeitados por não permitirem interatividade no cliente, hover suave nem customização de paletas em tempo de execução.

### Consequências e Trade-offs
- **Positivas:** Tempo de resposta de recoloração de ~120 ms; tráfego de rede ínfimo (< 65 KB por interação); experiência de 60 FPS no mapa.
- **Trade-off:** Exige a configuração minuciosa de expressões de estilo WebGL no MapLibre GL JS e que cada feição do vetor tile contenha `cd_ibge` como ID numérico promovido.

---

## ADR-003 — Insights 100% Determinísticos (Zero LLM no Caminho dos Dados)

### Status
**Aceito** (Aplicado no MVP)

### Contexto do Problema
Ao projetar a exibição de narrativas e conclusões estatísticas (Passo 4 da jornada), avaliou-se a possibilidade de conectar modelos de linguagem de grande porte (LLMs como GPT ou Claude) para redigir parágrafos analíticos em tempo real.
No entanto, auditorias de arquitetura demonstraram que modelos de linguagem introduzem riscos inaceitáveis para uma ferramenta cívica e científica:
- Alucinação de números e distorção de percentuais apurados pelo TSE.
- Inversão de sinais de correlações estatísticas (confundir correlação positiva com negativa).
- Incursão em falácia ecológica por relaxamento de restrições gramaticais.
- Custo financeiro contínuo por tokens e latências de resposta superiores a 2 segundos.

### Decisão Tomada e Aplicada no MVP
**Nenhum modelo de linguagem é executado no caminho dos dados da plataforma.**
1. Todos os cálculos matemáticos (Pearson, Spearman, $p$-valor, regressão linear OLS e decis) são executados em Python puro determinístico (`src/territorio/analytics/stats.py`).
2. Os textos explicativos, manchetes e conclusões são instanciados por um motor de templates auditável (`src/territorio/analytics/insights.py`), cujos ramos condicionais dependem estritamente dos limiares estatísticos calculados.

### Alternativas Rejeitadas
- **LLM com Retrieval-Augmented Generation (RAG):** Rejeitado por persistir o risco de alucinação de texto e inviabilizar a reprodutibilidade científica.
- **LLM gerando insights offline e cacheados:** Rejeitado pela complexidade de pré-computar todas as combinações de cargos, turnos, blocos e indicadores.

### Consequências e Trade-offs
- **Positivas:** Reprodutibilidade matemática absoluta (o mesmo dado sempre gera o mesmo texto); latência sub-milissegundo; custo zero de inferência; imunidade a acusações de viés de modelo.
- **Trade-off:** Menor variedade sintática nos textos, compensada pela precisão e autoridade científica.

---

## ADR-004 — Cálculo de Blocos Ideológicos via `votacao_partido_munzona` + Bolognesi et al. (2023)

### Status
**Aceito** (Aplicado no MVP)

### Contexto do Problema
O sistema precisa cobrir tanto cargos majoritários (Presidente, Governador, Senador) quanto cargos proporcionais (Deputados Federais, Estaduais e Distritais). No Brasil, as eleições proporcionais admitem **votos de legenda** (voto atribuído exclusivamente ao número do partido, sem escolher candidato nominal), representando milhões de sufrágios válidos. Além disso, a categorização ideológica de legendas costuma ser objeto de disputa partidária.

### Decisão Tomada e Aplicada no MVP
1. **Fonte Unificada de Dados Eleitorais:** Utilizar a tabela `votacao_partido_munzona` do TSE para todos os cargos, calculando a votação de cada partido pela soma de votos nominais e de legenda:
   $$\text{Votos Válidos do Partido} = \text{QT\_VOTOS\_NOMINAIS\_VALIDOS} + \text{QT\_TOTAL\_VOTOS\_LEG\_VALIDOS}$$
   A tabela de candidatos (`votacao_candidato_munzona`) é consultada apenas para elencar os concorrentes mais votados nos cargos majoritários.
2. **Fundamentação Acadêmica:** Adotar formalmente a classificação ideológica de **Bolognesi, Ribeiro & Codato (2023, Revista *Dados*)**, que atribui a cada legenda uma nota de 0 a 10 obtida via *survey* com cientistas políticos. Os blocos dividem-se em Esquerda ($<4,0$), Centro ($4,0$ a $6,0$) e Direita ($>6,0$).
3. **Média Ponderada para Fusões:** Partidos criados por fusões pós-pesquisa (ex.: União Brasil, PRD) recebem notas calculadas pela média ponderada das bancadas federais de origem.

### Alternativas Rejeitadas
- **Cálculo de blocos via soma exclusiva de candidatos nominais:** Rejeitado porque desconsideraria 100% dos votos de legenda em eleições proporcionais, gerando subnotificação grave da força partidária.
- **Classificação ideológica definida pela equipe do projeto:** Rejeitado para preservar a estrita isenção e neutralidade da ferramenta.

### Consequências e Trade-offs
- **Positivas:** Contempla a totalidade dos votos válidos; baseia-se em literatura acadêmica revisada por pares; reduz o volume de dados processados em mais de 20× em relação ao processamento de candidatos proporcionais.
- **Trade-off:** Exige manutenção de regras de exceção documentadas para novas fusões partidárias em `backend/data/reference/party_ideology.yaml`.

---

## ADR-005 — Ponderação por Votos Válidos nos Decis e Linguagem Ecológica Estrita

### Status
**Aceito** (Aplicado no MVP)

### Contexto do Problema
Os 5.571 municípios brasileiros apresentam desproporcionalidades demográficas monumentais: Borá (SP) tem cerca de 800 habitantes, enquanto a capital paulista possui mais de 11 milhões. Uma análise por quantis que calcule o comportamento eleitoral pela média aritmética dos percentuais municipais atribui a Borá o mesmo peso de São Paulo, gerando números falsos sobre a vontade real das urnas. Além disso, a extrapolação de dados territoriais para conclusões sobre indivíduos constitui falácia ecológica.

### Decisão Tomada e Aplicada no MVP
1. **Taxa Ponderada do Decil:** O percentual de votos de cada decil é calculado pela soma dos votos nominais e de legenda do bloco em todos os municípios do decil, dividida pela soma dos votos válidos totais do decil:
   $$\text{Taxa Ponderada} = \frac{\sum \text{Votos do Bloco}}{\sum \text{Votos Válidos Totais}} \times 100$$
2. **Linguagem Ecológica Obrigatória:** Todos os textos, cartões e cabeçalhos têm como sujeito estrito **"os municípios"** (ex.: *"Nos municípios com maior cobertura do programa..."*), sendo proibido o uso de expressões como *"eleitores pobres"* ou *"a população rica votou"*.

### Alternativas Rejeitadas
- **Média simples de percentuais municipais:** Rejeitada por distorcer o resultado eleitoral em favor de pequenas localidades rurais.
- **Linguagem jornalística coloquial generalista:** Rejeitada por induzir o leitor ao erro de atribuição individual (falácia ecológica).

### Consequências e Trade-offs
- **Positivas:** Rigor matemático inatacável; representação fidedigna das urnas; compromisso pedagógico com o combate à desinformação.
- **Trade-off:** Exige explicação metodológica complementar para usuários que esperam encontrar uma média aritmética convencional.

---

## ADR-006 — Separação Cromática Estrita entre Espectro Político e Indicadores

### Status
**Aceito** (Aplicado no MVP)

### Contexto do Problema
Se uma interface utiliza uma escala cromática contínua de vermelho a azul para representar vulnerabilidade social ou PIB, o cérebro humano associa subconscientemente o indicador ao bloco político que utiliza as mesmas cores (Esquerda = Vermelho, Direita = Azul), gerando vieses de julgamento e confusão na leitura dos mapas.

### Decisão Tomada e Aplicada no MVP
Instituiu-se a regra inegociável de isolamento cromático:
1. **Vermelho/Terracota (`#C23B22`) e Azul/Cobalto (`#1D6996`) são exclusivos para a visualização de votos de blocos políticos.**
2. Indicadores socioeconômicos e fiscais utilizam exclusivamente paletas sequenciais perceptualmente uniformes e seguras para daltonismo:
   - **Vulnerabilidade Social:** Rampa `YlOrPu` (Amarelo → Laranja → Roxo).
   - **Indicadores Fiscais e IDHM:** Rampa `SequentialTeal` (Tons de Turquesa).
   - **Economia e Agropecuária:** Rampa `SequentialEmerald` (Tons de Esmeralda).

### Alternativas Rejeitadas
- **Uso de rampas semafóricas (Verde vs. Vermelho):** Rejeitado por inacessibilidade a pessoas com daltonismo (deuteranopia/protanopia) e por emitir juízo de valor sobre o dado.
- **Uso de rampa divergente Vermelho-Azul para indicadores contínuos:** Rejeitado pelo risco imediato de viés de confirmação político.

### Consequências e Trade-offs
- **Positivas:** Clareza visual cognitiva imediata; neutralidade editorial; conformidade com as diretrizes de acessibilidade WCAG 2.2 AA.
- **Trade-off:** Reduz o espectro de paletas disponíveis para indicadores, exigindo calibragem precisa de tons de saturação.

---

## ADR-007 — Desacoplamento da Fábrica de ETL do Backend API e Estratégia de Deploy Cloud Free-Tier

### Status
**Aceito** (Evolução planejada para Pós-MVP / Fase F6)

### Contexto do Problema
O backend do repositório foi inicialmente estruturado como um monólito modular agrupando a API web (FastAPI) e a Fábrica de ETL (`src/territorio/etl`). O pipeline de ETL processa arquivos massivos do TSE com bibliotecas de dados pesadas (`pandas`, `geopandas`, `pyogrio`, bindings em C do GDAL/GEOS).
Contudo, para hospedagem pública de validação em nuvem gratuita (*cloud free-tier*, como Render, Railway, Fly.io, Neon e Cloudflare Pages), os contêineres web oferecem recursos extremamente modestos (256 a 512 MB de RAM). Rodar um pipeline pesado de ETL dentro do mesmo processo do servidor web causaria falhas fatais de esgotamento de memória (*Out-Of-Memory* - OOM) e derrubaria a API.

### Decisão Tomada e Aplicada no MVP
1. **Durante o MVP (Fases F0 a F5):**
   - Manter a coesão do monólito em `backend/` para maximizar a velocidade de desenvolvimento local e simplificar a suíte de testes.
   - Desacoplar operacionalmente a execução: o ETL roda sob demanda como job batch local ou runner gratuito (ex.: GitHub Actions com 7 GB de RAM), conectando-se remotamente ao banco PostGIS na nuvem com credenciais de escrita. A API web executa em modo estritamente *stateless* e *read-only*.
2. **Pós-MVP (Fase F6 / Produção):**
   - Reorganizar o projeto em monorepo com **UV Workspaces**:
     - `frontend/`: UI estática distribuída globalmente em edge gratuito (Cloudflare Pages ou Vercel).
     - `services/api/`: Servidor FastAPI ultraleve sem dependências em C de GIS (apenas `fastapi`, `uvicorn`, `psycopg`, `scipy`, `orjson`), consumindo menos de 80 MB de RAM em repouso.
     - `services/etl/`: Pacote batch de ingestão e validação executado exclusivamente sob demanda.
     - `packages/core/`: Modelos canônicos de domínio e migrações Alembic compartilhados.

### Alternativas Rejeitadas
- **Microsserviços distribuídos desde a Fase F0:** Rejeitado pelo custo desnecessário de complexidade de rede e orquestração durante a fase de prototipagem e validação do produto.
- **Hospedagem em instâncias de nuvem pagas de alta capacidade:** Rejeitado para viabilizar um projeto cívico sustentável com custo fixo zero de infraestrutura na fase de validação.

### Consequências e Trade-offs
- **Positivas:** Permite colocar a plataforma em produção na nuvem com custo zero; garante estabilidade da API e isolamento de permissões de escrita no banco.
- **Trade-off:** Exige uma etapa de refatoração de estrutura de diretórios na Fase F6 para formalizar os workspaces do UV.
