# Broker journal and offline review notes

Implemented in `broker/durability.py` and `broker/main.py`; tested only with temporary queues and mocked HTTP/model functions. No running broker or live RPC directory was accessed or migrated.

## Ordering and failure behavior

1. Open broker-private state and acquire nonblocking exclusive flock for the entire batch, including HTTP await. A second broker returns without reading/processing the queue. The batch list is bounded by max_queue_size; this is not a producer disk quota.
2. Atomically move a request entry into a private pending name, fsync directories, open O_NOFOLLOW/O_NONBLOCK, require a regular single-link inode, bound bytes, detect metadata changes during read, then parse/correlate the ID. Symlinks, FIFOs, directories, hardlinks and oversized files never reach inference. Producers holding an already-open descriptor are an additional reason to require trusted queue publication/ownership; the bounded snapshot is the input that is hashed and processed.
3. In a FULL-synchronous SQLite transaction persist ID + SHA-256 payload digest + CLAIMED before calling the backend. Same ID/different bytes rejects, including JSON whitespace differences. No lease expires a claim into permission to retry.
4. Completed backend response is persisted as COMPLETE before output publication. Temp response bytes are fsynced, linked atomically with no overwrite and output directory synced. A consumed/deleted response can be republished from the cache with no model call. Different existing output is never overwritten.
5. Failure before completion leaves CLAIMED/UNCERTAIN; a repeated request receives a correlated explicit uncertainty error and does not execute. Cancellation/process death releases OS lock and budget concurrency slot where possible, but never the persistent ID. Existing hourly budget accounting is still in memory.

## Deployment prerequisites and deliberate limits

`RPC_STATE_DIR` is optional; default is `<rpc_failed_dir>/.broker-state`. It must be persistent, owned by the broker UID, mode 0700, and inaccessible to the producer. Database is 0600. Parent directories must be trusted and cannot be replaceable by an untrusted producer. All broker instances for a queue must use the same state directory. The implementation assumes local Linux filesystem locking/rename/fsync semantics; shared/network filesystems have not been validated. State-file corruption or unsafe directory permissions fail closed.

The journal holds response bodies for replay but not prompts; confidentiality of upstream responses therefore depends on protected storage as well as existing prompt redaction. No journal bodies are printed or logged. Do not discard/restore an old journal to retry work: this can invalidate replay protection. Retention/archival with persistent tombstones, producer admission/expiry, protocol cancellation, authenticated target attribution and durable hourly budgets remain outstanding.

A crash after taking a pending file but before inserting its claim leaves an orphan private file. It is never automatically resubmitted. A crash after CLAIMED but before/after HTTP has an uncertain outcome; no generic exactly-once assertion is possible across the filesystem/SQLite/HTTP boundary. Offline regression kills a child process immediately after a fake model call, then proves the next broker refuses another call. A future operator-only reconciliation tool must classify orphans/uncertain IDs without deleting replay protection or fabricating success. No such tool or automatic resume was introduced.

Review decision: favor safety over availability. Disk-full, malformed state, corrupted ledger and publication failure may stop/reject work. This change is not permission to restart the production broker; rollout requires protected persistent state and an explicitly reviewed queue cutover.
