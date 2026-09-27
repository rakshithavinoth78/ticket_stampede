
# Ticket Stampede

A concurrent ticket-selling API built with Python, FastAPI, and SQLite. This project tests how a ticket seller handles simultaneous purchase requests while maintaining ticket allocation and request consistency.

## Features

- REST API for resetting a sale, buying tickets, and checking sale status.
- SQLite database for storing ticket purchases.
- Transaction-based ticket allocation to prevent overselling.
- Unique ticket numbers and request IDs.
- Idempotent purchase requests: replaying the same request ID returns the original ticket.
- Concurrent load-testing client with configurable requests and workers.
- Invariant checks for ticket allocation and sale consistency.

## Technologies

- Python
- FastAPI
- SQLite
- Uvicorn
- Requests
- ThreadPoolExecutor

## Project Files

- `app.py` — ticket-selling API.
- `load_test.py` — concurrent load-testing client.
- `requirements.txt` — Python dependencies.
- `load_test_results.png` — screenshot of the successful load test.
- `tickets.db` — local SQLite database, created when the application runs.

## Setup

### 1. Install Python

Install Python 3.10 or later.

### 2. Install dependencies

Open a terminal in the project folder and run:

```powershell
py -m pip install -r requirements.txt
```

### 3. Start the API

Run:

```powershell
py -m uvicorn app:app --reload
```

The API will be available at:

http://127.0.0.1:8000

Interactive API documentation:

http://127.0.0.1:8000/docs

Keep this terminal running while testing.

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/reset` | Reset the sale and set ticket capacity |
| POST | `/buy` | Purchase a ticket using a request ID |
| GET | `/status` | View capacity, sold tickets, remaining tickets, and purchases |

## Run the Load Test

Open a second terminal in the project folder and run:

```powershell
py load_test.py --tickets 100 --requests 200 --workers 50 --replays 50
```

The test resets the sale, sends concurrent purchase requests, replays request IDs, and checks the resulting ticket allocation.

## Observed Test Result

One local test run with 100 tickets, 200 regular requests, 50 replay requests, and 50 concurrent workers produced:

| Metric | Result |
|---|---:|
| Total requests | 250 |
| Successful responses | 132 |
| Sold-out responses | 118 |
| Errors | 0 |
| Elapsed time | 3.21 seconds |
| Throughput | 77.90 requests/second |
| Median latency | 211.34 ms |
| P99 latency | 2905.03 ms |
| Tickets sold | 100 |
| Tickets remaining | 0 |

All five invariant checks passed:
- Never oversell.
- No duplicate ticket numbers.
- Repeated request IDs return consistent results.
- Status count matches purchases.
- User mapping matches the sold count.

The 132 successful responses include successful replays; the final number of issued tickets was 100.

See `load_test_results.png` for the test output.

## Design and Limitations

## Naive vs. Fixed Implementation

To compare concurrency behavior, I tested an intentionally naive
implementation (`naive_app.py`) against the transaction-based
implementation (`app.py`).

Both tests used 100 tickets, 200 regular requests, 50 replay
requests, and 50 concurrent workers.

| Metric | Naive | Fixed |
|---|---:|---:|
| Total requests | 250 | 250 |
| Successful responses | 39 | 132 |
| Sold-out responses | 0 | 118 |
| Errors | 211 | 0 |
| Elapsed time | 1.54 s | 3.21 s |
| Throughput | 162.53 req/s | 77.90 req/s |
| Median latency | 248.64 ms | 211.34 ms |
| P99 latency | 546.53 ms | 2905.03 ms |
| Tickets sold | 32 | 100 |
| Tickets remaining | 68 | 0 |
| Overall result | FAIL | PASS |

The naive implementation experienced a large number of failed
requests under concurrency and did not complete the sale.
The load tester reported JSON parsing errors for failed responses.
The precise underlying server-side error has not yet been confirmed.

All five final-state invariant checks passed in both runs:
no overselling, no duplicate ticket numbers, consistent repeated
request IDs, matching status and purchase counts, and consistent
user-ticket mapping.

The fixed implementation completed the sale with no request
errors. Its successful response count includes idempotent
replays, so 132 successful responses represent 100 distinct
tickets issued plus successful repeated requests.

The results demonstrate a reliability difference under this
particular local workload. The naive implementation had higher
measured throughput, but failed to complete the sale. These
single-run measurements are not a general performance benchmark.

## Design and Limitations

The fixed API uses SQLite transactions to serialize ticket
allocation and database constraints to enforce unique ticket
numbers and request IDs.

SQLite's write serialization can limit throughput under
concurrency. The implementation has been tested locally, but
has not been verified across multiple independent seller
instances or in production.

The naive-versus-fixed comparison has been performed using the
same workload. Further work could investigate server-side errors,
latency under different concurrency levels, and datastore
failure and recovery behavior.
