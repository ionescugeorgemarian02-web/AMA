#!/usr/bin/env python3
"""Exercițiul de restaurare completă (F15.3, docs/25 §25.3, runbook `docs/runbooks/restaurare.md`).

Cap-coadă, cronometrat: backup real (ama_backup: pg_dump + media + configurare, criptate cu age) ->
mediu curat (o bază NOUĂ și un director media NOU, fără nimic de la sursă în afara copiei) -> restaurare
din copie (manifest verificat, decriptare cu cheia proprietarului, pg_restore, dezarhivare) -> verificare:
  1. versiunea migrărilor (`alembic_version`) identică;
  2. fiecare tabel are exact același număr de rânduri;
  3. aceleași tabele cu RLS activ și forțat;
  4. fișierele media identice (sha256);
  5. platforma funcțională: aplicația pornește pe baza restaurată, ca rolul aplicației, și `/readyz` = 200.
Durata totală se compară cu ținta (4 h, docs/22 §22.6). Ieșire: JSON pe stdout; cod 0 doar dacă totul trece.

Folosire (local, pe Postgres-ul de test sau pe staging):
  scripts/exercitiu_restaurare.py --sursa-admin URL --sursa-app URL [--media DIR] [--config DIR ...]
      [--tinta-ore 4] [--pastreaza]
`--sursa-admin`: superutilizator, spre baza sursă (pe același server se creează baza curată); `--sursa-app`:
rolul aplicației (oricare bază; se schimbă doar numele bazei).
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TINTA_ORE = 4.0  # docs/runbooks/restaurare.md: repunere în funcțiune în 4 h


def _ama_backup() -> Any:
    spec = importlib.util.spec_from_file_location("ama_backup", ROOT / "infra" / "backup" / "ama_backup.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("lipsește infra/backup/ama_backup.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _psql(url: str, sql: str) -> list[str]:
    r = subprocess.run(
        ["psql", "--dbname", url, "-v", "ON_ERROR_STOP=1", "-At", "-F", "\t", "-c", sql],
        capture_output=True,
        text=True,
        check=True,
    )
    return [x for x in r.stdout.splitlines() if x]


def _numaratori(url: str) -> dict[str, int]:
    tabele = _psql(
        url,
        "SELECT quote_ident(table_schema)||'.'||quote_ident(table_name) FROM information_schema.tables "
        "WHERE table_type='BASE TABLE' AND table_schema NOT IN ('pg_catalog','information_schema') "
        "ORDER BY 1",
    )
    if not tabele:
        return {}
    # numele vin din catalogul bazei, deja citate cu quote_ident
    sql = " UNION ALL ".join(f"SELECT '{t}', count(*) FROM {t}" for t in tabele)  # noqa: S608
    return {r.split("\t")[0]: int(r.split("\t")[1]) for r in _psql(url, sql)}


def _rls(url: str) -> list[str]:
    return _psql(
        url,
        "SELECT n.nspname||'.'||c.relname||':'||c.relforcerowsecurity FROM pg_class c "
        "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relrowsecurity ORDER BY 1",
    )


def _sume(d: Path | None) -> dict[str, str]:
    if d is None or not d.is_dir():
        return {}
    return {
        str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(d.rglob("*"))
        if p.is_file()
    }


def _readyz(app_url: str, media: Path) -> tuple[int, str]:
    cod = (
        "from fastapi.testclient import TestClient\nfrom app.main import create_app\n"
        "with TestClient(create_app()) as c:\n    r = c.get('/readyz')\n"
        "    print(r.status_code, r.text[:300])\n"
    )
    env = {**os.environ, "AMA_DATABASE_URL": app_url, "AMA_MEDIA_DIR": str(media), "AMA_ENV": "test"}
    r = subprocess.run(
        [sys.executable, "-c", cod], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300
    )
    if r.returncode != 0:
        return 0, (r.stderr or r.stdout)[-300:]
    cod_http, _, text = r.stdout.strip().splitlines()[-1].partition(" ")
    return int(cod_http), text


def exercitiu(
    sursa_admin: str,
    sursa_app: str,
    *,
    media: Path | None = None,
    config: list[Path] | None = None,
    tinta_ore: float = TINTA_ORE,
    pastreaza: bool = False,
    lucru: Path | None = None,
) -> dict[str, Any]:
    bk = _ama_backup()
    t0 = time.monotonic()
    etape: dict[str, float] = {}
    lucru = lucru or Path(tempfile.mkdtemp(prefix="ama-restaurare-"))
    lucru.mkdir(parents=True, exist_ok=True)
    cheie = lucru / "cheie-proprietar.key"
    r = subprocess.run(["age-keygen", "-o", str(cheie)], capture_output=True, text=True, check=True)
    publica = (r.stderr + r.stdout).split("Public key:")[1].split()[0]
    cfg = bk.Config(
        database_url=bk.libpq_url(sursa_admin),
        dest=str(lucru / "destinatie"),
        recipients=[publica],
        media_dir=media,
        config_paths=config or [],
        workdir=lucru / "work",
        status_dir=lucru / "status",
        admin_url=bk.libpq_url(sursa_admin),
        identity_file=cheie,
        mediu="exercitiu",
    )
    rez: dict[str, Any] = {"schema": "ama.exercitiu_restaurare/1", "tinta_ore": tinta_ore}
    nou = f"ama_restaurare_{uuid.uuid4().hex[:10]}"
    admin_nou = bk.with_database(bk.libpq_url(sursa_admin), nou)
    media_nou = lucru / "mediu-curat" / "media"
    creat = False
    try:
        # 1. backup-ul real, ca în producție
        b = bk.run_op("backup", cfg)
        if b["stare"] != "reusit":
            raise RuntimeError(f"backup eșuat: {b['eroare']}")
        etape["backup_sec"] = time.monotonic() - t0
        snap = b["id"]
        # 2. mediul curat: o bază nouă și un director media nou; doar copia trece dintr-o parte în alta
        t = time.monotonic()
        copie = lucru / "mediu-curat" / "copie"
        subprocess.run(["rclone", "copy", f"{cfg.dest}/{snap}", str(copie)], check=True, capture_output=True)
        manifest = json.loads((copie / "manifest.json").read_text(encoding="utf-8"))
        if probleme := bk.verify_manifest(manifest, copie):
            raise RuntimeError("copie coruptă: " + "; ".join(probleme))
        _psql(bk.libpq_url(sursa_admin), f'CREATE DATABASE "{nou}"')
        creat = True
        bk._decrypt_to(
            ["pg_restore", "--exit-on-error", "--dbname", admin_nou], copie / "baza.dump.age", cheie
        )
        media_nou.mkdir(parents=True)
        if (copie / "media.tar.gz.age").exists():
            bk._decrypt_to(["tar", "-xzf", "-", "-C", str(media_nou)], copie / "media.tar.gz.age", cheie)
        etape["restaurare_sec"] = time.monotonic() - t
        # 3. verificarea
        t = time.monotonic()
        sursa = bk.libpq_url(sursa_admin)
        app_nou = bk.with_database(bk.libpq_url(sursa_app), nou)
        n_sursa, n_nou = _numaratori(sursa), _numaratori(admin_nou)
        cod_http, text_http = _readyz(app_nou.replace("postgresql://", "postgresql+psycopg://", 1), media_nou)
        verificari = {
            "migrari": _psql(sursa, "SELECT version_num FROM alembic_version")
            == _psql(admin_nou, "SELECT version_num FROM alembic_version"),
            "randuri": n_sursa == n_nou and len(n_sursa) > 0,
            "rls": _rls(sursa) == _rls(admin_nou) and len(_rls(sursa)) > 0,
            "media": _sume(media) == _sume(media_nou),
            "functionala": cod_http == 200,
        }
        etape["verificare_sec"] = time.monotonic() - t
        diferente = sorted(k for k in set(n_sursa) | set(n_nou) if n_sursa.get(k) != n_nou.get(k))
        total = time.monotonic() - t0
        rez.update(
            copie=snap,
            tabele=len(n_nou),
            randuri=sum(n_nou.values()),
            fisiere_media=len(_sume(media_nou)),
            verificari=verificari,
            diferente_tabele=diferente[:20],
            readyz=text_http if cod_http != 200 else "ok",
            etape={k: round(v, 2) for k, v in etape.items()},
            durata_sec=round(total, 2),
            in_tinta=total <= tinta_ore * 3600,
        )
        rez["trecut"] = all(verificari.values()) and rez["in_tinta"]
        return rez
    except Exception as exc:  # raportul spune unde s-a oprit exercițiul
        rez.update(trecut=False, eroare=f"{type(exc).__name__}: {exc}"[:500], etape=etape)
        return rez
    finally:
        if creat and not pastreaza:
            with contextlib.suppress(subprocess.CalledProcessError):
                _psql(bk.libpq_url(sursa_admin), f'DROP DATABASE IF EXISTS "{nou}" WITH (FORCE)')
        if not pastreaza:
            shutil.rmtree(lucru, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--sursa-admin", required=True)
    p.add_argument("--sursa-app", required=True)
    p.add_argument("--media", type=Path)
    p.add_argument("--config", type=Path, action="append", default=[])
    p.add_argument("--tinta-ore", type=float, default=TINTA_ORE)
    p.add_argument("--pastreaza", action="store_true", help="nu șterge baza și directorul restaurate")
    a = p.parse_args(argv)
    rez = exercitiu(
        a.sursa_admin,
        a.sursa_app,
        media=a.media,
        config=a.config,
        tinta_ore=a.tinta_ore,
        pastreaza=a.pastreaza,
    )
    print(json.dumps(rez, ensure_ascii=False, indent=1))
    return 0 if rez.get("trecut") else 1


if __name__ == "__main__":
    sys.exit(main())
