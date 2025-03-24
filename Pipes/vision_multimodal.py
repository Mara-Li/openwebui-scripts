"""
title: Vision Multimodal
author: Mara-Li
author_url: https://github.com/mara-li
description: Allow to switch model based on image detection.
version: 0.0.1
licence: MIT
required_open_webui_version: 0.5.0
"""

from logging import getLogger
from pydantic import BaseModel, Field
from fastapi import Request
from open_webui.models.users import Users
from open_webui.utils.chat import generate_chat_completion
import re


class Pipe:
    class Valves(BaseModel):
        TEXT_MODEL_ID: str = Field(
            default="mistral:7b", description="Modèle principal pour le texte"
        )
        VISION_MODEL_ID: str = Field(
            default="gemma3:4b", description="Modèle pour l'analyse d'image"
        )
        VISION_PROMPT: str = Field(
            default="Décris précisément ce que tu vois dans cette image.",
            description="Prompt utilisé pour guider le modèle de vision",
        )
        DEBUG: bool = Field(
            default=False, description="Afficher les étapes de traitement pour le debug"
        )

    def _debug(self, message: str):
        if self.valves.DEBUG:
            self.logger.debug(message)

    def __init__(self):
        self.valves = self.Valves()
        self.logger = getLogger(__name__)

    async def pipe(self, body: dict, __user__: dict, __request__: Request) -> str:
        user = Users.get_user_by_id(__user__["id"])
        messages = body.get("messages", [])
        last_user_message = next(
            (m for m in reversed(messages) if m["role"] == "user"), None
        )
        self._debug(f"[Pipe] Configuration: {self.valves}")
        if last_user_message and self._contains_image(
            last_user_message.get("content", "")
        ):
            self._debug("[Pipe] Image détectée, envoi au modèle vision...")

            # Analyse de l'image via le modèle de vision
            vision_messages = [
                {"role": "system", "content": self.valves.VISION_PROMPT},
                last_user_message,
            ]
            vision_body = {
                "messages": vision_messages,
                "model": self.valves.VISION_MODEL_ID,
            }
            vision_response = await generate_chat_completion(
                __request__, vision_body, user
            )

            if self.valves.DEBUG:
                print(f"[Pipe] Résultat vision:\n{vision_response}")

            # Injecte l'analyse de l'image dans le contexte
            messages.append(
                {
                    "role": "system",
                    "content": f"Analyse de l'image :\n{vision_response}",
                }
            )
        else:
            self._debug(
                "[Pipe] Pas d'image détectée, envoi au modèle texte directement"
            )
        # Appel final au modèle texte
        body["model"] = self.valves.TEXT_MODEL_ID
        return await generate_chat_completion(__request__, body, user)

    def _contains_image(self, content: str) -> bool:
        if not content:
            return False
        img_extensions = [".png", ".jpg", ".jpeg", ".gif", ".webp"]
        url_pattern = r"https?:\/\/\S+\.(?:png|jpe?g|gif|webp)"
        is_data_uri = content.strip().startswith("data:image/")
        return (
            bool(re.search(url_pattern, content, re.IGNORECASE))
            or is_data_uri
            or any(ext in content.lower() for ext in img_extensions)
        )
