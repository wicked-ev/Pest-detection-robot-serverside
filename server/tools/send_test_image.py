"""Pretend to be a robot: send one JPEG to the server and print the detections.

Usage (from the server folder):
    .venv/Scripts/python tools/send_test_image.py path/to/image.jpg [--server ws://host:8000] [--robot test-robot]
"""

import argparse
import asyncio
import json
import os
from pathlib import Path

import websockets
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image", type=Path)
    parser.add_argument("--server", default="ws://localhost:8000")
    parser.add_argument("--robot", default="test-robot")
    parser.add_argument("--model", default="pest_model")
    args = parser.parse_args()

    jpeg = args.image.read_bytes()
    url = f"{args.server}/ws/stream/{args.robot}?model={args.model}"
    key = os.getenv("ROBOT_KEY", "").strip()
    headers = {"X-Robot-Key": key} if key else None

    async with websockets.connect(url, max_size=None, additional_headers=headers) as ws:
        for attempt in range(3):
            await ws.send(jpeg)
            try:
                reply = await asyncio.wait_for(ws.recv(), timeout=30)
            except asyncio.TimeoutError:
                print(f"No reply yet (attempt {attempt + 1}), resending...")
                continue
            print(json.dumps(json.loads(reply), indent=2))
            return


if __name__ == "__main__":
    asyncio.run(main())
