"""A minimal Google ADK assistant for testing model connectivity."""

from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from google.genai import types

retry_config = types.HttpRetryOptions(
    attempts=2,
    exp_base=7,
    initial_delay=1,
    http_status_codes=[429, 500, 503, 504],
)

root_agent = Agent(
    name="helpful_assistant",
    model=Gemini(
        model="gemini-3.5-flash-lite",
        retry_options=retry_config,
    ),
    description="A simple agent that can answer general questions.",
    instruction="You are a helpful assistant",
)
