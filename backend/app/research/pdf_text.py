import contextlib
import io
import json
import sys


def main() -> None:
    with contextlib.suppress(ImportError, ValueError, OSError):
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
        resource.setrlimit(resource.RLIMIT_AS, (2_000_000_000, 2_000_000_000))
    from pypdf import PdfReader

    data = sys.stdin.buffer.read(6_000_001)
    if len(data) > 6_000_000:
        raise ValueError("PDF too large")
    reader = PdfReader(io.BytesIO(data), strict=True)
    if reader.is_encrypted:
        raise ValueError("Encrypted PDF")
    result, size = [], 0
    for index, page in enumerate(reader.pages[:20]):
        text = page.extract_text() or ""
        if text.count("\ufffd") > max(5, len(text) // 100):
            raise ValueError("Unreliable extraction")
        size += len(text)
        if size > 150000:
            break
        if text.strip():
            result.append({"location": f"PDF page {index + 1}", "text": text})
    if not result:
        raise ValueError("OCR review required")
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(2)
