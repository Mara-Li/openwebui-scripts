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
from pydantic import BaseModel, Field
from typing import Any, Literal, Optional, Union

import requests
import dateparser


class MarineWeatherTool:
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
        tp: Optional[list[Literal[1, 3, 6, 12, 24]]] = Field(
            default=None,
            description="Switch between weather forecast time interval from 1 hourly, 3 hourly, 6 hourly, 12 hourly (day/night) or 24 hourly (day average). E.g:- tp=24 or tp=12 or tp=6 or tp=3 or tp=1",
        )
        tide: bool = Field(default=False, description="To return tide data information if available.")
        lang: Optional[str] = Field(
            default=None, description="Returns weather description text in the language of your choice."
        )

    def __init__(self):
        self.valves = self.Valves()  # Remplace par ta clé perso
        self.user_valves = self.UserValves()

    async def get_marine_weather(
        self,
        location: Union[str, dict],
        date: Optional[str] = None,
        hour: Optional[str] = None,
        __user__: Optional[dict] = None,
        __event_emitter__=None,
    ):
        """
        Get the current marine weather for a given location using World Weather Online API.

        If the day is not provided, the current weather is returned. Date can be set in the current language as "today" or "tomorrow" or in different format, as "YYYY-MM-DD" or "DD/MM/YYYY".

        If the hour is not provided, the current hour is returned. Hour can be set in the current language as "now", "in x hours", "at 2h" or in different format, as "HH:MM" or "HHMM".

        This asynchronous function supports queries that include both a city and a state/region or just a location (longitude and latitude).
        It uses the geocoding API to convert the location into latitude and longitude coordinates.
        Status messages are emitted via __event_emitter__ so that the user knows the process is running.

        **Valves**:
        - lang:  Returns weather description text in the language of your choice. E.g:- lang=ar (Arabic). Visit Multilingual support page for more information: http://www.worldweatheronline.com/weather-api-multilingual.aspx
        - includelocation: Returns the nearest weather point for which the weather data is returned for a given postcode, zipcode and lat/lon values. The possible values are yes or no. By default it is no. E.g:- includeLocation=yes or includeLocation=no
        - tp:  Switch between weather forecast time interval from 1 hourly, 3 hourly, 6 hourly, 12 hourly (day/night) or 24 hourly (day average). E.g:- tp=24 or tp=12 or tp=6 or tp=3 or tp=1
        - tide: To return tide data information if available. The possible values are yes or no. By default it is no. E.g:- tide=yes
        - citation: Toggle to include a citation in the output.
        - api_key: Your API key for World Weather Online.
        """
        if __user__:
            raw_valves = __user__.get("valves", {})
            self.user_valves = self.UserValves(**raw_valves)
        if isinstance(location, dict):
            lat = location.get("lat", None)
            lon = location.get("lon", None)
            if lat is None or lon is None:
                raise ValueError("Latitude and longitude must be provided in the location dictionary.")
            resolved_name = f"{lat},{lon}"
        else:
            try:
                if __event_emitter__ is not None:
                    await __event_emitter__({
                        "type": "status",
                        "data": {
                            "description": f"Fetching location data for '{location}'...",
                            "done": False,
                        },
                    })
                geo = requests.get(f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1")
                geo_data = geo.json()
                if geo.status_code != 200:
                    error_msg = "Error: Could not get geolocation data."
                    if __event_emitter__ is not None:
                        await __event_emitter__({
                            "type": "status",
                            "data": {"description": error_msg, "done": True},
                        })
                    return json.dumps({"message": error_msg}, ensure_ascii=False)
                if "results" not in geo_data or not geo_data["results"]:
                    error_msg = f"Error: Location '{location}' not found."
                    if __event_emitter__ is not None:
                        await __event_emitter__({
                            "type": "status",
                            "data": {"description": error_msg, "done": True},
                        })
                    return json.dumps({"message": error_msg}, ensure_ascii=False)
                chosen_geo: dict[str, Any] = {}
                if location:
                    for result in geo_data["results"]:
                        if "admin1" in result and result["admin1"].lower() == location.lower():
                            chosen_geo = result
                            break
                if not chosen_geo:
                    chosen_geo = geo_data["results"][0]
                lat = chosen_geo["latitude"]
                lon = chosen_geo["longitude"]
                resolved_name = geo_data["results"][0]["name"]
                if __event_emitter__ is not None:
                    await __event_emitter__({
                        "type": "status",
                        "data": {
                            "description": f"Location resolved: {resolved_name}. Fetching forecast data...",
                            "done": False,
                        },
                    })
                url = (
                    f"http://api.worldweatheronline.com/premium/v1/marine.ashx?key={self.valves.api_key}"
                    f"&q={lat},{lon}&format=json"
                )
                if self.user_valves.tp:
                    for interval in self.user_valves.tp:
                        url += f"&tp={interval}"
                if self.user_valves.lang:
                    url += f"&lang={self.user_valves.lang}"
                url += f"&tide={'yes' if self.user_valves.tide else 'no'}"
                url += f"&includeLocation={'yes' if self.user_valves.includelocation else 'no'}"
                response = requests.get(url)
                if response.status_code != 200:
                    error_msg = "Error: Could not get weather data."
                    if __event_emitter__ is not None:
                        await __event_emitter__({
                            "type": "status",
                            "data": {"description": error_msg, "done": True},
                        })
                    return json.dumps({"message": error_msg}, ensure_ascii=False)
                data = response.json()
                weather_days = data["data"].get("weather", [])
                if not weather_days:
                    error_msg = "Error: No weather data available."
                    if __event_emitter__ is not None:
                        await __event_emitter__({
                            "type": "status",
                            "data": {"description": error_msg, "done": True},
                        })
                    return json.dumps({"message": error_msg}, ensure_ascii=False)
                report = []
                languages = ["en", self.user_valves.lang] if self.user_valves.lang else ["en"]
                parsed_date = dateparser.parse(date, languages=languages) if date else None
                for day in weather_days:
                    date_str = day["date"]
                    if parsed_date and parsed_date.date().isoformat() != date_str:
                        continue
                astronomy = day.get("astronomy", [{}])[0]
                report.append(f"Date: {date_str}")
                report.append(f"Sunrise: {astronomy.get('sunrise', '?')} | Sunset: {astronomy.get('sunset', '?')}")
                selected_hours = day.get("hourly", [])
                if hour:
                    parsed_time = dateparser.parse(hour, languages=languages)
                    if parsed_time:
                        user_hour_str = f"{parsed_time.hour:02}00"
                    else:
                        user_hour_str = hour.replace(":", "").zfill(4)
                    selected_hours = [h for h in selected_hours if h["time"].zfill(4) == user_hour_str]
                for hourly in selected_hours:
                    time_h = hourly["time"].zfill(4)
                    hour_label = f"{time_h[:-2]}:{time_h[-2:]}"
                    wind_kph = float(hourly["windspeedKmph"])
                    wind_knots = round(wind_kph * 0.539957, 1)
                    desc = hourly["weatherDesc"][0]["value"]
                    if self.user_valves.lang and f"lang_{self.user_valves.lang}" in hourly:
                        desc = hourly[f"lang_{self.user_valves.lang}"][0]["value"]
                    report.extend([
                        f"\n— {hour_label} —",
                        f"Temp: {hourly['tempC']} °C | Water: {hourly['waterTemp_C']} °C",
                        f"Wind: {wind_knots} knots ({hourly['winddir16Point']})",
                        f"Swell: {hourly['swellHeight_m']} m {hourly['swellDir16Point']} {hourly['swellPeriod_secs']}s",
                        f"Pressure: {hourly['pressure']} hPa | Humidity: {hourly['humidity']}%",
                        f"Weather: {desc}",
                    ])
                return json.dumps({"message": "\n".join(report)}, ensure_ascii=False)
            except Exception as e:
                if __event_emitter__ is not None:
                    await __event_emitter__({
                        "type": "status",
                        "data": {
                            "description": f"An error occurred: {e}",
                            "done": True,
                        },
                    })
                return json.dumps({"message": error_msg}, ensure_ascii=False)
