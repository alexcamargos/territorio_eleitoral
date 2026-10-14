# 11 — Padrões de Engenharia, Qualidade e Estratégia de Testes

> **Diretrizes estritas de desenvolvimento Python e TypeScript, arquitetura de testes com Pytest e Vitest, e automação de garantia de qualidade no MVP.**

---

## 1. Princípios de Engenharia de Software

O desenvolvimento do **Território Eleitoral** pauta-se pelo rigor da engenharia moderna:
- **Prevenção ativa de defeitos:** Testes automatizados cobrindo cálculos estatísticos, contratos de dados, rotas de API e componentes de interface.
- **Homogeneidade de estilo:** Linters rápidos e estritos em ambas as frentes (Ruff no backend, ESLint/TypeScript no frontend).
- **Auditabilidade de código:** Docstrings padronizadas e tipagem estática em 100% das assinaturas de funções.

---

## 2. Padrões de Código Python (Backend)

O backend (`backend/`) adota convenções rigorosas:
1. **Gerenciador de Dependências:** Uso exclusivo do **Astral `uv`**. Comandos `pip` diretos não são utilizados no repositório.
2. **Conformidade PEP 8 e Ruff:**
   - Indentação de 4 espaços, limite de linha de 100 caracteres.
   - Imports ordenados em três blocos canônicos: biblioteca padrão, terceiros e módulos locais do projeto (Ruff `I`).
3. **Docstrings no Padrão Google:** Obrigatórias em todos os módulos, classes, funções e métodos públicos:
   ```python
   def calculate_weighted_deciles(
       df: pd.DataFrame,
       indicator_col: str,
       votes_col: str,
       valid_votes_col: str,
   ) -> list[dict[str, Any]]:
       """Calcula a participação eleitoral ponderada por votos válidos em 10 decis.

       Args:
           df: DataFrame contendo as métricas municipais.
           indicator_col: Nome da coluna contendo os valores do indicador.
           votes_col: Nome da coluna com a quantidade de votos do bloco.
           valid_votes_col: Nome da coluna com a quantidade de votos válidos.

       Returns:
           Lista de dicionários representando os decis de D1 a D10 com taxas ponderadas.

       Raises:
           ValueError: Se o DataFrame estiver vazio ou faltar alguma coluna obrigatória.
       """
   ```
4. **Tipagem Estática Completa:** Suporte a Python 3.12 com *type hinting* nativo em todas as variáveis e estruturas de retorno.

---

## 3. Estratégia de Testes do Backend (Pytest)

Em conformidade com as regras inegociáveis do projeto:
- **Estrutura Baseada em Funções:** Todos os testes são escritos exclusivamente como funções nativas do `pytest`. O uso do módulo `unittest`, de classes `unittest.TestCase` ou de `unittest.mock` é **terminantemente proibido**.
- **Mocking com `pytest-mock`:** Todo isolamento de dependências externas (como chamadas HTTP a portais de dados abertos ou conexões de rede) utiliza o fixture oficial `mocker`.

### 3.1 Camadas Testadas no Backend
- **Testes de Schema (`tests/test_schemas.py`):** Validação dos esquemas do Pandera garantindo que DataFrames inválidos lancem exceções descritivas.
- **Testes Estatísticos (`tests/test_stats.py`):** Validação dos algoritmos de correlação de Pearson, Spearman e decis ponderados contra conjuntos de dados de controle analítico.
- **Testes de Insights Determinísticos (`tests/test_insights.py`):** Checagem de que nenhuma frase contenha sujeitos individuais e de que os textos respeitem os limiares estatísticos calculados.
- **Testes de API e Contratos (`tests/test_api.py`):** Testes de integração com `TestClient` cobrindo rotas `/api/v1/meta`, `/api/v1/metrics`, `/api/v1/analytics/stats` e a integridade binária dos tiles MVT.

---

## 4. Padrões e Testes do Frontend (TypeScript & Vitest)

- **TypeScript Estrito:** Compilação em modo `strict: true` sem uso do tipo permissivo `any`.
- **Vitest como Test Runner:** Execução ultrarrápida de testes de unidade e componentes com ambiente DOM simulado via `jsdom`.
- **Testes de Contrato de Interface (`frontend/tests/components.test.tsx`):**
  - Auditoria automatizada do Design System para assegurar que nenhum componente `.tsx` contenha cores hexadecimais *hardcoded*.
  - Testes da lógica de sincronização bidirecional de parâmetros na URL (`urlSync.ts`).
  - Formatação invariante de números decimais no padrão brasileiro (`pt-BR`, ex.: `"1.234,56"`).

---

## 5. Testes E2E com Navegador Headless

Para homologar a integração real entre WebGL (MapLibre), Canvas (Scatter Plot) e a API FastAPI, o repositório conta com scripts de automação E2E baseados em navegadores headless (`scripts/verify_e2e_headless.py`):
1. Inicializa um navegador Chromium sem interface gráfica.
2. Navega até a aplicação e aguarda o carregamento dos tiles vetoriais no canvas WebGL.
3. Simula a interação do usuário com o seletor de indicadores e confere se os valores do Scatter Plot e o gráfico de decis foram atualizados em menos de 300 ms.
4. Captura evidências visuais e afere o console do navegador em busca de erros de execução.

---

## 6. Definition of Done (Critérios de Homologação)

Nenhum código é mesclado ao branch principal sem atender à linha completa de aceitação:

```powershell
# 1. Checagem de linter e formatação Python
cd backend
uv run ruff check .
uv run ruff format --check .

# 2. Execução dos testes unitários e de integração Python
uv run pytest

# 3. Execução dos testes do frontend
cd ../frontend
npm run test:run

# 4. Verificação de integridade dos dados pós-ETL
cd ../backend
uv run territorio etl verify
```
