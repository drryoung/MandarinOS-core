---
marp: true
theme: default
paginate: false
size: 9:16
style: |
  /* @theme mandarinos — vertical (9:16); content top two-thirds; bottom third clear for talking-head overlay */
  :root {
    --bg: #0f1115;
    --panel: #171a21;
    --text: #f5f7fb;
    --muted: #b7c0cf;
    --accent: #52e3c2;
    --accent2: #7aa2ff;
    --danger: #ff6b6b;
    --yellow: #ffd166;
  }

  section {
    font-family: Inter, Avenir Next, Segoe UI, Helvetica, Arial, sans-serif;
    position: relative;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    align-items: stretch;
    min-height: 100%;
    box-sizing: border-box;
    background:
      radial-gradient(circle at 50% 10%, rgba(82,227,194,0.08), transparent 24%),
      linear-gradient(180deg, #11151c 0%, #0e1014 100%);
    color: var(--text);
    padding: 32px 40px 0 56px;
    font-size: 26px;
    line-height: 1.25;
  }

  section::after {
    content: "";
    flex: 1 0 auto;
    min-height: 33%;
    pointer-events: none;
  }

  section::before {
    content: "";
    position: absolute;
    left: 28px;
    top: 28px;
    bottom: 34%;
    width: 8px;
    border-radius: 999px;
    background: linear-gradient(180deg, var(--accent) 0%, var(--accent2) 100%);
    opacity: 0.95;
  }

  h1, h2, h3 {
    margin: 0 0 0.25em 0;
    line-height: 1.05;
    letter-spacing: -0.03em;
  }

  h1 {
    font-size: 1.75em;
    max-width: 100%;
  }

  h2 {
    font-size: 1.5em;
    color: var(--accent);
  }

  p, li {
    color: var(--text);
  }

  .lead {
    font-size: 1.2em;
    font-weight: 700;
    color: var(--text);
  }

  .muted {
    color: var(--muted);
  }

  .big {
    font-size: 2.05em;
    font-weight: 900;
    letter-spacing: -0.05em;
    line-height: 0.95;
  }

  .huge {
    font-size: 2.65em;
    font-weight: 900;
    letter-spacing: -0.06em;
    line-height: 0.9;
  }

  .accent { color: var(--accent); }
  .blue { color: var(--accent2); }
  .danger { color: var(--danger); }
  .yellow { color: var(--yellow); }

  .grid-2 {
    display: grid;
    grid-template-columns: 1fr;
    gap: 18px;
  }

  .card {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 22px;
    padding: 22px 24px;
  }

  .card h3 {
    font-size: 1.05em;
    margin-bottom: 0.4em;
  }

  .list-tight ul, .list-tight ol {
    margin-top: 0.15em;
  }

  .list-tight li {
    margin: 0.2em 0;
  }

  .quote {
    font-size: 1.35em;
    font-weight: 700;
    line-height: 1.2;
  }

  .center {
    text-align: center;
  }

  .center h1, .center h2, .center p {
    margin-left: auto;
    margin-right: auto;
  }

  .kicker {
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.16em;
    font-size: 0.52em;
    font-weight: 800;
    margin-bottom: 1.25em;
  }

  footer {
    color: rgba(255,255,255,0.38);
    font-size: 0.45em;
  }

  small {
    color: var(--muted);
  }
---

<!--
MandarinOS MARP Template
Usage:
1) Duplicate this file for each new video.
2) Keep 1 core idea per slide.
3) Prefer 2–8 words on emphasis slides.
4) Slides are 9:16 vertical; reserve the bottom third for a talking-head overlay in post.
5) In Cursor/VS Code with the Marp extension, export to PDF/PPTX from the command palette.
-->

<!-- _class: center -->
<div class="kicker">MandarinOS / Video Deck Template</div>

# Replace with your hook

<p class="lead muted">One emotionally strong sentence.</p>

---

# Core proof

<div class="grid-2">
<div class="card">

### Pain / proof
- Cost
- time
- failed methods

</div>
<div class="card">

### Audience mirror
- what they tried
- where they freeze
- what they feel

</div>
</div>

---

<!-- _class: center -->
<p class="kicker">emphasis slide</p>

<div class="huge accent">Replace with a big claim</div>

<p class="muted">3–7 words underneath if needed</p>

---

# Aha moment

<div class="quote">“Explain the hidden distinction that changes how the audience sees the problem.”</div>

---

# Optional comparison

<div class="grid-2">
<div class="card">

### What people think
Old assumption

</div>
<div class="card">

### What you now believe
New framing

</div>
</div>

---

<!-- _class: center -->
<p class="kicker">CTA</p>

# Replace with your call to action

<p class="lead">Follow for the next breakdown.</p>
