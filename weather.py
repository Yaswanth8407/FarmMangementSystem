import requests
import os
from datetime import datetime

API_KEY = "717c13ef88f18552149659a09e08584e"


def get_weather(city):
    if not API_KEY:
        return None

    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}&units=metric"

    try:
        response = requests.get(url, timeout=5)
    except requests.exceptions.RequestException:
        return None

    if response.status_code != 200:
        return None

    data = response.json()

    weather = {
        "city": data["name"],
        "temperature": data["main"]["temp"],
        "humidity": data["main"]["humidity"],
        "condition": data["weather"][0]["main"],
        "wind": round(data["wind"]["speed"] * 3.6, 1)
    }

    return weather


def get_forecast(city, days=5):
    """Return up to `days` daily forecast summaries, or [] if unavailable."""
    if not API_KEY:
        return []

    url = (
        f"https://api.openweathermap.org/data/2.5/forecast"
        f"?q={city}&appid={API_KEY}&units=metric"
    )
    try:
        response = requests.get(url, timeout=5)
    except requests.exceptions.RequestException:
        return []

    if response.status_code != 200:
        return []

    try:
        entries = response.json().get("list", [])
    except ValueError:
        return []

    buckets = {}
    for entry in entries:
        try:
            day = datetime.utcfromtimestamp(entry["dt"]).date().isoformat()
        except (KeyError, TypeError, ValueError):
            continue

        bucket = buckets.setdefault(day, {
            "condition_counts": {},
            "temp_min": None,
            "temp_max": None,
            "rain": 0.0,
            "pop": 0.0,
            "wind": 0.0,
        })

        main = entry.get("main", {})
        temp_min = main.get("temp_min")
        temp_max = main.get("temp_max")
        if temp_min is not None:
            bucket["temp_min"] = temp_min if bucket["temp_min"] is None else min(bucket["temp_min"], temp_min)
        if temp_max is not None:
            bucket["temp_max"] = temp_max if bucket["temp_max"] is None else max(bucket["temp_max"], temp_max)

        weather_list = entry.get("weather") or [{}]
        condition = weather_list[0].get("main", "Unknown")
        bucket["condition_counts"][condition] = bucket["condition_counts"].get(condition, 0) + 1

        rain = entry.get("rain", {}).get("3h", 0) or 0
        bucket["rain"] += rain
        bucket["pop"] = max(bucket["pop"], entry.get("pop", 0) or 0)
        bucket["wind"] = max(bucket["wind"], (entry.get("wind", {}).get("speed", 0) or 0) * 3.6)

    forecast = []
    for day in sorted(buckets)[:days]:
        bucket = buckets[day]
        counts = bucket["condition_counts"]
        condition = max(counts, key=counts.get) if counts else "Unknown"
        rainy = (
            bucket["rain"] >= 0.5
            or bucket["pop"] >= 0.4
            or condition in ("Rain", "Drizzle", "Thunderstorm")
        )
        forecast.append({
            "date": day,
            "condition": condition,
            "temp_min": bucket["temp_min"],
            "temp_max": bucket["temp_max"],
            "rain": round(bucket["rain"], 1),
            "pop": round(bucket["pop"], 2),
            "wind": bucket["wind"],
            "will_rain": rainy,
        })

    return forecast


def get_farming_suggestion(weather):

    if not weather:
        return ["Weather data unavailable. Check your connection or API key."]

    temp = weather["temperature"]
    humidity = weather["humidity"]
    condition = weather["condition"]
    wind = weather["wind"]


    suggestions = []

    # Weather condition
    if condition == "Rain":
        suggestions.append("🌧 Avoid irrigation due to rainfall.")
    else:
        suggestions.append("🌱 Check soil moisture before watering.")

    # Temperature
    if temp > 35:
        suggestions.append("☀ High temperature. Water crops early morning.")
    elif temp < 15:
        suggestions.append("❄ Low temperature. Protect sensitive crops.")
    else:
        suggestions.append("✅ Temperature is suitable for crop growth.")

    # Humidity
    if humidity > 80:
        suggestions.append("💧 High humidity. Watch for fungal diseases.")
    elif humidity < 40:
        suggestions.append("💦 Low humidity. Increase irrigation.")
    else:
        suggestions.append("🌿 Humidity level is good.")

    # Wind
    if wind > 36:
        suggestions.append("🌬 Strong wind. Avoid pesticide spraying.")
    else:
        suggestions.append("🧴 Wind conditions are safe for spraying.")

    return suggestions[:4]