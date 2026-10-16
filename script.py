"""Minimal ADK agent example.

This module recreates the sample you provided using the latest ADK-style
imports. It will attempt to import the real libraries and will print a clear
error message if they are not installed.

Replace or configure credentials (GOOGLE_API_KEY or GOOGLE_APPLICATION_CREDENTIALS)
before running if you want to call the real Gemini model.
"""

import asyncio
import sys

try:
    from google.adk.agents import Agent
    from google.adk.models.google_llm import Gemini
    from google.adk.runners import InMemoryRunner
    from google.adk.tools import google_search
    from google.genai import types
except Exception as e:
    print(
        "Error: required google ADK packages are not installed or import failed:\n",
        e,
        file=sys.stderr,
    )
    print("Please install the ADK package and ensure your PYTHONPATH is correct.")
    print("For example: pip install google-adk")
    raise


retry_config = types.HttpRetryOptions(
    attempts=2,  # Maximum retry attempts
    exp_base=7,  # Delay multiplier
    initial_delay=1,  # Initial delay before first retry (in seconds)
    http_status_codes=[429, 500, 503, 504],  # Retry on these HTTP errors
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

print("✅ Root Agent defined.")


async def main():
    runner = InMemoryRunner(agent=root_agent)

    # If the ADK supports a run_debug method that returns a response object,
    # this will await that. The exact shape of the response depends on the
    # ADK implementation; here we print it raw.
    response = await runner.run_debug(
        "What is Agent Development Kit from Google google-adk? "
    )

    print(f"\nResponse:{response}")
    # try:
    #     # try to pretty-print common structures
    #     import json
    #
    #     print(json.dumps(response, indent=2, default=str))
    # except Exception:
    #     print(response)


if __name__ == "__main__":
    asyncio.run(main())
