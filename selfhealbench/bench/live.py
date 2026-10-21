"""Approval-gated isolated benchmark backend. Imported only for explicit live mode.

No deployment or network creation capability. A separate approved daemon and
pre-deployed, labelled benchmark containers are mandatory.
"""
import json
import os
import datetime
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from selfhealbench.bench.agents import NoRedirect
from selfhealbench.bench.network_safety import review
from selfhealbench.bench.pilot import SERVICES, healthy, prepare_evidence, validate, verify
from selfhealbench.bench.scoring import summarize

APPROVALS = ("campus_allocation", "network", "ports", "isolated_context",
             "deployment", "fault_injection", "recovery")


def validate_approvals(config):
    if not isinstance(config, dict):
        raise ValueError("operator approval configuration required")
    if any(config.get("approvals", {}).get(key) is not True for key in APPROVALS):
        raise ValueError("all independent live approvals are required")
    if not isinstance(config.get("operator"), str) or not config["operator"].strip():
        raise ValueError("identified approving operator required")
    context = config.get("docker_context", "")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", context) or context == "default":
        raise ValueError("default/shared context is prohibited")
    endpoint = config.get("docker_endpoint", "")
    # Benchmark HTTP ports are host loopback: require an isolated local daemon.
    # A remote VM needs a separately reviewed runner location, not implicit forwarding.
    if not endpoint.startswith("unix:///") or endpoint in (
            "unix:///var/run/docker.sock", "unix:///run/docker.sock"):
        raise ValueError("approved separate local daemon socket required")
    if os.path.realpath(endpoint[len("unix://"):]) in ("/run/docker.sock", "/var/run/docker.sock"):
        raise ValueError("shared socket alias prohibited")
    shared_id = config.get("shared_daemon_id")
    if not isinstance(shared_id, str) or not shared_id.strip() or shared_id == config.get("daemon_id"):
        raise ValueError("independently observed distinct shared daemon identity required")
    if not config.get("daemon_id") or config.get("project") != "selfhealbench-pilot":
        raise ValueError("exact daemon identity and reserved benchmark project required")
    if config.get("network") != "selfhealbench-pilot-review":
        raise ValueError("reviewed dedicated benchmark network required")
    if config.get("bind_address") != "127.0.0.1":
        raise ValueError("approved loopback binding required")
    if config.get("ipv6") is not False or config.get("internal") is not True:
        raise ValueError("reviewed IPv4-only internal network required")
    result = review(config.get("candidate"), config.get("inventory"), config.get("gateway"))
    if result["status"] != "eligible_for_operator_review":
        raise ValueError("complete non-overlap inventory and campus allocation confirmation required")
    ports = config.get("host_ports", {})
    if set(ports) != SERVICES | {"prometheus", "loki", "tempo"}:
        raise ValueError("all seven exact approved port mappings required")
    if any(type(p) is not int or not 1024 <= p <= 65535 for p in ports.values()):
        raise ValueError("invalid approved host port")
    if len(set(ports.values())) != len(ports):
        raise ValueError("duplicate approved ports")
    scenarios = config.get("approved_scenarios")
    if (not isinstance(scenarios, list) or not scenarios
            or any(s not in {"SHB-%03d" % n for n in range(1, 11)} for s in scenarios)):
        raise ValueError("explicit approved scenario IDs required")
    return config


class IsolatedBackend:
    def __init__(self, config, token):
        self.config = validate_approvals(config)
        if not isinstance(token, str) or len(token) < 16 or token == "local-benchmark-only":
            raise ValueError("dedicated benchmark token of at least 16 characters required")
        self.token = token
        self.ids = {}

    def _docker(self, *args):
        command = ["docker", "--context", self.config["docker_context"], *args]
        # Explicit context, no shell, bounded read, no inherited DOCKER_HOST override.
        import os
        env = {k: v for k, v in os.environ.items() if k not in ("DOCKER_HOST", "DOCKER_CONTEXT")}
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            result = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=45,
                                    env=env, check=False)
            if result.returncode:
                raise RuntimeError("isolated Docker operation failed")
            stdout.seek(0)
            raw = stdout.read(65537)
            if args and args[0] == "logs":
                stderr.seek(0)
                raw += stderr.read(max(0, 65537 - len(raw)))
        if len(raw) > 65536:
            raise ValueError("Docker response exceeds 64 KiB")
        return raw.decode()

    def _environment(self):
        endpoint = self._docker("context", "inspect", self.config["docker_context"],
                                "--format", "{{.Endpoints.docker.Host}}").strip()
        if endpoint != self.config["docker_endpoint"]:
            raise ValueError("Docker context endpoint changed")
        if self._docker("info", "--format", "{{.ID}}").strip() != self.config["daemon_id"]:
            raise ValueError("Docker daemon identity changed")
        all_ids = set(self._docker("ps", "-a", "--no-trunc", "--format", "{{.ID}}").split())
        owned_ids = set(self._docker("ps", "-a", "--no-trunc", "--filter",
            "label=com.docker.compose.project=selfhealbench-pilot",
            "--format", "{{.ID}}").split())
        if all_ids - owned_ids:
            raise ValueError("daemon contains workloads outside the isolated benchmark")
        network = json.loads(self._docker("network", "inspect", self.config["network"], "--format",
            '{"ipam":{{json .IPAM.Config}},"internal":{{json .Internal}},'
            '"ipv6":{{json .EnableIPv6}},"driver":{{json .Driver}}}'))
        expected = self.config
        if (network["driver"] != "bridge" or network["internal"] is not True
                or network["ipv6"] is not False or len(network["ipam"]) != 1
                or network["ipam"][0].get("Subnet") != expected["candidate"]
                or network["ipam"][0].get("Gateway") != expected["gateway"]):
            raise ValueError("network differs from reviewed IPAM")

    def _container(self, service):
        if service not in SERVICES:
            raise ValueError("service outside benchmark allowlist")
        ids = self._docker("ps", "-a", "--no-trunc", "--filter",
            "label=com.docker.compose.project=selfhealbench-pilot", "--filter",
            "label=com.docker.compose.service=" + service, "--format", "{{.ID}}").split()
        if len(ids) != 1 or not re.fullmatch(r"[a-f0-9]{64}", ids[0]):
            raise ValueError("exactly one benchmark container required")
        value = json.loads(self._docker("inspect", ids[0], "--format",
            '{"labels":{{json .Config.Labels}},"networks":{{json .NetworkSettings.Networks}},'
            '"privileged":{{json .HostConfig.Privileged}},"mounts":{{json .Mounts}},'
            '"ports":{{json .HostConfig.PortBindings}}}'))
        labels = value["labels"]
        if (labels.get("org.selfhealbench.scope") != "isolated-pilot"
                or labels.get("com.docker.compose.project") != "selfhealbench-pilot"
                or labels.get("com.docker.compose.service") != service
                or set(value["networks"]) != {self.config["network"]}
                or value["privileged"]
                or any(m.get("Type") != "tmpfs" or m.get("Destination") != "/tmp"
                       for m in value["mounts"])):
            raise ValueError("container isolation or ownership check failed")
        ports = value["ports"]
        if ports != {"8080/tcp": [{"HostIp": "127.0.0.1",
                                   "HostPort": str(self.config["host_ports"][service])}]}:
            raise ValueError("container port mapping differs from approval")
        return ids[0]

    def assert_ready(self):
        self._environment()
        self.ids = {service: self._container(service) for service in SERVICES}

    def require_recovery_router(self):
        # The trusted Router only executes scale_service. Benchmark start/clear
        # actions have no authorized adapter; never inject a fault we cannot
        # safely route and reconcile. Approval booleans cannot override this.
        raise ValueError("benchmark recovery Router integration is unavailable")

    def authorize_scenarios(self, scenarios):
        if any(s["id"] not in self.config["approved_scenarios"] for s in scenarios):
            raise ValueError("requested campaign exceeds approved scenario scope")
        self.require_recovery_router()

    def _http(self, service, path, payload=None, timeout=3, text_response=False):
        port = self.config["host_ports"][service]
        url = "http://127.0.0.1:%d%s" % (port, path)
        data = None if payload is None else json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        if payload is not None:
            headers["X-Bench-Token"] = self.token
        request = urllib.request.Request(url, data=data, headers=headers)
        started = time.monotonic()
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
                code, raw = response.status, response.read(65537)
        except urllib.error.HTTPError as exc:
            code, raw = exc.code, exc.read(65537)
        except (OSError, TimeoutError):
            return {"status": 0, "body": {"error": "request unavailable"},
                    "latency_ms": (time.monotonic() - started) * 1000}
        if len(raw) > 65536:
            raise ValueError("telemetry response too large")
        return {"status": code, "body": raw.decode() if text_response else json.loads(raw),
                "latency_ms": (time.monotonic() - started) * 1000}

    def telemetry_ready(self):
        results = {service: self._http(service, path, text_response=True)["status"]
                   for service, path in (("prometheus", "/-/ready"),
                                         ("loki", "/ready"), ("tempo", "/ready"))}
        if any(code != 200 for code in results.values()):
            raise RuntimeError("observability readiness failed")
        return results

    def probe(self):
        return {service: self._http(service, "/work") for service in sorted(SERVICES)}

    def verify(self):
        return verify(self.probe)

    def evidence(self):
        self.assert_ready()
        logs = []
        for service in sorted(SERVICES):
            logs.append(self._docker("logs", "--tail", "60", self.ids[service]))
        queries = {"up": 'up{job="selfheal-services"}'}
        metrics = {}
        errors = []
        for key, query in queries.items():
            try:
                metrics[key] = self._http("prometheus", "/api/v1/query?" +
                                          urllib.parse.urlencode({"query": query}), timeout=4)["body"]
            except Exception:
                errors.append("prometheus:" + key)
        try:
            traces = self._http("tempo", "/api/search?limit=20", timeout=4)["body"]
        except Exception:
            errors.append("tempo:search")
            traces = {"unavailable": True}
        return {"evidence": prepare_evidence({"probes": self.probe(),
                "docker_logs": "\n".join(logs), "prometheus": metrics}, (self.token,)),
                "collection_errors": errors, "tempo_search": traces}

    def _control(self, service, mode, delay=0):
        self.assert_ready()
        result = self._http(service, "/__bench/fault", {"mode": mode, "delay_ms": delay})
        if result["status"] != 200:
            raise RuntimeError("benchmark control endpoint failed")

    def inject(self, scenario):
        self.require_recovery_router()
        self.assert_ready()
        service, fault = scenario["target"], scenario["fault"]
        if fault == "none" and service == "none":
            return
        if service not in SERVICES:
            raise ValueError("invalid injection target")
        if fault == "stop":
            self._docker("stop", "--time", "5", self.ids[service])
        elif fault in ("error", "latency"):
            delay = scenario.get("delay_ms", 0)
            if type(delay) is not int or not 0 <= delay <= 3000:
                raise ValueError("invalid latency injection")
            self._control(service, fault, delay)
        else:
            raise ValueError("unsupported injection")

    def execute(self, plan):
        validate(plan)
        if plan["action"] in ("no_op", "escalate"):
            return {"executed": False, "action": plan["action"]}
        self.require_recovery_router()
        self.assert_ready()
        if plan["action"] == "start_container":
            self._docker("start", self.ids[plan["target"]])
        elif plan["action"] == "clear_fault":
            self._control(plan["target"], "none")
        return {"executed": True, "action": plan["action"], "target": plan["target"]}

    def cleanup(self):
        self.require_recovery_router()
        # Cleanup is itself recovery and uses the same independent approval gate.
        self.assert_ready()
        for service in sorted(SERVICES):
            self._docker("start", self.ids[service])
        time.sleep(2)
        for service in sorted(SERVICES):
            self._control(service, "none")
        if not self.verify()["recovered"]:
            raise RuntimeError("cleanup did not restore baseline; stop campaign")


def run_live(scenarios, agent, backend, checkpoint=None):
    """No live operation occurs before backend approval and identity validation."""
    backend.authorize_scenarios(scenarios)
    backend.assert_ready()
    records = {}
    for scenario in scenarios:
        record = {"status": "preflight_failed", "baseline_verified": False,
                  "injection_ok": False, "recovery_verified": False}
        records[scenario["id"]] = record
        cleanup_required = False
        try:
            record["telemetry_readiness"] = backend.telemetry_ready()
            baseline = backend.verify()
            record["baseline"] = baseline
            if not baseline["recovered"]:
                record["status"] = "baseline_failed"
                break
            record["baseline_verified"] = True
            onset = time.monotonic()
            record["fault_onset_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            cleanup_required = scenario["fault"] != "none"
            backend.inject(scenario)
            record["injection_ok"] = True
            collected = backend.evidence()
            record["before"] = collected
            if set(collected["evidence"].get("probes", {})) != SERVICES:
                raise RuntimeError("complete fault observation required")
            record["fault_observed"] = not healthy(collected["evidence"].get("probes"))
            if scenario["fault"] != "none" and not record["fault_observed"]:
                raise RuntimeError("fault not observed")
            started = time.monotonic()
            try:
                plan = validate(agent.diagnose(collected["evidence"]))
            finally:
                record["planning_seconds"] = time.monotonic() - started
            record["plan"] = plan
            if collected.get("collection_errors"):
                raise ValueError("incomplete diagnostic telemetry")
            if plan["action"] in ("clear_fault", "start_container"):
                if scenario["fault"] == "none" or healthy(collected["evidence"]["probes"]):
                    raise ValueError("recovery on healthy control prohibited")
            cleanup_required = cleanup_required or plan["action"] in ("clear_fault", "start_container")
            record["execution"] = backend.execute(plan)
            verification = backend.verify()
            record["verification"] = verification
            record["recovery_verified"] = verification["recovered"]
            if verification["recovered"]:
                record["recovery_seconds"] = time.monotonic() - onset
                record["agent_to_recovery_seconds"] = time.monotonic() - started
            record["status"] = "ok"
        except TimeoutError:
            record["status"] = "timeout"
        except ValueError:
            record["status"] = "invalid_decision"
        except Exception:
            record["status"] = "failed"
        finally:
            if cleanup_required:
                try:
                    backend.cleanup()
                    record["cleanup"] = "verified"
                except Exception:
                    record["cleanup"] = "failed"
                    record["status"] = "cleanup_failed"
            if checkpoint:
                partial = summarize(scenarios, records, mode="live")
                partial["records"] = records
                checkpoint(partial)
        if record.get("cleanup") == "failed":
            break
    report = summarize(scenarios, records, mode="live")
    report["records"] = records
    return report
