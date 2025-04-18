"""
title: Weather from open-meteo.com (with User Valves)
author: fianalins (edited by Mara-Li)
author_url: https://github.com/open-webui
git_url: https://github.com/mara-li/openwebui-scripts
description: Tool for grabbing the current weather from a provided location. Also adding support for knots as a wind speed unit.
version: 0.1.1
licence: MIT
requirements: dateparser
"""

import json
import re
import requests
from typing import Any, Dict, Optional, List
from urllib.parse import quote
from pydantic import BaseModel, Field
from datetime import datetime
import dateparser


def speed_unit(unit: str, use_imperial: bool = False) -> str:
    """Set the unit used for wind speed."""
    valid_speed_unit = {
        "km/h": "",
        "m/s": "ms",
        "mph": "mph",
        "knots": "kn",
    }
    default = "mph" if use_imperial else ""
    return valid_speed_unit.get(unit.lower(), default)


def parse_time_string(time_str: Optional[str]) -> Optional[str]:
    if not time_str:
        return None
    match = re.match(r"\s*à?\s*(\d{1,2})h", time_str.strip(), re.IGNORECASE)
    if match:
        hour = match.group(1)
        return f"{hour}:00"
    return time_str.strip()


def resolve_datetime(date_str: Optional[str], hour_str: Optional[str], lang: str) -> datetime:
    """Resolve date and hour strings to a datetime object."""
    base = datetime.now()
    combined_str = ""
    if date_str:
        combined_str += date_str
    if hour_str:
        combined_str += f" {parse_time_string(hour_str)}"
    language = ["en", lang] if lang else ["en"]
    print("Combined string:", combined_str)
    parsed = dateparser.parse(combined_str, settings={"RELATIVE_BASE": base}, languages=language)
    return parsed or base


class Tools:
    class Valves(BaseModel):
        citation: bool = Field(
            default=True,
            description="Toggle to include a citation in the output.",
        )

    class UserValves(BaseModel):
        use_imperial: bool = Field(
            default=False,
            description="Toggle to use Imperial units (Fahrenheit, mph, inch) instead of metric. Default is False (metric).",
        )
        shorten_location: bool = Field(
            default=False,
            description="If true, display only the city and country (omit region/admin1).",
        )
        show_humidity: bool = Field(
            default=True,
            description="Toggle to include relative humidity and dew point information.",
        )
        show_precipitation: bool = Field(
            default=True,
            description="Toggle to include precipitation amount and precipitation probability.",
        )
        show_wind: bool = Field(
            default=True,
            description="Toggle to include wind speed and wind direction information.",
        )
        wind_speed_unit: str = Field(
            default="km/h",
            description="The unit used for wind speed (km/h, m/s, mph and Knots). Default is km/h.",
        )
        show_visibility: bool = Field(default=False, description="Toggle to include visibility information.")
        show_uv_index: bool = Field(default=False, description="Toggle to include UV index information (daily).")
        show_sun_times: bool = Field(default=False, description="Toggle to include sunrise and sunset times (daily).")
        show_pressure: bool = Field(
            default=False,
            description="Toggle to include pressure information (surface pressure).",
        )
        show_cloud_cover: bool = Field(default=False, description="Toggle to include cloud cover information.")
        language: str = Field(
            default="en",
            description="Language for the weather report. Default is English.",
        )

    def __init__(self):
        """Initialize the tool and its valves."""
        self.valves = self.Valves()
        self.user_valves = self.UserValves()
        self.citation = self.valves.citation

    async def get_current_weather(
        self,
        location: str,
        date: Optional[str] = None,
        hour: Optional[str] = None,
        __user__: Optional[dict] = None,
        __event_emitter__=None,
    ) -> str:
        """
        Get the current weather information for a given location and day using the Open-Meteo API.

        If the day is not provided, the current weather is returned. Date can be set in the current language as "today" or "tomorrow" or in different format, as "YYYY-MM-DD" or "DD/MM/YYYY".

        If the hour is not provided, the current hour is returned. Hour can be set in the current language as "now", "in x hours", "at 2h" or in different format, as "HH:MM" or "HHMM".

        This asynchronous function supports queries that include both a city and state/region
        (e.g., "Columbus, Ohio"). It uses the geocoding API to resolve the location and then
        requests weather data. Status messages are emitted via __event_emitter__ so that the user
        knows the tool is working.

        **Valves (toggles):**
          - use_imperial: When True, uses Fahrenheit for temperature, mph for wind speed, and inch for precipitation.
          - shorten_location: When True, only the city and country are shown.
          - show_humidity: Includes relative humidity and dew point (hourly).
          - show_precipitation: Includes precipitation amount and probability (hourly).
          - show_wind: Includes wind speed and wind direction (from current weather).
          - show_visibility: Includes visibility (hourly).
          - show_uv_index: Includes daily maximum UV index (daily).
          - show_sun_times: Includes sunrise and sunset times (daily).
          - show_pressure: Includes surface pressure (hourly).
          - show_cloud_cover: Includes cloud cover (hourly).
        **Valves (string):**
        - wind_speed_unit: The unit used for wind speed (km/h, m/s, mph or Knots).
        - language: The language for the weather report (e.g., "en", "fr", "de").

        :param location: The name of the location (e.g., "Berlin", "Columbus, Ohio").
        :param date: The date for which to get the weather (e.g., "today", "tomorrow", "2023-10-01").
        :param hour: The hour for which to get the weather (e.g., "now", "in 2 hours", "14:00").
        :param __user__: A dictionary containing user settings for the tool.
        :param __event_emitter__: A callable used to emit status messages.
        :return: A json string containing the current weather information.
        """
        if __user__:
            raw_valves = __user__.get("valves", {})
            if isinstance(raw_valves, self.UserValves):
                raw_valves = raw_valves.model_dump()
            self.user_valves = self.UserValves(**raw_valves)
        calculated_speed_unit = speed_unit(self.user_valves.wind_speed_unit, self.user_valves.use_imperial)
        try:
            # Emit a status message indicating that location lookup has begun.
            if __event_emitter__ is not None:
                await __event_emitter__({
                    "type": "status",
                    "data": {
                        "description": f"Fetching location data for '{location}'...",
                        "done": False,
                    },
                })
            # Split the location into city and (optional) state/region.
            city_query = location.replace(" ", "-")
            state_query: Optional[str] = None
            if "," in location:
                parts: List[str] = location.split(",")
                city_query = parts[0].strip()
                state_query = parts[1].strip()

            # URL-encode the city name.
            encoded_city = quote(city_query)
            geocode_url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded_city}&count=10"
            geo_response = requests.get(geocode_url)
            if geo_response.status_code != 200:
                error_msg = "Error: Could not get geolocation data."
                if __event_emitter__ is not None:
                    await __event_emitter__({
                        "type": "status",
                        "data": {"description": error_msg, "done": True},
                    })
                return json.dumps({"message": error_msg}, ensure_ascii=False)
            geo_data = geo_response.json()
            if "results" not in geo_data or not geo_data["results"]:
                error_msg = f"Error: Location '{city_query}' not found."
                if __event_emitter__ is not None:
                    await __event_emitter__({
                        "type": "status",
                        "data": {"description": error_msg, "done": True},
                    })
                return json.dumps({"message": error_msg}, ensure_ascii=False)

            # If a state/region is provided, filter the candidate results.
            chosen_geo: Dict[str, Any] = {}
            if state_query:
                for result in geo_data["results"]:
                    if "admin1" in result and result["admin1"].lower() == state_query.lower():
                        chosen_geo = result
                        break
            if not chosen_geo:
                chosen_geo = geo_data["results"][0]

            latitude: float = chosen_geo["latitude"]
            longitude: float = chosen_geo["longitude"]

            # Build a resolved location string.
            resolved_location = chosen_geo.get("name", city_query)
            if not self.user_valves.shorten_location and "admin1" in chosen_geo:
                resolved_location += f", {chosen_geo['admin1']}"
            if "country" in chosen_geo:
                resolved_location += f", {chosen_geo['country']}"

            # Emit a status message that location has been resolved.
            if __event_emitter__ is not None:
                await __event_emitter__({
                    "type": "status",
                    "data": {
                        "description": f"Location resolved: {resolved_location}. Fetching forecast data...",
                        "done": False,
                    },
                })
            resolved_dt = resolve_datetime(date, hour, self.user_valves.language)
            target_hour_str = resolved_dt.strftime("%Y-%m-%dT%H:00")
            # Build the list of hourly parameters.
            hourly_params = [
                "apparent_temperature",
                "relativehumidity_2m",
                "precipitation",
                "windspeed_10m",
                "winddirection_10m",
                "weathercode",
                "temperature_2m",
            ]
            if self.user_valves.show_humidity:
                hourly_params.append("dewpoint_2m")
            if self.user_valves.show_precipitation:
                hourly_params.append("precipitation_probability")
            if self.user_valves.show_visibility:
                hourly_params.append("visibility")
            if self.user_valves.show_pressure:
                hourly_params.append("surface_pressure")
            if self.user_valves.show_cloud_cover:
                hourly_params.append("cloudcover")
            hourly_str = ",".join(hourly_params)

            # Build daily parameters if needed.
            daily_params = []
            if self.user_valves.show_uv_index:
                daily_params.append("uv_index_max")
            if self.user_valves.show_sun_times:
                daily_params.extend(["sunrise", "sunset"])
            daily_str = ",".join(daily_params) if daily_params else None

            # Build the forecast API parameters.
            params: Dict[str, Any] = {
                "latitude": latitude,
                "longitude": longitude,
                "current_weather": "true",
                "hourly": hourly_str,
                "timezone": "auto",
                "wind_speed_unit": calculated_speed_unit,
            }
            if daily_str:
                params["daily"] = daily_str

            # If imperial units are requested, add the appropriate parameters.
            if self.user_valves.use_imperial:
                params["temperature_unit"] = "fahrenheit"
                params["precipitation_unit"] = "inch"

            # Emit a status message before fetching forecast data.
            if __event_emitter__ is not None:
                await __event_emitter__({
                    "type": "status",
                    "data": {
                        "description": "Fetching forecast data...",
                        "done": False,
                    },
                })

            forecast_url = "https://api.open-meteo.com/v1/forecast"
            weather_response = requests.get(forecast_url, params=params)
            if weather_response.status_code != 200:
                error_msg = "Error: Could not get weather data."
                if __event_emitter__ is not None:
                    await __event_emitter__({
                        "type": "status",
                        "data": {"description": error_msg, "done": True},
                    })
                print(f"Error: {weather_response.status_code} - {weather_response.text}")
                return json.dumps({"message": error_msg}, ensure_ascii=False)
            weather_data = weather_response.json()
            # Emit a status message indicating that data is being processed.
            if __event_emitter__ is not None:
                await __event_emitter__({
                    "type": "status",
                    "data": {
                        "description": "Processing weather data...",
                        "done": False,
                    },
                })

            # Extract current weather details.
            current_weather = weather_data.get("current_weather")
            if not current_weather:
                error_msg = "Error: Weather data not available."
                if __event_emitter__ is not None:
                    await __event_emitter__({
                        "type": "status",
                        "data": {"description": error_msg, "done": True},
                    })
                return json.dumps({"message": error_msg}, ensure_ascii=False)

            temperature = current_weather.get("temperature", 0.0)
            windspeed = current_weather.get("windspeed", "N/A")
            winddirection = current_weather.get("winddirection", "N/A")
            weathercode = current_weather.get("weathercode", -1)

            # Map weather codes to human-readable descriptions.
            weather_code_mapping = {
                0: "Clear sky",
                1: "Mainly clear",
                2: "Partly cloudy",
                3: "Overcast",
                45: "Fog",
                48: "Depositing rime fog",
                51: "Light drizzle",
                53: "Moderate drizzle",
                55: "Dense drizzle",
                56: "Light freezing drizzle",
                57: "Dense freezing drizzle",
                61: "Slight rain",
                63: "Moderate rain",
                65: "Heavy rain",
                66: "Light freezing rain",
                67: "Heavy freezing rain",
                71: "Slight snowfall",
                73: "Moderate snowfall",
                75: "Heavy snowfall",
                77: "Snow grains",
                80: "Slight rain showers",
                81: "Moderate rain showers",
                82: "Violent rain showers",
                85: "Slight snow showers",
                86: "Heavy snow showers",
                95: "Thunderstorm",
                96: "Thunderstorm with slight hail",
                99: "Thunderstorm with heavy hail",
            }
            description: str = weather_code_mapping.get(weathercode, "Unknown weather")

            # Retrieve hourly data.
            hourly_data = weather_data.get("hourly", {})
            hourly_times = hourly_data.get("time", [])
            if target_hour_str in hourly_times:
                index = hourly_times.index(target_hour_str)
            else:
                print("[DEBUG] Exact hour not found, falling back to best match.")
                index = max(i for i, t in enumerate(hourly_times) if t.startswith(target_hour_str[:13]))
            print(f"[DEBUG] Requested datetime: {target_hour_str}")
            print(f"[DEBUG] Index found: {index}")
            print(f"[DEBUG] Matching hourly time: {hourly_times[index]}")
            print(f"[DEBUG] Temperature @ index: {hourly_data.get('temperature_2m', ['?'])[index]}")
            print(f"[DEBUG] Apparent Temperature @ index: {hourly_data.get('apparent_temperature', ['?'])[index]}")

            def extract_value(key):
                return (hourly_data.get(key, [None]) or [None])[index]

            apparent_temperature = extract_value("apparent_temperature")
            rel_humidity = extract_value("relativehumidity_2m")
            precipitation = extract_value("precipitation")
            dew_point = extract_value("dewpoint_2m") if self.user_valves.show_humidity else None
            precip_probability = (
                extract_value("precipitation_probability") if self.user_valves.show_precipitation else None
            )
            visibility = extract_value("visibility") if self.user_valves.show_visibility else None
            pressure = extract_value("surface_pressure") if self.user_valves.show_pressure else None
            cloud_cover = extract_value("cloudcover") if self.user_valves.show_cloud_cover else None
            temperature = extract_value("temperature_2m")
            windspeed = extract_value("windspeed_10m")
            winddirection = extract_value("winddirection_10m")
            weathercode = extract_value("weathercode")
            # Retrieve daily data if needed.
            daily_data = weather_data.get("daily", {})
            current_date = target_hour_str.split("T")[0]
            daily_index = (
                daily_data.get("time", []).index(current_date) if current_date in daily_data.get("time", []) else 0
            )
            uv_index = daily_data.get("uv_index_max", [None])[daily_index] if self.user_valves.show_uv_index else None
            sunrise = daily_data.get("sunrise", [None])[daily_index] if self.user_valves.show_sun_times else None
            sunset = daily_data.get("sunset", [None])[daily_index] if self.user_valves.show_sun_times else None

            # Set unit symbols based on the selected system.
            temp_unit = "°F" if self.user_valves.use_imperial else "°C"
            wind_speed_unit = "km/h" if calculated_speed_unit == "" else calculated_speed_unit
            precip_unit = "inch" if self.user_valves.use_imperial else "mm"

            # Build the weather report.
            report_lines = [
                f"Weather for {resolved_location} (Latitude: {latitude}, Longitude: {longitude}):",
                f"Time: {target_hour_str}",
                f"Temperature: {temperature:.1f}{temp_unit}",
                f"Feels Like: {apparent_temperature:.1f}{temp_unit}",
            ]
            if self.user_valves.show_humidity:
                report_lines.append(f"Relative Humidity: {rel_humidity}%")
                if dew_point is not None:
                    report_lines.append(f"Dew Point: {dew_point:.1f}{temp_unit}")
            if self.user_valves.show_precipitation:
                report_lines.append(f"Precipitation: {precipitation}{precip_unit}")
                if precip_probability is not None:
                    report_lines.append(f"Precipitation Probability: {precip_probability}%")
            if self.user_valves.show_wind:
                report_lines.append(f"Wind Speed: {windspeed} {wind_speed_unit}")
                report_lines.append(f"Wind Direction: {winddirection}°")
            if self.user_valves.show_visibility and visibility is not None:
                report_lines.append(f"Visibility: {visibility}m")
            if self.user_valves.show_pressure and pressure is not None:
                report_lines.append(f"Pressure: {pressure} hPa")
            if self.user_valves.show_cloud_cover and cloud_cover is not None:
                report_lines.append(f"Cloud Cover: {cloud_cover}%")
            if self.user_valves.show_uv_index and uv_index is not None:
                report_lines.append(f"UV Index (max): {uv_index}")
            if self.user_valves.show_sun_times:
                if sunrise is not None and sunset is not None:
                    report_lines.append(f"Sunrise: {sunrise}")
                    report_lines.append(f"Sunset: {sunset}")
            report_lines.append(f"Weather: {description} (Code: {weathercode})")

            # Emit a final status message indicating completion.
            if __event_emitter__ is not None:
                await __event_emitter__({
                    "type": "status",
                    "data": {
                        "description": "Weather data retrieval complete.",
                        "done": True,
                    },
                })
            return json.dumps({"message": "\n".join(report_lines)}, ensure_ascii=False)
        except Exception as e:
            # In case of an exception, send an error status message.
            if __event_emitter__ is not None:
                await __event_emitter__({
                    "type": "status",
                    "data": {
                        "description": f"An error occurred: {e}",
                        "done": True,
                    },
                })
            print(f"Error: {e}")
            return json.dumps({"message": f"An error occurred: {str(e)}"}, ensure_ascii=False)
