from __future__ import annotations

import asyncio

from simple_agent.config import load_config
from simple_agent.runtime.session_runtime import SessionRuntime
from simple_agent.utils.logging_utils import get_logger

logger = get_logger("app")


async def main(config_dir: str | None = None) -> None:
    config = load_config(config_dir)
    runtime = SessionRuntime(config)
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

            if not text or text in {"/exit", "exit", "quit"}:
                break

            result = await runtime.handle_user_input(session_id, text)
            print(f"\n{result.message}\n")

            if result.status == "waiting_user":
                try:
                    user_response = input("(user) ").strip()
                    if user_response:
                        result = await runtime.handle_user_input(session_id, user_response)
                        print(f"\n{result.message}\n")
                except (EOFError, KeyboardInterrupt):
                    break
    finally:
        await runtime.stop()
        print("Goodbye!")


if __name__ == "__main__":
    asyncio.run(main())
