#!/usr/bin/env python3
# ruff: noqa: S603
"""Serviciul intern de livrare (F1.8). Doar biblioteca standard; rulează pe VPS, fără port publicat.

Ciclu: staging urmărește registrul (eticheta AMA_DEPLOYER_STAGING_TAG); producția preia doar cererile de
promovare/revenire făcute din panou (GET /intern/livrare/cerere). Contractul cu aplicația: docs/specs/F1.8.md.

Strategia: două „sloturi” (blue/green) pe stivă. Se pornește slotul liber cu imaginea nouă, se verifică,
apoi se oprește slotul vechi (rămâne oprit, cu imaginea lui, pentru revenire rapidă). Proxy-ul trimite
cererile doar către slotul sănătos (verificări active pe /readyz).

Comenzi: run | once | status | deploy <staging|production> <imagine@sha256:…> | rollback <staging|production>
Toată logica de decizie e în funcții pure, testate în tests/unit/test_infra_deployer.py; efectele
(docker, registru, HTTP către aplicație) trec prin clasele de la sfârșit, înlocuibile în teste.
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

SLOTS = ("blue", "green")
DIGEST_REF = re.compile(r"^(?P<repo>[a-z0-9][a-z0-9._/\-]*)@sha256:(?P<digest>[0-9a-f]{64})$")
MAX_PENDING_REPORTS = 50
MAX_DONE_REQUESTS = 30
RETRY_FAILED_AFTER_S = 600
MAX_STAGING_ATTEMPTS = 3


class DeployError(Exception):
    """Un pas al livrării a eșuat; mesajul ajunge (scurt) în raport."""


# ---------------------------------------------------------------------------------------------------------
# Configurare
# ---------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Stack:
    name: str  # staging | production
    project: str  # numele proiectului Compose
    files: tuple[str, ...]  # fișiere Compose, relativ la infra/compose
    env_file: str  # fișier de mediu din AMA_ENV_DIR
    alias: str  # prefixul alias-urilor din rețeaua ama-edge: <alias>-blue, <alias>-green


STACKS = {
    "staging": Stack("staging", "ama-staging", ("base.yml", "staging.yml"), "staging.env", "staging"),
    "production": Stack("production", "ama-prod", ("base.yml", "production.yml"), "production.env", "prod"),
}


@dataclass(frozen=True)
class Config:
    repo: str  # ex. ghcr.io/proprietar/ama
    staging_tag: str = "main"
    infra_dir: str = "/srv/ama/repo/infra"
    env_dir: str = "/srv/ama/env"
    state_file: str = "/var/lib/ama-deployer/stare.json"
    panel_token: str = ""
    interval_s: int = 60
    ready_timeout_s: int = 90
    stable_checks: int = 3
    stable_interval_s: float = 5.0
    app_port: int = 8000
    registry_user: str = ""
    registry_token: str = ""

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Config:
        if not env.get("AMA_DEPLOYER_REPO"):
            raise DeployError("AMA_DEPLOYER_REPO lipsește")
        if len(env.get("AMA_DEPLOY_TOKEN", "")) < 32:
            raise DeployError("AMA_DEPLOY_TOKEN lipsește sau are sub 32 de caractere")
        return cls(
            repo=env["AMA_DEPLOYER_REPO"].lower(),
            staging_tag=env.get("AMA_DEPLOYER_STAGING_TAG", "main"),
            infra_dir=env.get("AMA_INFRA_DIR", cls.infra_dir),
            env_dir=env.get("AMA_ENV_DIR", cls.env_dir),
            state_file=env.get("AMA_DEPLOYER_STATE_FILE", cls.state_file),
            panel_token=env["AMA_DEPLOY_TOKEN"],
            interval_s=int(env.get("AMA_DEPLOYER_INTERVAL_S", "60")),
            ready_timeout_s=int(env.get("AMA_DEPLOYER_READY_TIMEOUT_S", "90")),
            registry_user=env.get("AMA_DEPLOYER_REGISTRY_USER", ""),
            registry_token=env.get("AMA_DEPLOYER_REGISTRY_TOKEN", ""),
        )


# ---------------------------------------------------------------------------------------------------------
# Logică pură
# ---------------------------------------------------------------------------------------------------------


def parse_image_ref(ref: str) -> tuple[str, str] | None:
    """`repo@sha256:…` -> (repo, digest); None dacă forma e alta (doar amprentă)."""
    m = DIGEST_REF.match(ref or "")
    return (m["repo"], "sha256:" + m["digest"]) if m else None


def other_slot(active: str | None) -> str:
    return "green" if active == "blue" else "blue"


def empty_stack_state() -> dict[str, Any]:
    return {
        "active": None,
        "previous": None,
        "slots": {"blue": None, "green": None},
        "failed": None,
        "done": [],
    }


def slot_url(stack: Stack, slot: str, port: int = 8000) -> str:
    return f"http://{stack.alias}-{slot}:{port}"


def compose_command(cfg: Config, stack: Stack, *args: str) -> list[str]:
    cmd = ["docker", "compose", "--project-name", stack.project]
    cmd += ["--env-file", f"{cfg.env_dir}/{stack.env_file}"]
    for f in stack.files:
        cmd += ["-f", f"{cfg.infra_dir}/compose/{f}"]
    return [*cmd, *args]


def compose_env(
    state: Mapping[str, Any], target_slot: str | None, image: str | None, migrate_image: str | None
) -> dict[str, str]:
    """Variabilele de imagine pentru Compose: fiecare slot păstrează imaginea lui; ținta primește cea nouă."""
    slots = dict(state["slots"])
    if target_slot and image:
        slots[target_slot] = image
    env = {f"AMA_IMAGE_{s.upper()}": slots[s] for s in SLOTS if slots.get(s)}
    if migrate_image:
        env["AMA_IMAGE_MIGRATE"] = migrate_image
    return env


@dataclass(frozen=True)
class Plan:
    kind: str  # nimic | implementare | revenire | respins
    image: str | None = None
    motiv: str = ""
    cerere_id: str | None = None
    deja_activa: bool = False


def plan_staging(desired_ref: str, state: Mapping[str, Any], now: float) -> Plan:
    """Staging: se implementează amprenta dorită dacă diferă de cea activă și nu a eșuat de curând."""
    active = state["slots"].get(state["active"]) if state["active"] else None
    if desired_ref == active:
        return Plan("nimic", motiv="staging are deja versiunea cea mai nouă")
    failed = state.get("failed")
    if failed and failed["ref"] == desired_ref:
        if failed["n"] >= MAX_STAGING_ATTEMPTS:
            return Plan("nimic", motiv="a eșuat de prea multe ori; așteaptă o versiune nouă")
        if now - failed["at"] < RETRY_FAILED_AFTER_S:
            return Plan("nimic", motiv="a eșuat de curând; reîncercare mai târziu")
    return Plan("implementare", image=desired_ref)


def plan_production(request: Mapping[str, Any] | None, state: Mapping[str, Any], repo: str) -> Plan:
    """Producția: doar ce cere panoul. Orice cerere nevalidă este respinsă cu motiv, nu ignorată."""
    if not request:
        return Plan("nimic")
    rid = str(request.get("id", ""))
    if not rid:
        return Plan("respins", motiv="cerere fără id")
    if rid in state.get("done", []):
        return Plan("nimic", cerere_id=rid, motiv="cerere deja tratată")
    tip = request.get("tip")
    if tip == "promovare":
        image = str(request.get("imagine", ""))
        parsed = parse_image_ref(image)
        if not parsed or parsed[0] != repo:
            return Plan(
                "respins", cerere_id=rid, motiv="imaginea nu este de forma <depozit-autorizat>@sha256:…"
            )
        active = state["slots"].get(state["active"]) if state["active"] else None
        if image == active:
            return Plan(
                "nimic", image=image, cerere_id=rid, motiv="versiunea este deja activă", deja_activa=True
            )
        return Plan("implementare", image=image, cerere_id=rid)
    if tip == "revenire":
        prev = state.get("previous")
        if prev and state["slots"].get(prev):
            return Plan("revenire", image=state["slots"][prev], cerere_id=rid)
        return Plan("respins", cerere_id=rid, motiv="nu există o versiune anterioară păstrată")
    return Plan("respins", cerere_id=rid, motiv=f"tip de cerere necunoscut: {tip!r}")


def evaluate_checks(
    responses: Mapping[str, tuple[int, str]],
) -> tuple[bool, list[dict[str, Any]], str | None]:
    """responses: cale -> (cod HTTP, corp). Întoarce (ok, verificări, versiune din /healthz)."""
    checks: list[dict[str, Any]] = []
    version: str | None = None
    health = responses.get("/healthz", (0, ""))
    ok_health = health[0] == 200
    if ok_health:
        try:
            body = json.loads(health[1])
            ok_health = body.get("status") == "ok"
            version = body.get("version")
        except ValueError:
            ok_health = False
    checks.append({"nume": "healthz", "ok": ok_health})
    checks.append({"nume": "readyz", "ok": responses.get("/readyz", (0, ""))[0] == 200})
    return all(c["ok"] for c in checks), checks, version


def parse_www_authenticate(header: str) -> dict[str, str]:
    """`Bearer realm="…",service="…",scope="…"` -> dict. Gol dacă nu e schema Bearer."""
    if not header.lower().startswith("bearer "):
        return {}
    return dict(re.findall(r'(\w+)="([^"]*)"', header))


def build_report(
    stack: str,
    stare: str,
    imagine: str | None,
    cerere_id: str | None,
    detalii: str = "",
    verificari: Sequence[Mapping[str, Any]] = (),
    versiune: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    return {
        "mediu": "productie" if stack == "production" else "staging",
        "stare": stare,
        "cerere_id": cerere_id,
        "imagine": imagine,
        "versiune": versiune,
        "detalii": detalii[:500],
        "verificari": [dict(v) for v in verificari],
        "momentul": (now or datetime.now(UTC)).astimezone(UTC).isoformat(timespec="seconds"),
    }


def mark_done(state: dict[str, Any], rid: str | None) -> None:
    if rid:
        state["done"] = [*state.get("done", []), rid][-MAX_DONE_REQUESTS:]


# ---------------------------------------------------------------------------------------------------------
# Interfețe cu efecte (înlocuibile în teste)
# ---------------------------------------------------------------------------------------------------------


class Runtime(Protocol):
    def pull(self, image: str) -> None: ...
    def migrate(self, stack: Stack, image: str, state: Mapping[str, Any]) -> None: ...
    def start_slot(self, stack: Stack, slot: str, image: str, state: Mapping[str, Any]) -> None: ...
    def stop_slot(self, stack: Stack, slot: str, state: Mapping[str, Any]) -> None: ...
    def http_get(self, url: str) -> tuple[int, str]: ...


class Registry(Protocol):
    def digest(self, repo: str, tag: str) -> str: ...


class Panel(Protocol):
    def fetch_request(self, base_url: str) -> dict[str, Any] | None: ...
    def report(self, base_url: str, payload: Mapping[str, Any]) -> None: ...


class StateStore(Protocol):
    def load(self) -> dict[str, Any]: ...
    def save(self, state: Mapping[str, Any]) -> None: ...


@dataclass
class Deployer:
    cfg: Config
    runtime: Runtime
    registry: Registry
    panel: Panel
    store: StateStore
    clock: Callable[[], float] = time.time
    sleep: Callable[[float], None] = time.sleep
    log: Callable[[str], None] = field(default=lambda m: print(m, flush=True))

    # -- stare ---------------------------------------------------------------------------------------------
    def _state(self) -> dict[str, Any]:
        data = self.store.load()
        data.setdefault("stacks", {})
        data.setdefault("pending_reports", [])
        for name in STACKS:
            data["stacks"].setdefault(name, empty_stack_state())
        return data

    def _panel_url(self, data: Mapping[str, Any]) -> str | None:
        prod = data["stacks"]["production"]
        return slot_url(STACKS["production"], prod["active"], self.cfg.app_port) if prod["active"] else None

    def _report(self, data: dict[str, Any], payload: dict[str, Any]) -> None:
        """Trimite raportul; dacă panoul nu răspunde, îl păstrează în coadă pentru ciclul următor."""
        data["pending_reports"] = [*data["pending_reports"], payload][-MAX_PENDING_REPORTS:]
        self._flush_reports(data)

    def _flush_reports(self, data: dict[str, Any]) -> None:
        url = self._panel_url(data)
        if not url:
            return
        left: list[dict[str, Any]] = []
        for i, payload in enumerate(data["pending_reports"]):
            try:
                self.panel.report(url, payload)
            except Exception as exc:
                self.log(f"raport netrimis ({type(exc).__name__}); rămâne în coadă")
                left = data["pending_reports"][i:]
                break
        data["pending_reports"] = left

    # -- verificări ----------------------------------------------------------------------------------------
    def _check_slot(self, stack: Stack, slot: str) -> tuple[bool, list[dict[str, Any]], str | None]:
        base = slot_url(stack, slot, self.cfg.app_port)
        responses: dict[str, tuple[int, str]] = {}
        for path in ("/healthz", "/readyz"):
            try:
                responses[path] = self.runtime.http_get(base + path)
            except Exception:
                responses[path] = (0, "")
        return evaluate_checks(responses)

    def _wait_ready(self, stack: Stack, slot: str) -> tuple[list[dict[str, Any]], str | None]:
        deadline = self.clock() + self.cfg.ready_timeout_s
        while True:
            ok, checks, version = self._check_slot(stack, slot)
            if ok:
                return checks, version
            if self.clock() >= deadline:
                bad = ", ".join(c["nume"] for c in checks if not c["ok"])
                raise DeployError(
                    f"slotul {slot} nu a devenit sănătos în {self.cfg.ready_timeout_s}s ({bad})"
                )
            self.sleep(2)

    def _stay_stable(self, stack: Stack, slot: str) -> None:
        for _ in range(self.cfg.stable_checks):
            self.sleep(self.cfg.stable_interval_s)
            ok, _checks, _version = self._check_slot(stack, slot)
            if not ok:
                raise DeployError("versiunea a devenit nesănătoasă după mutarea traficului")

    # -- operații ------------------------------------------------------------------------------------------
    def deploy(self, data: dict[str, Any], stack: Stack, image: str, rid: str | None) -> str:
        """Implementează `image`. Întoarce starea finală: reusita | esuata | revenita. Modifică `data`."""
        st = data["stacks"][stack.name]
        old = st["active"]
        target = other_slot(old)
        self._report(data, build_report(stack.name, "in_curs", image, rid, "pornește implementarea"))
        started = False
        try:
            self.runtime.pull(image)
            self.runtime.migrate(stack, image, st)
            started = True
            self.runtime.start_slot(stack, target, image, st)
            checks, version = self._wait_ready(stack, target)
        except Exception as exc:
            if started:
                self._safe_stop(stack, target, st)
            n = (st["failed"]["n"] + 1) if st.get("failed") and st["failed"]["ref"] == image else 1
            st["failed"] = {"ref": image, "at": self.clock(), "n": n}
            mark_done(st, rid)
            self._report(data, build_report(stack.name, "esuata", image, rid, _short(exc)))
            return "esuata"
        # Mutarea: slotul nou e sănătos. Se oprește cel vechi (rămâne ca imagine și container oprit).
        st["slots"][target] = image
        st["previous"], st["active"] = old, target
        st["failed"] = None
        if old:
            self._safe_stop(stack, old, st)
        try:
            self._stay_stable(stack, target)
        except DeployError as exc:
            mark_done(st, rid)
            if old:
                return self._rollback_to(data, stack, old, rid, f"revenire automată: {_short(exc)}")
            st["active"], st["previous"], st["slots"][target] = None, None, None
            self._safe_stop(stack, target, st)
            self._report(data, build_report(stack.name, "esuata", image, rid, _short(exc)))
            return "esuata"
        mark_done(st, rid)
        self._report(
            data, build_report(stack.name, "reusita", image, rid, "implementare încheiată", checks, version)
        )
        return "reusita"

    def rollback(self, data: dict[str, Any], stack: Stack, rid: str | None) -> str:
        st = data["stacks"][stack.name]
        prev = st["previous"]
        if not prev or not st["slots"].get(prev):
            self._report(data, build_report(stack.name, "esuata", None, rid, "nu există versiune anterioară"))
            mark_done(st, rid)
            return "esuata"
        res = self._rollback_to(data, stack, prev, rid, "revenire cerută")
        mark_done(st, rid)
        return res

    def _rollback_to(self, data: dict[str, Any], stack: Stack, slot: str, rid: str | None, why: str) -> str:
        st = data["stacks"][stack.name]
        current, image = st["active"], st["slots"][slot]
        try:
            self.runtime.start_slot(stack, slot, image, st)
            checks, version = self._wait_ready(stack, slot)
        except Exception as exc:
            self._safe_stop(stack, slot, st)
            self._report(
                data, build_report(stack.name, "esuata", image, rid, f"revenirea a eșuat: {_short(exc)}")
            )
            return "esuata"
        st["active"], st["previous"] = slot, current
        if current and current != slot:
            self._safe_stop(stack, current, st)
        self._report(data, build_report(stack.name, "revenita", image, rid, why, checks, version))
        return "revenita"

    def _safe_stop(self, stack: Stack, slot: str, st: Mapping[str, Any]) -> None:
        try:
            self.runtime.stop_slot(stack, slot, st)
        except Exception as exc:
            self.log(f"nu am putut opri {stack.name}/{slot}: {_short(exc)}")

    # -- cicluri -------------------------------------------------------------------------------------------
    def tick_staging(self, data: dict[str, Any]) -> None:
        try:
            digest = self.registry.digest(self.cfg.repo, self.cfg.staging_tag)
        except Exception as exc:
            self.log(f"registrul nu răspunde: {_short(exc)}")
            return
        plan = plan_staging(f"{self.cfg.repo}@{digest}", data["stacks"]["staging"], self.clock())
        if plan.kind == "implementare" and plan.image:
            self.log(f"staging: implementez {plan.image}")
            self.deploy(data, STACKS["staging"], plan.image, None)

    def tick_production(self, data: dict[str, Any]) -> None:
        url = self._panel_url(data)
        if not url:
            return  # producția nu e pornită încă; prima instalare se face cu comanda `deploy`
        try:
            request = self.panel.fetch_request(url)
        except Exception as exc:
            self.log(f"panoul nu răspunde: {_short(exc)}")
            return
        st = data["stacks"]["production"]
        plan = plan_production(request, st, self.cfg.repo)
        if plan.kind == "respins":
            self._report(data, build_report("production", "esuata", None, plan.cerere_id, plan.motiv))
            mark_done(st, plan.cerere_id)
        elif plan.kind == "implementare" and plan.image:
            self.log(f"producție: implementez {plan.image}")
            self.deploy(data, STACKS["production"], plan.image, plan.cerere_id)
        elif plan.kind == "revenire":
            self.log("producție: revenire")
            self.rollback(data, STACKS["production"], plan.cerere_id)
        elif plan.deja_activa:
            self._report(data, build_report("production", "reusita", plan.image, plan.cerere_id, plan.motiv))
            mark_done(st, plan.cerere_id)

    def tick(self) -> None:
        data = self._state()
        try:
            self._flush_reports(data)
            self.tick_staging(data)
            self.tick_production(data)
        finally:
            self.store.save(data)

    def run_forever(self) -> None:  # pragma: no cover
        while True:
            try:
                self.tick()
            except Exception as exc:
                self.log(f"ciclu eșuat: {_short(exc)}")
            self.sleep(self.cfg.interval_s)


def _short(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:300]


# ---------------------------------------------------------------------------------------------------------
# Implementări reale (neacoperite de teste unitare; vezi „NEVERIFICAT” în docs/specs/F1.8.md)
# ---------------------------------------------------------------------------------------------------------


class JsonFileStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        if not isinstance(data, dict):
            raise DeployError("fișierul de stare este corupt")
        return data

    def save(self, state: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(self.path)


class DockerRuntime:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def _run(self, cmd: Sequence[str], env: Mapping[str, str] | None = None, timeout: int = 600) -> None:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env={**os.environ, **(env or {})},
        )
        if r.returncode != 0:
            raise DeployError(f"{' '.join(cmd[:3])} a eșuat ({r.returncode}): {r.stderr.strip()[-300:]}")

    def pull(self, image: str) -> None:
        self._run(["docker", "pull", "--quiet", image])

    def migrate(self, stack: Stack, image: str, state: Mapping[str, Any]) -> None:
        env = compose_env(state, None, None, image)
        self._run(compose_command(self.cfg, stack, "run", "--rm", "--no-TTY", "migrate"), env)

    def start_slot(self, stack: Stack, slot: str, image: str, state: Mapping[str, Any]) -> None:
        env = compose_env(state, slot, image, None)
        self._run(
            compose_command(self.cfg, stack, "up", "--detach", "--no-deps", "--pull", "never", f"app_{slot}"),
            env,
        )

    def stop_slot(self, stack: Stack, slot: str, state: Mapping[str, Any]) -> None:
        env = compose_env(state, None, None, None)
        self._run(compose_command(self.cfg, stack, "stop", f"app_{slot}"), env)

    def http_get(self, url: str) -> tuple[int, str]:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:  # noqa: S310 - adrese interne construite de noi
                return resp.status, resp.read(65536).decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, ""


class OciRegistry:
    """Amprenta curentă a unei etichete, prin API-ul HTTP al registrului (flux Bearer)."""

    ACCEPT = ", ".join(
        [
            "application/vnd.oci.image.index.v1+json",
            "application/vnd.docker.distribution.manifest.list.v2+json",
            "application/vnd.oci.image.manifest.v1+json",
            "application/vnd.docker.distribution.manifest.v2+json",
        ]
    )

    def __init__(self, user: str = "", token: str = "") -> None:
        self.user, self.token = user, token

    def digest(self, repo: str, tag: str) -> str:
        host, _, name = repo.partition("/")
        url = f"https://{host}/v2/{name}/manifests/{tag}"
        headers = {"Accept": self.ACCEPT}
        try:
            return self._head(url, headers)
        except urllib.error.HTTPError as exc:
            if exc.code != 401:
                raise
            challenge = parse_www_authenticate(exc.headers.get("WWW-Authenticate", ""))
            if "realm" not in challenge:
                raise DeployError("registrul cere autentificare necunoscută") from exc
            headers["Authorization"] = "Bearer " + self._token(challenge)
            return self._head(url, headers)

    def _head(self, url: str, headers: Mapping[str, str]) -> str:
        req = urllib.request.Request(url, headers=dict(headers), method="HEAD")  # noqa: S310
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            digest = resp.headers.get("Docker-Content-Digest", "")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise DeployError("registrul nu a întors o amprentă validă")
        return digest

    def _token(self, challenge: Mapping[str, str]) -> str:
        query = urllib.parse.urlencode({k: challenge[k] for k in ("service", "scope") if k in challenge})
        headers = {}
        if self.user and self.token:
            headers["Authorization"] = (
                "Basic " + base64.b64encode(f"{self.user}:{self.token}".encode()).decode()
            )
        req = urllib.request.Request(f"{challenge['realm']}?{query}", headers=headers)  # noqa: S310
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            body = json.loads(resp.read())
        return str(body.get("token") or body["access_token"])


class HttpPanel:
    def __init__(self, token: str) -> None:
        self.token = token

    def _call(self, method: str, url: str, body: Mapping[str, Any] | None = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(  # noqa: S310
            url,
            data=data,
            method=method,
            headers={"X-Livrare-Token": self.token, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            return json.loads(resp.read() or b"{}")

    def fetch_request(self, base_url: str) -> dict[str, Any] | None:
        body = self._call("GET", f"{base_url}/intern/livrare/cerere")
        cerere = body.get("cerere") if isinstance(body, dict) else None
        return cerere if isinstance(cerere, dict) else None

    def report(self, base_url: str, payload: Mapping[str, Any]) -> None:
        self._call("POST", f"{base_url}/intern/livrare/rezultat", payload)


def build(cfg: Config) -> Deployer:
    return Deployer(
        cfg,
        DockerRuntime(cfg),
        OciRegistry(cfg.registry_user, cfg.registry_token),
        HttpPanel(cfg.panel_token),
        JsonFileStore(cfg.state_file),
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        cfg = Config.from_env(os.environ)
    except DeployError as exc:
        print(f"configurare greșită: {exc}", file=sys.stderr)
        return 2
    dep = build(cfg)
    cmd = args[0] if args else ""
    if cmd == "run":
        dep.run_forever()
        return 0
    if cmd == "once":
        dep.tick()
        return 0
    if cmd == "status":
        print(json.dumps(dep._state(), indent=2))
        return 0
    if cmd in ("deploy", "rollback") and len(args) >= 2 and args[1] in STACKS:
        data = dep._state()
        stack = STACKS[args[1]]
        if cmd == "deploy":
            if len(args) != 3 or not parse_image_ref(args[2]):
                print("folosire: deploy <staging|production> <depozit@sha256:…>", file=sys.stderr)
                return 2
            result = dep.deploy(data, stack, args[2], None)
        else:
            result = dep.rollback(data, stack, None)
        dep.store.save(data)
        print(result)
        return 0 if result in ("reusita", "revenita") else 1
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
