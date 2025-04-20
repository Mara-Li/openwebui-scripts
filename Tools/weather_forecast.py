"""
title: Weather from open-meteo.com (with User Valves)
author: fianalins (edited by Mara-Li)
author_url: https://github.com/open-webui
git_url: https://github.com/mara-li/openwebui-scripts
description: Tool for grabbing the current weather from a provided location. Also adding support for knots as a wind speed unit.
version: 0.2.0
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
        "km/h": "kmh",
        "m/s": "ms",
        "mph": "mph",
        "knots": "kn",
    }
    default = "mph" if use_imperial else "kmh"
    return valid_speed_unit.get(unit.lower(), default)


def parse_time_string(time_str: Optional[str]) -> Optional[str]:
    """Parse hour format from natural language to HH:MM format."""
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
    parsed = dateparser.parse(combined_str, settings={"RELATIVE_BASE": base}, languages=language)
    return parsed or base


async def emit_status(emitter, message: str, done: bool = False):
    """Helper function to emit status messages."""
    if emitter is not None:
        await emitter({"type": "status", "data": {"description": message, "done": done}})


def get_weather_code_description(code: int) -> str:
    """Map weather codes to human-readable descriptions."""
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
    return weather_code_mapping.get(code, "Unknown weather")


def get_unit_symbols(use_imperial: bool, calculated_speed_unit: str) -> Dict[str, str]:
    """Return appropriate unit symbols based on the selected system."""
    return {
        "temp": "°F" if use_imperial else "°C",
        "wind": "km/h" if calculated_speed_unit == "" else calculated_speed_unit,
        "precip": "inch" if use_imperial else "mm",
    }


def extract_hourly_value(hourly_data: Dict[str, List], key: str, index: int, default: int | str = 0):
    """Helper function to safely extract values from hourly data."""
    values = hourly_data.get(key, [default])
    return values[index] if index < len(values) else default


def build_hourly_params(user_valves) -> List[str]:
    """Build the list of hourly parameters based on user valves."""
    params = [
        "apparent_temperature",
        "relativehumidity_2m",
        "precipitation",
        "windspeed_10m",
        "winddirection_10m",
        "weathercode",
        "temperature_2m",
    ]

    if user_valves.show_humidity:
        params.append("dewpoint_2m")
    if user_valves.show_precipitation:
        params.append("precipitation_probability")
    if user_valves.show_visibility:
        params.append("visibility")
    if user_valves.show_pressure:
        params.append("surface_pressure")
    if user_valves.show_cloud_cover:
        params.append("cloudcover")

    return params


def build_daily_params(user_valves) -> List[str]:
    """Build the list of daily parameters based on user valves."""
    params = []
    if user_valves.show_uv_index:
        params.append("uv_index_max")
    if user_valves.show_sun_times:
        params.extend(["sunrise", "sunset"])
    return params


def build_weather_report(data: Dict[str, Any], units: Dict[str, str]) -> List[str]:
    """Build a formatted weather report from the collected data."""
    report_lines = [
        f"Weather for {data['location']} (Latitude: {data['latitude']}, Longitude: {data['longitude']}):",
        f"Time: {data['time']}",
        f"Temperature: {data['temperature']:.1f}{units['temp']}",
        f"Feels Like: {data['apparent_temperature']:.1f}{units['temp']}",
    ]

    if data.get("show_humidity"):
        report_lines.append(f"Relative Humidity: {data['humidity']}%")
        if data.get("dew_point") is not None:
            report_lines.append(f"Dew Point: {data['dew_point']:.1f}{units['temp']}")

    if data.get("show_precipitation"):
        report_lines.append(f"Precipitation: {data['precipitation']}{units['precip']}")
        if data.get("precip_probability") is not None:
            report_lines.append(f"Precipitation Probability: {data['precip_probability']}%")

    if data.get("show_wind"):
        report_lines.append(f"Wind Speed: {data['windspeed']} {units['wind']}")
        report_lines.append(f"Wind Direction: {data['winddirection']}°")

    if data.get("show_visibility") and data.get("visibility") is not None:
        report_lines.append(f"Visibility: {data['visibility']}m")

    if data.get("show_pressure") and data.get("pressure") is not None:
        report_lines.append(f"Pressure: {data['pressure']} hPa")

    if data.get("show_cloud_cover") and data.get("cloud_cover") is not None:
        report_lines.append(f"Cloud Cover: {data['cloud_cover']}%")

    if data.get("show_uv_index") and data.get("uv_index") is not None:
        report_lines.append(f"UV Index (max): {data['uv_index']}")

    if data.get("show_sun_times"):
        if data.get("sunrise") is not None and data.get("sunset") is not None:
            report_lines.append(f"Sunrise: {data['sunrise']}")
            report_lines.append(f"Sunset: {data['sunset']}")

    report_lines.append(f"Weather: {data['description']} (Code: {data['weathercode']})")

    return report_lines


async def resolve_geo(lat: float, lon: float):
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        "lat": lat,
        "lon": lon,
        "format": "json",
        "zoom": 10,  # niveau de détail (10 = ville, 18 = adresse précise)
        "addressdetails": 1,
    }
    headers = {"User-Agent": "OpenWebUI-WeatherScript"}
    resp = requests.get(url, params=params, headers=headers)
    if resp.ok:
        data = resp.json()
        return data.get("display_name", f"{lat}, {lon}")
    return f"{lat}, {lon}"


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
        location: str = "",
        date: str = "",
        hour: str = "",
        __user__: Optional[dict] = None,
        __metadata__: Optional[dict] = None,
        __event_emitter__=None,
    ) -> str:
        """
        Get the current weather information for a given location and day using the Open-Meteo API.

        The location can be optional, and empty. If not provided, the function will attempt to resolve the location from the __metadata__ object, and you will use it.

        If provided, The location can be a city name, a state name, or a combination of both (e.g., "Berlin", "Columbus, Ohio"). It can also be coordinate values (e.g., "45.775, 4.881" or "45.775/4.881" or "45.775x4.881").

        If the day is not provided, the current weather is returned.

        Date can be set in the current language as "today" or "tomorrow" or in different format, as "YYYY-MM-DD" or "DD/MM/YYYY". You can use also different language ("fr", "de", "es", etc.).
        For example, an user can say "aujourd'hui" or "demain" in French, and the tool will understand it as "today" or "tomorrow".

        If the hour is not provided, the current hour is returned. Hour can be set in the current language as "now", "in x hours", "at 2h" or in different format, as "HH:MM" or "HHMM". It can be also set in different language ("fr", "de", "es", etc.). So for example, an user can say "maintenant" or "dans 2 heures" in French, and the tool will understand it as "now" or "in 2 hours".

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

        :param location: (Optional) The location for which to get the weather (e.g., "Berlin", "Columbus, Ohio", "45.775, 4.881").
        :param date: (Optional) The date for which to get the weather (e.g., "today", "tomorrow", "2023-10-01").
        :param hour: (Optional) The hour for which to get the weather (e.g., "now", "in 2 hours", "14:00").
        :param __metadata__: Metadata containing variables like {{USER_LOCATION}}.
        :param __user__: A dictionary containing user settings for the tool.
        :param __event_emitter__: A callable used to emit status messages.
        :return: A json string containing the current weather information.
        """
        if __user__ and __user__.get("valves"):
            self.user_valves: Tools.UserValves = __user__.get("valves", self.user_valves)

        latitude: Optional[float] = None
        longitude: Optional[float] = None
        if location == "":
            # get location from __metadata__
            if __metadata__ and __metadata__.get("variables"):
                meta_location = __metadata__["variables"].get("{{USER_LOCATION}}")
                if meta_location:
                    # format: 45.775, 4.881 (lat, long)
                    meta_location_reg = re.match(r"(?P<lat>[\d\.]+), (?P<long>[\d\.]+)", meta_location)
                    if meta_location_reg:
                        latitude = float(meta_location_reg.group("lat").strip())
                        longitude = float(meta_location_reg.group("long").strip())
                        resolved_location = await resolve_geo(latitude, longitude)
                        await emit_status(
                            __event_emitter__, f"Location resolved from metadata: {resolved_location}.", False
                        )
        print(f"[DEBUG] Location: {location}, Date: {date}, Hour: {hour}")

        # Initialize user valves from user settings if provided

        calculated_speed_unit = speed_unit(self.user_valves.wind_speed_unit, self.user_valves.use_imperial)
        print(f"[DEBUG] Calculated speed unit: {calculated_speed_unit}")
        print(f"[DEBUG] User valves: {self.user_valves}")

        try:
            if not latitude and not longitude:
                # Start location lookup
                await emit_status(__event_emitter__, f"Fetching location data for '{location}'...")

                # Parse location query into city and optional state/region
                city_query = location.replace(" ", "-")
                state_query: Optional[str] = None
                if "," in location:
                    parts: List[str] = location.split(",")
                    city_query = parts[0].strip()
                    state_query = parts[1].strip()
                # if float = lon/lat
                if state_query and re.match(r"\d+", city_query) and re.match(r"\d+", state_query):
                    latitude = float(city_query)
                    longitude = float(state_query)
                    resolved_location = await resolve_geo(latitude, longitude)
                    await emit_status(
                        __event_emitter__, f"Location resolved from coordinates: {resolved_location}.", False
                    )
                else:
                    # Get geolocation data
                    encoded_city = quote(city_query)
                    geocode_url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded_city}&count=10"
                    geo_response = requests.get(geocode_url)

                    if geo_response.status_code != 200:
                        error_msg = "Error: Could not get geolocation data."
                        await emit_status(__event_emitter__, error_msg, done=True)
                        return json.dumps({"message": error_msg}, ensure_ascii=False)

                    geo_data = geo_response.json()
                    if "results" not in geo_data or not geo_data["results"]:
                        error_msg = f"Error: Location '{city_query}' not found."
                        await emit_status(__event_emitter__, error_msg, done=True)
                        return json.dumps({"message": error_msg}, ensure_ascii=False)

                    # Find the best matching location
                    chosen_geo: Dict[str, Any] = {}
                    if state_query:
                        for result in geo_data["results"]:
                            if "admin1" in result and result["admin1"].lower() == state_query.lower():
                                chosen_geo = result
                                break

                    if not chosen_geo:
                        chosen_geo = geo_data["results"][0]

                    latitude = chosen_geo["latitude"]
                    longitude = chosen_geo["longitude"]

                    # Build resolved location string
                    resolved_location = chosen_geo.get("name", city_query)
                    if not self.user_valves.shorten_location and "admin1" in chosen_geo:
                        resolved_location += f", {chosen_geo['admin1']}"
                    if "country" in chosen_geo:
                        resolved_location += f", {chosen_geo['country']}"

                # Notify that location has been resolved
            await emit_status(__event_emitter__, f"Location resolved: {resolved_location}. Fetching forecast data...")

            # Resolve requested datetime
            resolved_dt = resolve_datetime(date, hour, self.user_valves.language)
            target_hour_str = resolved_dt.strftime("%Y-%m-%dT%H:00")

            # Build API request parameters
            hourly_params = build_hourly_params(self.user_valves)
            daily_params = build_daily_params(self.user_valves)

            hourly_str = ",".join(hourly_params)
            daily_str = ",".join(daily_params) if daily_params else None

            # Build forecast API parameters
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

            # Set imperial units if requested
            if self.user_valves.use_imperial:
                params["temperature_unit"] = "fahrenheit"
                params["precipitation_unit"] = "inch"

            # Fetch forecast data
            await emit_status(__event_emitter__, "Fetching forecast data...")
            forecast_url = "https://api.open-meteo.com/v1/forecast"
            weather_response = requests.get(forecast_url, params=params)

            if weather_response.status_code != 200:
                error_msg = "Error: Could not get weather data."
                await emit_status(__event_emitter__, error_msg, done=True)
                print(f"Error: {weather_response.status_code} - {weather_response.text}")
                return json.dumps({"message": error_msg}, ensure_ascii=False)

            weather_data = weather_response.json()
            await emit_status(__event_emitter__, "Processing weather data...")

            # Extract current weather details
            current_weather = weather_data.get("current_weather", {})
            if not current_weather:
                error_msg = "Error: Weather data not available."
                await emit_status(__event_emitter__, error_msg, done=True)
                return json.dumps({"message": error_msg}, ensure_ascii=False)

            # Find the correct hourly data index
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

            # Extract hourly values
            temperature = extract_hourly_value(hourly_data, "temperature_2m", index, 0)
            apparent_temperature = extract_hourly_value(hourly_data, "apparent_temperature", index, 0)
            rel_humidity = extract_hourly_value(hourly_data, "relativehumidity_2m", index, 0)
            precipitation = extract_hourly_value(hourly_data, "precipitation", index, 0)
            windspeed = extract_hourly_value(hourly_data, "windspeed_10m", index, "N/A")
            winddirection = extract_hourly_value(hourly_data, "winddirection_10m", index, "N/A")
            weathercode = extract_hourly_value(hourly_data, "weathercode", index, -1)

            # Extract conditional values based on user preferences
            dew_point = None
            precip_probability = None
            visibility = None
            pressure = None
            cloud_cover = None

            if self.user_valves.show_humidity:
                dew_point = extract_hourly_value(hourly_data, "dewpoint_2m", index)

            if self.user_valves.show_precipitation:
                precip_probability = extract_hourly_value(hourly_data, "precipitation_probability", index)

            if self.user_valves.show_visibility:
                visibility = extract_hourly_value(hourly_data, "visibility", index)

            if self.user_valves.show_pressure:
                pressure = extract_hourly_value(hourly_data, "surface_pressure", index)

            if self.user_valves.show_cloud_cover:
                cloud_cover = extract_hourly_value(hourly_data, "cloudcover", index)

            # Get weather description
            if (weathercode is not None and type(weathercode) is int) and weathercode >= 0:
                description = get_weather_code_description(weathercode)

            # Extract daily data if needed
            daily_data = weather_data.get("daily", {})
            current_date = target_hour_str.split("T")[0]
            daily_index = 0

            if current_date in daily_data.get("time", []):
                daily_index = daily_data.get("time", []).index(current_date)

            uv_index = None
            sunrise = None
            sunset = None

            if self.user_valves.show_uv_index:
                uv_index = (
                    daily_data.get("uv_index_max", [None])[daily_index] if daily_data.get("uv_index_max") else None
                )

            if self.user_valves.show_sun_times:
                sunrise = daily_data.get("sunrise", [None])[daily_index] if daily_data.get("sunrise") else None
                sunset = daily_data.get("sunset", [None])[daily_index] if daily_data.get("sunset") else None

            # Get unit symbols
            units = get_unit_symbols(self.user_valves.use_imperial, calculated_speed_unit)

            # Prepare data for the weather report
            weather_info = {
                "location": resolved_location,
                "latitude": latitude,
                "longitude": longitude,
                "time": target_hour_str,
                "temperature": temperature,
                "apparent_temperature": apparent_temperature,
                "humidity": rel_humidity,
                "precipitation": precipitation,
                "windspeed": windspeed,
                "winddirection": winddirection,
                "weathercode": weathercode,
                "description": description,
                "dew_point": dew_point,
                "precip_probability": precip_probability,
                "visibility": visibility,
                "pressure": pressure,
                "cloud_cover": cloud_cover,
                "uv_index": uv_index,
                "sunrise": sunrise,
                "sunset": sunset,
                "show_humidity": self.user_valves.show_humidity,
                "show_precipitation": self.user_valves.show_precipitation,
                "show_wind": self.user_valves.show_wind,
                "show_visibility": self.user_valves.show_visibility,
                "show_pressure": self.user_valves.show_pressure,
                "show_cloud_cover": self.user_valves.show_cloud_cover,
                "show_uv_index": self.user_valves.show_uv_index,
                "show_sun_times": self.user_valves.show_sun_times,
            }

            # Build the weather report
            report_lines = build_weather_report(weather_info, units)

            # Notify completion
            await emit_status(__event_emitter__, "Weather data retrieval complete.", done=True)
            return json.dumps({"message": "\n".join(report_lines)}, ensure_ascii=False)

        except Exception as e:
            await emit_status(__event_emitter__, f"An error occurred: {e}", done=True)
            print(f"Error: {e}")
            return json.dumps({"message": f"An error occurred: {str(e)}"}, ensure_ascii=False)
