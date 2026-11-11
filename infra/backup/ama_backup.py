#!/usr/bin/env python3
# ruff: noqa: S603, S607
"""Backup și restaurare de test (F1.9). Doar biblioteca standard.

Unelte externe: pg_dump, pg_restore, psql, age, rclone, tar (apelate cu liste de argumente, fără shell).

Comenzi:
  backup        copie completă (bază + media + configurare), criptată cu age, încărcată cu rclone, retenție
  restore-test  descarcă ultima copie (sau AMA_RESTORE_SNAPSHOT), verifică sumele, restaurează în bază de test
  prune         aplică doar retenția
  serve         buclă de programare (zilnic: backup; săptămânal: restore-test)

Fiecare rulare scrie un rezultat JSON (contractul din docs/specs/F1.9.md) în AMA_BACKUP_STATUS_DIR și,
opțional, îl trimite comenzii din AMA_BACKUP_REPORT_CMD (JSON pe stdin; calea în AMA_BACKUP_RESULT_FILE).
Cod de ieșire: 0 la succes, 1 la eșec.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SCHEMA = "ama.backup/1"
SNAPSHOT_FMT = "%Y%m%dT%H%M%SZ"
SNAPSHOT_RE = re.compile(r"^\d{8}T\d{6}Z$")
KEEP_DAILY, KEEP_WEEKLY, KEEP_MONTHLY = 7, 4, 6


# ---------------------------------------------------------------------------------------------------------
# Logică pură (testată în tests/unit/test_infra_backup.py)
# ---------------------------------------------------------------------------------------------------------


def snapshot_time(snapshot_id: str) -> datetime:
    return datetime.strptime(snapshot_id, SNAPSHOT_FMT).replace(tzinfo=UTC)


def new_snapshot_id(now: datetime) -> str:
    return now.astimezone(UTC).strftime(SNAPSHOT_FMT)


def plan_retention(
    ids: Sequence[str], daily: int = KEEP_DAILY, weekly: int = KEEP_WEEKLY, monthly: int = KEEP_MONTHLY
) -> tuple[list[str], list[str]]:
    """Întoarce (de păstrat, de șters). Numele care nu sunt copii valide nu se ating (nu apar în rezultat).

    Regula: din fiecare zi UTC se ia cea mai nouă copie; se păstrează ultimele `daily` zile care au copii.
    La fel pentru săptămâni ISO (`weekly`) și luni (`monthly`). Reuniunea celor trei se păstrează.
    Cea mai nouă copie este întotdeauna păstrată.
    """
    valid = sorted((i for i in set(ids) if SNAPSHOT_RE.match(i)), reverse=True)  # cele mai noi întâi

    def newest_per(bucket: Callable[[datetime], Any], n: int) -> set[str]:
        first: dict[Any, str] = {}
        for i in valid:  # ordine descrescătoare: prima copie dintr-o găleată este cea mai nouă
            first.setdefault(bucket(snapshot_time(i)), i)
        return set(list(first.values())[:n])

    keep = (
        newest_per(lambda d: d.date(), daily)
        | newest_per(lambda d: d.isocalendar()[:2], weekly)
        | newest_per(lambda d: (d.year, d.month), monthly)
    )
    return sorted(keep), sorted(set(valid) - keep)


def due_jobs(
    now: datetime,
    last_backup: datetime | None,
    last_restore: datetime | None,
    hour: int = 3,
    weekday: int = 6,
) -> list[str]:
    """Ce trebuie rulat acum. `weekday`: 0=luni … 6=duminică. Ora este UTC.

    Backup: dacă azi (UTC) ora programată a trecut și nu există încă o copie de azi după acea oră.
    Test de restaurare: în ziua săptămânală, după backup, o singură dată pe săptămână ISO.
    """
    now = now.astimezone(UTC)
    slot = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    jobs: list[str] = []
    if now >= slot and (last_backup is None or last_backup < slot):
        jobs.append("backup")
    if now.weekday() == weekday and now >= slot + timedelta(minutes=30):
        week = now.isocalendar()[:2]
        stale = last_restore is None or last_restore.astimezone(UTC).isocalendar()[:2] != week
        if stale and "backup" not in jobs:
            jobs.append("restore-test")
    return jobs


def libpq_url(url: str) -> str:
    """postgresql+psycopg://… -> postgresql://… (libpq nu cunoaște sufixul de driver)."""
    return re.sub(r"^(postgres(?:ql)?)\+\w+://", r"\1://", url)


def with_database(url: str, dbname: str) -> str:
    return re.sub(r"^([^:]+://[^/]*)/[^?]*", rf"\1/{dbname}", libpq_url(url), count=1)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_manifest(manifest: Mapping[str, Any], directory: Path) -> list[str]:
    """Întoarce lista problemelor (goală = în regulă): fișier lipsă, mărime sau sumă SHA-256 diferită."""
    problems: list[str] = []
    for art in manifest.get("artefacte", []):
        p = directory / art["nume"]
        if not p.is_file():
            problems.append(f"lipsește {art['nume']}")
        elif p.stat().st_size != art["octeti"]:
            problems.append(f"mărime diferită: {art['nume']}")
        elif sha256_file(p) != art["sha256"]:
            problems.append(f"suma SHA-256 nu se potrivește: {art['nume']}")
    if not manifest.get("artefacte"):
        problems.append("manifest fără artefacte")
    return problems


# ---------------------------------------------------------------------------------------------------------
# Configurare și efecte
# ---------------------------------------------------------------------------------------------------------


class BackupError(Exception):
    pass


@dataclass
class Config:
    database_url: str
    dest: str
    recipients: list[str]
    media_dir: Path | None = None
    config_paths: list[Path] = field(default_factory=list)
    workdir: Path = Path("/var/lib/ama-backup/work")
    status_dir: Path = Path("/var/lib/ama-backup/status")
    report_cmd: str = ""
    admin_url: str = ""  # baza pe care se creează baza de probă; implicit aceeași cu database_url
    identity_file: Path | None = None
    verify_sql: str = (
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema NOT IN ('pg_catalog','information_schema')"
    )
    mediu: str = "productie"
    versiune: str = ""
    snapshot: str = ""  # restaurare: o copie anume; gol = ultima

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Config:
        def need(name: str) -> str:
            if not env.get(name):
                raise BackupError(f"variabila {name} lipsește")
            return env[name]

        recipients = [r.strip() for r in env.get("AMA_BACKUP_AGE_RECIPIENTS", "").split(",") if r.strip()]
        if rf := env.get("AMA_BACKUP_AGE_RECIPIENTS_FILE"):
            recipients += [
                line.strip()
                for line in Path(rf).read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")
            ]
        return cls(
            database_url=libpq_url(need("AMA_BACKUP_DATABASE_URL")),
            dest=need("AMA_BACKUP_DEST").rstrip("/"),
            recipients=recipients,
            media_dir=Path(env["AMA_BACKUP_MEDIA_DIR"]) if env.get("AMA_BACKUP_MEDIA_DIR") else None,
            config_paths=[Path(p) for p in env.get("AMA_BACKUP_CONFIG_PATHS", "").split(":") if p],
            workdir=Path(env.get("AMA_BACKUP_WORKDIR", "/var/lib/ama-backup/work")),
            status_dir=Path(env.get("AMA_BACKUP_STATUS_DIR", "/var/lib/ama-backup/status")),
            report_cmd=env.get("AMA_BACKUP_REPORT_CMD", ""),
            admin_url=libpq_url(env.get("AMA_RESTORE_TEST_ADMIN_URL", "")),
            identity_file=Path(env["AMA_RESTORE_IDENTITY_FILE"])
            if env.get("AMA_RESTORE_IDENTITY_FILE")
            else None,
            verify_sql=env.get("AMA_BACKUP_VERIFY_SQL") or cls.verify_sql,
            mediu=env.get("AMA_BACKUP_ENV", "productie"),
            versiune=env.get("AMA_VERSION", ""),
            snapshot=env.get("AMA_RESTORE_SNAPSHOT", ""),
        )


def _run(cmd: Sequence[str], **kw: Any) -> subprocess.CompletedProcess[str]:
    r = subprocess.run(cmd, capture_output=True, text=True, check=False, **kw)
    if r.returncode != 0:
        raise BackupError(f"{cmd[0]} a eșuat ({r.returncode}): {r.stderr.strip()[-500:]}")
    return r


def _pipe_to_age(
    producer: Sequence[str], out: Path, recipients: Sequence[str], cwd: str | None = None
) -> None:
    """producer | age -r … -o out. Fără fișier necriptat pe disc."""
    age_cmd = ["age", *[a for r in recipients for a in ("-r", r)], "-o", str(out)]
    with subprocess.Popen(producer, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd) as prod:
        with subprocess.Popen(age_cmd, stdin=prod.stdout, stderr=subprocess.PIPE) as enc:
            if prod.stdout:
                prod.stdout.close()
            enc_err = (enc.stderr.read() if enc.stderr else b"").decode(errors="replace")
            enc_rc = enc.wait()
        prod_err = (prod.stderr.read() if prod.stderr else b"").decode(errors="replace")
        prod_rc = prod.wait()
    if prod_rc != 0:
        raise BackupError(f"{producer[0]} a eșuat ({prod_rc}): {prod_err.strip()[-500:]}")
    if enc_rc != 0:
        raise BackupError(f"age a eșuat ({enc_rc}): {enc_err.strip()[-500:]}")


def _decrypt_to(cmd_consumer: Sequence[str], enc_file: Path, identity: Path) -> None:
    """age -d -i identity enc_file | consumer."""
    with subprocess.Popen(
        ["age", "-d", "-i", str(identity), str(enc_file)], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    ) as dec:
        with subprocess.Popen(
            cmd_consumer, stdin=dec.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        ) as con:
            if dec.stdout:
                dec.stdout.close()
            con_err = (con.stderr.read() if con.stderr else b"").decode(errors="replace")
            con_rc = con.wait()
        dec_err = (dec.stderr.read() if dec.stderr else b"").decode(errors="replace")
        dec_rc = dec.wait()
    if dec_rc != 0:
        raise BackupError(f"decriptarea a eșuat pentru {enc_file.name}: {dec_err.strip()[-300:]}")
    if con_rc != 0:
        raise BackupError(
            f"{cmd_consumer[0]} a eșuat pentru {enc_file.name} ({con_rc}): {con_err.strip()[-500:]}"
        )


def _artifact(path: Path) -> dict[str, Any]:
    return {"nume": path.name, "octeti": path.stat().st_size, "sha256": sha256_file(path)}


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def _rclone_ids(dest: str) -> list[str]:
    out = _run(["rclone", "lsf", "--dirs-only", dest]).stdout
    return [line.rstrip("/") for line in out.splitlines() if SNAPSHOT_RE.match(line.rstrip("/"))]


# ---------------------------------------------------------------------------------------------------------
# Operații
# ---------------------------------------------------------------------------------------------------------


def do_backup(cfg: Config, now: datetime | None = None) -> dict[str, Any]:
    started = now or _now()
    snap = new_snapshot_id(started)
    if not cfg.recipients:
        raise BackupError("niciun destinatar age (AMA_BACKUP_AGE_RECIPIENTS)")
    work = cfg.workdir / snap
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, mode=0o700)
    try:
        artifacts: list[dict[str, Any]] = []
        db = work / "baza.dump.age"
        _pipe_to_age(
            ["pg_dump", "--format=custom", "--compress=6", "--dbname", cfg.database_url], db, cfg.recipients
        )
        artifacts.append(_artifact(db))
        omise: list[str] = []
        if cfg.media_dir and cfg.media_dir.is_dir():
            media = work / "media.tar.gz.age"
            _pipe_to_age(["tar", "-czf", "-", "-C", str(cfg.media_dir), "."], media, cfg.recipients)
            artifacts.append(_artifact(media))
        else:
            omise.append("media")
        paths = [p for p in cfg.config_paths if p.exists()]
        if paths:
            conf = work / "configurare.tar.gz.age"
            _pipe_to_age(
                ["tar", "-czf", "-", "-P", *[str(p) for p in paths]], conf, cfg.recipients
            )  # căi absolute păstrate: se restaurează la locul lor
            artifacts.append(_artifact(conf))
        else:
            omise.append("configurare")
        manifest = {
            "schema": SCHEMA,
            "id": snap,
            "creat": _iso(started),
            "mediu": cfg.mediu,
            "versiune": cfg.versiune,
            "artefacte": artifacts,
            "omise": omise,
        }
        (work / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        remote = f"{cfg.dest}/{snap}"
        _run(["rclone", "copy", str(work), remote])
        _run(["rclone", "check", str(work), remote, "--one-way"])
        keep, delete = plan_retention([*_rclone_ids(cfg.dest)])
        for old in delete:
            _run(["rclone", "purge", f"{cfg.dest}/{old}"])
        return {
            "id": snap,
            "artefacte": [
                *artifacts,
                {"nume": "manifest.json", "octeti": (work / "manifest.json").stat().st_size},
            ],
            "omise": omise,
            "retentie": {"pastrate": keep, "sterse": delete},
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


def do_restore_test(cfg: Config) -> dict[str, Any]:
    if not cfg.identity_file or not cfg.identity_file.is_file():
        raise BackupError("lipsește cheia de verificare (AMA_RESTORE_IDENTITY_FILE)")
    ids = _rclone_ids(cfg.dest)
    if not ids:
        raise BackupError("nu există nicio copie la destinație")
    snap = cfg.snapshot or sorted(ids)[-1]
    if snap not in ids:
        raise BackupError(f"copia {snap} nu există la destinație")
    work = cfg.workdir / f"restaurare-{snap}-{uuid.uuid4().hex[:6]}"
    work.mkdir(parents=True, mode=0o700)
    admin = cfg.admin_url or cfg.database_url
    scratch = f"ama_restoretest_{uuid.uuid4().hex[:10]}"
    created = False
    try:
        _run(["rclone", "copy", f"{cfg.dest}/{snap}", str(work)])
        try:
            manifest = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise BackupError(f"manifest ilizibil: {exc}") from exc
        if problems := verify_manifest(manifest, work):
            raise BackupError("copie coruptă: " + "; ".join(problems))
        _run(["psql", "--dbname", admin, "-v", "ON_ERROR_STOP=1", "-c", f'CREATE DATABASE "{scratch}"'])
        created = True
        scratch_url = with_database(admin, scratch)
        _decrypt_to(
            [
                "pg_restore",
                "--no-owner",
                "--no-acl",
                "--no-comments",
                "--exit-on-error",
                "--dbname",
                scratch_url,
            ],
            work / "baza.dump.age",
            cfg.identity_file,
        )
        out = _run(
            ["psql", "--dbname", scratch_url, "-v", "ON_ERROR_STOP=1", "-At", "-c", cfg.verify_sql]
        ).stdout
        value = out.strip().splitlines()[0] if out.strip() else ""
        try:
            number = float(value)
        except ValueError as exc:
            raise BackupError(f"interogarea de verificare nu a întors un număr: {value!r}") from exc
        if number <= 0:
            raise BackupError(f"interogarea de verificare a întors {value} (se așteaptă > 0)")
        for art in manifest["artefacte"]:  # media și configurarea: se decriptează și se citește arhiva
            if art["nume"].startswith(("media", "configurare")):
                _decrypt_to(["tar", "-tzf", "-"], work / art["nume"], cfg.identity_file)
        return {
            "id": snap,
            "artefacte": [{k: a[k] for k in ("nume", "octeti", "sha256")} for a in manifest["artefacte"]],
            "verificare": {"interogare": cfg.verify_sql, "valoare": number},
        }
    finally:
        if created:
            with contextlib.suppress(BackupError):
                _run(["psql", "--dbname", admin, "-c", f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)'])
        shutil.rmtree(work, ignore_errors=True)


def do_prune(cfg: Config) -> dict[str, Any]:
    keep, delete = plan_retention(_rclone_ids(cfg.dest))
    for old in delete:
        _run(["rclone", "purge", f"{cfg.dest}/{old}"])
    return {"id": None, "retentie": {"pastrate": keep, "sterse": delete}}


OPS = {"backup": do_backup, "restore-test": do_restore_test, "prune": do_prune}
STATUS_FILE = {
    "backup": "ultimul-backup.json",
    "restore-test": "ultima-restaurare-test.json",
    "prune": "ultima-curatare.json",
}
RESULT_TYPE = {"backup": "backup", "restore-test": "restaurare_test", "prune": "curatare"}


def run_op(op: str, cfg: Config) -> dict[str, Any]:
    """Rulează o operație și scrie mereu rezultatul JSON (și la eșec)."""
    started = _now()
    t0 = time.monotonic()
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "tip": RESULT_TYPE[op],
        "mediu": cfg.mediu,
        "versiune": cfg.versiune,
        "inceput": _iso(started),
        "destinatie": re.sub(r"(//[^@/]*@)", "//", cfg.dest),  # fără parole, dacă destinația ar fi un URL
        "stare": "reusit",
        "eroare": None,
    }
    try:
        if op == "backup":
            result.update(do_backup(cfg, started))
        else:
            result.update(OPS[op](cfg))
    except BackupError as exc:
        result.update(stare="esuat", eroare=str(exc)[:1000])
    except Exception as exc:  # orice altceva tot trebuie raportat
        result.update(stare="esuat", eroare=f"{type(exc).__name__}: {exc}"[:1000])
    result["sfarsit"] = _iso(_now())
    result["durata_s"] = round(time.monotonic() - t0, 2)
    _publish(cfg, op, result)
    return result


def _publish(cfg: Config, op: str, result: dict[str, Any]) -> None:
    """Scrie rezultatul (atomic) și îl raportează; eroarea de raportare nu schimbă starea."""
    result["raportare"] = "dezactivata"
    try:
        cfg.status_dir.mkdir(parents=True, exist_ok=True)
        target = cfg.status_dir / STATUS_FILE[op]
        payload = json.dumps(result, indent=2, ensure_ascii=False)
        if cfg.report_cmd:
            try:
                env = {**os.environ, "AMA_BACKUP_RESULT_FILE": str(target)}
                subprocess.run(
                    shlex.split(cfg.report_cmd),
                    input=payload,
                    text=True,
                    env=env,
                    check=True,
                    timeout=60,
                    capture_output=True,
                )
                result["raportare"] = "trimis"
            except (subprocess.SubprocessError, OSError) as exc:
                result["raportare"] = f"eroare: {type(exc).__name__}"
        payload = json.dumps(result, indent=2, ensure_ascii=False)
        with tempfile.NamedTemporaryFile("w", dir=cfg.status_dir, delete=False, encoding="utf-8") as tmp:
            tmp.write(payload)
        Path(tmp.name).replace(target)
        target.chmod(0o644)
        with (cfg.status_dir / "istoric.jsonl").open("a", encoding="utf-8") as hist:
            hist.write(json.dumps(result, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"nu pot scrie rezultatul: {exc}", file=sys.stderr)


def _last_run(cfg: Config, op: str) -> datetime | None:
    try:
        data = json.loads((cfg.status_dir / STATUS_FILE[op]).read_text(encoding="utf-8"))
        return datetime.fromisoformat(data["inceput"]) if data.get("stare") == "reusit" else None
    except (OSError, ValueError, KeyError):
        return None


def serve(
    cfg: Config, env: Mapping[str, str], sleep: float = 60.0
) -> None:  # pragma: no cover - buclă infinită
    hour, weekday = int(env.get("AMA_BACKUP_HOUR", "3")), int(env.get("AMA_RESTORE_TEST_WEEKDAY", "6"))
    last_fail: dict[str, datetime] = {}
    while True:
        now = _now()
        for job in due_jobs(now, _last_run(cfg, "backup"), _last_run(cfg, "restore-test"), hour, weekday):
            if job in last_fail and now - last_fail[job] < timedelta(hours=1):
                continue  # după un eșec se reîncearcă cel mai devreme peste o oră
            if run_op(job, cfg)["stare"] != "reusit":
                last_fail[job] = now
        time.sleep(sleep)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in (*OPS, "serve"):
        print(__doc__, file=sys.stderr)
        return 2
    try:
        cfg = Config.from_env(os.environ)
    except BackupError as exc:
        print(f"configurare greșită: {exc}", file=sys.stderr)
        return 2
    if args[0] == "serve":
        serve(cfg, os.environ)
        return 0
    result = run_op(args[0], cfg)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["stare"] == "reusit" else 1


if __name__ == "__main__":
    sys.exit(main())
