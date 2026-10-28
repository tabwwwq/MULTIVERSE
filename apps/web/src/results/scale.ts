/*
 * Axis domains and ticks. Honest scales (PRD FP-09, docs/10 chart grammar): absolute
 * values always include zero, so a 3% move cannot fill the chart; changes against the
 * baseline are centred on zero with equal room above and below.
 */

export type DomainRule = "include_zero" | "symmetric_zero";

function niceStep(span: number, count: number): number {
  const raw = span / Math.max(1, count);
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const fraction = raw / magnitude;
  const nice =
    fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10;
  return nice * magnitude;
}

export interface Axis {
  min: number;
  max: number;
  ticks: number[];
}

export function axisFor(values: readonly number[], rule: DomainRule, tickCount = 5): Axis {
  const finite = values.filter(Number.isFinite);
  let low = Math.min(0, ...finite);
  let high = Math.max(0, ...finite);
  if (rule === "symmetric_zero") {
    const reach = Math.max(Math.abs(low), Math.abs(high));
    low = -reach;
    high = reach;
  }
  if (high - low === 0) {
    high = rule === "symmetric_zero" ? 1 : high + 1;
    low = rule === "symmetric_zero" ? -1 : low;
  }
  const step = niceStep(high - low, tickCount);
  const min = Math.floor(low / step) * step;
  const max = Math.ceil(high / step) * step;
  const ticks: number[] = [];
  for (let tick = min; tick <= max + step / 2; tick += step)
    ticks.push(Number(tick.toPrecision(12)));
  return { min, max, ticks };
}

export function linear(
  domain: [number, number],
  range: [number, number],
): (value: number) => number {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const span = d1 - d0 || 1;
  return (value) => r0 + ((value - d0) / span) * (r1 - r0);
}
