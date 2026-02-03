""" "Main module for the Google GenAI Chat App."""

# %% IMPORTS

import json
import logging
import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from google import genai
from google.genai import types
from pythonjsonlogger import jsonlogger

# %% CONFIGS

ROOT_FOLDER = Path(__file__).parent

COMMANDS = json.loads((ROOT_FOLDER / "commands.json").read_text())

GOOGLE_CLOUD_PROJECT = os.environ["GOOGLE_CLOUD_PROJECT"]
GOOGLE_CLOUD_LOCATION = os.environ["GOOGLE_CLOUD_LOCATION"]
GOOGLE_GENAI_USE_VERTEXAI = os.environ["GOOGLE_GENAI_USE_VERTEXAI"].lower() == "true"

LOGGING_LEVEL = os.environ.get("LOGGING_LEVEL", "INFO").upper()

MODEL_NAME = os.environ["MODEL_NAME"]
MODEL_CONTEXT = (ROOT_FOLDER / "context.md").read_text()
MODEL_MAX_OUTPUT_TOKENS = 5000

# %% LOGGING

formatter = jsonlogger.JsonFormatter(
    fmt="%(asctime)s %(levelname)s %(message)s %(name)s %(module)s %(lineno)d",
    rename_fields={"levelname": "severity", "asctime": "timestamp"},
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)

logger = logging.getLogger()
logger.handlers.clear()
logger.addHandler(handler)
logger.setLevel(LOGGING_LEVEL)

# %% CLIENTS

client = genai.Client(
    project=GOOGLE_CLOUD_PROJECT,
    location=GOOGLE_CLOUD_LOCATION,
    vertexai=GOOGLE_GENAI_USE_VERTEXAI,
)
config = types.GenerateContentConfig(
    max_output_tokens=MODEL_MAX_OUTPUT_TOKENS,
    system_instruction=MODEL_CONTEXT,
    safety_settings=[
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
            threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
        ),
    ],
)

# %% APPS

app = FastAPI()

# %% HELPERS


async def chat(prompt: str) -> str:
    """Generate a response from the model based on the prompt."""
    response = await client.aio.models.generate_content(
        model=MODEL_NAME, contents=[prompt], config=config
    )
    return response.text or ""


def respond(text: str) -> dict:
    """Format the text into a chat message response."""
    return {
        "hostAppDataAction": {
            "chatDataAction": {
                "createMessageAction": {
                    "message": {
                        "text": text,
                    }
                }
            }
        }
    }


# %% HANDLERS


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/")
async def index(request: Request) -> dict:
    """Handle incoming chat events."""
    event = await request.json()
    logger.info("Chat Event received.", extra={"event": event})
    try:
        event_chat = event.get("chat", {})
        if "addedToSpacePayload" in event_chat:
            return {} # ignore added to space events
        app_command_payload = event_chat.get("appCommandPayload", {})
        app_command_metadata = app_command_payload.get("appCommandMetadata", {})
        message = (
            app_command_payload.get("message")
            or event_chat.get("messagePayload", {}).get("message")
            or {}
        )
        user_input = (message.get("argumentText") or message.get("text") or "").strip()
        if command_id := app_command_metadata.get("appCommandId"):  # an app command was used
            command_id = str(int(command_id))
            if command_id in COMMANDS:
                command_text = COMMANDS[command_id]
                command_type = app_command_metadata.get("appCommandType")
                if command_type == "QUICK_COMMAND":  # reply with the command text directly
                    return respond(command_text)
                if command_type == "SLASH_COMMAND":  # append the user input to the command text
                    return respond(await chat(f"{command_text}. USER INPUT: {user_input}"))
                logger.warning("Unknown command type.", extra={"command_type": command_type})
            else:
                logger.warning("Unknown command ID.", extra={"command_id": command_id})
        if not user_input:
            logger.warning("Empty message received.", extra={"event": event})
            return respond("I didn't receive any message. Please try again.")
        return respond(await chat(user_input))  # generate a chat response
    except Exception as error:
        logger.error("Error processing event.", extra={"error": error}, exc_info=True)
        return respond("An error occurred while processing your request. Please check the logs.")
