"""Read-only host/Docker inventory. Writes only the requested local JSON report."""
import argparse
import datetime
import ipaddress
import json
import subprocess
from pathlib import Path


def collect():
    commands = {
        "hostname": ["hostname"],
        "addresses": ["ip", "-j", "address", "show"],
        "routes": ["ip", "-j", "-4", "route", "show", "table", "all"],
        "rules": ["ip", "-j", "-4", "rule", "show"],
        "ipv6_routes": ["ip", "-j", "-6", "route", "show", "table", "all"],
        "listeners": ["ss", "-ltn"],
        "context": ["docker", "context", "show"],
        "contexts": ["docker", "context", "ls", "--format", "{{json .}}"],
        "daemon": ["docker", "info", "--format", '{"name":{{json .Name}},"id":{{json .ID}}}'],
        "networks": ["docker", "network", "ls", "--format", "{{.Name}}"],
        "containers": ["docker", "ps", "--format",
                       '{"name":{{json .Names}},"status":{{json .Status}},"networks":{{json .Networks}},"ports":{{json .Ports}}}'],
    }
    observed, errors = {}, {}
    for key, command in commands.items():
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=True)
            observed[key] = result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            errors[key] = "read-only discovery failed"
    networks = []
    for name in observed.get("networks", "").splitlines():
        try:
            raw = subprocess.check_output(
                ["docker", "network", "inspect", name, "--format",
                 '{"name":{{json .Name}},"driver":{{json .Driver}},"scope":{{json .Scope}},'
                 '"internal":{{json .Internal}},"ipv6":{{json .EnableIPv6}},"ipam":{{json .IPAM}}}'],
                timeout=20, text=True)
            networks.append(json.loads(raw))
        except (OSError, subprocess.SubprocessError, ValueError):
            errors["network:" + name] = "network IPAM inspection failed"
    addresses = json.loads(observed.get("addresses", "[]"))
    routes = json.loads(observed.get("routes", "[]"))
    host_cidrs = sorted({str(ipaddress.ip_interface(
        address["local"] + "/" + str(address["prefixlen"])).network)
        for interface in addresses for address in interface.get("addr_info", [])
        if address["family"] == "inet"})
    # A default route is reachability, not proof of allocation of all IPv4.
    # Preserve it in raw observations, exclude only it from occupied ranges.
    route_cidrs = sorted({str(ipaddress.ip_network(route["dst"], strict=False))
                          for route in routes if route.get("dst") not in (None, "default", "0.0.0.0/0")})
    docker_cidrs = sorted({item["Subnet"] for network in networks
                          for item in network["ipam"].get("Config") or [] if item.get("Subnet")})
    container_rows = [json.loads(row) for row in observed.get("containers", "").splitlines()]
    contexts = [json.loads(row) for row in observed.get("contexts", "").splitlines()]
    shared_services = {"broker", "litellm", "onecli", "onecli-postgres-1"}
    shared = any(row["name"] in shared_services or row["name"].startswith("infer-")
                 for row in container_rows)
    return {
        "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "host": observed.get("hostname"), "docker_context": observed.get("context"),
        "daemon": json.loads(observed.get("daemon", "{}")),
        "shared_daemon": shared,
        "other_contexts_observed": [row["Name"] for row in contexts
                                    if row["Name"] != observed.get("context")],
        "isolated_context_available": None,
        "complete": {"host": "addresses" not in errors, "routes": "routes" not in errors,
                     "rules": "rules" not in errors,
                     "docker": "networks" not in errors and not any(k.startswith("network:") for k in errors),
                     "vpn": "addresses" not in errors and "routes" not in errors and "rules" not in errors},
        "host_cidrs": host_cidrs, "route_cidrs": route_cidrs,
        "docker_cidrs": docker_cidrs, "vpn_cidrs": [], "institutional_cidrs": [],
        "campus_allocation": {"confirmed": False, "authority": None, "candidate": None},
        "scope_note": "VPN completeness covers visible local interfaces/routes only. Campus/VPN allocations remain unconfirmed.",
        "default_route_note": "Default routes retained in observations; not treated as allocated CIDRs.",
        "network_details": networks, "observations": observed, "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = collect()
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("host", "docker_context", "daemon", "errors")}, indent=2))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
