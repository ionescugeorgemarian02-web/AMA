"""# SIMULAT: un server de inferență local fals, pe un socket real (loopback), în forma API-ului llama.cpp
`llama-server`: `POST /v1/chat/completions` (cu `usage` și `timings.predicted_per_second`), `POST
/v1/embeddings`, `GET /health`.

Folosit unde contează drumul HTTP real (adaptorul `local`, comanda de măsurare). Viteza fiecărui model se
scriptează (`viteze`: tokeni de ieșire pe secundă, raportați în `timings`); un model absent din `viteze`
primește 404, ca la un llama.cpp care servește alt model. Nicio rețea în afara lui 127.0.0.1.
"""

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class ServerLocalFals:
    def __init__(self, viteze: dict[str, float], *, tokeni_iesire: int = 40, dim: int = 8) -> None:
        self.viteze = viteze
        self.tokeni_iesire = tokeni_iesire
        self.dim = dim
        self.cereri: list[dict[str, Any]] = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a: object) -> None:  # fără zgomot în teste
                return

            def _raspunde(self, cod: int, corp: dict[str, Any]) -> None:
                date = json.dumps(corp).encode()
                self.send_response(cod)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(date)))
                self.end_headers()
                self.wfile.write(date)

            def do_GET(self) -> None:
                self._raspunde(200, {"status": "ok"}) if self.path == "/health" else self._raspunde(404, {})

            def do_POST(self) -> None:
                corp = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                server.cereri.append({"cale": self.path, "corp": corp, "antete": dict(self.headers)})
                if self.path == "/v1/embeddings":
                    texte = corp.get("input", [])
                    date = [
                        {
                            "index": i,
                            "embedding": [b / 255 for b in hashlib.sha256(t.encode()).digest()[: server.dim]],
                        }
                        for i, t in enumerate(texte)
                    ]
                    return self._raspunde(200, {"data": date, "usage": {"prompt_tokens": len(texte) * 3}})
                if self.path != "/v1/chat/completions" or corp.get("model") not in server.viteze:
                    return self._raspunde(404, {"error": {"type": "not_found", "message": "model"}})
                text = '{"eticheta": "pozitiv", "dovezi": ["local"], "incredere": 0.8}'
                self._raspunde(200, {
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 30, "completion_tokens": server.tokeni_iesire},
                    "timings": {"predicted_per_second": server.viteze[corp["model"]]},
                })  # fmt: skip

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._fir = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}/v1"

    def __enter__(self) -> "ServerLocalFals":
        self._fir.start()
        return self

    def __exit__(self, *a: object) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
