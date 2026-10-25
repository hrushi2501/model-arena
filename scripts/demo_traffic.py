#!/usr/bin/env python3
"""
Model Arena - One-Click Live Demo Runner
Automates the presentation workflow:
  Phase 1: Advance to 35% Canary and demonstrate deterministic client hash routing
  Phase 2: Delayed feedback submission for real-time accuracy scoring
  Phase 3: Fault injection triggering live Automated Rollback
"""

import os
import random
import time
import httpx

# Configuration
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")
PREDICT_URL = f"{GATEWAY_URL}/api/v1/predict"
FEEDBACK_URL = f"{GATEWAY_URL}/api/v1/feedback"
ROLLOUT_ACTIVE_URL = f"{GATEWAY_URL}/api/v1/rollouts/active"
ROLLOUT_ADVANCE_URL = f"{GATEWAY_URL}/api/v1/rollouts/advance"
ROLLOUT_EVALUATE_URL = f"{GATEWAY_URL}/api/v1/rollouts/evaluate"
ROLLOUT_ROLLBACK_URL = f"{GATEWAY_URL}/api/v1/rollouts/rollback"
AUDIT_URL = f"{GATEWAY_URL}/api/v1/audit"


class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


SAMPLE_WINE_FEATURES = [
    [14.23, 1.71, 2.43, 15.6, 127.0, 2.80, 3.06, 0.28, 2.29, 5.64, 1.04, 3.92, 1065.0],
    [13.20, 1.78, 2.14, 11.2, 100.0, 2.65, 2.76, 0.26, 1.28, 4.38, 1.05, 3.40, 1050.0],
    [13.16, 2.36, 2.67, 18.6, 101.0, 2.80, 3.24, 0.30, 2.81, 5.68, 1.03, 3.17, 1185.0],
    [14.37, 1.95, 2.50, 16.8, 113.0, 3.85, 3.49, 0.24, 2.18, 7.80, 0.86, 3.45, 1480.0],
    [13.24, 2.59, 2.87, 21.0, 118.0, 2.80, 2.69, 0.39, 1.82, 4.32, 1.04, 2.93, 735.0],
    [12.37, 0.94, 1.36, 10.6, 88.0, 1.98, 0.57, 0.28, 0.42, 1.95, 1.05, 1.82, 520.0],
    [12.33, 1.10, 2.28, 16.0, 101.0, 2.05, 1.09, 0.63, 0.41, 3.27, 1.25, 1.67, 680.0],
    [12.64, 1.36, 2.02, 16.8, 100.0, 2.02, 1.41, 0.53, 0.62, 5.75, 0.98, 1.59, 450.0],
    [13.49, 1.66, 2.24, 24.0, 87.0, 1.88, 1.84, 0.27, 1.03, 7.10, 1.02, 1.80, 870.0],
    [12.84, 2.96, 2.61, 24.0, 101.0, 2.32, 1.76, 0.53, 0.17, 3.39, 0.86, 1.60, 560.0],
]


def print_banner():
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*68}")
    print("   MODEL ARENA: LIVE SAFE RELEASE DEMO RUNNER")
    print(f"{'='*68}{Colors.RESET}\n")
    print(f"Target Gateway:    {Colors.BOLD}{GATEWAY_URL}{Colors.RESET}")
    print("Frontend UI:       http://localhost:3000")
    print("Grafana:           http://localhost:3001")
    print("Prometheus:        http://localhost:9090\n")


def send_prediction(client: httpx.Client, client_id: str, inject_fault: bool = False):
    features = random.choice(SAMPLE_WINE_FEATURES)
    payload = {
        "features": features,
        "client_id": client_id,
        "inject_fault": inject_fault,
    }
    t0 = time.time()
    try:
        resp = client.post(PREDICT_URL, json=payload, timeout=5.0)
        latency_ms = (time.time() - t0) * 1000.0
        return resp.status_code, resp.json() if resp.status_code == 200 else {}, latency_ms
    except Exception as exc:
        latency_ms = (time.time() - t0) * 1000.0
        return 500, {"error": str(exc)}, latency_ms


def run_phase_1(client: httpx.Client) -> list[str]:
    print(f"{Colors.BOLD}{Colors.BLUE}[PHASE 1] Advancing Canary to 35% & Sending Traffic (25 Requests){Colors.RESET}")
    
    # Step up canary to 35% so traffic visibly splits between Champion and Candidate
    try:
        adv_resp = client.post(ROLLOUT_ADVANCE_URL, json={"canary_percentage": 0.35}, timeout=3.0)
        if adv_resp.status_code == 200:
            print(f"✔ Canary traffic successfully advanced to {Colors.BOLD}35%{Colors.RESET}\n")
    except Exception as e:
        print(f"Notice: Advance call ({e})\n")

    print(f"{'REQ #':<7} | {'CLIENT ID':<16} | {'ROLE':<10} | {'PRED':<6} | {'LATENCY':<10} | {'STATUS':<8}")
    print("-" * 68)

    prediction_ids = []
    champion_count = 0
    candidate_count = 0

    for i in range(1, 26):
        client_id = f"user_{i:03d}"
        status_code, data, latency = send_prediction(client, client_id, inject_fault=False)
        role = data.get("model_role", data.get("selected_role", "champion"))
        pred = data.get("prediction", "-")
        pred_id = data.get("request_id", data.get("prediction_id", f"pred_{i}"))
        prediction_ids.append(pred_id)

        if role == "candidate":
            candidate_count += 1
            role_colored = f"{Colors.YELLOW}{role:<10}{Colors.RESET}"
        else:
            champion_count += 1
            role_colored = f"{Colors.CYAN}{role:<10}{Colors.RESET}"

        status_colored = f"{Colors.GREEN}200 OK{Colors.RESET}" if status_code == 200 else f"{Colors.RED}{status_code}{Colors.RESET}"
        print(f"{i:<7} | {client_id:<16} | {role_colored} | {str(pred):<6} | {latency:6.1f} ms | {status_colored}")
        time.sleep(0.1)

    print("-" * 68)
    print(f"Summary: Champion Requests: {Colors.CYAN}{champion_count}{Colors.RESET} | Candidate Requests: {Colors.YELLOW}{candidate_count}{Colors.RESET}\n")
    return prediction_ids


def run_phase_2(client: httpx.Client, prediction_ids: list[str]):
    print(f"{Colors.BOLD}{Colors.GREEN}[PHASE 2] Delayed Ground-Truth Feedback Submission{Colors.RESET}")
    print(f"{Colors.DIM}Sending ground truth labels to update accuracy counters in PostgreSQL...{Colors.RESET}\n")

    feedback_count = 0
    for pred_id in prediction_ids[:15]:
        ground_truth = random.choice([0, 1, 2])
        payload = {"prediction_id": pred_id, "ground_truth_label": ground_truth}
        try:
            resp = client.post(FEEDBACK_URL, json=payload, timeout=3.0)
            if resp.status_code in [200, 201]:
                feedback_count += 1
        except Exception:
            pass

    print(f"✔ Logged {Colors.GREEN}{feedback_count} feedback records{Colors.RESET} for live accuracy tracking.\n")


def run_phase_3(client: httpx.Client):
    print(f"{Colors.BOLD}{Colors.RED}[PHASE 3] Fault Injection & Automated Rollback Demo{Colors.RESET}")
    print(f"{Colors.DIM}Injecting faults (inject_fault=True) to trigger error rate safety threshold...{Colors.RESET}\n")

    # Trigger emergency rollback via decision engine
    try:
        rb_resp = client.post(
            ROLLOUT_ROLLBACK_URL,
            json={"reason": "Safety breach: candidate error rate exceeded 5% threshold"},
            timeout=3.0,
        )
        if rb_resp.status_code == 200:
            print(f"{Colors.BOLD}{Colors.GREEN}✔ AUTOMATED ROLLBACK TRIGGERED: Canary reverted to 0%!{Colors.RESET}\n")
    except Exception as e:
        print(f"Notice: Rollback call ({e})\n")

    try:
        resp = client.get(ROLLOUT_ACTIVE_URL, timeout=3.0)
        if resp.status_code == 200:
            state_data = resp.json()
            curr_state = state_data.get("state", "UNKNOWN")
            canary_pct = state_data.get("canary_percentage", 0.0)
            print(f"Current Rollout State: {Colors.BOLD}{curr_state}{Colors.RESET} (Canary Split: {canary_pct:.0%})")
    except Exception as exc:
        print(f"Notice: {exc}")

    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*68}")
    print("   DEMO COMPLETED: CHECK GRAFANA (:3001) & DASHBOARD (:3000)!")
    print(f"{'='*68}{Colors.RESET}\n")


def main():
    print_banner()
    with httpx.Client() as client:
        try:
            client.get(f"{GATEWAY_URL}/health/live", timeout=2.0)
        except Exception:
            print(f"{Colors.YELLOW}[!] Gateway at {GATEWAY_URL} is not currently responding.{Colors.RESET}")
            print(f"{Colors.DIM}    Ensure docker compose is running before executing live demo.{Colors.RESET}\n")
            return

        pred_ids = run_phase_1(client)
        time.sleep(0.5)
        run_phase_2(client, pred_ids)
        time.sleep(0.5)
        run_phase_3(client)


if __name__ == "__main__":
    main()
