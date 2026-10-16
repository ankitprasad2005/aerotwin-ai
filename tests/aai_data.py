"""Real AAI Traffic News fixtures (August 2026) and a helper that turns page text back into a text PDF."""
import json
from pathlib import Path

from app.datasets import aai_traffic

AAI_FIXTURES = Path(__file__).parent / "fixtures" / "aai"
LINE_HEIGHT = 9


def real_pages(annex: int, month: str = "2026_08") -> list[str]:
    """The extracted page text of a real annexure PDF (annexure 2, 3 or 4)."""
    return json.loads((AAI_FIXTURES / f"aai_{month}_annex{annex}.json").read_text(encoding="utf-8"))


def make_pages_pdf(pages: list[str]) -> bytes:
    """A text PDF with one page per entry. Non-latin-1 characters (the Hindi half of the headings) are dropped."""

    def esc(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    objects: list[str] = []
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objects.append("<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>")
    font = 3 + 2 * len(pages)
    for i, page in enumerate(pages):
        lines = [line.encode("latin-1", "ignore").decode("latin-1") for line in page.splitlines()]
        stream = f"BT /F1 7 Tf {LINE_HEIGHT} TL 20 820 Td " + " ".join(f"({esc(line)}) Tj T*" for line in lines) + " ET"
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {4 + 2 * i} 0 R "
            f"/Resources << /Font << /F1 {font} 0 R >> >> >>"
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def index_html() -> bytes:
    return (AAI_FIXTURES / "traffic_news_index.html").read_bytes()


def annex_url(period_file: str, annex: int) -> str:
    base = "https://www.aai.aero/sites/default/files/traffic-news/"
    return f"{base}{period_file}Annex{'_' if annex == 4 and period_file == 'Aug2k26' else ''}{annex}.pdf"


def pages_for(annex: int, month_name: str = "August") -> list[str]:
    """The real August pages, relabelled for another month (the figures stay August's: tests only need the shape)."""
    return [page.replace("August", month_name) for page in real_pages(annex)]


def mock_aai(respx_mock, *, periods=(("Aug2k26", "August"), ("Jul2k26", "July")), index=None):
    """Serve the index and, for every listed month, the three annexures built from the real August pages."""
    import httpx

    respx_mock.get(aai_traffic.INDEX_URL).mock(return_value=httpx.Response(200, content=index or index_html()))
    for period, month_name in periods:
        for annex in aai_traffic.ANNEXES:
            respx_mock.get(annex_url(period, annex)).mock(
                return_value=httpx.Response(200, content=make_pages_pdf(pages_for(annex, month_name)))
            )
