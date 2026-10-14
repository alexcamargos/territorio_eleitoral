import { useEffect } from "preact/hooks";
import { BLOC_LABELS_PT, formatDecimalPt } from "../lib/format";
import {
  isMethodologyOpenSignal,
  metaDataSignal,
} from "../state/store";

export function MethodologyModal() {
  const isOpen = isMethodologyOpenSignal.value;
  const meta = metaDataSignal.value;

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === "Escape") {
        isMethodologyOpenSignal.value = false;
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen]);

  if (!isOpen) {
    return null;
  }

  const closeModal = (): void => {
    isMethodologyOpenSignal.value = false;
  };

  const parties = meta?.party_ideology ?? [];

  return (
    <div
      class="modal-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          closeModal();
        }
      }}
    >
      <div
        class="methodology-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="methodology-modal-title"
      >
        <header class="modal-header">
          <div>
            <h2 id="methodology-modal-title" class="editorial-headline">
              Metodologia, Fontes e Classificação Ideológica
            </h2>
            <p class="indicator-row-meta" style={{ margin: "4px 0 0 0" }}>
              Transparência estatística, proveniência oficial e interpretação ecológica
            </p>
          </div>
          <button
            type="button"
            class="icon-btn"
            aria-label="Fechar janela de metodologia"
            onClick={closeModal}
          >
            Fechar ✕
          </button>
        </header>

        <div class="modal-body">
          <section class="panel-section">
            <h3 class="section-title">
              1. Abordagem Ecológica (Prevenção à Falácia Ecológica)
            </h3>
            <p class="insight-card-body">
              A unidade de análise do <strong>Território Eleitoral</strong> é o{" "}
              <strong>município brasileiro (5.571 municípios na malha IBGE 2025)</strong>.
              Todas as correlações (Spearman ρ e Pearson r) e participações por
              decis descrevem como <em>municípios</em> com diferentes condições
              sociais, econômicas e fiscais votaram de forma agregada. Esses
              resultados <strong>jamais</strong> devem ser interpretados como
              inferência direta sobre o comportamento individual de moradores.
            </p>
          </section>

          <section class="panel-section">
            <h3 class="section-title">
              2. Ponderação por Votos Válidos nos Decis
            </h3>
            <p class="insight-card-body">
              Para evitar que municípios de pequeno porte tenham o mesmo peso
              eleitoral que grandes metrópoles na comparação entre decis (D1 a
              D10), a participação de cada bloco dentro de cada decil é
              calculada pela razão entre a{" "}
              <strong>soma total de votos do bloco nos municípios do decil</strong>{" "}
              e a <strong>soma total de votos válidos no decil</strong>{" "}
              (<code>weighted_share</code>).
            </p>
          </section>

          <section class="panel-section">
            <h3 class="section-title">
              3. Classificação Ideológica Partidária — Bolognesi, Ribeiro &amp; Codato (2023)
            </h3>
            <p class="insight-card-body">
              Os partidos são agrupados em <strong>Esquerda</strong> (nota{" "}
              <span class="tabular-nums">0,00 ≤ s &lt; 4,00</span>),{" "}
              <strong>Centro</strong> (<span class="tabular-nums">4,00 ≤ s ≤ 6,00</span>)
              e <strong>Direita</strong> (<span class="tabular-nums">6,00 &lt; s ≤ 10,00</span>)
              segundo o <em>expert survey</em> publicado na revista{" "}
              <em>Dados — Revista de Ciências Sociais</em> (v. 66, n. 2, 2023),
              com regras documentadas de média ponderada por bancada para fusões
              partidárias pós-survey (UNIÃO, PRD).
            </p>

            {parties.length > 0 && (
              <table
                class="accessible-table tabular-nums"
                aria-label="Tabela de classificação ideológica dos partidos"
              >
                <thead>
                  <tr>
                    <th scope="col">Partido</th>
                    <th scope="col">Nota (0–10)</th>
                    <th scope="col">Bloco</th>
                    <th scope="col">Método</th>
                    <th scope="col">Fonte / Regra</th>
                  </tr>
                </thead>
                <tbody>
                  {parties.map((p) => (
                    <tr key={p.party_code}>
                      <td>
                        <strong class="mono-code">{p.party_code}</strong>
                      </td>
                      <td>{formatDecimalPt(p.score, 2)}</td>
                      <td>{BLOC_LABELS_PT[p.bloc]}</td>
                      <td>{p.method}</td>
                      <td>{p.source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section class="panel-section">
            <h3 class="section-title">4. Fontes Públicas e Exceções Territoriais</h3>
            <p class="insight-card-body">
              Dados eleitorais: <strong>TSE — Repositório de Dados Eleitorais (2026)</strong>.
              Indicadores e malha cartográfica: <strong>IBGE (Malha 2025, Censo 2022, SIDRA, Cidades)</strong>,{" "}
              <strong>Portal da Transparência / CGU</strong>,{" "}
              <strong>Tesouro Nacional (SICONFI / CAPAG)</strong>,{" "}
              <strong>Firjan (IFDM/IFGF)</strong>, <strong>IPS Brasil</strong>,{" "}
              <strong>IPEA (IVS)</strong> e <strong>PNUD / Atlas Brasil (IDHM)</strong>.
              Exceções estruturais documentadas: Boa Esperança do Norte/MT
              (<code>5101837</code>, instalado em 2025), Brasília/DF (
              <code>5300108</code>, regime fiscal estadual/distrital) e Fernando
              de Noronha/PE (<code>2605459</code>, distrito estadual).
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
