#!/usr/bin/env python3
"""
Model Arena - Gradual Canary Rollout to 100% Promotion Demo
Demonstrates step-by-step traffic expansion:
  Step 1: 5% Canary
  Step 2: 15% Canary
  Step 3: 50% Canary
  Step 4: 100% Full Promotion (Candidate becomes the new Champion!)
"""

import os
import random
import time
import httpx

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")
PREDICT_URL = f"{GATEWAY_URL}/api/v1/predict"
FEEDBACK_URL = f"{GATEWAY_URL}/api/v1/feedback"
ROLLOUT_ADVANCE_URL = f"{GATEWAY_URL}/api/v1/rollouts/advance"
ROLLOUT_ACTIVE_URL = f"{GATEWAY_URL}/api/v1/rollouts/active"


class Colors:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


SAMPLE_WINE_FEATURES = [
    [14.23, 1.71, 2.43, 15.6, 127.0, 2.80, 3.06, 0.28, 2.29, 5.64, 1.04, 3.92, 1065.0],
    [13.20, 1.78, 2.14, 11.2, 100.0, 2.65, 2.76, 0.26, 1.28, 4.38, 1.05, 3.40, 1050.0],
    [13.16, 2.36, 2.67, 18.6, 101.0, 2.80, 3.24, 0.30, 2.81, 5.68, 1.03, 3.17, 1185.0],
    [12.37, 0.94, 1.36, 10.6, 88.0, 1.98, 0.57, 0.28, 0.42, 1.95, 1.05, 1.82, 520.0],
]


def send_batch(client: httpx.Client, count: int, step_name: str):
    champ_count = 0
    cand_count = 0
    for i in range(1, count + 1):
        client_id = f"client_{random.randint(100, 999)}_{i}"
        features = random.choice(SAMPLE_WINE_FEATURES)
        resp = client.post(PREDICT_URL, json={"features": features, "client_id": client_id}, timeout=3.0)
        if resp.status_code == 200:
            role = resp.json().get("model_role", "champion")
            if role == "candidate":
                cand_count += 1
            else:
                champ_count += 1
        time.sleep(0.04)

    cand_pct = (cand_count / count) * 100
    print(f"  Traffic Sample: Champion: {Colors.CYAN}{champ_count}{Colors.RESET} | Candidate: {Colors.YELLOW}{cand_count} ({cand_pct:.0f}%){Colors.RESET}")


def run_gradual_rollout():
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*68}")
    print("   MODEL ARENA: GRADUAL CANARY ROLLOUT (5% -> 100% PROMOTION)")
    print(f"{'='*68}{Colors.RESET}\n")

    steps = [
        (0.05, "Step 1: Initial Canary Probe (5%)"),
        (0.15, "Step 2: Small Scale Deployment (15%)"),
        (0.50, "Step 3: Majority Canary Split (50%)"),
        (1.00, "Step 4: Final Safe Promotion (100% Traffic to Candidate!)"),
    ]

    with httpx.Client() as client:
        for percentage, label in steps:
            print(f"{Colors.BOLD}{Colors.GREEN}{label}{Colors.RESET}")
            # Advance rollout
            resp = client.post(ROLLOUT_ADVANCE_URL, json={"canary_percentage": percentage}, timeout=3.0)
            if resp.status_code == 200:
                data = resp.json()
                print(f"  State: {Colors.BOLD}{data.get('state')}{Colors.RESET} | Canary Target: {Colors.BOLD}{percentage:.0%}{Colors.RESET}")
            
            # Send sample traffic batch to verify split
            send_batch(client, 20, label)
            print()
            time.sleep(1.0)

        # Final check
        active = client.get(ROLLOUT_ACTIVE_URL, timeout=3.0).json()
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*68}")
        print(f"   ROLLOUT COMPLETE: Model State is {Colors.GREEN}{active.get('state')}!{Colors.RESET}")
        print(f"   Candidate is now serving 100% of live production traffic!")
        print(f"{'='*68}{Colors.RESET}\n")


if __name__ == "__main__":
    run_gradual_rollout()
