# 07 — Metodologia Científica e Rigor Estatístico

> **Fundamentação teórica, combate à falácia ecológica, ponderação demográfica de decis, classificação ideológica e métricas de correlação.**

---

## 1. Princípios Metodológicos

O **Território Eleitoral** foi concebido com uma premissa fundamental: dados políticos possuem alto impacto social e não podem ser apresentados com descuido metodológico. Cada número, gráfico e texto gerado na plataforma segue critérios rigorosos da ciência política e da estatística aplicada.

---

## 2. A Falácia Ecológica e a Regra da Linguagem Ecológica

### 2.1 O Que É a Falácia Ecológica?
Documentada pioneiramente por William S. Robinson (1950), a **falácia ecológica** consiste no erro estatístico e cognitivo de deduzir conclusões sobre o comportamento de **indivíduos** a partir de dados agregados de **grupos ou territórios**.

> *Exemplo de falácia:* "O município X tem 80% de beneficiários do Bolsa Família e deu 75% dos votos ao candidato A; logo, os beneficiários do Bolsa Família votam no candidato A."

Essa dedução é cientificamente incorreta: é matematicamente possível que o candidato A tenha recebido votos predominantemente de não-beneficiários naquele município ou que outros fatores locais expliquem o resultado.

### 2.2 Como o Território Eleitoral Resolve Esse Risco ([ADR-005](13-decisoes-arquiteturais.md#adr-005--ponderação-por-votos-válidos-nos-decis-e-linguagem-ecológica-estrita))
1. **Regra Gramatical Estrita nos Templates:** Todos os textos e cartões gerados pela plataforma têm como sujeito gramatical **"os municípios"**, e nunca pessoas ou classes sociais:
   - *Correto:* "Nos municípios com maior dependência de transferências, o bloco X obteve..."
   - *Proibido:* "Os eleitores mais pobres votaram no bloco X..."
2. **Aviso Metodológico Permanente:** A interface exibe aviso pedagógico formal informando que os dados retratam agregados territoriais e não devem ser extrapolados para o comportamento de indivíduos isolados.

---

## 3. Ponderação Demográfica nos Decis (D1 a D10)

### 3.1 A Armadilha da Média Simples de Municípios
O Brasil possui 5.571 municípios com disparidades demográficas extremas:
- **Serra da Saudade (MG)** e **Borá (SP)** possuem menos de 900 habitantes cada.
- **São Paulo (SP)** possui mais de 11,4 milhões de habitantes.

Se calcularmos o comportamento do eleitorado de um decil através da média aritmética simples dos percentuais municipais, o resultado será espúrio: a cidade de 800 habitantes terá exatamente o mesmo peso que a metrópole de 11 milhões, gerando uma distorção grave da vontade das urnas.

### 3.2 A Fórmula Correta Aplicada no MVP
Para cada decil de indicador $d$, o percentual de votos de um bloco político é calculado pela razão matemática entre a **soma de votos absolutos do bloco** e a **soma de votos válidos de todos os municípios do decil**:

$$\text{Taxa Ponderada do Bloco } (\% ) = \frac{\sum_{i \in d} \text{Votos do Bloco}_i}{\sum_{i \in d} \text{Votos Válidos}_i} \times 100$$

A média simples dos percentuais municipais é calculada apenas como metadado secundário para comparação de dispersão interna, mas o gráfico de barras principal reflete estritamente a taxa ponderada.

---

## 4. Classificação Ideológica dos Partidos Políticos

Para evitar subjetivismos editoriais ou acusações de partidarismo, a categorização dos partidos políticos no MVP apoia-se em uma única fonte acadêmica consagrada na ciência política contemporânea:

### 4.1 A Escala Bolognesi, Ribeiro & Codato (2023)
- **Referência:** BOLOGNESI, Bruno; RIBEIRO, Ednaldo; CODATO, Adriano. *A Nova Classificação Ideológica dos Partidos Políticos Brasileiros*. Dados — Revista de Ciências Sociais, Rio de Janeiro, vol. 66, n. 2, 2023.
- **Metodologia dos Autores:** Pesquisa tipo *expert survey* com dezenas de cientistas políticos brasileiros avaliando o posicionamento das legendas em uma escala contínua de **0 (extrema-esquerda) a 10 (extrema-direita)**.

### 4.2 Agrupamento em Blocos no MVP
Os partidos são agrupados em três blocos operacionais conforme seus escores médios:
- **Esquerda (`left`):** Escore ideológico $< 4,0$ (ex.: PT, PSOL, PCdoB, PSB, PDT, Rede).
- **Centro (`center`):** Escore ideológico entre $4,0$ e $6,0$ (ex.: MDB, PSD, Cidadania, PSDB).
- **Direita (`right`):** Escore ideológico $> 6,0$ (ex.: PL, PP, Republicanos, União Brasil, Novo).

### 4.3 Regra para Fusões e Mudanças Pós-Pesquisa
Para partidos resultantes de fusões recentes que não constavam no levantamento original de 2023, o escore é calculado pela média ponderada pelo número de deputados federais eleitos pelas siglas de origem na legislatura correspondente:
- **União Brasil (UNIÃO):** Média ponderada entre DEM e PSL.
- **PRD:** Média ponderada entre PTB e Patriota.

A fonte da verdade reside no arquivo versionado `backend/data/reference/party_ideology.yaml`. Se um partido sem classificação for encontrado pelo pipeline, o ETL aborta imediatamente com erro ([ADR-004](13-decisoes-arquiteturais.md#adr-004--cálculo-de-blocos-ideológicos-via-votacao_partido_munzona--bolognesi-et-al-2023)).

---

## 5. Fórmulas Estatísticas Determinísticas

Todas as análises do módulo `analytics/stats.py` são executadas com algoritmos fechados e reprodutíveis:

### 5.1 Correlação Linear de Pearson ($r$)
Avalia a intensidade e o sentido da associação linear entre o indicador $X$ e o percentual de votos $Y$:

$$r = \frac{\sum (X_i - \bar{X})(Y_i - \bar{Y})}{\sqrt{\sum (X_i - \bar{X})^2 \sum (Y_i - \bar{Y})^2}}$$

### 5.2 Correlação por Postos de Spearman ($\rho$)
Mede a força de uma relação monótona, mesmo que não seja puramente linear, sendo resistente a outliers e assimetrias comuns em indicadores de renda:

$$\rho = 1 - \frac{6 \sum d_i^2}{n(n^2 - 1)}$$

Onde $d_i$ é a diferença entre os postos ranqueados de $X_i$ e $Y_i$.

### 5.3 Regressão Linear por Mínimos Quadrados Ordinários (OLS)
Determina a linha de tendência traçada no gráfico de dispersão:
- **Inclinação ($\beta_1$):** $\beta_1 = \frac{\text{Cov}(X, Y)}{\text{Var}(X)}$
- **Intercepto ($\beta_0$):** $\beta_0 = \bar{Y} - \beta_1 \bar{X}$
- **Coeficiente de Determinação ($R^2$):** Proporção da variância eleitoral associada à variação do indicador ($R^2 = r^2$).
