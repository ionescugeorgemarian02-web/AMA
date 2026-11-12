"""Ajutoare pentru testele de avarie: workeri reali (subprocese), așteptări fără pauze lungi."""

import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from tests.conftest import ROOT, BazaTest


def asteapta(conditie: Callable[[], bool], *, timeout_sec: float = 30.0, mesaj: str = "condiția") -> None:
    """Sondează des și scurt; pică cu mesaj la expirare (nu există `sleep` lung în teste)."""
    limita = time.monotonic() + timeout_sec
    while not conditie():
        if time.monotonic() > limita:
            raise AssertionError(f"{mesaj} nu s-a îndeplinit în {timeout_sec} s")
        time.sleep(0.02)


class Worker:
    """Un proces `python -m app.worker` real, pe baza de test."""

    def __init__(
        self, baza: BazaTest, dir_proba: Path, *, worker_id: str = "worker-test", **mediu: str
    ) -> None:
        self.jurnal = dir_proba / f"{worker_id}.log"
        self._mediu = {
            **os.environ,
            "AMA_ENV": "test",
            "AMA_DATABASE_URL": baza.app_url,
            "AMA_DATABASE_OWNER_URL": baza.owner_url,
            "AMA_WORKER_ID": worker_id,
            "AMA_WORKER_MODULE_TEST": "tests.chaos.fluxuri_proba",
            "AMA_PROBA_DIR": str(dir_proba),
            "AMA_MOTOR_POLLING_SEC": "0.1",
            "AMA_WORKER_OPRIRE_SEC": "5",
            **mediu,
        }
        self.proces: subprocess.Popen[bytes] | None = None

    def porneste(self) -> "Worker":
        iesire = self.jurnal.open("ab")
        self.proces = subprocess.Popen(
            [sys.executable, "-m", "app.worker"],
            cwd=ROOT,
            env=self._mediu,
            stdout=iesire,
            stderr=subprocess.STDOUT,
        )
        iesire.close()
        return self

    def asteapta_pornit(self, timeout_sec: float = 30.0) -> None:
        asteapta(lambda: "worker pornit" in self.text(), timeout_sec=timeout_sec, mesaj="pornirea workerului")

    def text(self) -> str:
        return self.jurnal.read_text(encoding="utf-8", errors="replace") if self.jurnal.exists() else ""

    def omoara(self) -> None:
        """SIGKILL: fără nicio șansă de curățare, ca la o cădere reală."""
        assert self.proces is not None
        self.proces.send_signal(signal.SIGKILL)
        self.proces.wait(timeout=10)

    def opreste_curat(self, timeout_sec: float = 30.0) -> int:
        assert self.proces is not None
        self.proces.send_signal(signal.SIGTERM)
        return self.proces.wait(timeout=timeout_sec)

    def viu(self) -> bool:
        return self.proces is not None and self.proces.poll() is None

    def curata(self) -> None:
        if self.viu():
            assert self.proces is not None
            self.proces.kill()
            self.proces.wait(timeout=10)
