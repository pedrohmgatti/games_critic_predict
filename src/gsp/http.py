"""Sessão HTTP "educada": rate limit, retries com backoff e cache em disco.

O cache guarda a resposta bruta (gzip) indexada por URL+parâmetros, então qualquer
etapa pode ser re-executada/re-parseada sem bater no servidor de novo.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

from gsp.config import HTTP_CACHE

log = logging.getLogger(__name__)


class PoliteSession:
    def __init__(
        self,
        user_agent: str,
        min_interval: float,
        cache_dir: Path = HTTP_CACHE,
        namespace: str = "default",
        max_retries: int = 8,
        timeout: float = 60,
    ):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = user_agent
        self.min_interval = min_interval
        self.cache_dir = cache_dir / namespace
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_retries = max_retries
        self.timeout = timeout
        self._last = 0.0

    def _key(self, url: str, params, data=None) -> Path:
        raw = url + "?" + urlencode(params or [], doseq=True)
        if data:
            raw += "#POST#" + urlencode(data, doseq=True)
        return self.cache_dir / (hashlib.sha1(raw.encode()).hexdigest() + ".gz")

    def is_cached(self, url: str, params=None) -> bool:
        return self._key(url, params).exists()

    def get_text(self, url: str, params=None, headers=None, use_cache: bool = True,
                 validate=None, data=None) -> str:
        """GET (ou POST se `data` for dado), com cache.

        `validate(text) -> bool`: respostas inválidas não são cacheadas e são refeitas.
        """
        path = self._key(url, params, data)
        if use_cache and path.exists():
            return gzip.decompress(path.read_bytes()).decode("utf-8", errors="replace")

        for attempt in range(1, self.max_retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                r = self.s.request("POST" if data else "GET", url, params=params, data=data,
                                   headers=headers, timeout=self.timeout)
            except requests.RequestException as e:
                log.warning("erro de rede (%s) tentativa %d: %s", url, attempt, e)
            else:
                if r.status_code == 200:
                    text = r.text
                    if validate is None or validate(text):
                        if use_cache:
                            path.write_bytes(gzip.compress(text.encode("utf-8")))
                        return text
                    log.warning("resposta inválida/truncada em %s (tentativa %d)", url, attempt)
                else:
                    log.warning("HTTP %s em %s (tentativa %d)", r.status_code, url, attempt)
                    if r.status_code not in (429, 500, 502, 503, 504, 520, 522, 524):
                        r.raise_for_status()
            # backoff exponencial até 10 min: tolera ~20 min de indisponibilidade/bloqueio
            time.sleep(min(600, 5 * 2 ** (attempt - 1)))
        raise RuntimeError(f"falha após {self.max_retries} tentativas: {url}")

    def get_json(self, url: str, params=None, headers=None, use_cache: bool = True):
        return json.loads(self.get_text(url, params=params, headers=headers, use_cache=use_cache))
