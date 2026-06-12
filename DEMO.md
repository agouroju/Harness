# Demo Speaker Notes — AI DevTool Radar (3 minutes)

## Before you're called up (do this 5 min early)

1. Open these 4 tabs, in order, and keep them warm:
   - **Tab 1:** https://ai-devtool-radar.onrender.com  ← load it NOW (free tier cold-starts ~50s)
   - **Tab 2:** Langfuse traces: us.cloud.langfuse.com → project `radar` → Tracing
   - **Tab 3:** cloud.airbyte.com → Connections (shows all 13 pipelines)
   - **Tab 4:** https://cited.md/article/d8589037-c7f0-4aa3-957f-5c7ba0f5600b
2. On Tab 1, press **Sync & publish briefing** once as a dress rehearsal, so a fresh
   `success` row exists no matter what happens live.

---

## 0:00 — The hook (Tab 1 visible, don't click yet)

> "Every person in this room loses hours a week trying to keep up with AI tooling —
> new models, breaking changes, repo drama. Human analysts are slow and don't cite
> sources. LLM summaries hallucinate.
>
> This is **AI DevTool Radar**: a fully autonomous analyst. You tell it what to
> watch — it does literally everything else, and every claim it publishes comes
> with a receipt."

## 0:30 — Show the product (Tab 1, interact)

Point at the metrics row:

> "It's watching 10 GitHub repos and 12 news feeds right now — OpenAI, Anthropic,
> DeepMind, Hugging Face, Hacker News. Each one is a **real Airbyte pipeline**
> syncing into ClickHouse every hour."

Type a feed URL into "Track a new source" (have one ready, e.g. `https://blog.cloudflare.com/rss/`), click **Start tracking**:

> "Watch this — I just added a source. The app talked to Airbyte's API and created
> an actual managed pipeline, first sync already running. That's the only thing a
> human ever does."

Click **Sync & publish briefing**:

> "Now I've asked it to publish. While it works, let me show you what 'it works' means."

## 1:15 — The brain (Tab 2: Langfuse)

Open the most recent trace, click into `propose-sql` / the generation:

> "This is the part I'm proudest of. The agent is shown the live database schema and
> **writes its own SQL** — this query, hunting for issue spikes and provider news,
> was authored by the model seconds ago, not by me. It then fetches the *full*
> source articles and HN comment threads for what it found — so it summarizes what
> actually happened, not RSS snippets. Every prompt, every query, every cent —
> about two-hundredths of a cent per run — is traced here."

## 1:45 — The pipes (Tab 3: Airbyte, 15 seconds, don't linger)

> "Thirteen managed pipelines, hourly, incremental — including the one I created on
> stage a minute ago. No scraping code anywhere in the repo."

## 2:00 — The payoff (Tab 4: cited.md)

Scroll the article slowly:

> "And this is the output — a published intelligence briefing on cited.md, updated
> autonomously throughout the day. Look at the links: **every single claim cites
> the issue, the post, or the thread it came from.** An analyst that never sleeps
> and always shows receipts."

(Flip to Tab 1, point at the run row showing `success` — the rehearsal run, or the
live one if it finished.)

## 2:30 — Stack + business, then land it

> "Five sponsor tools, each load-bearing: **Airbyte** is the entire ingestion layer
> and the control plane. **ClickHouse** is the memory and the analysis engine.
> **Senso** grounds the evidence and publishes to **cited.md**. **Langfuse** makes an
> autonomous agent auditable. And the whole product — frontend and backend — runs
> on **Render**.
>
> Monetization: the daily briefing is free; premium deep-dives go behind an **x402
> paywall so other agents pay to read them** — the publishing pipeline already
> supports it.
>
> AI DevTool Radar: you choose the sources, it does the rest — with receipts. Thanks."

## 3:00 — done.

---

## Q&A ammo (likely questions)

- **"Is the SQL really written by the model?"** → Yes — show the Langfuse generation:
  schema goes in, SQL comes out; there's a SELECT-only guard so it can't mutate data.
- **"What if a feed publishes 6 posts at once?"** → Airbyte syncs incrementally on the
  published-date cursor — all 6 land as separate rows; the agent considers everything
  in a 24h window, not just the latest.
- **"One article or many?"** → One briefing per day, updated by each run (Senso dedupes
  to the daily title). Multiple per-topic articles is the x402 premium tier.
- **"Why not LangChain/agent framework?"** → The loop is ~300 lines of stdlib Python;
  the leverage is in the managed services, not glue frameworks.
- **"What breaks?"** → OpenAI/Anthropic block bot RSS readers — solved with Google News
  mirror feeds. ClickHouse Cloud doesn't support FINAL — agent dedupes with argMax.
  Both are in the repo's HANDOFF.md.

## If something fails on stage

- **App cold/slow** → talk over it with Tab 2 (Langfuse) — the trace story works alone.
- **Live run is slow** → the rehearsal run's `success` row + Tab 4's article ARE the
  proof; never wait silently on a spinner.
- **Wi-Fi dies entirely** → the repo README has the architecture diagram; pitch from it.
