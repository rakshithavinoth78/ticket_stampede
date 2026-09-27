
import requests
import time
import argparse
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict


def buy_ticket(url, user_id, request_id):
    start = time.perf_counter()

    try:
        response = requests.post(
            url + "/buy",
            json={
                "user_id": user_id,
                "request_id": request_id
            },
            timeout=60
        )

        latency = (time.perf_counter() - start) * 1000

        return {
            "request_id": request_id,
            "response": response.json(),
            "latency": latency,
            "error": None
        }

    except Exception as error:
        return {
            "request_id": request_id,
            "response": {},
            "latency": (time.perf_counter() - start) * 1000,
            "error": str(error)
        }


def run_load_test(url, tickets, requests_count, workers, replays):
    print("Resetting ticket sale...")

    reset = requests.post(
        url + "/reset",
        json={"ticket_count": tickets},
        timeout=30
    )
    reset.raise_for_status()

    # Create unique purchase requests.
    jobs = [
        (f"user-{i}", f"request-{i}")
        for i in range(requests_count)
    ]

    # Add repeated requests to test idempotency.
    replay_count = min(replays, requests_count)
    for i in range(replay_count):
        jobs.append(jobs[i])

    print(f"Sending {len(jobs)} requests...")
    print(f"Concurrent workers: {workers}")

    start = time.perf_counter()
    results = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(buy_ticket, url, user, request_id)
            for user, request_id in jobs
        ]

        for future in as_completed(futures):
            results.append(future.result())

    elapsed = time.perf_counter() - start

    # Get final server status.
    status_response = requests.get(url + "/status", timeout=30)
    status_response.raise_for_status()
    status = status_response.json()

    # Analyze responses.
    latencies = [r["latency"] for r in results]
    errors = [r for r in results if r["error"] is not None]

    successful = [
        r for r in results
        if r["response"].get("status") == "success"
    ]

    sold_out = [
        r for r in results
        if r["response"].get("status") == "sold_out"
    ]

    # Group responses by request ID.
    grouped = defaultdict(list)
    for result in results:
        if result["error"] is None:
            grouped[result["request_id"]].append(result["response"])

    # Check that repeated requests return the same outcome and ticket.
    idempotency_ok = True
    for responses in grouped.values():
        if len(responses) > 1:
            signatures = {
                (
                    r.get("status"),
                    r.get("ticket_number")
                )
                for r in responses
            }
            if len(signatures) != 1:
                idempotency_ok = False

    # Verify ticket invariants using final server status.
    purchases = status["purchases"]
    numbers = [p["ticket_number"] for p in purchases]
    sold = status["sold"]
    capacity = status["capacity"]

    no_overselling = sold <= capacity
    no_duplicate_tickets = len(numbers) == len(set(numbers))
    count_matches = sold == len(purchases)

    mapping_count = sum(
        len(ticket_list)
        for ticket_list in status["user_tickets"].values()
    )
    mapping_matches = mapping_count == sold

    # Performance measurements.
    rps = len(results) / elapsed if elapsed else 0
    median_latency = statistics.median(latencies) if latencies else 0
    p99_latency = (
        sorted(latencies)[min(
            len(latencies) - 1,
            int(0.99 * len(latencies))
        )]
        if latencies else 0
    )

    print("\n========== LOAD TEST RESULTS ==========")
    print(f"Total requests:       {len(results)}")
    print(f"Successful:           {len(successful)}")
    print(f"Sold out:             {len(sold_out)}")
    print(f"Errors:               {len(errors)}")
    print(f"Elapsed time:         {elapsed:.2f} seconds")
    print(f"Requests per second:  {rps:.2f}")
    print(f"Median latency:       {median_latency:.2f} ms")
    print(f"P99 latency:          {p99_latency:.2f} ms")

    print("\n========== INVARIANT CHECKS ==========")

    checks = {
        "Never oversell": no_overselling,
        "No duplicate ticket numbers": no_duplicate_tickets,
        "Repeated request IDs are consistent": idempotency_ok,
        "Status count matches purchases": count_matches,
        "User mapping matches sold count": mapping_matches
    }

    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {name}")

    print("\n========== FINAL STATUS ==========")
    print(f"Capacity:  {capacity}")
    print(f"Sold:      {sold}")
    print(f"Remaining: {status['remaining']}")

    if errors:
        print("\nSample errors:")
        for error in errors[:5]:
            print(error["error"])

    overall = all(checks.values()) and not errors
    print("\nOVERALL:", "PASS" if overall else "FAIL")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    parser.add_argument("--tickets", type=int, default=100)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--workers", type=int, default=50)
    parser.add_argument("--replays", type=int, default=50)

    args = parser.parse_args()

    if args.tickets < 0 or args.requests <= 0:
        parser.error("Tickets must be non-negative and requests positive")
    if args.workers <= 0 or args.replays < 0:
        parser.error("Workers must be positive and replays non-negative")

    try:
        run_load_test(
            args.url.rstrip("/"),
            args.tickets,
            args.requests,
            args.workers,
            args.replays
        )
    except requests.RequestException as error:
        print(f"Could not reach the server: {error}")