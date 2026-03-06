# Tobu — AI Running Coach

## Project Overview

Tobu (飛ぶ — Japanese for "to fly") is a personal AI-powered running coach that pulls Garmin data after every run, combines it with contextual information, and uses Claude to analyze performance and suggest the next run. The goal is steady, sustainable fitness improvement — not race training.

## Core Loop

1. User runs → Garmin captures all data
2. Tobu pulls run stats via `python-garminconnect`
3. User answers a single post-run check-in question (harder / easier / same)
4. Weather and terrain context are added automatically
5. Claude analyzes everything against recent run history
6. Claude outputs a plain-text next-run recommendation

## Goals & Principles

- Improve aerobic fitness at a safe, consistent rate
- No race targets — just get better overall
- Keep weekly mileage increase within ~10% to avoid injury
- Follow the 80/20 rule: ~80% of runs should be easy, ~20% hard efforts
- Personal tool first — built for one user, maybe shared with 1-2 friends
- Keep Claude prompts concise — send summarized run data, not raw GPS

## Tech Stack

- **Garmin data:** `python-garminconnect` (unofficial Python wrapper, no approval needed)
- **AI analysis:** Anthropic Claude API (`claude-sonnet-4-6`)
- **Weather:** OpenWeatherMap API (free tier)
- **Terrain/hills:** OpenTopoData API (free)
- **Storage:** SQLite or local JSON for run history
- **Frontend:** TBD

## Data Pulled from Garmin

### Objective Stats
- Average and max heart rate, HR zones
- Pace and splits
- Cadence and ground contact time
- Elevation gain
- HRV and training load
- VO₂ max
- Shoe mileage

### Subjective Stats (Post-run Form)
- Harder / easier / same vs. recent runs (Beli-style)
- Optional free-text: "anything feel off?" (legs, breathing, joints)

## Key Features

- **Beli-style check-in** — one question after every run: harder / easier / same
- **Weather awareness** — contextualize performance against temp & humidity at time of run
- **Terrain/hill awareness** — know what elevation is nearby, factor into suggestions
- **Run type variety** — mix easy, tempo, and interval runs automatically
- **Shoe tracking** — warn when shoes approach ~400 miles
- **Rest day intelligence** — suggest rest proactively based on HRV + training load
- **Weekly digest** — Claude-generated summary of the week and focus for next week
- **Progress visualization** — VO₂ max trend, weekly mileage, HR at given pace over time
- **Fitness progression logic** — ensure weekly load increases safely, flag plateaus
- **80/20 enforcement** — flag if the user is running too hard too often

## Intelligence Rules for Claude

When analyzing a run and generating recommendations, Claude should:

1. Compare the run against the last 3–5 runs and note trends
2. Check if weekly mileage is increasing by more than ~10% — if so, pull back
3. Check the ratio of hard to easy runs — flag if too many hard efforts recently
4. Factor in weather (high heat/humidity = adjust effort expectations)
5. Factor in nearby terrain (hills available? recovery run or strength day?)
6. Flag early injury warning signs: asymmetric ground contact, rising RPE with declining pace
7. Suggest rest if HRV is trending down and training load is high
8. Track shoe mileage and warn when approaching 400 miles

## Project Phases

### Phase 1 — Foundation & Research
- [x] Name the app (Tobu)
- [x] Set up Notion workspace
- [x] Read `python-garminconnect` docs and run demo.py
- [x] Identify exact Garmin fields to pull
- [x] Get Anthropic API key and test a basic Claude call

### Phase 2 — Core Data Loop (MVP)
- [x] Script to log into Garmin and pull last run stats
- [x] Design post-run check-in (harder / easier / same + optional text)
- [x] Build Claude prompt with run data + check-in
- [x] Get Claude returning a plain-text next-run recommendation
- [x] Test end-to-end on a real run

### Phase 3 — Intelligence Layer
- [x] Add weather context to Claude prompt
- [x] Implement Beli-style comparison (last 3–5 runs)
- [ ] Fitness progression logic (safe weekly load increase)
- [x] 80/20 rule awareness
- [x] Rest day recommendations

### Phase 4 — Progress Visualization
- [ ] Decide key metrics to visualize
- [ ] Build simple dashboard or weekly summary view
- [ ] Weekly Claude-generated digest

### Phase 5 — Polish & Friends
- [ ] Clean up UI for sharing
- [ ] Make Garmin login easy for others
- [ ] Gather feedback from 1–2 friends
- [ ] Iterate based on real usage

## API Notes

- Official Garmin API requires business approval — skip, use `python-garminconnect` instead
- Claude API costs ~cents per run analysis at personal scale
- Store API keys in a `.env` file — never hardcode them
- Use `python-dotenv` to load environment variables

## Environment Variables

```
ANTHROPIC_API_KEY=your_key_here
GARMIN_EMAIL=your_garmin_email
GARMIN_PASSWORD=your_garmin_password
OPENWEATHER_API_KEY=your_key_here
```
