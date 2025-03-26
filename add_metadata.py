"""
title: Add User Preferences
author: Mara-Li
description: Ajoute les préférences de l'utilisateur dans les messages, ainsi que son statut et d'autres informations.
required_open_webui_version: 0.5.0
version: 0.0.1
licence: MIT
"""

from pydantic import BaseModel, Field
from typing import Optional, Callable, Any
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


class Filter:
    class Valves(BaseModel):
        debug: bool = Field(
            default=False,
            description="Active le mode debug, pour afficher les logs dans la console",
            title="Mode debug",
        )
        timezone: str = Field(
            default="Europe/Paris",
            description="Fuseau horaire par défaut pour les dates et heures",
            title="Fuseau horaire",
        )

    class UserValves(BaseModel):
        date_de_naissance: Optional[str] = Field(
            default=None,
            description="Au format JJ/MM/AAAA, JJ-MM-AAAA, AAAA-MM-JJ ou JJ.MM.AAAA",
            title="Date de naissance",
        )
        aime: Optional[str] = Field(
            default=None,
            description="Ce que vous aimez (séparé par des virgules)",
            title="Aime",
        )
        aime_pas: Optional[str] = Field(
            default=None,
            description="Ce que vous n'aimez pas (séparé par des virgules)",
            title="N'aime pas",
        )
        couleur_preferee: Optional[str] = Field(
            default=None, description="Votre couleur préférée", title="Couleur préférée"
        )
        statut: Optional[str] = Field(
            default=None,
            description="Votre statut par rapport à l'application (ex: Codeur, Papa, Maman, etc.)",
            title="Statut",
        )
        surnom: Optional[str] = Field(
            default=None,
            description="Surnom que peut vous donner l'application, séparé par des virgules (ex: Papa, Stéphane, Capitaine, etc.)",
            title="Surnoms",
        )
        autres_infos: Optional[str] = Field(
            default=None,
            title="Autres informations (zone de texte)",
            description="Vous pouvez écrire ici des informations supplémentaires",
        )

    def __init__(self):
        self.valves = self.Valves()

    def _format_date(self, date_str: Optional[str]) -> Optional[str]:
        if not date_str:
            return None
        formats_to_try = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"]
        for fmt in formats_to_try:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.strftime("%d/%m/%Y")
            except ValueError:
                continue
        return None

    def _get_current_date(self) -> str:
        """
        Get the current date.
        :return: The current date as a string.
        """
        # current_date = datetime.now().strftime("%A, %B %d, %Y")
        # return f"Today's date is {current_date}"

        now_utc = datetime.now(timezone.utc)
        tz = ZoneInfo(self.valves.timezone)
        now_desired = now_utc.astimezone(tz)
        return now_desired.strftime("%d/%m/%Y")

    def _get_current_time(self) -> str:
        """
        Get the current time.
        :return: The current time as a string.
        """
        # current_time = datetime.now().strftime("%H:%M:%S")
        # return f"Current Time: {current_time}"

        now_utc = datetime.now(timezone.utc)
        tz = ZoneInfo(self.valves.timezone)
        now_desired = now_utc.astimezone(tz)
        return now_desired.strftime("%H:%M")

    async def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Callable[[dict], Any] = None, # type: ignore
    ) -> dict:
        # Récupérer les valves de l'utilisateur
        if __user__:
            raw_valves = __user__.get("valves", {})
            if isinstance(raw_valves, self.UserValves):
                self.user_valves = raw_valves
            else:
                self.user_valves = self.UserValves(**raw_valves)
        else:
            self.user_valves = None

        # print(f"User valves: {self.user_valves}")

        user_info = {}
        if __user__:
            user_info = {
                "Nom": __user__.get("name"),
                "Email": __user__.get("email"),
                "Rôle": __user__.get("role"),
            }

        # Préparer les préférences de l'utilisateur
        if not self.user_valves:
            preferences = None
        else:
            preferences = {
                "Date de naissance": (
                    self._format_date(self.user_valves.date_de_naissance)
                    if self.user_valves.date_de_naissance
                    else None
                ),
                "Aime": (
                    [x.strip() for x in self.user_valves.aime.split(",")]
                    if self.user_valves.aime
                    else None
                ),
                "N'aime pas": (
                    [x.strip() for x in self.user_valves.aime_pas.split(",")]
                    if self.user_valves.aime_pas
                    else None
                ),
                "Couleur préférée": (
                    self.user_valves.couleur_preferee
                    if self.user_valves.couleur_preferee
                    else None
                ),
            }
            statut_message = ""
            surnom_message = ""
            autre_message = ""
            if self.user_valves.statut:
                statut_message = (
                    f"L'utilisateur est, par rapport à toi : {self.user_valves.statut}\n"
                )
            if self.user_valves.surnom:
                surnom_message = f"Tu peux l'appeler : {', '.join([x.strip() for x in self.user_valves.surnom.split(',')])} en fonction du contexte.\n"
            if self.user_valves.autres_infos:
                autre_message = f"Autres informations entrée par l'utilisateur: {self.user_valves.autres_infos}\n"


        # Construire le contenu du message système
        system_message = "------ SYSTEM INFO ------\n"
        system_message += f"- Date du jour : {self._get_current_date()}\n"
        system_message += f"- Heure du message : {self._get_current_time()}\n"
        system_message += "------ USER INFO ------\n"
        system_message += "Voici des informations à propos de l'utilisateur :\n"
        for key, val in user_info.items():
            system_message += f"- {key} : {val}\n"
        
        is_empty = True
        if preferences:
            is_empty = all([val is None for val in preferences.values()])
            if not is_empty:
                system_message += "\nPréférences personnelles :\n"
                for key, val in preferences.items():
                    if isinstance(val, list):
                        system_message += f"- {key} : {', '.join(val)}\n"
                    elif val:
                        system_message += f"- {key} : {val}\n"
        system_message += statut_message
        system_message += surnom_message
        system_message += autre_message
        print(f"System message: {system_message}")

        system_message += "Tu dois utiliser ses informations pour personnaliser tes réponses, et répondre de manière précise aux questions de l'utilisateur. Par exemple, si ce dernier mentionne avoir un chat, tu dois pouvoir répondre qu'il a un chat. De même, si l'utilisateur te demande l'heure ou la date du jour, tu dois pouvoir répondre !"

        body.setdefault("messages", []).insert(
            0, {"role": "system", "content": system_message}
        )

        return body
