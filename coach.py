import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

CLIENT = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are Tobu, a personal AI running coach. Your job is to analyze a runner's most recent run and recommend what their next run should be.

Guidelines:
- Keep weekly mileage increases within ~10% to avoid injury
- Follow the 80/20 rule: ~80% of runs should be easy (zone 1-2), ~20% hard efforts
- Factor in HRV, resting HR, body battery, and sleep quality when assessing recovery
- If HRV is below baseline or body battery is low, lean toward rest or easy run
- Infer run type from splits and HR zones (intervals, tempo, easy, long run)
- Be concise — 3 to 5 sentences max
- Output plain text only, no markdown, no bullet points
- Use miles and min/mile for all distances and paces
- End with a single specific next-run recommendation: type, distance in miles, and effort level"""


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
        lines.append(
            f"  {r['date'][:10]}  {r['distance_mi']}mi  {pace}  "
            f"avg HR {r.get('avg_hr', '?')}  {load_str}"
        )
    return "\n".join(lines)


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


def build_prompt(current_run, recent_runs, health, feel, notes):
    splits_text = _fmt_splits(current_run.get("splits", []))
    recent_text = _fmt_recent(recent_runs)

    bb = health.get("body_battery") or {}
    stress = health.get("stress") or {}

    prompt = f"""Here is data from my most recent run. Please recommend what my next run should be.

--- TODAY'S RUN ---
Date: {current_run['date'][:10]}
Distance: {current_run['distance_mi']} mi
Duration: {current_run['duration_min']} min
Avg pace: {current_run['avg_pace_min_mi']}
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

--- RECENT RUNS (past 2 weeks) ---
{recent_text}

--- RECOVERY & HEALTH (today) ---
HRV: {_fmt_hrv(health.get('hrv'))}
Resting HR: {health.get('resting_hr')} bpm
Sleep: {_fmt_sleep(health.get('sleep'))}
Body battery charged overnight: {health.get('body_battery_charged')}
Body battery today — charged: {bb.get('charged')}  drained: {bb.get('drained')}
Avg stress today: {stress.get('avg')}  Max stress: {stress.get('max')}

What should my next run be?"""

    return prompt


def get_recommendation(current_run, recent_runs, health, feel, notes):
    prompt = build_prompt(current_run, recent_runs, health, feel, notes)

    message = CLIENT.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    return message.content[0].text
