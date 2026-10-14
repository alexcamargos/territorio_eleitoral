import { tokenizeInsightText } from "../lib/format";
import { analysisDataSignal, blocSignal } from "../state/store";
import type { InsightCardPayload } from "../types/api";

interface InsightCardsProps {
  cardsOverride?: readonly InsightCardPayload[];
}

export function InsightCards({ cardsOverride }: InsightCardsProps) {
  const analysis = analysisDataSignal.value;
  const bloc = blocSignal.value;
  const cards = cardsOverride ?? analysis?.insights ?? [];

  if (cards.length === 0) {
    return null;
  }

  return (
    <div
      class="insight-cards-list"
      aria-live="polite"
      aria-atomic="false"
      role="region"
      aria-label="Conclusões e notas metodológicas determinísticas"
    >
      {cards.map((card) => {
        const tokens = tokenizeInsightText(card.text);
        return (
          <article
            key={card.template_id}
            class={`insight-card severity-${card.severity} bloc-${bloc}`}
          >
            <h3 class="insight-card-title">{card.title}</h3>
            <p class="insight-card-body">
              {tokens.map((tok, idx) =>
                tok.bold ? (
                  <strong key={idx} class="tabular-nums">
                    {tok.text}
                  </strong>
                ) : (
                  <span key={idx}>{tok.text}</span>
                ),
              )}
            </p>
          </article>
        );
      })}
    </div>
  );
}
