/**
 * Spatial indexing and radius scaling for the high-density Canvas + SVG ScatterPlot (`docs/09-frontend.md` §4).
 */

import { quadtree, type Quadtree } from "d3-quadtree";

export interface ScreenScatterPoint {
  cdIbge: number;
  uf?: string;
  name?: string;
  px: number;
  py: number;
  radius: number;
  xVal: number;
  yVal: number;
  validVotes: number;
  region: string;
}

export interface SpatialScatterIndex {
  findNearest(
    mouseX: number,
    mouseY: number,
    maxDistancePx?: number,
  ): ScreenScatterPoint | null;
}

/**
 * Computes the screen radius in pixels (`[minR, maxR]`) proportional to `sqrt(validVotes)`.
 */
export function computePointRadius(
  validVotes: number,
  maxValidVotes: number,
  minR = 2.5,
  maxR = 7.0,
): number {
  if (maxValidVotes <= 0 || validVotes <= 0) {
    return minR;
  }
  const ratio = Math.min(1, Math.sqrt(validVotes) / Math.sqrt(maxValidVotes));
  return minR + ratio * (maxR - minR);
}

/**
 * Builds a `d3-quadtree` spatial index over projected screen coordinates for `< 0.05 ms` hover lookups.
 */
export function buildSpatialIndex(
  points: readonly ScreenScatterPoint[],
): SpatialScatterIndex {
  const tree: Quadtree<ScreenScatterPoint> = quadtree<ScreenScatterPoint>()
    .x((d) => d.px)
    .y((d) => d.py)
    .addAll([...points]);

  return {
    findNearest(
      mouseX: number,
      mouseY: number,
      maxDistancePx = 12,
    ): ScreenScatterPoint | null {
      const found = tree.find(mouseX, mouseY, maxDistancePx);
      return found ?? null;
    },
  };
}
