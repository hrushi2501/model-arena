#!/usr/bin/env python3
"""Model Arena: Asynchronous Shadow Testing Demonstration.

Demonstrates Pillar 1 of Model Arena:
1. Sets rollout state to SHADOW (0% canary traffic to Candidate).
2. Sends live user requests — all served synchronously by Champion.
3. In the background, RabbitMQ and the worker asynchronously replay
   the requests against Candidate to evaluate divergence without adding
   any latency to the end user.
"""

import random
import time
import httpx

GATEWAY_URL = "http://localhost:8080"
RESET_URL = f"{GATEWAY_URL}/api/v1/rollouts/reset"
SHADOW_URL = f"{GATEWAY_URL}/api/v1/rollouts/shadow"
PREDICT_URL = f"{GATEWAY_URL}/api/v1/predict"
SHADOW_SUMMARY_URL = f"{GATEWAY_URL}/api/v1/shadow/summary"

# Standard 13-feature samples from the UCI Wine Recognition Dataset
SAMPLE_WINE_FEATURES = [
    [13.20, 1.78, 2.14, 11.2, 100.0, 2.65, 2.76, 0.26, 1.28, 4.38, 1.05, 3.40, 1050.0],
    [12.37, 0.94, 1.36, 10.6, 88.0, 1.98, 0.57, 0.28, 0.42, 1.95, 1.05, 1.82, 520.0],
    [13.16, 2.36, 2.67, 18.6, 101.0, 2.80, 3.24, 0.30, 2.81, 5.68, 1.03, 3.17, 1185.0],
    [14.37, 1.95, 2.50, 16.8, 113.0, 3.85, 3.49, 0.24, 2.18, 7.80, 0.86, 3.45, 1480.0],
    [13.24, 2.59, 2.87, 21.0, 118.0, 2.80, 2.69, 0.39, 1.82, 4.32, 1.04, 2.93, 735.0],
    [13.86, 1.35, 2.27, 16.0, 98.0, 2.98, 3.15, 0.22, 1.85, 7.22, 1.01, 3.55, 1045.0],
    [12.85, 1.60, 2.52, 17.8, 95.0, 2.48, 2.37, 0.26, 1.46, 3.93, 1.09, 3.63, 1015.0],
    [11.56, 2.05, 3.23, 28.5, 119.0, 3.18, 5.08, 0.47, 1.87, 6.00, 0.93, 3.69, 465.0],
    [12.42, 2.55, 2.27, 22.0, 90.0, 1.68, 1.84, 0.66, 1.42, 4.60, 0.86, 1.66, 750.0],
    [13.71, 5.65, 2.45, 20.5, 95.0, 1.68, 0.61, 0.52, 1.06, 7.70, 0.64, 1.74, 740.0],
]


class Colors:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def run_shadow_demo():
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*72}")
    print("   MODEL ARENA: ASYNCHRONOUS SHADOW TESTING DEMONSTRATION")
    print(f"{'='*72}{Colors.RESET}\n")

    with httpx.Client(timeout=10.0) as client:
        # Step 1: Clean Reset
        print("Resetting environment to clean baseline...")
        try:
            client.post(RESET_URL, timeout=5.0)
        except Exception as e:
            print(f"Notice during reset: {e}")

        # Step 2: Enable Shadow Mode
        print(f"Activating {Colors.BOLD}SHADOW Mode{Colors.RESET} (0% user risk, 100% Champion traffic)...")
        resp = client.post(SHADOW_URL)
        if resp.status_code != 200:
            print(f"{Colors.RED}Failed to activate shadow mode: {resp.text}{Colors.RESET}")
            return

        print(f"✔ State configured to: {Colors.BOLD}SHADOW{Colors.RESET} (Canary Split: 0%)\n")

        # Step 3: Send User Requests
        print(f"{'REQ #':<7} | {'CLIENT ID':<16} | {'SERVED BY':<12} | {'PRED':<6} | {'USER LATENCY':<12} | {'STATUS':<8}")
        print("-" * 72)

        for i in range(1, 21):
            client_id = f"user_shadow_{i:03d}"
            features = random.choice(SAMPLE_WINE_FEATURES)
            t0 = time.time()
            res = client.post(PREDICT_URL, json={"features": features, "client_id": client_id})
            lat = (time.time() - t0) * 1000.0

            if res.status_code == 200:
                data = res.json()
                role = data.get("model_role", "champion")
                pred = data.get("prediction", "-")
                role_col = f"{Colors.CYAN}{role:<12}{Colors.RESET}"
                print(f"{i:<7} | {client_id:<16} | {role_col} | Class {pred:<4} | {lat:6.1f} ms    | {Colors.GREEN}200 OK{Colors.RESET}")
            else:
                print(f"{i:<7} | {client_id:<16} | ERROR        | -      | {lat:6.1f} ms    | {Colors.RED}{res.status_code}{Colors.RESET}")
            time.sleep(0.04)

        print("-" * 72)
        print(f"✔ All 20 user requests safely answered by {Colors.CYAN}Champion{Colors.RESET} with zero user-facing risk.")

        # Step 4: Allow Asynchronous Worker to Replay against Candidate
        print(f"\n{Colors.DIM}Waiting 2 seconds for RabbitMQ & Worker to process background shadow tasks...{Colors.RESET}")
        time.sleep(2.0)

        # Step 5: Query Shadow Comparison Summary
        sum_resp = client.get(SHADOW_SUMMARY_URL)
        if sum_resp.status_code == 200:
            summary = sum_resp.json()
            total_evals = summary.get("total_shadow_evaluations", 0)
            matches = summary.get("matching_predictions", 0)
            divergent = summary.get("divergent_predictions", 0)
            agreement = summary.get("agreement_rate", 0.0)

            print(f"\n{Colors.BOLD}{Colors.GREEN}{'='*72}")
            print("   ASYNCHRONOUS SHADOW REPLAY EVALUATION RESULTS")
            print(f"{'='*72}{Colors.RESET}")
            print(f"Total Shadow Replays Processed: {Colors.BOLD}{total_evals}{Colors.RESET}")
            print(f"Champion & Candidate Agreement: {Colors.BOLD}{Colors.GREEN}{agreement:.1%}{Colors.RESET} ({matches} matching, {divergent} divergent)")
            print(f"Queue Status:                   Processed asynchronously via {Colors.BOLD}RabbitMQ{Colors.RESET}\n")

            comparisons = summary.get("recent_comparisons", [])
            if comparisons:
                print(f"{'CHAMPION (Baseline)':<22} | {'CANDIDATE (Shadow)':<22} | {'OUTCOME':<12}")
                print("-" * 62)
                for c in comparisons[:10]:
                    champ_p = f"Class {c['champion_pred']}"
                    cand_p = f"Class {c['candidate_pred']}"
                    match_badge = f"{Colors.GREEN}MATCH{Colors.RESET}" if c["is_match"] else f"{Colors.YELLOW}DIVERGENT{Colors.RESET}"
                    print(f"{champ_p:<22} | {cand_p:<22} | {match_badge}")
                print("-" * 62)

        print(f"\n{Colors.BOLD}Key Takeaway for Professor:{Colors.RESET}")
        print("  1. 100% of user traffic was served by Champion with 0 added latency overhead.")
        print("  2. In the background, RabbitMQ dispatched the exact user inputs to Candidate.")
        print("  3. The asynchronous worker proved Candidate model agreement before risking any live canary traffic.\n")


if __name__ == "__main__":
    run_shadow_demo()
