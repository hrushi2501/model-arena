#!/usr/bin/env python3
"""
Model Arena - Autonomous Safety & Automated Rollback Demo
Driven 100% by the Decision Engine:
  Phase 1: Canary Traffic & Feedback (normal healthy operation)
  Phase 2: Live Fault Injection on Candidate (inject_fault=True)
  Phase 3: Decision Engine Evaluation (catches >5% error rate and triggers instant ROLLBACK)
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
ROLLOUT_RESET_URL = f"{GATEWAY_URL}/api/v1/rollouts/reset"
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
    [12.37, 0.94, 1.36, 10.6, 88.0, 1.98, 0.57, 0.28, 0.42, 1.95, 1.05, 1.82, 520.0],
]


def print_banner():
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*72}")
    print("   MODEL ARENA: LIVE SAFETY DEMO (DECISION ENGINE ROLLBACK)")
    print(f"{'='*72}{Colors.RESET}\n")
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
    print(f"{Colors.BOLD}{Colors.BLUE}[PHASE 1] Active Canary Traffic (35% Traffic Share){Colors.RESET}")
    
    # Set canary traffic to 35% so traffic reaches both Champion and Candidate
    try:
        client.post(ROLLOUT_ADVANCE_URL, json={"canary_percentage": 0.35}, timeout=3.0)
        print(f"✔ Canary traffic configured at {Colors.BOLD}35%{Colors.RESET}\n")
    except Exception as e:
        print(f"Notice: Advance call ({e})\n")

    print(f"{'REQ #':<7} | {'CLIENT ID':<16} | {'ROLE':<10} | {'PRED':<6} | {'LATENCY':<10} | {'STATUS':<8}")
    print("-" * 72)

    prediction_ids = []
    champion_count = 0
    candidate_count = 0

    for i in range(1, 26):
        client_id = f"user_{i:03d}"
        status_code, data, latency = send_prediction(client, client_id, inject_fault=False)
        role = data.get("model_role", "champion")
        pred = data.get("prediction", "-")
        pred_id = data.get("request_id")
        if pred_id:
            prediction_ids.append((pred_id, pred))

        if role == "candidate":
            candidate_count += 1
            role_colored = f"{Colors.YELLOW}{role:<10}{Colors.RESET}"
        else:
            champion_count += 1
            role_colored = f"{Colors.CYAN}{role:<10}{Colors.RESET}"

        status_colored = f"{Colors.GREEN}200 OK{Colors.RESET}" if status_code == 200 else f"{Colors.RED}{status_code}{Colors.RESET}"
        print(f"{i:<7} | {client_id:<16} | {role_colored} | {str(pred):<6} | {latency:6.1f} ms | {status_colored}")
        time.sleep(0.04)

    print("-" * 72)
    print(f"Summary: Champion: {Colors.CYAN}{champion_count}{Colors.RESET} | Candidate: {Colors.YELLOW}{candidate_count}{Colors.RESET}\n")
    return [pid for pid, _ in prediction_ids]


def run_phase_2(client: httpx.Client, prediction_ids: list[str]):
    print(f"{Colors.BOLD}{Colors.GREEN}[PHASE 2] Submitting Ground-Truth Feedback for Accuracy{Colors.RESET}")
    feedback_count = 0
    for pred_id in prediction_ids[:15]:
        ground_truth = random.choice([0, 1, 2])
        try:
            resp = client.post(FEEDBACK_URL, json={"prediction_id": pred_id, "ground_truth_label": ground_truth}, timeout=2.0)
            if resp.status_code in [200, 201]:
                feedback_count += 1
        except Exception:
            pass

    print(f"✔ Submitted {Colors.GREEN}{feedback_count} ground-truth labels{Colors.RESET} into PostgreSQL.\n")


def run_phase_3(client: httpx.Client):
    print(f"{Colors.BOLD}{Colors.RED}[PHASE 3] Live Fault Injection & Autonomous Decision Engine Rollback{Colors.RESET}")
    print(f"{Colors.DIM}Injecting faults (inject_fault=True) directly into Candidate model server...{Colors.RESET}\n")

    # Send 15 requests with inject_fault=True to Candidate
    fault_count = 0
    for i in range(1, 16):
        # We target candidate hash clients
        client_id = f"fault_user_{i:03d}"
        status_code, data, latency = send_prediction(client, client_id, inject_fault=True)
        if status_code >= 500 or data.get("status_code", 200) >= 500:
            fault_count += 1
            print(f"  ⚡ Injected Fault #{i}: Candidate failed (HTTP 500 Internal Error, latency {latency:.1f}ms)")
        time.sleep(0.05)

    print(f"\n✔ Injected {Colors.RED}{fault_count} faults{Colors.RESET} into Candidate inference.\n")

    # Now call the Decision Engine to evaluate health!
    print(f"{Colors.BOLD}Invoking Decision Engine (POST /api/v1/rollouts/evaluate)...{Colors.RESET}")
    eval_resp = client.post(ROLLOUT_EVALUATE_URL, timeout=3.0)
    
    if eval_resp.status_code == 200:
        data = eval_resp.json()
        decision = data.get("decision")
        reason = data.get("reason")
        stats = data.get("stats", {})
        curr_state = data.get("rollout_state")
        canary_pct = data.get("canary_percentage", 0.0)

        print(f"\n{Colors.BOLD}{'='*72}")
        print(f"   DECISION ENGINE VERDICT: {Colors.RED}{decision}!{Colors.RESET}")
        print(f"   Reason: {reason}")
        print(f"   Candidate Error Rate: {Colors.RED}{stats.get('error_rate', 0):.1%}{Colors.RESET} (Threshold is 5.0%)")
        print(f"   Active Rollout State: {Colors.BOLD}{curr_state}{Colors.RESET} (Canary Split: {Colors.BOLD}{canary_pct:.0%}{Colors.RESET})")
        print(f"{'='*72}{Colors.RESET}\n")
    else:
        print(f"Evaluation error: {eval_resp.status_code}")

    print("👉 Check the UI Dashboard (http://localhost:3000) - Status shows ROLLED_BACK with 0% traffic.")
    print("👉 Check Grafana (http://localhost:3001) - Notice the error rate spike and rollback event.\n")


def main():
    print_banner()
    with httpx.Client() as client:
        try:
            client.get(f"{GATEWAY_URL}/health/live", timeout=2.0)
        except Exception:
            print(f"{Colors.YELLOW}[!] Gateway at {GATEWAY_URL} is not currently responding.{Colors.RESET}")
            print(f"{Colors.DIM}    Ensure docker compose is running before executing live demo.{Colors.RESET}\n")
            return

        try:
            client.post(ROLLOUT_RESET_URL, timeout=3.0)
        except Exception:
            pass

        pred_ids = run_phase_1(client)
        time.sleep(0.5)
        run_phase_2(client, pred_ids)
        time.sleep(0.5)
        run_phase_3(client)


if __name__ == "__main__":
    main()
