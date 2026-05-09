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

<!-- _class: center -->
<div class="kicker">MandarinOS / Pre-launch Video 1</div>

# Imagine spending over <span class="accent">$7,000</span> learning Chinese…

<p class="lead muted">…and still not being able to properly hold a conversation.</p>

---

# That’s literally me.

<div class="grid-2">
<div class="card">

### My situation
- Chinese wife
- daily access to a native speaker
- years of study
- still struggle speaking

</div>
<div class="card">

### What I expected
More exposure = easier speaking

### What actually happened
I still froze in real conversations

</div>
</div>

---

<!-- _class: center -->

<p class="kicker">what I tried</p>

<div class="big">$1,700 China immersion</div>


![width:200](CLI.png)

<div class="big">$2,000 coaching</div>

![width:200](CantoMando.png)

<div class="big">$800 Mandarin Blueprint</div>

![width:200](MandarinBlueprint.png)

---

# And then the apps.

<div class="card list-tight">

![width:150](duolingo.png)![width:200](LanguaTalk.jpg) ![width:500](superchinese.png)
![width:200](RosettaStone.svg)![width:100](pimsleur.jpg)  ![width:200](MaaYot.svg) 

</div>

<p class="muted">Basically every serious option I could find.</p>

---

<!-- _class: center -->
<p class="kicker">the reality</p>

<div class="huge danger">I still freeze.</div>

<p class="lead">One or two sentences… then my brain goes blank.</p>

---

<!-- _class: center -->
<p class="kicker">what it feels like</p>

<div class="quote">Panic. Blank mind. Pressure. Then I switch back to English.</div>

---

<!-- _class: center -->
<p class="kicker">the embarrassing part</p>

# “Sorry, my Chinese isn’t very good.”

<p class="muted">After all that time, money, and exposure.</p>

---

# And I know I’m not the only one.

<div class="grid-2">
<div class="card">

### So many learners…
- study for years
- know lots of vocabulary
- understand grammar
- can read basic Chinese

</div>
<div class="card">

### But then…
- conversation starts
- speed increases
- pressure rises
- everything falls apart

</div>
</div>

---

<!-- _class: center -->
<p class="kicker">the question</p>

<div class="big">How can someone spend this much time, money, and effort…</div>

<div class="big yellow">and STILL not speak?</div>

---

# My realisation

<div class="card">

### The problem is not:
❌ laziness
❌ lack of discipline
❌ Chinese being “too hard”

</div>

---

<!-- _class: center -->
<p class="kicker">core insight</p>

<div class="huge accent">We are being taught the wrong skill.</div>

---

<!-- _class: center -->
<p class="kicker">close</p>

# If this sounds like your experience…

<p class="lead">follow me.</p>

<p class="muted">In the next few posts, I’ll explain why most Chinese learning methods fail intermediate learners.</p>
