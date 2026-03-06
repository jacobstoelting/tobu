# Tobu 飛ぶ

An AI-powered personal running coach that pulls Garmin data after every run and uses Claude to analyze your performance and suggest your next run.

## What it does

After each run, Tobu:
1. Pulls your stats from Garmin (pace, heart rate, cadence, elevation, HRV, etc.)
2. Asks one simple check-in question: *harder / easier / same?*
3. Adds weather and terrain context automatically
4. Sends everything to Claude for analysis
5. Returns a plain-text recommendation for your next run

## Goals

- Improve aerobic fitness at a safe, sustainable rate
- Keep weekly mileage increases within ~10%
- Follow the 80/20 rule: ~80% easy runs, ~20% hard efforts
- No race targets — just consistent improvement

## Tech Stack

- **Garmin data** — `python-garminconnect`
- **AI analysis** — Anthropic Claude API (`claude-sonnet-4-6`)
- **Weather** — OpenWeatherMap API
- **Terrain** — OpenTopoData API
- **Storage** — SQLite

## Setup

1. Clone the repo
2. Install dependencies:
pip install -r requirements.txt


3. Create a `.env` file in the project root:
ANTHROPIC_API_KEY=your_key_here
GARMIN_EMAIL=your_garmin_email
GARMIN_PASSWORD=your_garmin_password
OPENWEATHER_API_KEY=your_key_here


4. Run:
python main.py



## Status

Currently in active development — Phase 2 (Core Data Loop).
