# NanoClaw audit lock recovery

Status: offline operational procedure; not an automated cleanup mechanism.

The audit writer uses an exclusive `.lock` file. A process crash may
leave this file behind. Writers wait up to 10 seconds and then fail
closed with `audit_lock_timeout`.

## Recovery procedure

1. Stop or quiesce every trusted writer using this ledger.
2. Confirm no writer process remains active and no other host or
   process can access the ledger concurrently.
3. Preserve a copy of the ledger and lock metadata for investigation.
4. Verify the ledger hash chain and inspect the reason for the crash.
5. Only after exclusive ownership is established, have an authorized
   operator remove the specific stale `.lock` file.
6. Re-run audit verification and the offline regression suite before
   resuming writes.

Never automatically remove a lock based only on its age or PID.
Never delete or truncate a corrupted production audit ledger.
Do not restart live services without infrastructure-owner approval.
