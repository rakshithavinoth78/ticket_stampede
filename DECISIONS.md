
# Design Decisions — Ticket Stampede

## 1. Architecture

I built the ticket-selling service using Python, FastAPI, and SQLite. The application provides three endpoints:

- `POST /reset` — resets the sale and configures ticket capacity.
- `POST /buy` — processes a ticket purchase using a user ID and request ID.
- `GET /status` — reports sale capacity, sold tickets, remaining tickets, and purchases.

SQLite stores the sale and purchase records. The purchases table uses a unique ticket number and a unique request ID to prevent duplicate allocations and support idempotency.

The fixed `/buy` endpoint uses `BEGIN IMMEDIATE` to acquire a write transaction before checking availability and allocating a ticket. This serializes competing database writes, preventing concurrent requests from allocating the same next ticket.

Repeated requests with the same request ID return the previously allocated ticket, allowing clients to retry safely.

The load-testing client uses Python's `ThreadPoolExecutor` to send concurrent requests, replay request IDs, verify ticket allocation invariants, and measure throughput and latency.

## 2. Alternatives Considered

- **In-memory ticket counter:** Simple to implement, but state can be lost when the process restarts and is not shared across independent instances.
- **Application-level lock:** Can protect concurrent threads within one process, but does not coordinate separate application processes or machines.
- **Redis or a dedicated database:** Could support a more scalable distributed design, but adds infrastructure and setup complexity. SQLite was chosen for this local assignment implementation.

## 3. Trade-offs

SQLite transactions and database uniqueness constraints provide consistency safeguards without requiring an external database service.

The main trade-off is write serialization: SQLite can become a throughput bottleneck under heavy concurrent load. The fixed implementation prioritizes reliable ticket allocation over maximum request throughput.

The implementation has been tested locally. The results do not establish correctness across multiple independent seller instances or provide production performance guarantees.

## 4. Testing and Results

I ran the following local load test against the fixed implementation:

```powershell
py load_test.py --tickets 100 --requests 200 --workers 50 --replays 50
```

### Fixed implementation

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
| Overall result | PASS |

All five reported invariant checks passed:

1. Never oversell.
2. No duplicate ticket numbers.
3. Repeated request IDs return consistent results.
4. Status count matches purchases.
5. User mapping matches the sold count.

The 132 successful responses include successful idempotent replays. The final number of distinct tickets issued was 100.

### Naive-versus-fixed comparison

I also tested an intentionally naive implementation (`naive_app.py`) using the same workload. The naive implementation does not use transaction-based serialization in its purchase endpoint.

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

The naive implementation failed to complete the sale under concurrent load, with 211 request errors and only 32 tickets sold. The load tester reported JSON parsing errors for failed responses; the exact underlying server-side cause has not been confirmed.

All five final-state invariant checks passed in both runs. The observed naive failure was due to request errors and an incomplete sale, not demonstrated overselling or duplicate ticket allocation.

The fixed implementation completed the sale with zero request errors and all 100 tickets allocated. Its 132 successful responses include successful idempotent replays.

Although the naive implementation showed higher measured throughput, it failed many requests and left 68 tickets unsold. The fixed implementation had higher P99 latency in this run, illustrating the performance cost associated with serialized writes. These are individual local test results, not general performance benchmarks.

## 5. Known Limitations

- SQLite write serialization may limit throughput at higher concurrency.
- The current tests are local and do not verify behavior across multiple independent seller instances.
- Datastore outage and recovery behavior has not been tested.
- The precise server-side cause of the naive implementation's failed requests has not been confirmed.
- Latency and throughput depend on the local machine and test conditions.

## 6. Next Two Weeks

1. Investigate the naive implementation's server-side errors and improve error reporting in the load tester.
2. Repeat tests at different concurrency levels and compare reliability and latency.
3. Investigate database write contention and latency under higher concurrency.
4. Test behavior when the datastore is unavailable and after it recovers.
5. Explore a multi-instance design using database-level coordination or a shared datastore.
6. Improve automated tests and document reproducible setup and test commands.