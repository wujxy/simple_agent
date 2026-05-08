from __future__ import annotations

import asyncio

from simple_agent.config import load_config
from simple_agent.runtime.cli_renderer import CliEventRenderer
from simple_agent.runtime.session_runtime import SessionRuntime
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("app")


async def main(config_dir: str | None = None) -> None:
    config = load_config(config_dir)
    runtime = SessionRuntime(config)
    runtime.subscribe_events(CliEventRenderer())
    await runtime.start()

    session_id = await runtime.create_session()
    print(f"Session started: {session_id}")
    print("Type your tasks. Enter '/exit' to quit.\n")

    try:
        while True:
            try:
                text = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if text in {"/exit", "exit", "quit"}:
                break
            if not text:
                continue
            if text == "/mode":
                print(f"Current mode: {runtime.get_session_mode(session_id)}")
                continue
            if text.startswith("/mode "):
                requested = text.split(maxsplit=1)[1].strip()
                mode = runtime.set_session_mode(session_id, requested)
                print(f"Mode set to: {mode}")
                continue

            result = await runtime.handle_user_input(session_id, text)

            if result.status == "waiting_user":
                try:
                    user_response = input("(user) ").strip()
                    if user_response:
                        result = await runtime.handle_user_input(session_id, user_response)
                        # Keep prompting if the loop re-enters a waiting state
                        while result.status == "waiting_user":
                            try:
                                user_response = input("(user) ").strip()
                            except (EOFError, KeyboardInterrupt):
                                break
                            if not user_response:
                                break
                            result = await runtime.handle_user_input(session_id, user_response)
                except (EOFError, KeyboardInterrupt):
                    break
    finally:
        await runtime.stop()
        print("Goodbye!")


if __name__ == "__main__":
    asyncio.run(main())
