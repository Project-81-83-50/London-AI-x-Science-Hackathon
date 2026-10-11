import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path

from .models import Source

INDEX_VERSION = "bm25-lsa-v1"


class Store:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.directory / "research.sqlite3"
        self.db = sqlite3.connect(path, timeout=15)
        os.chmod(path, 0o600)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE VIRTUAL TABLE IF NOT EXISTS source_search USING fts5(id UNINDEXED, title, text);
            CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS results(key TEXT PRIMARY KEY, created REAL, payload TEXT);
        """)
        self._index_key = None
        self._vectorizer = self._reducer = self._vectors = None
        self._vector_ids: list[str] = []

    def close(self) -> None:
        self.db.close()

    def version(self) -> str:
        payloads = self.db.execute("SELECT payload FROM sources ORDER BY id").fetchall()
        return hashlib.sha256((INDEX_VERSION + "\n" + "\n".join(row[0] for row in payloads)).encode()).hexdigest()

    def put(self, source: Source) -> None:
        previous = self.db.execute("SELECT payload FROM sources WHERE id=?", (source.id,)).fetchone()
        if previous:
            old = Source.model_validate_json(previous[0])
            if old.content_hash == source.content_hash and old.status == "approved" and source.updates != "notice":
                source = source.model_copy(update={"status": "approved"})
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO sources VALUES(?,?)", (source.id, source.model_dump_json()))
            self.db.execute("DELETE FROM source_search WHERE id=?", (source.id,))
            self.db.execute("INSERT INTO source_search VALUES(?,?,?)", (source.id, source.title, source.text))
        self._index_key = None

    def sources(self) -> dict[str, Source]:
        return {
            s.id: s
            for (raw,) in self.db.execute("SELECT payload FROM sources")
            if (s := Source.model_validate_json(raw))
        }

    def admit(self, source_id: str, approved: bool) -> None:
        source = self.sources().get(source_id)
        if source is None:
            raise ValueError("Unknown source ID")
        if approved and source.updates == "notice":
            raise ValueError("Resolve the post-publication notice before source admission")
        source.status = "approved" if approved else "excluded"
        with self.db:
            self.db.execute("UPDATE sources SET payload=? WHERE id=?", (source.model_dump_json(), source_id))
        self._index_key = None

    def seed(self, path: Path) -> None:
        if not path.is_file():
            return
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        previous = self.db.execute("SELECT value FROM metadata WHERE key='seed'").fetchone()
        if previous and previous[0] == digest:
            return
        records = json.loads(data)
        for source in self.sources().values():
            if source.access == "seed":
                self.admit(source.id, False)
        for group in ("features", "properties", "imaging_modes", "artifacts"):
            rows = records.get(group, [])
            rows = rows.values() if isinstance(rows, dict) else rows
            for index, row in enumerate(rows):
                if not isinstance(row, dict) or row.get("verification", {}).get("status") in {"deleted", "retracted"}:
                    continue
                text = json.dumps(row, ensure_ascii=False)
                content_hash = hashlib.sha256(text.encode()).hexdigest()
                sid = "S" + hashlib.sha256((group + str(index) + content_hash).encode()).hexdigest()[:20]
                self.put(
                    Source(
                        id=sid,
                        document_id=f"seed:{group}:{row.get('id', index)}",
                        title=row.get("name", group),
                        text=text,
                        location=f"local reference/{group}/{index}",
                        content_hash=content_hash,
                        access="seed",
                        status="approved",
                        checked_at=time.time(),
                        caveats=[
                            "Title/abstract-level checks only; original full text was not reviewed.",
                            "Illustrative values are not acceptance thresholds. Use this as a discovery lead.",
                        ],
                    )
                )
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO metadata VALUES('seed',?)", (digest,))

    def search(
        self,
        query: str,
        candidate_ids: set[str],
        max_age: int,
        limit: int = 6,
        originals_only: bool = False,
        exclude_ids: set[str] | None = None,
    ) -> list[Source]:
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.preprocessing import normalize

        available = {
            key: source
            for key, source in self.sources().items()
            if source.status != "excluded"
            and key not in (exclude_ids or set())
            and (not originals_only or source.access in {"full_text", "technical"})
            and source.updates != "notice"
            and (source.status == "approved" or key in candidate_ids)
            and (source.access == "seed" or 0 <= time.time() - source.checked_at <= max_age)
        }
        if not available:
            return []
        terms = list(dict.fromkeys(re.findall(r"[a-z][a-z0-9]+", query.lower())))[:24]
        expression = " OR ".join('"' + term + '"' for term in terms)
        lexical = (
            [
                row[0]
                for row in self.db.execute(
                    "SELECT id FROM source_search WHERE source_search MATCH ? ORDER BY bm25(source_search) LIMIT 100",
                    (expression,),
                )
                if row[0] in available
            ]
            if expression
            else []
        )
        ranks = {key: 1 / (60 + i) for i, key in enumerate(lexical, 1)}
        index_key = tuple(sorted((key, source.content_hash) for key, source in available.items()))
        if self._index_key != index_key:
            self._vector_ids = sorted(available)
            self._vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=20000, sublinear_tf=True)
            vectors = self._vectorizer.fit_transform(
                [available[key].title + " " + available[key].text for key in self._vector_ids]
            )
            self._reducer = None
            if min(vectors.shape) > 3:
                self._reducer = TruncatedSVD(n_components=min(64, min(vectors.shape) - 1), random_state=0)
                vectors = self._reducer.fit_transform(vectors)
            self._vectors = normalize(vectors)
            self._index_key = index_key
        vector = self._vectorizer.transform([query])
        if self._reducer is not None:
            vector = self._reducer.transform(vector)
        scores = self._vectors @ normalize(vector).T
        scores = scores.toarray().ravel() if hasattr(scores, "toarray") else scores.ravel()
        for i, index in enumerate(scores.argsort()[::-1][:100], 1):
            if scores[index] > 0:
                key = self._vector_ids[index]
                ranks[key] = ranks.get(key, 0) + 1 / (60 + i)
        return [available[key] for key in sorted(ranks, key=lambda k: (-ranks[k], k))[:limit]]

    def cached(self, key: str, ttl: int) -> dict | None:
        row = self.db.execute("SELECT created,payload FROM results WHERE key=?", (key,)).fetchone()
        if row and 0 <= time.time() - row[0] <= ttl:
            try:
                return json.loads(row[1])
            except ValueError:
                return None
        return None

    def cache(self, key: str, result: dict) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO results VALUES(?,?,?)",
                (key, time.time(), json.dumps(result, ensure_ascii=False)),
            )
