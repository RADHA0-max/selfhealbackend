# Docker and network safety report

**NETWORK_PREFLIGHT_BLOCKED** — no network creation, Docker mutation, or fault injection was performed.

Read-only collection succeeded after sandbox access was permitted. The sanitized capture is `docs/verification/network-inventory.json`; it retains the machine UTC timestamp. User-facing audit date is 21 October 2026 (Asia/Kolkata client date); execution-host wall-clock dates are not used as client dates.

## Fresh observations

| Check | Evidence | Result |
|---|---|---|
| Context | `docker context show` and context list | `default`; no alternate context observed |
| Daemon | `docker info` restricted to name/ID | Host `dada`, shared workload daemon; ID recorded in inventory |
| Host addresses | `ip -j address show` | 127.0.0.0/8, 172.16.40.0/22, 172.17.0.0/16, 172.20.0.0/16, 10.250.10.0/26, 10.250.20.0/26 |
| Routes | IPv4/IPv6 all-table route reads and IPv4 policy rules | Local route inventory collected; specific /32 routes preserved in JSON |
| Docker IPAM | Network list and restricted network inspect | 172.17.0.0/16, 172.20.0.0/16, 10.250.10.0/26, 10.250.20.0/26 already occupied |
| VPN/tunnels | Visible interfaces/routes | Only local visibility; does not establish remote or future VPN allocations |
| Campus allocation | No authoritative confirmation supplied | BLOCK |
| Isolation | No approved separate daemon/socket/context | BLOCK |
| Exact operation approval | No live scenario/deployment authorization | BLOCK |

Default routes are retained as reachability evidence and are not treated as allocating all IPv4. No proposed new network was selected. Existing deployment files mention `10.250.30.0/26`; that historical candidate is **not approved or proven safe** and was not used to create anything. It is CIDR-aligned with 64 total addresses, 62 conventional usable addresses, and 61 after a gateway; `10.250.30.1` is syntactically usable. Arithmetic does not establish allocation, routability, or permission. Campus/VPN conflicts remain unresolved.

## Required evidence before a future review

1. Authoritative campus/VPN allocation approval for an exact candidate and gateway, including nonlocal ranges; refreshed local inventory and all relevant routing rules/tables.
2. Approved isolated environment identity, context endpoint and canonical socket; independently observed shared daemon ID and distinct candidate ID. Prove a socket/context alias cannot reach the shared daemon. An empty daemon or benchmark-only names alone are insufficient.
3. Exact resource ownership, all workload inventory, network membership/IPAM, port reservations, capability/mount restrictions and readiness for dedicated targets and telemetry services.
4. Named approval for exact operations/scenarios, expiry/scope and reviewed cleanup/rollback. Resolve the missing trusted Router recovery adapter before injection.

`network_safety.review` never grants execution: invalid/misaligned CIDR, overlaps or invalid gateway reject; missing inventories or campus confirmation block; a complete nonoverlapping candidate is only `eligible_for_operator_review`, with `provisioning_allowed=false`. `live.validate_approvals` separately rejects default context, canonical shared socket aliases, missing shared identity and matching daemon IDs. Live mutations remain disabled at the missing Router boundary.

The root Compose proxy grants POST/container/service access to `/var/run/docker.sock`; `:ro` does not make Docker API calls read-only. Do not deploy it as an isolation mechanism. This audit made no changes to that shared infrastructure.
