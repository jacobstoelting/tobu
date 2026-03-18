import os
from datetime import datetime, timedelta, date as date_type
from garminconnect import Garmin
from dotenv import load_dotenv

load_dotenv()

METERS_PER_MILE = 1609.34
FEET_PER_METER = 3.28084
INCHES_PER_CM = 0.393701


def get_client(email: str, password: str):
    from db import get_garmin_tokens, save_garmin_tokens

    cached = get_garmin_tokens(email)
    if cached:
        try:
            client = Garmin(email, password)
            client.login(tokenstore=cached)
            return client
        except Exception:
            pass

    client = Garmin(email, password)
    client.login()
    try:
        save_garmin_tokens(email, client.garth.dumps())
    except Exception:
        pass
    return client


def get_last_run(email: str = None, password: str = None):
    email = email or os.environ.get("GARMIN_EMAIL")
    password = password or os.environ.get("GARMIN_PASSWORD")
    client = get_client(email, password)

    activities = client.get_activities(0, 10)
    last_run = next(
        (a for a in activities if a.get("activityType", {}).get("typeKey") == "running"),
        None
    )

    if not last_run:
        print("No recent runs found.")
        return None

    activity_id = last_run["activityId"]
    splits_data = client.get_activity_splits(activity_id)

    run = {
        # Core
        "date": last_run.get("startTimeLocal"),
        "start_lat": last_run.get("startLatitude"),
        "start_lon": last_run.get("startLongitude"),
        "distance_mi": round(last_run.get("distance", 0) / METERS_PER_MILE, 2),
        "duration_min": round(last_run.get("duration", 0) / 60, 1),
        "avg_pace_min_mi": _pace(last_run.get("distance"), last_run.get("duration")),
        "fastest_mile_pace": _pace(METERS_PER_MILE, last_run.get("fastestSplit_1609")),
        "location": last_run.get("locationName"),

        # Heart rate
        "avg_hr": last_run.get("averageHR"),
        "max_hr": last_run.get("maxHR"),
        "hr_zone_1_sec": last_run.get("hrTimeInZone_1"),
        "hr_zone_2_sec": last_run.get("hrTimeInZone_2"),
        "hr_zone_3_sec": last_run.get("hrTimeInZone_3"),
        "hr_zone_4_sec": last_run.get("hrTimeInZone_4"),
        "hr_zone_5_sec": last_run.get("hrTimeInZone_5"),

        # Running dynamics
        "avg_cadence": last_run.get("averageRunningCadenceInStepsPerMinute"),
        "avg_ground_contact_ms": last_run.get("avgGroundContactTime"),
        "avg_vertical_oscillation_in": round(last_run.get("avgVerticalOscillation", 0) * INCHES_PER_CM, 2) or None,
        "avg_vertical_ratio_pct": last_run.get("avgVerticalRatio"),
        "avg_stride_length_in": round(last_run.get("avgStrideLength", 0) * INCHES_PER_CM, 1) or None,

        # Power
        "avg_power_w": last_run.get("avgPower"),
        "normalized_power_w": last_run.get("normPower"),

        # Elevation
        "elevation_gain_ft": round(last_run.get("elevationGain", 0) * FEET_PER_METER, 0),

        # Training load / effect
        "aerobic_training_effect": last_run.get("aerobicTrainingEffect"),
        "anaerobic_training_effect": last_run.get("anaerobicTrainingEffect"),
        "training_load": last_run.get("activityTrainingLoad"),
        "vo2max": last_run.get("vO2MaxValue"),

        # Wellness
        "calories": last_run.get("calories"),
        "body_battery_change": last_run.get("differenceBodyBattery"),

        # Splits (per-lap breakdown)
        "splits": _parse_splits(splits_data),
    }

    return run


def get_recent_runs(days=14, email: str = None, password: str = None):
    email = email or os.environ.get("GARMIN_EMAIL")
    password = password or os.environ.get("GARMIN_PASSWORD")
    client = get_client(email, password)
    cutoff = datetime.now() - timedelta(days=days)

    activities = client.get_activities(0, 20)
    recent_runs = []
    for a in activities:
        if a.get("activityType", {}).get("typeKey") != "running":
            continue
        start = a.get("startTimeLocal", "")
        try:
            run_date = datetime.strptime(start[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if run_date < cutoff:
            continue
        recent_runs.append({
            "date": start,
            "distance_mi": round(a.get("distance", 0) / METERS_PER_MILE, 2),
            "duration_min": round(a.get("duration", 0) / 60, 1),
            "avg_pace_min_mi": _pace(a.get("distance"), a.get("duration")),
            "avg_hr": a.get("averageHR"),
            "max_hr": a.get("maxHR"),
            "avg_cadence": a.get("averageRunningCadenceInStepsPerMinute"),
            "elevation_gain_ft": round(a.get("elevationGain", 0) * FEET_PER_METER, 0),
            "aerobic_training_effect": a.get("aerobicTrainingEffect"),
            "anaerobic_training_effect": a.get("anaerobicTrainingEffect"),
            "training_load": a.get("activityTrainingLoad"),
            "vo2max": a.get("vO2MaxValue"),
        })

    return recent_runs


def get_health_snapshot(for_date: str = None, email: str = None, password: str = None):
    email = email or os.environ.get("GARMIN_EMAIL")
    password = password or os.environ.get("GARMIN_PASSWORD")
    client = get_client(email, password)
    if for_date is None:
        for_date = date_type.today().isoformat()

    snapshot = {}

    # HRV
    try:
        hrv_data = client.get_hrv_data(for_date)
        summary = hrv_data.get("hrvSummary", {})
        baseline = summary.get("baseline", {})
        snapshot["hrv"] = {
            "last_night_avg": summary.get("lastNightAvg"),
            "weekly_avg": summary.get("weeklyAvg"),
            "5min_peak": summary.get("lastNight5MinHigh"),
            "status": summary.get("status"),
            "baseline_low": baseline.get("lowUpper"),
            "baseline_balanced_low": baseline.get("balancedLow"),
            "baseline_balanced_high": baseline.get("balancedUpper"),
        }
    except Exception:
        snapshot["hrv"] = None

    # Sleep
    try:
        sleep = client.get_sleep_data(for_date)
        dto = sleep.get("dailySleepDTO", {})
        scores = dto.get("sleepScores", {})
        snapshot["sleep"] = {
            "total_hours": round(dto.get("sleepTimeSeconds", 0) / 3600, 1),
            "deep_hours": round(dto.get("deepSleepSeconds", 0) / 3600, 1),
            "light_hours": round(dto.get("lightSleepSeconds", 0) / 3600, 1),
            "rem_hours": round(dto.get("remSleepSeconds", 0) / 3600, 1),
            "overall_score": scores.get("overall", {}).get("value"),
            "score_qualifier": scores.get("overall", {}).get("qualifierKey"),
            "avg_spo2": dto.get("averageSpO2Value"),
            "avg_respiration": dto.get("averageRespirationValue"),
            "avg_sleep_hr": dto.get("averageSpO2HRSleep"),
            "avg_sleep_stress": dto.get("avgSleepStress"),
            "feedback": dto.get("sleepScoreFeedback"),
        }
        snapshot["resting_hr"] = sleep.get("restingHeartRate")
        snapshot["hrv_overnight_avg"] = sleep.get("avgOvernightHrv")
        snapshot["hrv_status"] = sleep.get("hrvStatus")
        snapshot["body_battery_charged"] = sleep.get("bodyBatteryChange")
    except Exception:
        snapshot["sleep"] = None
        snapshot["resting_hr"] = None

    # Body battery
    try:
        bb_data = client.get_body_battery(for_date)
        if bb_data:
            bb = bb_data[0]
            snapshot["body_battery"] = {
                "charged": bb.get("charged"),
                "drained": bb.get("drained"),
            }
    except Exception:
        snapshot["body_battery"] = None

    # Stress
    try:
        stress = client.get_stress_data(for_date)
        snapshot["stress"] = {
            "avg": stress.get("avgStressLevel"),
            "max": stress.get("maxStressLevel"),
        }
    except Exception:
        snapshot["stress"] = None

    return snapshot


def _parse_splits(splits_data):
    if not splits_data or "lapDTOs" not in splits_data:
        return []
    result = []
    for i, lap in enumerate(splits_data["lapDTOs"], 1):
        result.append({
            "lap": i,
            "distance_mi": round(lap.get("distance", 0) / METERS_PER_MILE, 2),
            "pace": _pace(lap.get("distance"), lap.get("duration")),
            "avg_hr": lap.get("averageHR"),
            "avg_cadence": lap.get("averageRunCadence"),
            "avg_power_w": lap.get("averagePower"),
            "ground_contact_ms": lap.get("groundContactTime"),
            "vertical_oscillation_in": round(lap.get("verticalOscillation", 0) * INCHES_PER_CM, 2) or None,
        })
    return result


def _pace(distance_m, duration_s):
    if not distance_m or not duration_s:
        return None
    pace_s_per_mi = duration_s / (distance_m / METERS_PER_MILE)
    minutes = int(pace_s_per_mi // 60)
    seconds = int(pace_s_per_mi % 60)
    return f"{minutes}:{seconds:02d} /mi"


if __name__ == "__main__":
    print("=== Last Run ===")
    run = get_last_run()
    if run:
        splits = run.pop("splits", [])
        for key, value in run.items():
            print(f"{key}: {value}")
        print("\nSplits:")
        for s in splits:
            print(f"  Lap {s['lap']}: {s['distance_mi']}mi  {s['pace']}  HR {s['avg_hr']}  cadence {s['avg_cadence']}")

    print("\n=== Health Snapshot ===")
    health = get_health_snapshot()
    for key, value in health.items():
        print(f"{key}: {value}")
