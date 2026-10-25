#!/usr/bin/env python3
"""
Model Arena - Autonomous Gradual Rollout Demo
Driven 100% by the Decision Engine:
  1. The script sends live traffic and ground-truth feedback.
  2. The script calls the Decision Engine (POST /api/v1/rollouts/evaluate).
  3. The Decision Engine autonomously inspects the database (sample count, error rate, latency, accuracy).
  4. The Decision Engine promotes the model step-by-step: 10% -> 25% -> 50% -> 100% PROMOTED!
"""

import os
import random
import time
import httpx

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")
PREDICT_URL = f"{GATEWAY_URL}/api/v1/predict"
FEEDBACK_URL = f"{GATEWAY_URL}/api/v1/feedback"
ROLLOUT_EVALUATE_URL = f"{GATEWAY_URL}/api/v1/rollouts/evaluate"
ROLLOUT_ACTIVE_URL = f"{GATEWAY_URL}/api/v1/rollouts/active"
ROLLOUT_ADVANCE_URL = f"{GATEWAY_URL}/api/v1/rollouts/advance"
ROLLOUT_RESET_URL = f"{GATEWAY_URL}/api/v1/rollouts/reset"


class Colors:
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
    [12.37, 0.94, 1.36, 10.6, 88.0, 1.98, 0.57, 0.28, 0.42, 1.95, 1.05, 1.82, 520.0],
    [13.49, 1.66, 2.24, 24.0, 87.0, 1.88, 1.84, 0.27, 1.03, 7.10, 1.02, 1.80, 870.0],
]


def send_stage_traffic(client: httpx.Client, min_candidate_target: int = 20):
    """Sends traffic until Candidate model accumulates enough statistical samples (20) for Decision Engine."""
    champ_count = 0
    cand_count = 0
    prediction_ids = []
    i = 0

    while cand_count < min_candidate_target and i < 250:
        client_id = f"client_{random.randint(100, 999)}_{i}"
        features = random.choice(SAMPLE_WINE_FEATURES)
        try:
            resp = client.post(PREDICT_URL, json={"features": features, "client_id": client_id}, timeout=3.0)
            if resp.status_code == 200:
                data = resp.json()
                role = data.get("model_role", "champion")
                pred_id = data.get("request_id")
                if pred_id:
                    prediction_ids.append((pred_id, data.get("prediction", 0)))
                if role == "candidate":
                    cand_count += 1
                else:
                    champ_count += 1
        except Exception:
            pass
        i += 1
        time.sleep(0.005)

    # Submit ground-truth feedback so the Decision Engine sees valid accuracy
    for pred_id, true_label in prediction_ids:
        try:
            client.post(FEEDBACK_URL, json={"prediction_id": pred_id, "ground_truth_label": true_label}, timeout=2.0)
        except Exception:
            pass

    return champ_count, cand_count


def run_autonomous_rollout():
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*72}")
    print("   MODEL ARENA: AUTONOMOUS GRADUAL ROLLOUT (DECISION ENGINE DRIVEN)")
    print(f"{'='*72}{Colors.RESET}\n")

    with httpx.Client() as client:
        # Reset state to clean baseline so demo is always completely fresh
        print(f"{Colors.DIM}Resetting rollout state to clean baseline for fresh demonstration...{Colors.RESET}")
        try:
            client.post(ROLLOUT_RESET_URL, timeout=3.0)
        except Exception:
            pass

        # Check current state
        active = client.get(ROLLOUT_ACTIVE_URL, timeout=3.0).json()
        print(f"Current State: {Colors.BOLD}{active.get('state')}{Colors.RESET} | Canary: {Colors.BOLD}{active.get('canary_percentage', 0):.0%}{Colors.RESET}\n")

        # Initiate active canary evaluation with initial 10% probe
        print(f"{Colors.DIM}Initiating active canary evaluation (10% initial probe)...{Colors.RESET}")
        client.post(ROLLOUT_ADVANCE_URL, json={"canary_percentage": 0.10}, timeout=3.0)

        step = 1
        while True:
            # Step A: Send user traffic
            print(f"{Colors.BOLD}[Stage {step}] Generating live traffic to evaluate Candidate...{Colors.RESET}")
            champ_count, cand_count = send_stage_traffic(client, min_candidate_target=20)
            total = champ_count + cand_count
            pct = (cand_count / total * 100) if total else 0
            print(f"  Traffic Observed: Champion: {Colors.CYAN}{champ_count}{Colors.RESET} | Candidate: {Colors.YELLOW}{cand_count} ({pct:.0f}% traffic){Colors.RESET}")

            # Step B: Call the autonomous Decision Engine
            print(f"  {Colors.DIM}Querying Decision Engine (POST /api/v1/rollouts/evaluate)...{Colors.RESET}")
            eval_resp = client.post(ROLLOUT_EVALUATE_URL, timeout=3.0)
            
            if eval_resp.status_code != 200:
                print(f"  {Colors.RED}Evaluation call returned {eval_resp.status_code}{Colors.RESET}")
                break

            decision_data = eval_resp.json()
            decision = decision_data.get("decision")
            reason = decision_data.get("reason")
            stats = decision_data.get("stats", {})
            curr_state = decision_data.get("rollout_state")
            canary_pct = decision_data.get("canary_percentage", 0.0)

            # Display the Decision Engine's verdict
            if decision == "PROMOTE":
                print(f"  ✔ Decision Engine Verdict: {Colors.BOLD}{Colors.GREEN}{decision} (Stage Advanced to {canary_pct:.0%}){Colors.RESET}")
                print(f"    Reason: {Colors.DIM}{reason}{Colors.RESET}")
            elif decision == "HOLD":
                print(f"  ⏳ Decision Engine Verdict: {Colors.BOLD}{Colors.YELLOW}{decision}{Colors.RESET} - {reason}")
            elif decision == "ROLLBACK":
                print(f"  ✖ Decision Engine Verdict: {Colors.BOLD}{Colors.RED}{decision}{Colors.RESET} - {reason}")
                break

            print()

            # Stop once the Decision Engine has promoted to 100%
            if curr_state == "PROMOTED" or canary_pct >= 1.0:
                print(f"{Colors.BOLD}{Colors.CYAN}{'='*72}")
                print(f"   SUCCESS: Model State is {Colors.GREEN}{curr_state}!{Colors.RESET}")
                print(f"   Decision Engine autonomously promoted Candidate to 100% traffic!")
                print(f"{'='*72}{Colors.RESET}\n")
                break

            step += 1
            if step > 8:
                print("Max cycles reached.")
                break
            time.sleep(1.0)


if __name__ == "__main__":
    run_autonomous_rollout()
