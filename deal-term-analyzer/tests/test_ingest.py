"""Pruebas de la ingesta sobre un contrato SINTÉTICO (inventado) con trampas:
índice con números de página, referencias cruzadas a principio de línea,
cabeceras/pies de navegador y un anexo con su propio "ARTICLE I".

Ejecutar desde la carpeta del proyecto:  python -m pytest
"""

import pytest

from deal_analyzer.ingest import check_numbering, ingest

PDF = ingest("tests/fixtures/synthetic_merger_agreement.pdf")
HTML = ingest("tests/fixtures/synthetic_merger_agreement.html")

# Cada prueba se ejecuta dos veces: con el PDF y con el HTML del mismo contrato
pytestmark = pytest.mark.parametrize("CHUNKS", [PDF, HTML], ids=["pdf", "html"])


def sections(chunks):
    return {c.number: c for c in chunks if c.kind == "section"}


def test_finds_every_section_once(CHUNKS):
    SECTIONS = sections(CHUNKS)
    assert list(SECTIONS) == [
        "1.1", "1.2", "1.3", "1.4", "2.1", "2.2", "2.3",
        "3.1", "3.2", "3.3", "3.4", "4.1", "4.2", "4.3", "5.1", "5.2", "5.3",
    ]
    assert check_numbering(CHUNKS) == []


def test_titles_and_articles(CHUNKS):
    SECTIONS = sections(CHUNKS)
    assert SECTIONS["4.2"].title == "No Solicitation"
    assert SECTIONS["4.2"].article == "ARTICLE IV"
    assert SECTIONS["4.2"].article_title == "COVENANTS"
    assert SECTIONS["5.3"].title == "Termination Fee"


def test_cross_references_stay_inside_their_section(CHUNKS):
    SECTIONS = sections(CHUNKS)
    # La mención a "Section 5.3 Termination Fee shall..." vive dentro de la 5.1
    assert "Section 5.3 Termination Fee shall be payable" in SECTIONS["5.1"].text


def test_headers_and_footers_are_removed(CHUNKS):
    SECTIONS = sections(CHUNKS)
    for chunk in CHUNKS:
        assert "example.com" not in chunk.text
        assert "AM Document" not in chunk.text


def test_article_intro_and_exhibits_are_separate(CHUNKS):
    SECTIONS = sections(CHUNKS)
    kinds = [c.kind for c in CHUNKS]
    assert kinds[0] == "preamble" and kinds[-1] == "back_matter"
    intro = [c for c in CHUNKS if c.kind == "article_intro"]
    assert len(intro) == 1 and "Company Disclosure Letter" in intro[0].text
    assert "CERTIFICATE OF INCORPORATION" in CHUNKS[-1].text


def test_html_has_no_pages(CHUNKS):
    if CHUNKS is HTML:
        assert sections(CHUNKS)["4.2"].location == "Section 4.2"
    else:
        assert sections(CHUNKS)["4.2"].location == "Section 4.2 (p. 14)"
