"""Verify Champion-only SHADOW requests and completed asynchronous comparisons."""

import time

import httpx
from demo_common import GATEWAY, examples, post, send


def main():
    rows = examples()
    with httpx.Client(timeout=5) as client:
        post(client, "/rollouts/reset")
        post(client, "/rollouts/shadow")
        for row in rows[:20]:
            code, prediction = send(client, row)
            if code != 200 or prediction["model_role"] != "champion":
                raise SystemExit("SHADOW did not return a successful Champion result")
        deadline = time.monotonic() + 30
        while True:
            response = client.get(GATEWAY + "/api/v1/shadow/summary")
            response.raise_for_status()
            summary = response.json()
            if (
                summary["total_shadow_evaluations"] >= 20
                and summary["pending_tasks"] == 0
            ):
                print(summary)
                print(
                    "Verified 20 Champion responses and 20 completed asynchronous comparisons."
                )
                return
            if time.monotonic() >= deadline:
                raise SystemExit(f"Incomplete shadow processing: {summary}")
            time.sleep(0.2)


if __name__ == "__main__":
    main()
