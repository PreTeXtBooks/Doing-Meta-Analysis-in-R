@import url("https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Serif:wght@400;500;600;700&display=swap");

/* Tier 2 overrides loaded via html.css.extra */
:root {
  /* Brand palette */
  --brand-orange: #F37021;
  --brand-teal: #649BA3;
  --brand-slate: #44575E;
  --brand-mint: #C1FDE8;

  /* Variables used by default-modern theme.css */
  --font-headings: "IBM Plex Sans", "Helvetica Neue", Helvetica, Arial, sans-serif;
  --font-body: "IBM Plex Sans", "Helvetica Neue", Helvetica, Arial, sans-serif;
  --font-monospace: "IBM Plex Mono", Consolas, Monaco, monospace;
  --font-print: "IBM Plex Serif", "Times New Roman", Times, serif;

  /* Direct color overrides used throughout the theme */
  --primary-color: var(--brand-orange);
  --secondary-color: var(--brand-teal);
  --doc-title-color: var(--brand-slate);
  --link-text-color: var(--brand-orange);
  --link-active-text-color: var(--brand-slate);
}

/* Explicit selectors ensure font overrides apply even if vars change upstream */
body.pretext {
  font-family: var(--font-body);
}

.heading,
.ptx-masthead .title-container {
  font-family: var(--font-headings);
}

code,
pre,
.program,
.console,
.code-display {
  font-family: var(--font-monospace);
}

/* Layout for a custom link row injected by custom-footer.js */
.ptx-page-footer {
  flex-wrap: wrap;
  row-gap: 0.25rem;
}

.custom-site-footer-link-wrap {
  display: block;
  flex-basis: 100%;
  order: 99;
  margin: 0;
  padding: 0 0 1.1rem;
  text-align: center;
}

.custom-site-footer-link {
  font-size: 0.9rem;
  color: var(--brand-orange);
  text-decoration: underline;
  text-underline-offset: 0.15em;
}

.custom-site-footer-link:hover,
.custom-site-footer-link:focus-visible {
  color: var(--link-active-text-color);
}

/* Match this theme's dark mode strategy (:root.dark-mode) */
:root.dark-mode {
  --page-color: #0a0a0a;
  --content-background: #111111;
  --body-text-color: #e0e0e0;
  --body-title-color: #f0f0f0;
  --page-border-color: #333333;
  --link-text-color: #C1FDE8;
  --link-active-text-color: #7DB1B8;
}
