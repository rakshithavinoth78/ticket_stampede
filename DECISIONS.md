
# Design Decisions — Ticket Stampede

## 1. Architecture

I built the ticket-selling service using Python, FastAPI, and SQLite. The application provides three endpoints:

- `POST /reset` — resets the sale and configures ticket capacity.
- `POST /buy` — processes a ticket purchase using a request ID.
- `GET /status` — reports sale capacity, sold tickets, remaining tickets, and purchases.

SQLite stores the sale and purchase records. The purchase table uses a unique request ID and ticket number. The `/buy` endpoint uses a database transaction (`BEGIN IMMEDIATE`) to serialize competing writes and avoid allocating the same ticket to multiple requests.

Repeated requests with the same request ID return the previously allocated ticket, making purchase retries idempotent.

The load-testing client uses Python's `ThreadPoolExecutor` to send concurrent requests and replay request IDs. It checks ticket allocation invariants and reports throughput and latency.

## 2. Alternatives Considered

- **In-memory ticket counter:** Simple to implement, but state can be lost when the process restarts and is not shared across independent instances.
- **Application-level lock:** Could protect concurrent threads in one process, but would not coordinate separate application processes or machines.
- **Redis or a dedicated database:** Could support a more scalable distributed design, but adds infrastructure and setup complexity. SQLite was chosen for this local assignment implementation.

## 3. Trade-offs

SQLite transactions and database uniqueness constraints provide straightforward consistency safeguards without requiring an external database service.

However, SQLite serializes writes, which can limit throughput under heavy concurrent load. This implementation has only been tested locally; it does not establish correctness across multiple independent seller instances.

The load-test results are specific to the local environment and should not be treated as production performance guarantees.

## 4. Testing and Results

I ran the following local load test:

`py load_test.py --tickets 100 --requests 200 --workers 50 --replays 50`

Observed results:

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
| Final tickets sold | 100 |
| Remaining tickets | 0 |

All five reported invariant checks passed:

1. Never oversell.
2. No duplicate ticket numbers.
3. Repeated request IDs are consistent.
4. Status count matches purchases.
5. User mapping matches sold count.

The successful response count includes repeated requests that returned an already allocated ticket; it does not mean 132 distinct tickets were issued.

### Naive-versus-Fixed Comparison

I also ran the same workload against an intentionally naive
implementation (`naive_app.py`) without transaction-based
serialization in the purchase endpoint.

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
| Remaining tickets | 68 | 0 |
| Overall result | FAIL | PASS |

The naive implementation failed to complete the sale under
concurrent load, with 211 request errors and only 32 tickets
sold. The load tester reported JSON parsing errors for failed
responses; the exact server-side cause has not been verified.

All five final-state invariant checks passed in both runs.
Therefore, the observed naive failure was due to request
handling errors and incomplete sales, not demonstrated
overselling or duplicate ticket allocation.

The fixed implementation completed the sale with zero request
errors and all 100 tickets allocated. Its 132 successful
responses include successful idempotent replays.

The naive version's higher measured throughput does not mean
it performed better: it failed many requests and left 68
tickets unsold. These results are from local test runs and
should not be generalized into production performance claims. The required intentionally naive implementation and its failing load-test run have not yet been demonstrated. A comparison between the naive and transactional implementations is needed before submission.

## 5. Known Limitations

- SQLite write serialization may become a bottleneck at higher concurrency.
- The current test is local and does not verify behavior across multiple independent seller instances.
- Datastore outage and recovery behavior has not been tested.
-The exact server-side cause of the naive implementation's failed requests has not yet been confirmed.
- The observed latency and throughput depend on the local machine and test conditions.

## 6. Next Two Weeks

1. Investigate the naive implementation's server-side errors and improve error reporting in the load tester.
2. Repeat tests at different concurrency levels and compare reliability and latency.
3. Investigate latency under higher concurrency and identify database write contention.
4. Test behavior when the datastore is unavailable and after it recovers.
5. Explore a multi-instance design using database-level coordination or a shared datastore.
6. Improve automated tests and document reproducible setup and test commands.