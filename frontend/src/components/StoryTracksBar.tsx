import { STORY_TRACKS } from "../data/storyTracks";
import {
  activeStoryTrackSignal,
  applyStoryTrack,
  indicatorSignal,
} from "../state/store";
import type { StoryTrack } from "../types/api";

export function StoryTracksBar() {
  const activeTrackId = activeStoryTrackSignal.value;
  const currentTrack = STORY_TRACKS.find((t) => t.id === activeTrackId);

  const handleSelectTrack = (track: StoryTrack): void => {
    if (activeTrackId === track.id) {
      activeStoryTrackSignal.value = null;
      return;
    }
    applyStoryTrack(track);
  };

  return (
    <section
      class="story-tracks-container"
      aria-label="Pautas Editoriais em Destaque"
    >
      <div class="story-tracks-header">
        <span class="story-tracks-badge">Pautas em Destaque</span>
        <span class="story-tracks-hint">
          Cruze indicadores e votos com 1 clique:
        </span>
      </div>

      <div
        class="story-tracks-grid"
        role="group"
        aria-label="Pautas temáticas guiadas"
      >
        {STORY_TRACKS.map((track, idx) => {
          const isSelected =
            activeTrackId === track.id &&
            indicatorSignal.value === track.preset.indicator;
          const isFullWidth =
            idx === STORY_TRACKS.length - 1 && STORY_TRACKS.length % 2 !== 0;

          return (
            <button
              key={track.id}
              type="button"
              class={`story-track-chip story-track-card ${isSelected ? "is-selected" : ""} ${isFullWidth ? "is-full-width" : ""}`}
              aria-pressed={isSelected}
              onClick={() => handleSelectTrack(track)}
              title={track.description}
            >
              <span class="story-track-icon" aria-hidden="true">
                {track.icon}
              </span>
              <div class="story-track-info">
                <span class="story-track-title">{track.short_title}</span>
                <span class="story-track-theme">{track.theme}</span>
              </div>
            </button>
          );
        })}
      </div>

      {currentTrack && (
        <div class="story-track-active-banner">
          <div class="story-track-active-row">
            <span class="story-track-active-tag">
              {currentTrack.icon} {currentTrack.title}
            </span>
            <button
              type="button"
              class="theme-tab-btn"
              onClick={() => {
                activeStoryTrackSignal.value = null;
              }}
              aria-label="Fechar resumo da trilha"
            >
              ✕ Fechar trilha
            </button>
          </div>
          <p class="story-track-question">{currentTrack.question}</p>
          <p class="story-track-desc">{currentTrack.description}</p>
        </div>
      )}
    </section>
  );
}
