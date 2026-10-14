import {
  indicatorSignal,
  navigateToStoryStep,
  storyStepSignal,
} from "../state/store";
import type { StoryStep } from "../types/api";

interface StepConfig {
  step: StoryStep;
  title: string;
  subtitle: string;
}

const STEPS: readonly StepConfig[] = [
  { step: 1, title: "Visão Macro", subtitle: "Panorama nacional" },
  { step: 2, title: "A Pergunta", subtitle: "Escolha o indicador" },
  { step: 3, title: "A Revelação", subtitle: "Dispersão e decis" },
  { step: 4, title: "A Conclusão", subtitle: "Insights e método" },
];

export function StoryStepper() {
  const currentStep = storyStepSignal.value;
  const hasIndicator = indicatorSignal.value !== null;

  return (
    <nav class="story-stepper" aria-label="Etapas da narrativa de dados">
      {STEPS.map((item) => {
        const isActive = currentStep === item.step;
        return (
          <button
            key={item.step}
            type="button"
            class={`stepper-btn ${isActive ? "is-active" : ""}`}
            aria-current={isActive ? "step" : undefined}
            onClick={() => {
              if (item.step >= 3 && !hasIndicator) {
                navigateToStoryStep(2);
              } else {
                navigateToStoryStep(item.step);
              }
            }}
          >
            <span class="stepper-num tabular-nums">Etapa {item.step}</span>
            <span class="stepper-label">{item.title}</span>
          </button>
        );
      })}
    </nav>
  );
}
