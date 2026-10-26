"""Observe automatic rollback from real, opt-in Candidate HTTP faults."""

import time

import httpx
from demo_common import active, examples, post, sample, send


def main():
    rows = examples()
    with httpx.Client(timeout=5) as client:
        post(client, "/rollouts/reset")
        post(client, "/rollouts/advance", {"canary_percentage": 0.1})
        target, row = None, None
        for i in range(200):
            row = sample(rows)
            candidate_client = f"fault-probe-{i}"
            code, data = send(client, row, candidate_client)
            if code == 200 and data["model_role"] == "candidate":
                target = candidate_client
                break
        if target is None:
            raise SystemExit("No naturally routed Candidate found")
        for _ in range(25):
            if active(client)["state"] == "ROLLED_BACK":
                break
            code, data = send(client, row, target, fault=True)
            if code in (403, 409):
                raise SystemExit(
                    f"Fault was rejected: {data}. Enable ENABLE_DEMO_FAULTS for this demo."
                )
            if code < 500:
                raise SystemExit("Expected a real upstream fault")
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            state = active(client)
            if state["state"] == "ROLLED_BACK":
                print(
                    "Verified automatic rollback to 100% Champion after Candidate errors."
                )
                return
            time.sleep(0.2)
        raise SystemExit("Automatic rollback did not occur; inspect live stage metrics")


if __name__ == "__main__":
    main()
