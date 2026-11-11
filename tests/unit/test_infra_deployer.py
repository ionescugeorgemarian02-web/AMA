"""F1.8 — decizia și orchestrarea serviciului de livrare, cu efecte false (fără docker, fără rețea)."""

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

PATH = Path(__file__).resolve().parents[2] / "infra" / "deployer" / "deployer.py"
spec = importlib.util.spec_from_file_location("ama_deployer", PATH)
assert spec and spec.loader
d = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = d
spec.loader.exec_module(d)

REPO = "ghcr.io/acme/ama"
A = f"{REPO}@sha256:{'a' * 64}"
B = f"{REPO}@sha256:{'b' * 64}"
C = f"{REPO}@sha256:{'c' * 64}"
HEALTHY = (200, '{"status":"ok","version":"v1"}')


def state_with(
    active: str | None, image: str | None, previous: str | None = None, prev_image: str | None = None
):
    st = d.empty_stack_state()
    st["active"], st["previous"] = active, previous
    if active:
        st["slots"][active] = image
    if previous:
        st["slots"][previous] = prev_image
    return st


# ---------------------------------------------------------------------------------------- funcții pure


def test_referinta_de_imagine_accepta_doar_amprenta() -> None:
    assert d.parse_image_ref(A) == (REPO, "sha256:" + "a" * 64)
    for bad in (
        "",
        f"{REPO}:latest",
        f"{REPO}@sha256:abc",
        f"{REPO}@sha256:{'G' * 64}",
        "x y@sha256:" + "a" * 64,
    ):
        assert d.parse_image_ref(bad) is None


def test_slotul_urmator_alterneaza() -> None:
    assert (
        d.other_slot(None) == "blue" and d.other_slot("blue") == "green" and d.other_slot("green") == "blue"
    )


def test_staging_implementeaza_amprenta_noua_si_ignora_pe_cea_activa() -> None:
    st = state_with("blue", A)
    assert d.plan_staging(A, st, 0).kind == "nimic"
    plan = d.plan_staging(B, st, 0)
    assert plan.kind == "implementare" and plan.image == B
    assert d.plan_staging(A, d.empty_stack_state(), 0).kind == "implementare"


def test_staging_nu_reincearca_in_bucla_o_versiune_esuata() -> None:
    st = state_with("blue", A)
    st["failed"] = {"ref": B, "at": 1000.0, "n": 1}
    assert d.plan_staging(B, st, 1000.0 + 10).kind == "nimic"  # prea devreme
    assert d.plan_staging(B, st, 1000.0 + d.RETRY_FAILED_AFTER_S + 1).kind == "implementare"
    st["failed"]["n"] = d.MAX_STAGING_ATTEMPTS
    assert d.plan_staging(B, st, 10**9).kind == "nimic"
    assert d.plan_staging(C, st, 0).kind == "implementare"  # o versiune nouă resetează


def test_productia_fara_cerere_nu_face_nimic() -> None:
    assert d.plan_production(None, state_with("blue", A), REPO).kind == "nimic"


@pytest.mark.parametrize(
    "request_",
    [
        {"id": "r1", "tip": "promovare", "imagine": "evil.example/ama@sha256:" + "a" * 64},
        {"id": "r1", "tip": "promovare", "imagine": f"{REPO}:latest"},
        {"id": "r1", "tip": "promovare"},
        {"id": "r1", "tip": "altceva"},
        {"tip": "promovare", "imagine": A},
    ],
)
def test_productia_respinge_cereri_nevalide(request_: dict[str, Any]) -> None:
    plan = d.plan_production(request_, state_with("blue", A), REPO)
    assert plan.kind == "respins" and plan.motiv


def test_productia_promoveaza_o_amprenta_valida() -> None:
    plan = d.plan_production({"id": "r1", "tip": "promovare", "imagine": B}, state_with("blue", A), REPO)
    assert (plan.kind, plan.image, plan.cerere_id) == ("implementare", B, "r1")


def test_productia_recunoaste_versiunea_deja_activa_si_cererile_tratate() -> None:
    st = state_with("blue", A)
    plan = d.plan_production({"id": "r1", "tip": "promovare", "imagine": A}, st, REPO)
    assert plan.kind == "nimic" and plan.deja_activa
    st["done"] = ["r1"]
    assert d.plan_production({"id": "r1", "tip": "promovare", "imagine": B}, st, REPO).kind == "nimic"


def test_revenirea_cere_o_versiune_anterioara_pastrata() -> None:
    req = {"id": "r2", "tip": "revenire"}
    assert d.plan_production(req, state_with("blue", A), REPO).kind == "respins"
    plan = d.plan_production(req, state_with("green", B, "blue", A), REPO)
    assert (plan.kind, plan.image) == ("revenire", A)


def test_verificarile_cer_healthz_ok_si_readyz_200() -> None:
    ok, checks, version = d.evaluate_checks({"/healthz": HEALTHY, "/readyz": (200, "{}")})
    assert ok and version == "v1" and [c["ok"] for c in checks] == [True, True]
    assert not d.evaluate_checks({"/healthz": HEALTHY, "/readyz": (503, "")})[0]
    assert not d.evaluate_checks({"/healthz": (200, "nu e json"), "/readyz": (200, "")})[0]
    assert not d.evaluate_checks({"/healthz": (200, '{"status":"degradat"}'), "/readyz": (200, "")})[0]
    assert not d.evaluate_checks({})[0]


def test_imaginile_slorurilor_si_comanda_compose() -> None:
    st = state_with("blue", A)
    env = d.compose_env(st, "green", B, None)
    assert env == {"AMA_IMAGE_BLUE": A, "AMA_IMAGE_GREEN": B}
    assert d.compose_env(st, None, None, B) == {"AMA_IMAGE_BLUE": A, "AMA_IMAGE_MIGRATE": B}
    cfg = d.Config(repo=REPO, infra_dir="/i", env_dir="/e")
    cmd = d.compose_command(cfg, d.STACKS["production"], "stop", "app_blue")
    assert cmd[:4] == ["docker", "compose", "--project-name", "ama-prod"]
    assert "/e/production.env" in cmd and "/i/compose/base.yml" in cmd and cmd[-2:] == ["stop", "app_blue"]


def test_provocarea_de_autentificare_a_registrului() -> None:
    h = 'Bearer realm="https://ghcr.io/token",service="ghcr.io",scope="repository:acme/ama:pull"'
    assert d.parse_www_authenticate(h) == {
        "realm": "https://ghcr.io/token",
        "service": "ghcr.io",
        "scope": "repository:acme/ama:pull",
    }
    assert d.parse_www_authenticate('Basic realm="x"') == {}


def test_configurarea_cere_token_lung() -> None:
    with pytest.raises(d.DeployError):
        d.Config.from_env({"AMA_DEPLOYER_REPO": REPO, "AMA_DEPLOY_TOKEN": "scurt"})
    cfg = d.Config.from_env({"AMA_DEPLOYER_REPO": "GHCR.io/Acme/AMA", "AMA_DEPLOY_TOKEN": "x" * 32})
    assert cfg.repo == "ghcr.io/acme/ama"


# ---------------------------------------------------------------------------------------- orchestrare


class FakeRuntime:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.fail_on: set[str] = set()
        self.health: dict[str, list[tuple[int, str]]] = {}  # url -> răspunsuri succesive (ultimul se repetă)

    def pull(self, image: str) -> None:
        self.calls.append(("pull", image))
        if "pull" in self.fail_on:
            raise d.DeployError("pull eșuat")

    def migrate(self, stack: Any, image: str, state: Any) -> None:
        self.calls.append(("migrate", stack.name, image))
        if "migrate" in self.fail_on:
            raise d.DeployError("migrare eșuată")

    def start_slot(self, stack: Any, slot: str, image: str, state: Any) -> None:
        self.calls.append(("start", stack.name, slot, image))

    def stop_slot(self, stack: Any, slot: str, state: Any) -> None:
        self.calls.append(("stop", stack.name, slot))

    def http_get(self, url: str) -> tuple[int, str]:
        seq = self.health.get(url)
        if seq is None:
            return (200, '{"status":"ok","version":"v1"}') if url.endswith("/healthz") else (200, "{}")
        resp = seq.pop(0) if len(seq) > 1 else seq[0]
        return resp


class FakeRegistry:
    def __init__(self, digest: str) -> None:
        self._digest = digest
        self.broken = False

    def digest(self, repo: str, tag: str) -> str:
        if self.broken:
            raise OSError("registru indisponibil")
        return self._digest


class FakePanel:
    def __init__(self) -> None:
        self.request: dict[str, Any] | None = None
        self.reports: list[dict[str, Any]] = []
        self.down = False

    def fetch_request(self, base_url: str) -> dict[str, Any] | None:
        if self.down:
            raise OSError("panou indisponibil")
        return self.request

    def report(self, base_url: str, payload: Any) -> None:
        if self.down:
            raise OSError("panou indisponibil")
        self.reports.append(dict(payload))


class MemStore:
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.data = data or {}

    def load(self) -> dict[str, Any]:
        return self.data

    def save(self, state: Any) -> None:
        self.data = dict(state)


def make(digest: str = "sha256:" + "b" * 64, prod_active: str | None = "blue", prod_image: str | None = A):
    cfg = d.Config(repo=REPO, ready_timeout_s=10, stable_checks=2, stable_interval_s=0)
    store = MemStore()
    if prod_active:
        data = {"stacks": {"production": state_with(prod_active, prod_image)}}
        store.data = data
    clock = {"t": 0.0}
    dep = d.Deployer(
        cfg,
        FakeRuntime(),
        FakeRegistry(digest),
        FakePanel(),
        store,
        clock=lambda: clock["t"],
        sleep=lambda s: clock.__setitem__("t", clock["t"] + max(s, 0.5)),
        log=lambda m: None,
    )
    return dep, clock


def states(panel: FakePanel) -> list[str]:
    return [r["stare"] for r in panel.reports]


def test_staging_primeste_versiunea_noua_fara_interventie() -> None:
    dep, _ = make()
    dep.tick()
    st = dep.store.data["stacks"]["staging"]
    assert st["active"] == "blue" and st["slots"]["blue"] == B and st["failed"] is None
    kinds = [c[0] for c in dep.runtime.calls]
    assert kinds == ["pull", "migrate", "start"]  # migrările rulează înaintea pornirii
    assert states(dep.panel) == ["in_curs", "reusita"] and dep.panel.reports[-1]["mediu"] == "staging"
    dep.tick()  # a doua oară nu mai face nimic
    assert [c[0] for c in dep.runtime.calls] == ["pull", "migrate", "start"]


def test_staging_porneste_noul_slot_langa_cel_vechi_si_il_opreste_pe_cel_vechi() -> None:
    dep, _ = make()
    dep.tick()
    dep.registry._digest = "sha256:" + "c" * 64
    dep.runtime.calls.clear()
    dep.tick()
    st = dep.store.data["stacks"]["staging"]
    assert (st["active"], st["previous"]) == ("green", "blue") and st["slots"] == {"blue": B, "green": C}
    assert ("stop", "staging", "blue") in dep.runtime.calls
    assert dep.runtime.calls.index(("start", "staging", "green", C)) < dep.runtime.calls.index(
        ("stop", "staging", "blue")
    )


def test_slot_nesanatos_nu_muta_traficul_si_se_raporteaza_esecul() -> None:
    dep, _ = make()
    dep.tick()
    dep.registry._digest = "sha256:" + "c" * 64
    dep.runtime.health["http://staging-green:8000/readyz"] = [(503, "")]
    dep.tick()
    st = dep.store.data["stacks"]["staging"]
    assert st["active"] == "blue" and st["slots"]["blue"] == B  # vechea versiune nu a fost atinsă
    assert st["failed"]["ref"] == C and ("stop", "staging", "green") in dep.runtime.calls
    assert ("stop", "staging", "blue") not in dep.runtime.calls
    assert states(dep.panel)[-1] == "esuata"


@pytest.mark.parametrize("step", ["pull", "migrate"])
def test_pull_sau_migrare_esuate_opresc_livrarea_inainte_de_pornire(step: str) -> None:
    dep, _ = make()
    dep.runtime.fail_on = {step}
    dep.tick()
    assert not any(c[0] == "start" for c in dep.runtime.calls)
    assert states(dep.panel)[-1] == "esuata"
    assert dep.store.data["stacks"]["staging"]["active"] is None


def test_versiune_care_se_strica_dupa_mutare_revine_automat() -> None:
    dep, _ = make()
    dep.tick()
    dep.registry._digest = "sha256:" + "c" * 64
    ok = (200, '{"status":"ok","version":"v1"}')
    # slotul green: sănătos la pornire, apoi pică în fereastra de stabilitate
    dep.runtime.health["http://staging-green:8000/healthz"] = [ok, (500, "")]
    dep.tick()
    st = dep.store.data["stacks"]["staging"]
    assert st["active"] == "blue" and states(dep.panel)[-1] == "revenita"
    assert ("start", "staging", "blue", B) in dep.runtime.calls


def test_productia_nu_se_atinge_fara_cerere_din_panou() -> None:
    dep, _ = make()
    dep.tick()
    assert dep.store.data["stacks"]["production"]["slots"]["blue"] == A
    assert not any(c[1] == "production" for c in dep.runtime.calls if len(c) > 1 and c[0] != "pull")


def test_promovarea_ceruta_din_panou_ajunge_in_productie_si_se_raporteaza_o_singura_data() -> None:
    dep, _ = make(digest="sha256:" + "a" * 64)  # staging rămâne la A (nimic nou)
    dep.tick()
    dep.panel.request = {"id": "r1", "tip": "promovare", "imagine": B}
    dep.runtime.calls.clear()
    dep.tick()
    prod = dep.store.data["stacks"]["production"]
    assert (prod["active"], prod["previous"]) == ("green", "blue") and prod["slots"]["green"] == B
    prod_reports = [r for r in dep.panel.reports if r["mediu"] == "productie"]
    assert [r["stare"] for r in prod_reports] == ["in_curs", "reusita"] and prod_reports[-1][
        "cerere_id"
    ] == "r1"
    n = len(dep.runtime.calls)
    dep.tick()  # panoul mai servește aceeași cerere: nu se reia
    assert len(dep.runtime.calls) == n and "r1" in prod["done"]


def test_cerere_nevalida_de_promovare_este_respinsa_cu_raport() -> None:
    dep, _ = make(digest="sha256:" + "a" * 64)
    dep.tick()
    dep.runtime.calls.clear()
    dep.panel.request = {"id": "r9", "tip": "promovare", "imagine": "altundeva/ama@sha256:" + "a" * 64}
    dep.tick()
    assert dep.panel.reports[-1]["stare"] == "esuata" and dep.panel.reports[-1]["cerere_id"] == "r9"
    assert not any(c[0] == "start" for c in dep.runtime.calls)


def test_revenirea_ceruta_porneste_versiunea_anterioara() -> None:
    dep, _ = make(digest="sha256:" + "a" * 64)
    dep.tick()
    dep.panel.request = {"id": "r1", "tip": "promovare", "imagine": B}
    dep.tick()
    dep.panel.request = {"id": "r2", "tip": "revenire"}
    dep.runtime.calls.clear()
    dep.tick()
    prod = dep.store.data["stacks"]["production"]
    assert prod["active"] == "blue" and prod["slots"]["blue"] == A
    assert dep.runtime.calls == [("start", "production", "blue", A), ("stop", "production", "green")]
    assert dep.panel.reports[-1]["stare"] == "revenita" and dep.panel.reports[-1]["cerere_id"] == "r2"


def test_raportul_netrimis_ramane_in_coada_si_pleaca_la_ciclul_urmator() -> None:
    dep, _ = make(digest="sha256:" + "a" * 64)
    dep.panel.down = True
    dep.tick()  # staging deja la A? nu: staging gol -> implementează A; raportul nu poate pleca
    assert dep.store.data["pending_reports"]
    dep.panel.down = False
    dep.tick()
    assert dep.store.data["pending_reports"] == [] and states(dep.panel)[:2] == ["in_curs", "reusita"]


def test_registrul_indisponibil_nu_strica_ciclul() -> None:
    dep, _ = make()
    dep.registry.broken = True
    dep.tick()
    assert dep.runtime.calls == []
