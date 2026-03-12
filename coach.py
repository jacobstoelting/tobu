import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

CLIENT = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are Tobu, a personal AI running coach. Respond in exactly two sections using these headers:

ANALYZING YOUR RUN
YOUR NEXT RUN

Guidelines for ANALYZING YOUR RUN:
- Interpret the data — don't just repeat numbers. Tell the runner what the data means.
- Assess training load and estimate recovery time needed before the next hard effort.
- If the runner mentions any issues, injuries, or notes, address them directly.
- Identify trends over recent runs (improving, plateau, overreaching, etc.).
- Flag anything relevant: 80/20 balance, injury warning signs, weekly mileage creep.
- Use the ELO ranking and pairwise comparisons to contextualize how hard this run was relative to recent history. Do not mention ELO scores or rankings in your response — use them only to inform your interpretation.
- Factor in weather only if it meaningfully affected performance (e.g., significant heat, high humidity, strong wind, notable altitude). Do not list raw weather stats — interpret the impact.
- Keep this section to 3-5 concise bullet points.

Guidelines for YOUR NEXT RUN:
- Recommend one specific next run. Be concrete: type, distance, effort level.
- You may recommend structured workouts when appropriate, such as:
  - Interval sessions (e.g., "4x1200m at 5K effort with 90s rest")
  - Fartlek runs (e.g., "30-min fartlek — alternate 1 min hard / 2 min easy")
  - Tempo runs (e.g., "4mi with 2mi at threshold pace")
  - Easy/recovery runs, long runs, strides
- If the forecast is notable (heat wave, rain, etc.), factor it into the recommendation timing or type.
- Keep this section to 2-3 sentences.

Use miles and min/mile for all distances and paces. Use plain prose with bullet points only in the analysis section."""


def _fmt_weather(weather, forecast):
    if not weather:
        w_line = "Weather data unavailable (no GPS or API error)."
    else:
        parts = []
        if weather.get("temp_f") is not None:
            parts.append(f"{weather['temp_f']}°F")
        if weather.get("feels_like_f") is not None:
            parts.append(f"feels like {weather['feels_like_f']}°F")
        if weather.get("humidity_pct") is not None:
            parts.append(f"{weather['humidity_pct']:.0f}% humidity")
        if weather.get("wind_mph") is not None:
            parts.append(f"wind {weather['wind_mph']} mph")
        if weather.get("uv_index") is not None:
            parts.append(f"UV {weather['uv_index']:.0f}")
        if weather.get("precipitation_in") and weather["precipitation_in"] > 0:
            parts.append(f"{weather['precipitation_in']}\" precip")
        if weather.get("altitude_ft") is not None:
            parts.append(f"altitude ~{weather['altitude_ft']:,} ft")
        w_line = "  ".join(parts) if parts else "No data."

    if not forecast:
        f_lines = "  Forecast unavailable."
    else:
        f_lines = "\n".join(
            f"  {f['date']}  {f['summary']}  "
            f"H:{f['high_f']}°F L:{f['low_f']}°F  "
            f"wind {f['wind_mph']} mph  UV {f['uv_index']:.0f}"
            for f in forecast
            if f.get("high_f") is not None
        )

    return w_line, f_lines


def _fmt_splits(splits):
    if not splits:
        return "No split data."
    lines = []
    for s in splits:
        hr = f"HR {s['avg_hr']:.0f}" if s.get("avg_hr") else ""
        lines.append(f"  Lap {s['lap']}: {s['distance_mi']}mi at {s['pace']} {hr}")
    return "\n".join(lines)


def _fmt_recent(recent_runs):
    if not recent_runs:
        return "No recent runs in the past 2 weeks."
    lines = []
    for r in recent_runs[:5]:
        load = r.get("training_load")
        load_str = f"load {load:.0f}" if load else ""
        pace = r.get("avg_pace_min_mi") or r.get("avg_pace", "?")
        elo = r.get("elo_score")
        elo_str = f"ELO {elo:.0f}" if elo else ""
        lines.append(
            f"  {r['date'][:10]}  {r['distance_mi']}mi  {pace}  "
            f"avg HR {r.get('avg_hr', '?')}  {load_str}  {elo_str}"
        )
    return "\n".join(lines)


def _fmt_comparisons(comparisons, elo_ranking, today_date):
    if not comparisons:
        return "No pairwise comparisons available."
    harder = sum(1 for c in comparisons if c["result"] == "harder")
    easier = sum(1 for c in comparisons if c["result"] == "easier")
    same   = sum(1 for c in comparisons if c["result"] == "same")
    total  = len(comparisons)
    summary = f"Harder than {harder}/{total} recent runs, easier than {easier}/{total}, same as {same}/{total}."

    # ELO rank (for context only — not shown in output)
    rank_str = ""
    if elo_ranking:
        for i, r in enumerate(elo_ranking):
            if r["date"][:10] == today_date[:10]:
                rank_str = f" Relative difficulty rank: {i + 1} of {len(elo_ranking)} (use for context only, do not quote this)."
                break

    details = "\n".join(
        f"  vs {c['other_date']}: {c['result']}" for c in comparisons
    )
    return f"{summary}{rank_str}\n{details}"


def _fmt_hrv(hrv):
    if not hrv:
        return "HRV data unavailable."
    return (
        f"Last night avg: {hrv['last_night_avg']} ms  "
        f"Weekly avg: {hrv['weekly_avg']} ms  "
        f"Status: {hrv['status']}  "
        f"Baseline range: {hrv['baseline_balanced_low']}–{hrv['baseline_balanced_high']} ms"
    )


def _fmt_sleep(sleep):
    if not sleep:
        return "Sleep data unavailable."
    return (
        f"{sleep['total_hours']}h total  "
        f"({sleep['deep_hours']}h deep, {sleep['rem_hours']}h REM)  "
        f"Score: {sleep['overall_score']} ({sleep['score_qualifier']})  "
        f"Avg stress during sleep: {sleep['avg_sleep_stress']}"
    )


def build_prompt(current_run, recent_runs, health, feel, notes, comparisons=None, elo_ranking=None, weather=None, forecast=None):
    splits_text = _fmt_splits(current_run.get("splits", []))
    recent_text = _fmt_recent(recent_runs)
    comparison_text = _fmt_comparisons(comparisons or [], elo_ranking or [], current_run.get("date", ""))
    weather_text, forecast_text = _fmt_weather(weather, forecast)

    bb = health.get("body_battery") or {}
    stress = health.get("stress") or {}

    prompt = f"""Here is data from my most recent run. Analyze it and recommend my next run.

--- TODAY'S RUN ---
Date: {current_run['date'][:10]}
Distance: {current_run['distance_mi']} mi
Duration: {current_run['duration_min']} min
Avg pace: {current_run.get('avg_pace_min_mi') or current_run.get('avg_pace', '?')}
Fastest mile: {current_run.get('fastest_mile_pace')}
Avg HR: {current_run.get('avg_hr')} bpm  Max HR: {current_run.get('max_hr')} bpm
HR zones (seconds): Z1={current_run.get('hr_zone_1_sec', 0):.0f}  Z2={current_run.get('hr_zone_2_sec', 0):.0f}  Z3={current_run.get('hr_zone_3_sec', 0):.0f}  Z4={current_run.get('hr_zone_4_sec', 0):.0f}  Z5={current_run.get('hr_zone_5_sec', 0):.0f}
Cadence: {current_run.get('avg_cadence', '?')} spm
Elevation gain: {current_run.get('elevation_gain_ft')} ft
Aerobic training effect: {current_run.get('aerobic_training_effect')}
Anaerobic training effect: {current_run.get('anaerobic_training_effect')}
Training load: {current_run.get('training_load')}
VO2 max: {current_run.get('vo2max')}
Body battery change during run: {current_run.get('body_battery_change')}

Splits:
{splits_text}

--- HOW IT FELT ---
Feel rating: {feel}
Notes: {notes or 'None'}

--- PAIRWISE COMPARISONS & ELO ---
{comparison_text}

--- RECENT RUNS (past 2 weeks) ---
{recent_text}

--- WEATHER DURING RUN ---
{weather_text}

--- 3-DAY FORECAST ---
{forecast_text}

--- RECOVERY & HEALTH (today) ---
HRV: {_fmt_hrv(health.get('hrv'))}
Resting HR: {health.get('resting_hr')} bpm
Sleep: {_fmt_sleep(health.get('sleep'))}
Body battery charged overnight: {health.get('body_battery_charged')}
Body battery today — charged: {bb.get('charged')}  drained: {bb.get('drained')}
Avg stress today: {stress.get('avg')}  Max stress: {stress.get('max')}

What should my next run be?"""

    return prompt


def get_recommendation(current_run, recent_runs, health, feel, notes, comparisons=None, elo_ranking=None, weather=None, forecast=None):
    prompt = build_prompt(current_run, recent_runs, health, feel, notes, comparisons, elo_ranking, weather, forecast)

    message = CLIENT.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    return message.content[0].text
