"""Pure CIDR review. This module cannot create or attach a Docker network."""
import argparse
import ipaddress
import json
from pathlib import Path

REQUIRED_INVENTORIES = ("host", "routes", "rules", "docker", "vpn")
OCCUPIED_FIELDS = ("host_cidrs", "route_cidrs", "docker_cidrs",
                   "vpn_cidrs", "institutional_cidrs")


def review(candidate, inventory, gateway=None):
    result = {"candidate": candidate, "status": "rejected", "reasons": [],
              "overlaps": [], "provisioning_allowed": False}
    try:
        network = ipaddress.ip_network(candidate, strict=True)
        if network.version != 4 or not network.subnet_of(ipaddress.ip_network("10.0.0.0/8")):
            raise ValueError("candidate must be inside private 10.0.0.0/8")
        if network.prefixlen != 26:
            raise ValueError("approved sizing proposal requires exactly /26")
        if gateway is not None:
            address = ipaddress.ip_address(gateway)
            if address not in network or address in (network.network_address, network.broadcast_address):
                raise ValueError("gateway must be a usable address in candidate")
    except (ValueError, TypeError) as exc:
        result["reasons"].append(str(exc))
        return result
    result.update(total_addresses=network.num_addresses,
                  conventional_usable_addresses=network.num_addresses - 2,
                  container_capacity_after_gateway=network.num_addresses - 3,
                  gateway=gateway)
    if not isinstance(inventory, dict):
        result.update(status="blocked", reasons=["network inventory missing"])
        return result
    complete = inventory.get("complete", {})
    if not isinstance(complete, dict):
        complete = {}
    missing = [name for name in REQUIRED_INVENTORIES if complete.get(name) is not True]
    for field in OCCUPIED_FIELDS:
        values = inventory.get(field)
        if not isinstance(values, list):
            missing.append(field)
            continue
        for value in values:
            try:
                occupied = ipaddress.ip_network(value, strict=True)
            except (ValueError, TypeError):
                result["reasons"].append("invalid inventory CIDR in " + field)
                return result
            if occupied.version == 4 and network.overlaps(occupied):
                result["overlaps"].append({"source": field, "cidr": str(occupied)})
    if result["overlaps"]:
        result["reasons"].append("candidate overlaps supplied occupied ranges")
        return result
    result["status"] = "blocked"
    if missing:
        result["reasons"].append("incomplete inventory: " + ", ".join(missing))
    campus = inventory.get("campus_allocation", {})
    if not isinstance(campus, dict):
        campus = {}
    if not (campus.get("confirmed") is True and campus.get("candidate") == str(network)
            and isinstance(campus.get("authority"), str) and campus["authority"].strip()):
        result["reasons"].append("candidate-specific campus/VPN allocation confirmation missing")
    if not result["reasons"]:
        result["status"] = "eligible_for_operator_review"
    # Even complete local evidence and campus confirmation are not deployment approval.
    result["operator_network_approval_required"] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--gateway")
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = review(args.candidate, json.loads(args.inventory.read_text()), args.gateway)
    text = json.dumps(result, indent=2) + "\n"
    if args.out:
        args.out.write_text(text)
    print(text, end="")
    return 0 if result["status"] == "eligible_for_operator_review" else 2


if __name__ == "__main__":
    raise SystemExit(main())
