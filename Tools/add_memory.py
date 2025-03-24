"""
title: Memory Management Tool
author: Mara-Li
author_url: https://github.com/mara-li
description: A simple tool for adding and updating memories in conversations. It will works on any model that don't not have the "tools" native support (like Gemma, for example).
version: 0.0.1
licence: MIT
required_open_webui_version: 0.5.0
"""

import json
from typing import Callable, Any, List

from open_webui.models.memories import Memories
from pydantic import BaseModel, Field
import difflib


class EventEmitter:
    def __init__(self, event_emitter: Callable[[dict], Any] = None):
        self.event_emitter = event_emitter

    async def emit(self, description="Unknown state", status="in_progress", done=False):
        """
        Send a status event to the event emitter.

        :param description: Event description
        :param status: Event status
        :param done: Whether the event is complete
        """
        if self.event_emitter:
            await self.event_emitter(
                {
                    "type": "status",
                    "data": {
                        "status": status,
                        "description": description,
                        "done": done,
                    },
                }
            )
            print(f"Event emitted: {description} - {status} - Done: {done}")


# Pydantic model for memory update operations
class MemoryUpdate(BaseModel):
    index: int = Field(..., description="Index of the memory entry (1-based)")
    content: str = Field(..., description="Updated content for the memory")


class Tools:
    """
    Memory
        Utilise cet outil pour sauvegarder, modifier ou rechercher des souvenirs de manière autonome dans tes conversations.

    IMPORTANT : il est rare que les utilisateurs te disent explicitement quoi retenir !
    Tu dois observer activement et identifier les informations importantes à mémoriser.

    Caractéristiques principales :
    1. Création proactive de souvenirs : identifie les préférences de l'utilisateur, le contexte du projet et les schémas récurrents.
    2. Utilisation intelligente des souvenirs : fais référence aux informations stockées sans que l'utilisateur ait à se répéter.
    3. Bonnes pratiques : stocke les informations utiles, maintiens leur pertinence et fais remonter les souvenirs au bon moment.
    4. Correspondance linguistique : crée toujours les souvenirs dans la langue de l'utilisateur en s'inspirant de son ton.

    NOTE IMPORTANTE SUR L'EFFACEMENT DES SOUVENIRS :
    Si un utilisateur te demande d'effacer tous ses souvenirs, n'essaie surtout pas de le faire via du code.
    Informe-le que la suppression complète de la mémoire est une opération à haut risque, qui doit être effectuée depuis les paramètres de son compte personnel, dans le panneau de configuration, en utilisant le bouton « Effacer la mémoire ».
    Cela permet d'éviter toute perte accidentelle de données.
    """

    class Valves(BaseModel):
        threshold: float = Field(
            0.8, description="Similarity threshold for memory update operations."
        )
        use_native_tools: bool = Field(
            False,
            description="Whether to use the native memory management tools if available. Will return a json response instead of a text response.",
        )
        citation: bool = Field(
            True,
            description="Whether to include the citation in the response message.",
        )

    def __init__(self):
        """Initialize the memory management tool."""
        self.valves = self.Valves()
        self.citation = self.valves.citation

    def _reply(self, message: str) -> str:
        """Format the response message."""
        if self.valves.use_native_tools:
            return json.dumps({"message": message}, ensure_ascii=False)
        return message

    async def add_memory(
        self,
        input_text: List[
            str
        ],  # Modified to only accept list, JSON Schema items.type is string
        __user__: dict = None,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Ajoute un ou plusieurs mémoires au coffre-fort de l'utilisateur.

        IMPORTANT : il est rare que les utilisateurs te disent explicitement quoi retenir !
        Tu dois observer activement et identifier les informations importantes à mémoriser.

        Si l'utilisateur te demande de te souvenir de quelque chose, enregistre-le dans ta mémoire immédiatement.
        Utilise toujours la fonction pour réellement stocker les données ; ne simule pas et ne fais pas semblant d'enregistrer des informations sans utiliser la fonction.
        N'invente pas et n'omets pas d'informations.

        Bons candidats pour les mémoires :
        - Préférences personnelles (sujets favoris, divertissements, couleurs)
        - Informations professionnelles (domaine d'expertise, projets en cours)
        - Relations importantes (famille, animaux de compagnie, amis proches)
        - Besoins ou demandes récurrentes (questions courantes, flux de travail réguliers)
        - Objectifs d'apprentissage et centres d'intérêt (sujets étudiés, compétences à développer)
        - Informations sur toi (couleur, vitesse, etc.)

        Tu dois reformuler le souvenir pour le rendre concis et clair. Corrige les fautes d'orthographe et adopte un ton neutre. Évite de conserver la ponctuation inutile.

        Dans les phrases de l'utilisateur, garde uniquement l'information importante. Supprime les mots superflus et les détails inutiles.
        Par exemple, si l'utilisateur dit : « N'oublie pas que tu es rouge ! », tu dois enregistrer : « Je suis rouge. »

        **IMPORTANT**
        Si l'utilisateur utilise "JE" tu dois considérer qu'il parle de LUI-MÊME. L'information enregistrée doit donc être "L'utilisateur". Mais si l'utilisateur parle de quelqu'un d'autre, tu dois enregistrer le nom de la personne.

        Si l'utilisateur utilise "TU" il parle de TOI, ARIA. L'information enregistrée doit donc être "Aria".

        Exemples :
        - « J'adore le bleu » ⇒ « L'utilisateur aime le bleu. »
        - « Je suis ingénieure en informatique » ⇒ « L'Utilisateur est ingénieure en informatique. »
        - « Hey, oublie pas que Stéphane possède un golden Retriever nommé Max !=> « Stéphane a un golden retriever nommé Max. »
        - « Pierre adore son chat Évolie ! » ⇒ « Pierre a un chat nommé Évoli. »
        - « J'aimerai apprendre le python… » ⇒ « L'utilisateur veut apprendre le Python. »
        - « Hey ! Tu sais que tu es un beau voilier rouge ??? » => « Aria est un beau voilier rouge. »

        Une fois les mémoires enregistrées, indique-le dans ton message. La mémoire est très importante ici !

        Souvent, l'utilisateur utilisera des phrases comme « tu te souviens ? » ou « tu sais » voire « N'oublie pas ! » pour te demander de te souvenir de quelque chose. Il est important de sauvegarder les mémoires.

        Si une mémoire similaire existe déjà, tu dois le mettre à jour avec la nouvelle information.

        N'enregistre que les informations pertinentes et utiles. N'enregistre pas des données composée d'un seul mot. Ainsi, si un utilisateur te demande la météo de Bastia, n'enregistre pas "Bastia" comme mémoire !

        :param input_text: Chaîne de souvenir unique ou liste de chaînes de mémoire à stocker
        :param __user__: Dictionnaire utilisateur contenant l'ID de l'utilisateur
        :param __event_emitter__: Émetteur d'événement optionnel pour le suivi de l'état
        :return: Chaîne de message indiquant le nombre de mémoires ajoutées ou mise à jour ainsi que les détails
        """
        try:
            # Initialize the event emitter
            emitter = EventEmitter(__event_emitter__)

            # Emit a status event
            if not __user__:
                message = "User ID not provided."
                await emitter.emit(
                    description=message, status="missing_user_id", done=True
                )
                return self._format_response(message)

            user_id = __user__.get("id")
            if not user_id:
                message = "User ID not provided."
                await emitter.emit(
                    description=message, status="missing_user_id", done=True
                )
                return self._format_response(message)

            if isinstance(input_text, str):
                input_text = [input_text]

            await emitter.emit(
                description="Processing memory entries.",
                status="processing_memory",
                done=False,
            )

            user_memories = Memories.get_memories_by_user_id(user_id)
            sorted_memories = sorted(user_memories, key=lambda m: m.created_at)
            added = []
            updated = []
            failed = []
            for new in input_text:
                updated_existing = False
                for idx, existing in enumerate(sorted_memories):
                    similarity = difflib.SequenceMatcher(
                        None, new, existing.content
                    ).ratio()
                    if similarity > self.valves.threshold:
                        result = Memories.update_memory_by_id(existing.id, new)
                        if result:
                            updated.append((idx + 1, new))
                            updated_existing = True
                            break
                if not updated_existing:
                    result = Memories.insert_new_memory(user_id, new)
                    if result:
                        added.append(new)
                    else:
                        failed.append(new)
            message_parts = []
            if added:
                message_parts.append(f"{len(added)} souvenir(s) ajoutée(s).")
            if updated:
                message_parts.append(f"{len(updated)} souvenir(s) mise(s) à jour.")
            if failed:
                message_parts.append(
                    f"{len(failed)} souvenir(s) n'a/n'ont pas pu être ajouté(s) ou mis à jour."
                )

            if not added and not updated and not failed:
                message_parts.append("Aucun souvenir ajouté ou mis à jour.")

            await emitter.emit(
                description="Traitement terminé.",
                status="done",
                done=True,
            )
            messages = " ".join(message_parts)
            if not self.valves.use_native_tools:
                added_str = (
                    "\nNouveaux souvenirs : \n- " + "\n- ".join(added)
                    if len(added) > 0
                    else ""
                )
                updated_str = (
                    "\nMis à jour : \n- "
                    + "\n- ".join([f"{idx}. {content}" for idx, content in updated])
                    if len(updated) > 0
                    else ""
                )

                messages = " ".join(message_parts) + added_str + updated_str

            return self._reply(messages)

        except Exception as e:
            message = f"An error occurred: {str(e)}"
            print(e)
            await emitter.emit(description=message, status="error", done=True)
            return self._reply(message)
