import hashlib
import http.client
import ipaddress
import json
import re
import socket
import ssl
import subprocess
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urlencode, urljoin, urlsplit

from .config import ResearchError
from .facts import CONCEPTS
from .models import Source

TECHNICAL = {
    "detector_contrast": [
        (
            "JEOL: low-kV SEM imaging and detector contrast",
            "https://www.jeolusa.com/RESOURCES/Electron-Optics/Documents-Downloads/some-thoughts-on-why-you-want-to-use-low-kv-imaging",
        )
    ],
}


class SourceError(ResearchError):
    def __init__(self, message: str):
        super().__init__("source_unavailable", message)


class Transport:
    def __init__(self, requests: int, deadline: float, timeout: float = 20):
        self.limit = requests
        self.deadline = deadline
        self.timeout = timeout
        self.count = 0

    @staticmethod
    def resolve(url: str) -> tuple:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            raise SourceError("Only public HTTPS sources without embedded credentials are allowed")
        addresses = sorted({row[4][0] for row in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)})
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise SourceError("Private-network source addresses are blocked")
        return parsed, addresses[0]

    def get(self, url: str, headers: dict | None = None, limit: int = 6_000_000) -> tuple[bytes, str]:
        for _ in range(5):
            if self.count >= self.limit or time.monotonic() >= self.deadline:
                raise SourceError("Online research budget exhausted")
            self.count += 1
            connection = None
            try:
                parsed, address = self.resolve(url)
                timeout = max(0.1, min(self.timeout, self.deadline - time.monotonic()))
                connection = http.client.HTTPSConnection(parsed.hostname, timeout=timeout)
                sock = socket.create_connection((address, 443), timeout=timeout)
                connection.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=parsed.hostname)
                path = parsed.path or "/"
                if parsed.query:
                    path += "?" + parsed.query
                connection.request(
                    "GET",
                    path,
                    headers={"User-Agent": "SEMResearch/1.0", "Accept-Encoding": "identity", **(headers or {})},
                )
                response = connection.getresponse()
                if response.status in {301, 302, 303, 307, 308}:
                    destination = response.getheader("Location")
                    if not destination:
                        raise SourceError("Source redirect has no destination")
                    url, headers = urljoin(url, destination), {}
                    continue
                if response.status != 200:
                    raise SourceError(f"Source returned HTTP {response.status}")
                if response.getheader("Content-Encoding", "identity") not in {"identity", ""}:
                    raise SourceError("Compressed source responses require offline review")
                length = response.getheader("Content-Length")
                if length and int(length) > limit:
                    raise SourceError("Source exceeds size limit")
                body = bytearray()
                while True:
                    remaining = self.deadline - time.monotonic()
                    if remaining <= 0:
                        raise SourceError("Source read deadline exhausted")
                    if connection.sock:
                        connection.sock.settimeout(min(timeout, remaining))
                    chunk = response.read(min(65536, limit + 1 - len(body)))
                    if not chunk:
                        break
                    body.extend(chunk)
                    if len(body) > limit:
                        raise SourceError("Source exceeds size limit")
                return bytes(body), response.getheader("Content-Type", "")
            except (OSError, ValueError, http.client.HTTPException) as exc:
                raise SourceError("Source transport or metadata failed") from exc
            finally:
                if connection:
                    connection.close()
        raise SourceError("Too many source redirects")

    def json(self, url: str, headers: dict | None = None) -> dict:
        body, _ = self.get(url, headers, limit=3_000_000)
        try:
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError("Expected metadata object")
            return data
        except ValueError as exc:
            raise SourceError("Invalid scholarly metadata") from exc


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "nav", "header", "footer"}:
            self.skip += 1
        if tag in {"p", "h1", "h2", "h3", "section", "li"} and not self.skip:
            self.parts.append("\n\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "nav", "header", "footer"} and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def extract(body: bytes, kind: str) -> list[dict]:
    if body.startswith(b"%PDF") or "pdf" in kind.lower():
        try:
            process = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("pdf_text.py"))],
                input=body,
                capture_output=True,
                timeout=25,
            )
            if process.returncode:
                raise SourceError("PDF extraction needs review")
            return json.loads(process.stdout)
        except (subprocess.TimeoutExpired, ValueError) as exc:
            raise SourceError("PDF extraction quarantined") from exc
    if any(format_name in kind.lower() for format_name in ("html", "xml", "text/plain")):
        parser = TextParser()
        parser.feed(body.decode("utf-8", errors="replace"))
        text = re.sub(r"[ \t]+", " ", "".join(parser.parts)).strip()
        if len(text) < 150:
            raise SourceError("Insufficient readable source content")
        return [{"location": "HTML/XML text", "text": text[:150000]}]
    raise SourceError("Unsupported source format")


def split_passages(text: str, size: int = 2200):
    block = ""
    for paragraph in re.split(r"\n\s*\n", text):
        if len(block) + len(paragraph) > size and block:
            yield block.strip()
            block = ""
        if len(paragraph) > size:
            for offset in range(0, len(paragraph), size):
                yield paragraph[offset : offset + size]
        else:
            block += paragraph + "\n\n"
    if block.strip():
        yield block.strip()


PUBLIC_QUERIES = {
    "detector_contrast": (
        "SEM secondary backscattered electron contrast",
        "SEM detector contrast topography charging",
        "SEM compositional contrast artefacts",
    ),
    "porosity": (
        "lithium ion electrode porosity microscopy",
        "electrode porosity two dimensional stereology",
        "electrode porosity segmentation uncertainty",
    ),
    "particles": (
        "silicon oxide graphite anode particle size",
        "silicon graphite particle size microscopy segmentation",
        "silicon oxide anode morphology limitations",
    ),
    "carbon_binder": (
        "lithium ion electrode carbon binder SEM",
        "carbon binder domain segmentation uncertainty",
        "carbon binder graphite electron contrast",
    ),
    "attribution": (
        "linear classifier feature attribution",
        "feature attribution explanation limitations",
        "saliency maps sanity checks",
    ),
    "transport": (
        "battery electrode Bruggeman tortuosity",
        "electrode Bruggeman tortuosity assumptions",
        "electrode Bruggeman tortuosity deviations",
    ),
    "anisotropy": (
        "battery electrode pore anisotropy",
        "electrode pore chord length microscopy",
        "electrode anisotropy stereology limitations",
    ),
}


class ResearchSources:
    def __init__(self, transport: Transport, env: dict[str, str]):
        self.transport = transport
        self.openalex_key = env.get("OPENALEX_API_KEY", "")
        self.warnings: list[str] = []
        self.fetched: set[str] = set()

    def discover(self, concept: str, focus: str) -> list[dict]:
        if concept not in CONCEPTS or focus not in {"meaning", "limitations", "counter_evidence"}:
            raise SourceError("Outbound research requires an approved public concept, not private facts")
        query = PUBLIC_QUERIES[concept][("meaning", "limitations", "counter_evidence").index(focus)]
        candidates = [
            {"title": title, "url": url, "fulltext": url, "technical": True}
            for title, url in TECHNICAL.get(concept, [])
        ]
        try:
            headers = {"Authorization": "Bearer " + self.openalex_key} if self.openalex_key else {}
            data = self.transport.json(
                "https://api.openalex.org/works?"
                + urlencode({"search": query, "per-page": 5, "filter": "type:article|review,is_oa:true"}),
                headers,
            )
            for work in data.get("results", []):
                if work.get("is_retracted") or not work.get("doi"):
                    continue
                location = work.get("best_oa_location") or {}
                positions = {
                    index: word
                    for word, indexes in (work.get("abstract_inverted_index") or {}).items()
                    for index in indexes
                }
                doi = work["doi"].removeprefix("https://doi.org/")
                candidates.append(
                    {
                        "title": work.get("display_name", "Untitled"),
                        "doi": doi,
                        "url": "https://doi.org/" + doi,
                        "fulltext": location.get("pdf_url") or location.get("landing_page_url"),
                        "license": location.get("license"),
                        "open_access": bool(location.get("is_oa")),
                        "year": work.get("publication_year"),
                        "authors": [a.get("author", {}).get("display_name", "") for a in work.get("authorships", [])],
                        "abstract": " ".join(positions[i] for i in sorted(positions)),
                    }
                )
        except (SourceError, TypeError, KeyError) as exc:
            self.warnings.append(str(exc) if isinstance(exc, SourceError) else "OpenAlex metadata was incomplete")
        if not any(c.get("doi") for c in candidates):
            try:
                data = self.transport.json(
                    "https://api.crossref.org/works?" + urlencode({"query.bibliographic": query, "rows": 5})
                )
                for work in data.get("message", {}).get("items", []):
                    if work.get("DOI"):
                        candidates.append(
                            {
                                "title": (work.get("title") or ["Untitled"])[0],
                                "doi": work["DOI"],
                                "url": "https://doi.org/" + work["DOI"],
                                "abstract": re.sub(r"<[^>]+>", " ", work.get("abstract", "")),
                            }
                        )
            except (SourceError, TypeError, KeyError) as exc:
                self.warnings.append(str(exc) if isinstance(exc, SourceError) else "Crossref metadata was incomplete")

        def priority(candidate):
            if candidate.get("technical"):
                return 0
            accessible = (
                candidate.get("fulltext")
                and candidate.get("open_access")
                and candidate.get("license") in {"cc-by", "cc-by-sa", "cc0", "public-domain"}
            )
            return 1 if accessible else 2

        return sorted(candidates, key=priority)

    def fetch(self, candidate: dict) -> list[Source]:
        candidate = dict(candidate)
        doi, updates = candidate.get("doi"), "unknown"
        if doi:
            try:
                metadata = self.transport.json("https://api.crossref.org/works/" + quote(doi, safe=""))["message"]
                a = set(re.findall(r"\w+", (metadata.get("title") or [""])[0].lower()))
                b = set(re.findall(r"\w+", candidate["title"].lower()))
                if a and len(a & b) / max(len(a | b), 1) < 0.45:
                    raise ValueError("DOI/title mismatch")
                for license_info in metadata.get("license", []):
                    license_url = license_info.get("URL", "")
                    parsed_license = urlsplit(license_url)
                    if parsed_license.hostname in {
                        "creativecommons.org",
                        "www.creativecommons.org",
                    } and parsed_license.path.startswith(("/licenses/by/", "/licenses/by-sa/", "/publicdomain/zero/")):
                        links = metadata.get("link", [])
                        if not candidate.get("fulltext"):
                            candidate["fulltext"] = next(
                                (
                                    link["URL"]
                                    for link in links
                                    if link.get("content-type") in {"application/pdf", "application/xml", "text/xml"}
                                ),
                                candidate["url"],
                            )
                        candidate.update(
                            open_access=True,
                            license="cc0"
                            if "zero" in parsed_license.path
                            else "cc-by-sa"
                            if "by-sa" in parsed_license.path
                            else "cc-by",
                        )
                        break
                notices = self.transport.json(
                    "https://api.crossref.org/works?" + urlencode({"filter": "updates:" + doi, "rows": 5})
                )["message"]["items"]
                updates = "notice" if notices or metadata.get("update-to") else "none_found"
            except SourceError:
                self.warnings.append("Publication-update lookup unavailable; source status remains unknown.")
            except (KeyError, TypeError, ValueError) as exc:
                raise SourceError("Inconsistent DOI metadata") from exc
        if updates == "notice":
            raise SourceError("Source has a post-publication notice; excluded pending human review")
        pages, access = [], "abstract"
        permitted = (
            candidate.get("technical")
            or candidate.get("open_access")
            and candidate.get("license") in {"cc-by", "cc-by-sa", "cc0", "public-domain"}
        )
        if candidate.get("fulltext") and permitted:
            try:
                body, kind = self.transport.get(candidate["fulltext"])
                pages = extract(body, kind)
                access = "technical" if candidate.get("technical") else "full_text"
            except SourceError as exc:
                self.warnings.append(str(exc))
        if not pages and candidate.get("abstract"):
            pages = [{"location": "Abstract", "text": candidate["abstract"]}]
        if not pages:
            raise SourceError("No readable, lawfully accessible full text or abstract")
        result = []
        for page in pages:
            for index, text in enumerate(split_passages(page["text"])):
                digest = hashlib.sha256(text.encode()).hexdigest()
                identity = doi or candidate["url"]
                sid = (
                    "S" + hashlib.sha256((identity + page["location"] + str(index) + digest).encode()).hexdigest()[:20]
                )
                result.append(
                    Source(
                        id=sid,
                        document_id=identity,
                        title=candidate["title"],
                        text=text,
                        url=candidate["url"],
                        doi=doi,
                        year=candidate.get("year"),
                        authors=candidate.get("authors", []),
                        location=f"{page['location']}, passage {index + 1}",
                        content_hash=digest,
                        access=access,
                        license=candidate.get("license"),
                        updates=updates,
                        checked_at=time.time(),
                        caveats=[
                            "Applicability to this sample requires review; publication alone does not establish relevance."
                        ]
                        + (
                            ["Abstract only; supporting methods and results were not inspected."]
                            if access == "abstract"
                            else []
                        ),
                    )
                )
        return result[:80]
