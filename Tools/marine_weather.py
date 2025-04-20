"""
title: Weather from World Weather Online
author: Mara-Li
author_url: https://github.com/open-webui
git_url: https://github.com/mara-li/openwebui-scripts
description: Tool to get marine weather from World Weather Online API.
version: 0.0.1
licence: MIT
requirements: dateparser
"""

import json
import re
from urllib.parse import quote
from pydantic import BaseModel, Field
from typing import Any, Optional, Dict, Tuple, Union, List

import requests
import dateparser


def parse_time_string(time_str: str) -> str:
    """Parse time string to standard format."""
    match = re.match(r"\s*à?\s*(\d{1,2})h", time_str.strip(), re.IGNORECASE)
    if match:
        hour = match.group(1)
        return f"{hour}:00"
    return time_str.strip()


def convert_unit(value: Union[str, float], from_unit: str, to_unit: str) -> float:
    """Generic unit conversion function."""
    value_float = float(value)

    # Temperature conversions
    if from_unit == "celsius" and to_unit == "fahrenheit":
        return value_float * 9 / 5 + 32
    elif from_unit == "celsius" and to_unit == "kelvin":
        return value_float + 273.15

    # Speed conversions
    elif from_unit == "kmh" and to_unit == "mph":
        return value_float * 0.621371
    elif from_unit == "kmh" and to_unit == "knots":
        return value_float * 0.539957

    # Distance conversions
    elif from_unit == "m" and to_unit == "ft":
        return value_float * 3.28084
    elif from_unit == "km" and to_unit == "miles":
        return value_float * 0.621371

    # Pressure conversions
    elif from_unit == "hpa" and to_unit == "inhg":
        return value_float * 0.02953

    # Default: no conversion
    return value_float


def format_unit(value: Union[str, float], unit_type: str, unit_system: str) -> Tuple[float, str]:
    """Format value with appropriate unit based on unit system."""
    value_float = float(value)

    if unit_type == "temperature":
        if unit_system == "celsius":
            return value_float, "°C"
        elif unit_system == "fahrenheit":
            return value_float, "°F"
        elif unit_system == "kelvin":
            return value_float + 273.15, "K"

    elif unit_type == "wind":
        if unit_system == "metrique":
            return value_float, "km/h"
        elif unit_system == "imperial":
            return value_float * 0.621371, "mph"
        elif unit_system == "knots":
            return value_float * 0.539957, "knots"

    elif unit_type == "distance":
        if unit_system == "metric":
            return value_float, "m"
        elif unit_system == "imperial":
            return value_float * 3.28084, "ft"

    elif unit_type == "visibility":
        if unit_system == "metric":
            return value_float, "km"
        elif unit_system == "imperial":
            return value_float, "miles"

    elif unit_type == "pressure":
        if unit_system == "metric":
            return value_float, "hPa"
        elif unit_system == "imperial":
            return value_float, "inHg"

    # Default: return as is
    return value_float, ""


class Tools:
    class Valves(BaseModel):
        citation: bool = Field(
            default=True,
            description="Toggle to include a citation in the output.",
        )
        api_key: str = Field(
            default="",
            description="Your API key for World Weather Online.",
        )

    class UserValves(BaseModel):
        includelocation: bool = Field(
            default=False,
            description="Returns the nearest weather point for which the weather data is returned for a given postcode, zipcode and lat/lon values.",
        )
        tp: Optional[str] = Field(
            default="1",
            description="Switch between weather forecast time interval from 1 hourly, 3 hourly, 6 hourly, 12 hourly (day/night) or 24 hourly (day average).",
        )
        tide: bool = Field(default=False, description="To return tide data information if available.")
        lang: Optional[str] = Field(
            default=None, description="Returns weather description text in the language of your choice."
        )
        temp: Optional[str] = Field(
            default="celsius",
            description="Temperature unit. Possible values: celsius, fahrenheit, kelvin.",
        )
        wind: Optional[str] = Field(
            default="knots",
            description="Wind unit. Possible values: metric (km/h), imperial (miles/h) and knots.",
        )
        units: Optional[str] = Field(
            default="metric",
            description="Units for the weather data. Possible values: metric (m/hPA), imperial (miles and inches).",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.user_valves = self.UserValves()

    async def _emit_status(self, __event_emitter__=None, description: str = "", done: bool = False) -> None:
        """Helper method to emit status updates to the user."""
        if __event_emitter__ is not None:
            await __event_emitter__({
                "type": "status",
                "data": {"description": description, "done": done},
            })

    async def resolve_name(self, lat: float, lon: float):
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
            return data.get("display_name", f"{lat},{lon}")
        return f"{lat},{lon}"

    async def _resolve_location(self, location: str = "", __event_emitter__=None, __metadata__: Optional[dict] = None):
        """Resolve location to coordinates."""
        search_geo = True
        resolved_name = location
        lat, lon = 0, 0
        if location == "" and __metadata__ and __metadata__.get("variables"):
            meta_location = __metadata__["variables"].get("{{USER_LOCATION}}")
            if meta_location:
                # format: 45.775, 4.881 (lat, long)
                meta_location_reg = re.match(r"(?P<lat>[\d\.]+), (?P<long>[\d\.]+)", meta_location)
                if meta_location_reg:
                    lat = float(meta_location_reg.group("lat").strip())
                    lon = float(meta_location_reg.group("long").strip())
                    resolved_name = await self.resolve_name(lat, lon)
                return lat, lon, resolved_name

        # Check if location is already coordinates
        if "," in location or "/" in location or "x" in location:
            parts = (
                location.split(",")
                if "," in location
                else location.split("/")
                if "/" in location
                else location.split("x")
            )
            if len(parts) >= 2:
                search_geo = False
                lat = parts[0].strip()
                lon = parts[1].strip()
                if lat.endswith("°"):
                    lat = lat[:-1].strip()
                if lon.endswith("°"):
                    lon = lon[:-1].strip()
                resolved_name = await self.resolve_name(float(lat), float(lon))
                lat = float(lat)
                lon = float(lon)

        # If not coordinates, search for location
        if search_geo:
            await self._emit_status(__event_emitter__, f"Fetching location data for '{location}'...", False)

            city_query = location.replace(" ", "-")
            state_query: Optional[str] = None
            if "," in city_query:
                parts: list[str] = city_query.split(",")
                city_query = parts[0].strip()
                state_query = parts[1].strip()

            encoded_city = quote(city_query)
            geo = requests.get(f"https://geocoding-api.open-meteo.com/v1/search?name={encoded_city}&count=10")

            if geo.status_code != 200:
                raise ValueError("Could not get geolocation data.")

            geo_data = geo.json()
            if "results" not in geo_data or not geo_data["results"]:
                raise ValueError(f"Location '{location}' not found.")

            chosen_geo: dict[str, Any] = {}
            if state_query:
                for result in geo_data["results"]:
                    if "admin1" in result and result["admin1"].lower() == state_query.lower():
                        chosen_geo = result
                        break

            if not chosen_geo:
                chosen_geo = geo_data["results"][0]

            lat = chosen_geo["latitude"]
            lon = chosen_geo["longitude"]
            resolved_name = geo_data["results"][0]["name"]

        return lat, lon, resolved_name

    def _build_weather_url(self, lat: float, lon: float) -> str:
        """Build the weather API URL with appropriate parameters."""
        url = (
            f"http://api.worldweatheronline.com/premium/v1/marine.ashx?key={self.valves.api_key}"
            f"&q={lat},{lon}&format=json"
        )

        if self.user_valves.tp:
            url += f"&tp={self.user_valves.tp}"

        if self.user_valves.lang:
            url += f"&lang={self.user_valves.lang}"

        url += f"&tide={'yes' if self.user_valves.tide else 'no'}"
        url += f"&includeLocation={'yes' if self.user_valves.includelocation else 'no'}"

        return url

    def _format_weather_report(self, weather_data: Dict, parsed_date, hour: str = "") -> List[str]:
        """Format weather data into readable report."""
        report = []
        languages = ["en", self.user_valves.lang] if self.user_valves.lang else ["en"]
        weather_days = weather_data["data"].get("weather", [])

        for day in weather_days:
            date_str = day["date"]
            if parsed_date and parsed_date.date().isoformat() != date_str:
                continue

            astronomy = day.get("astronomy", [{}])[0]
            report.append(f"Date: {date_str}")
            report.append(f"Sunrise: {astronomy.get('sunrise', '?')} | Sunset: {astronomy.get('sunset', '?')}")

            selected_hours = day.get("hourly", [])
            if hour:
                parsed_time = dateparser.parse(parse_time_string(hour), languages=languages)
                if parsed_time:
                    user_hour_str = f"{parsed_time.hour:02}00"
                else:
                    user_hour_str = re.sub(r"\\D", "", hour).zfill(4)

                matched_hours = [h for h in selected_hours if h["time"].zfill(4) == user_hour_str]
                if not matched_hours:
                    all_times = sorted((int(h["time"]) for h in selected_hours))
                    fallback_time = min(
                        (t for t in all_times if t > int(user_hour_str)), default=max(all_times, default=None)
                    )
                    if fallback_time is not None:
                        user_hour_str = str(fallback_time).zfill(4)
                        matched_hours = [h for h in selected_hours if h["time"].zfill(4) == user_hour_str]
                selected_hours = matched_hours

            for hourly in selected_hours:
                time_h = hourly["time"].zfill(4)
                hour_label = f"{time_h[:-2]}:{time_h[-2:]}"

                # Format temperature data
                temp_unit = "°C"
                temp = float(hourly["tempC"])
                water_temp = float(hourly["waterTemp_C"])
                feel_like = float(hourly["FeelsLikeC"])

                if self.user_valves.temp == "fahrenheit":
                    temp_unit = "°F"
                    temp = float(hourly["tempF"])
                    water_temp = float(hourly["waterTemp_F"])
                    feel_like = float(hourly["FeelsLikeF"])
                elif self.user_valves.temp == "kelvin":
                    temp_unit = "K"
                    temp = float(hourly["tempC"]) + 273.15
                    water_temp = float(hourly["waterTemp_C"]) + 273.15
                    feel_like = float(hourly["FeelsLikeC"]) + 273.15

                # Format wind data
                wind_unit = "km/h"
                wind = float(hourly["windspeedKmph"])
                if self.user_valves.wind == "imperial":
                    wind = float(hourly["windspeedMiles"])
                    wind_unit = "mph"
                elif self.user_valves.wind == "knots":
                    wind_unit = "knots"
                    wind = round(wind * 0.539957, 1)

                # Format other measurements based on unit system
                dist_unit = "m"
                swell_height = float(hourly["swellHeight_m"])
                visibility = float(hourly["visibility"])
                pressure = hourly["pressure"]
                unit = "hPa"

                if self.user_valves.units == "imperial":
                    pressure = float(hourly["pressureInches"])
                    unit = "inHg"
                    swell_height = float(hourly["swellHeight_ft"])
                    visibility = float(hourly["visibilityMiles"])
                    dist_unit = "miles"

                # Get description in appropriate language
                desc = hourly["weatherDesc"][0]["value"]
                if self.user_valves.lang and f"lang_{self.user_valves.lang}" in hourly:
                    desc = hourly[f"lang_{self.user_valves.lang}"][0]["value"]

                # Format hourly report
                report.extend([
                    f"\n— {hour_label} —",
                    f"Temp: {temp} {temp_unit} (Feel Like: {feel_like} {temp_unit}) | Water: {water_temp} {temp_unit}",
                    f"Wind: {wind} {wind_unit} ({hourly['winddir16Point']})",
                    f"Swell: {swell_height} {dist_unit} {hourly['swellDir16Point']} {hourly['swellPeriod_secs']}s",
                    f"Pressure: {pressure} {unit} | Humidity: {hourly['humidity']}%",
                    f"Visibility: {visibility} {dist_unit} | Cloud Cover: {hourly['cloudcover']}%",
                    f"UV Index: {hourly['uvIndex']}",
                    f"Weather: {desc}",
                ])

        return report

    async def get_marine_weather(
        self,
        location: str = "",
        date: str = "",
        hour: str = "",
        __metadata__: Optional[dict] = None,
        __user__: Optional[dict] = None,
        __event_emitter__=None,
    ) -> str:
        """
        Get the current marine weather for a given location using World Weather Online API.

        The location can be optional, and empty. If not provided, the function will attempt to resolve the location from the metadata.
        The location, if provided, can be a city name, a state name, or a combination of both (e.g., "Berlin", "Columbus, Ohio"). It can also be coordinate values (e.g., "45.775, 4.881" or "45.775/4.881" or "45.775x4.881").

        Date can be set in the current language as "today" or "tomorrow" or in different format, as "YYYY-MM-DD" or "DD/MM/YYYY". You can use also different language ("fr", "de", "es", etc.).
        For example, an user can say "aujourd'hui" or "demain" in French, and the tool will understand it as "today" or "tomorrow".

        If the hour is not provided, the current hour is returned. Hour can be set in the current language as "now", "in x hours", "at 2h" or in different format, as "HH:MM" or "HHMM". It can be also set in different language ("fr", "de", "es", etc.). So for example, an user can say "maintenant" or "dans 2 heures" in French, and the tool will understand it as "now" or "in 2 hours".

        This asynchronous function supports queries that include both a city and a state/region or just a location (longitude and latitude).
        It uses the geocoding API to convert the location into latitude and longitude coordinates.
        Status messages are emitted via __event_emitter__ so that the user knows the process is running.

        **Valves**:
        - lang:  Returns weather description text in the language of your choice. E.g:- lang=ar (Arabic). Visit Multilingual support page for more information: http://www.worldweatheronline.com/weather-api-multilingual.aspx
        - includelocation: Returns the nearest weather point for which the weather data is returned for a given postcode, zipcode and lat/lon values.
        - tp:  Switch between weather forecast time interval from 1 hourly, 3 hourly, 6 hourly, 12 hourly (day/night) or 24 hourly (day average).
        - tide: To return tide data information if available
        - temp:  Temperature unit. Possible values: celsius, fahrenheit, kelvin.
        - wind:  Wind unit. Possible values: metric (km/h), imperial (miles/h) and knots.
        - units:  Units for the weather data. Possible values: metric (m/hPA), imperial (miles and inches).


        :param location: (Optional) Location string (e.g., "Berlin", "Columbus, Ohio", "45.775, 4.881").
        :param date: (Optional) The date for which to get the weather (e.g., "today", "tomorrow", "2023-10-01").
        :param hour: (Optional) The hour for which to get the weather (e.g., "now", "in 2 hours", "14:00").
        :param __metadata__: Metadata containing different models and prompt information
        :param __user__: A dictionary containing user settings for the tool.
        :param __event_emitter__: A callable used to emit status messages.
        :return: A json string containing the weather information.
        """
        if __user__ and __user__.get("valves"):
            self.user_valves: Tools.UserValves = __user__.get("valves", self.user_valves)

        try:
            # Validate TP parameter
            valid_tp = ["1", "3", "6", "12", "24"]
            if self.user_valves.tp and self.user_valves.tp not in valid_tp:
                error_msg = (
                    f"Error: Invalid time interval '{self.user_valves.tp}'. Valid values are {', '.join(valid_tp)}."
                )
                await self._emit_status(__event_emitter__, error_msg, True)
                return json.dumps({"message": error_msg}, ensure_ascii=False)

            # Resolve location to coordinates
            lat, lon, resolved_name = await self._resolve_location(location, __event_emitter__)
            print(f"Resolved location: {resolved_name} ({lat}, {lon})")

            # Fetch weather data
            await self._emit_status(
                __event_emitter__, f"Location resolved: {resolved_name}. Fetching forecast data...", False
            )

            url = self._build_weather_url(lat, lon)
            response = requests.get(url)

            if response.status_code != 200:
                error_msg = "Error: Could not get weather data."
                await self._emit_status(__event_emitter__, error_msg, True)
                return json.dumps({"message": error_msg}, ensure_ascii=False)

            data = response.json()
            if not data["data"].get("weather", []):
                error_msg = "Error: No weather data available."
                await self._emit_status(__event_emitter__, error_msg, True)
                return json.dumps({"message": error_msg}, ensure_ascii=False)

            # Parse date
            languages = ["en", self.user_valves.lang] if self.user_valves.lang else ["en"]
            parsed_date = dateparser.parse(date, languages=languages) if date else dateparser.parse("today")

            # Generate report
            report = self._format_weather_report(data, parsed_date, hour)

            # Success
            await self._emit_status(__event_emitter__, "Weather data fetched successfully.", True)
            return json.dumps({"message": "\n".join(report)}, ensure_ascii=False)

        except Exception as e:
            error_msg = f"An error occurred: {str(e)}"
            await self._emit_status(__event_emitter__, error_msg, True)
            return json.dumps({"message": error_msg}, ensure_ascii=False)
