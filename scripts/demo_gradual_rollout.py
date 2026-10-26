"""Observe real automatic decisions using held-out labels; promotion is not guaranteed."""

import time

import httpx
from demo_common import active, examples, post, sample, send


def main():
    rows = examples()
    with httpx.Client(timeout=5) as client:
        post(client, "/rollouts/reset")
        post(client, "/rollouts/advance", {"canary_percentage": 0.1})
        deadline = time.monotonic() + 120
        previous = None
        while time.monotonic() < deadline:
            state = active(client)
            marker = state["state"], state["canary_percentage"]
            if marker != previous:
                print(f"Automatic state: {marker}", flush=True)
                previous = marker
            if state["state"] in ("PROMOTED", "ROLLED_BACK"):
                print(
                    "Finished with the actual policy decision; all labels came from held-out data."
                )
                return
            code, data = send(client, sample(rows))
            if code != 200:
                print(f"Inference failed honestly (HTTP {code}): {data.get('error')}")
            time.sleep(0.02)
        raise SystemExit(
            "Evaluation remained on HOLD; inspect stage sample and label counts in the UI"
        )


if __name__ == "__main__":
    main()
