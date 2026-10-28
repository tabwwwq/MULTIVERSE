/*
 * Hero illustration: the product's own chart grammar. Observed history reaches a
 * decision date and splits into a dashed baseline and two alternatives, with a
 * quantile band and the orbit of the brand mark. It is a picture of the visual
 * language, not data. The draw-in runs once on load and only when the user has not
 * asked for reduced motion (styles in app/globals.css, .motif-*). The default is the
 * finished, static drawing.
 */

export function TimelineMotif() {
  return (
    <svg
      viewBox="0 0 960 400"
      role="img"
      aria-labelledby="motif-title motif-desc"
      className="motif h-auto w-full"
      data-testid="timeline-motif"
    >
      <title id="motif-title">Diverging scenario paths</title>
      <desc id="motif-desc">
        Illustration only. One observed history reaches a decision date and splits into a dashed
        baseline forecast and two alternative scenarios, one with an uncertainty band.
      </desc>

      <g className="motif-grid" stroke="var(--color-line)" strokeWidth="1">
        {[60, 140, 220, 300, 380].map((y) => (
          <line key={y} x1="0" y1={y} x2="960" y2={y} opacity="0.55" />
        ))}
        {[120, 240, 360, 600, 720, 840].map((x) => (
          <line key={x} x1={x} y1="372" x2={x} y2="388" opacity="0.9" />
        ))}
      </g>

      <line
        className="motif-marker"
        x1="480"
        y1="36"
        x2="480"
        y2="380"
        stroke="var(--color-ink-muted)"
        strokeWidth="1.5"
        strokeDasharray="3 5"
      />

      <path
        className="motif-observed"
        pathLength={1}
        d="M24 312 C 96 304, 132 262, 196 270 S 300 232, 352 222 S 432 204, 480 200"
        fill="none"
        stroke="var(--color-observed)"
        strokeWidth="3"
        strokeLinecap="round"
      />

      <g className="motif-branches">
        <path
          className="motif-band"
          d="M480 200 C 600 160, 720 96, 936 48 L 936 140 C 720 154, 600 182, 480 200 Z"
          fill="var(--color-mint)"
          opacity="0.14"
        />
        <path
          d="M480 200 C 600 190, 720 180, 936 168"
          fill="none"
          stroke="var(--color-blue)"
          strokeWidth="3"
          strokeDasharray="10 8"
          strokeLinecap="round"
        />
        <path
          d="M480 200 C 600 172, 720 124, 936 92"
          fill="none"
          stroke="var(--color-mint)"
          strokeWidth="3.5"
          strokeLinecap="round"
        />
        <path
          d="M480 200 C 600 220, 720 256, 936 276"
          fill="none"
          stroke="var(--color-violet)"
          strokeWidth="3"
          strokeDasharray="2 7"
          strokeLinecap="round"
        />
      </g>

      <g className="motif-orbit">
        <ellipse
          cx="480"
          cy="200"
          rx="86"
          ry="30"
          transform="rotate(-18 480 200)"
          fill="none"
          stroke="var(--color-line-strong)"
          strokeWidth="1.5"
        />
        <circle cx="560" cy="176" r="4" fill="var(--color-mint)" />
      </g>
      <circle
        cx="480"
        cy="200"
        r="7"
        fill="var(--color-canvas)"
        stroke="var(--color-ink)"
        strokeWidth="2.5"
      />
    </svg>
  );
}
