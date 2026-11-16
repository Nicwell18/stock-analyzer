"""Capa 1 - Ingesta.

Convierte un contrato (HTML o PDF) en una lista de "chunks" (trozos), donde cada
chunk es una Section numerada del contrato (1.1, 1.2, ... 5.3, ...).

El proceso tiene tres pasos, cada uno en su función:

    load_html() / load_pdf()   archivo -> líneas de texto
    clean_lines()   (solo PDF)  líneas -> líneas sin cabeceras/pies de página
    split_into_chunks()  líneas    -> lista de Chunk (uno por Section)

Este archivo NO sabe nada de M&A. Solo sabe que los contratos se organizan en
"ARTICLE N" y "Section N.M". Por eso sirve igual para un credit agreement.
"""

import logging
import re
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

import pdfplumber

# pdfminer (la librería que pdfplumber usa por debajo) avisa de detalles de
# las fuentes del PDF que no nos afectan. Solo mostramos errores de verdad.
logging.getLogger("pdfminer").setLevel(logging.ERROR)


# ---------------------------------------------------------------------------
# Estructuras de datos
# ---------------------------------------------------------------------------

@dataclass
class Line:
    """Una línea de texto y la página de la que viene.

    El HTML no tiene páginas: en ese caso page vale 0.
    """
    page: int
    text: str


@dataclass
class Chunk:
    """La unidad de análisis: normalmente, una Section del contrato.

    kind puede ser:
      - "preamble":      todo lo anterior al ARTICLE I (partes, recitals, índice)
      - "article_intro": texto justo debajo de un ARTICLE, antes de su primera
                         Section (p. ej. el lead-in de las representations)
      - "section":       una Section numerada (el caso normal)
      - "back_matter":   firmas y anexos, después de "IN WITNESS WHEREOF"
    """
    kind: str
    article: str        # "ARTICLE V" (vacío en preamble y back_matter)
    article_title: str  # "COVENANTS"
    number: str         # "5.3" (vacío si no es una section)
    title: str          # "No Solicitation"
    text: str           # texto literal completo del chunk
    page_start: int
    page_end: int

    @property
    def location(self) -> str:
        """Ubicación legible para citar: 'Section 5.3 (pp. 41-44)'."""
        if self.kind == "section":
            where = f"Section {self.number}"
        elif self.kind == "article_intro":
            where = f"{self.article} (intro)"
        else:
            where = self.kind
        if self.page_start == 0:  # viene de un HTML: no hay páginas
            return where
        if self.page_start == self.page_end:
            return f"{where} (p. {self.page_start})"
        return f"{where} (pp. {self.page_start}-{self.page_end})"


# ---------------------------------------------------------------------------
# Paso 1 (HTML): archivo -> líneas
# ---------------------------------------------------------------------------

# Etiquetas que en pantalla empiezan en una línea nueva (párrafos, filas de
# tabla...). El resto (<b>, <u>, <font>...) va dentro de la línea.
BLOCK_TAGS = {"p", "div", "br", "tr", "table", "li", "hr", "center",
              "h1", "h2", "h3", "h4", "h5", "h6"}
SKIP_TAGS = {"script", "style", "head"}  # su contenido no es texto del contrato


class TextExtractor(HTMLParser):
    """Recorre el HTML y se queda solo con el texto, línea a línea.

    HTMLParser (de la librería estándar) lee el archivo y nos "avisa" llamando
    a estos métodos cada vez que encuentra una etiqueta o un trozo de texto.
    """

    def __init__(self):
        super().__init__()
        self.lines: list[str] = []
        self.current = ""   # la línea que estamos construyendo
        self.skipping = 0   # > 0 mientras estamos dentro de <script>, <style>...

    def end_line(self):
        text = " ".join(self.current.split())  # colapsa espacios y saltos
        if text:
            self.lines.append(text)
        self.current = ""

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skipping += 1
        elif tag in BLOCK_TAGS:
            self.end_line()
        elif tag == "td":
            self.current += " "  # las celdas de una fila van en la misma línea

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self.skipping -= 1
        elif tag in BLOCK_TAGS:
            self.end_line()

    def handle_data(self, data):
        if not self.skipping:
            self.current += data


def load_html(path: str) -> list[Line]:
    """Lee un contrato en HTML (el formato nativo de EDGAR).

    Ventaja sobre el PDF: cada párrafo es UNA línea. No hay saltos de línea
    artificiales ni cabeceras de página, así que el texto sale más limpio.
    Lo único que quitamos son los números de página que el documento original
    lleva como párrafos sueltos ("12", "- 12 -").
    """
    raw = Path(path).read_bytes()
    try:
        html = raw.decode("utf-8")
    except UnicodeDecodeError:
        html = raw.decode("cp1252")  # codificación habitual en EDGAR antiguo

    extractor = TextExtractor()
    extractor.feed(html)
    extractor.end_line()
    return [Line(page=0, text=t) for t in extractor.lines if not PAGE_NUMBER_RE.match(t)]


# ---------------------------------------------------------------------------
# Paso 1 (PDF): archivo -> líneas
# ---------------------------------------------------------------------------

def load_pdf(path: str) -> list[Line]:
    """Lee el PDF y devuelve todas sus líneas, recordando la página de cada una.

    Guardamos la página porque luego queremos poder decir "esto está en la
    página 41": es parte de la trazabilidad.
    """
    lines = []
    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""  # None si la página no tiene texto
            for text in page_text.splitlines():
                lines.append(Line(page=page_number, text=text.strip()))
    return lines


# ---------------------------------------------------------------------------
# Paso 2: quitar cabeceras y pies de página
# ---------------------------------------------------------------------------

# Una línea que es solo un número de página: "12", "- 12 -", "Page 12", "A-12", "ii"
PAGE_NUMBER_RE = re.compile(
    r"^[-–—\s]*(?:page\s+)?(?:[A-Z]-)?(?:\d{1,3}|[ivxl]{1,6})[-–—\s]*$", re.IGNORECASE
)

EDGE = 2  # cuántas líneas al principio y al final de cada página miramos


def clean_lines(lines: list[Line]) -> list[Line]:
    """Elimina cabeceras/pies repetidos y números de página sueltos.

    Problema: el PDF mete en mitad del texto cosas como "42" o la URL del
    documento en cada página. Si no las quitamos, aparecen dentro de las
    cláusulas y ensucian las citas.

    Idea: una cabecera o pie es una línea que (a) está en el borde de la
    página y (b) se repite en muchas páginas. Para compararlas ignorando el
    número de página, sustituimos cada dígito por '#':
        "sec.gov/doc.htm 12/98" y "sec.gov/doc.htm 13/98" -> la misma "firma".
    """
    # Agrupar las líneas por página
    pages: dict[int, list[Line]] = {}
    for line in lines:
        pages.setdefault(line.page, []).append(line)

    def signature(text: str) -> str:
        return re.sub(r"\d", "#", text)

    def edge_lines(page_lines: list[Line]) -> list[Line]:
        """Las primeras y últimas EDGE líneas (sin duplicar en páginas cortas)."""
        if len(page_lines) <= 2 * EDGE:
            return page_lines
        return page_lines[:EDGE] + page_lines[-EDGE:]

    # Contar en cuántas páginas aparece cada "firma" en un borde
    counts = Counter()
    for page_lines in pages.values():
        signatures_here = {signature(l.text) for l in edge_lines(page_lines) if l.text}
        counts.update(signatures_here)

    # Es cabecera/pie si aparece en más de la mitad de las páginas (mínimo 3)
    threshold = max(3, len(pages) // 2)
    repeated = {sig for sig, n in counts.items() if n >= threshold}

    cleaned = []
    for page_lines in pages.values():
        edges = {id(l) for l in edge_lines(page_lines)}
        for line in page_lines:
            if id(line) in edges:
                if signature(line.text) in repeated or PAGE_NUMBER_RE.match(line.text):
                    continue  # la saltamos: es cabecera, pie o número de página
            cleaned.append(line)
    return cleaned


# ---------------------------------------------------------------------------
# Paso 3: líneas -> chunks
# ---------------------------------------------------------------------------

# "ARTICLE V" / "Article 5", opcionalmente seguido del título en la misma línea
ARTICLE_RE = re.compile(r"^ARTICLE\s+([IVXLC]+|\d+)\b[\s.:–—-]*(.*)$", re.IGNORECASE)

# "Section 5.3 No Solicitation. (a) The Company shall not..."
# También acepta el estilo sin la palabra Section: "5.3 No Solicitation."
SECTION_RE = re.compile(r"^(?:Section\s+)?(\d+)\.(\d+)\.?(?:\s+(.*))?$", re.IGNORECASE)

# Donde termina el cuerpo del contrato y empiezan firmas y anexos
BACK_MATTER_RE = re.compile(r"^IN WITNESS WHEREOF", re.IGNORECASE)

ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def roman_to_int(roman: str) -> int:
    """'XIV' -> 14. Si un símbolo es menor que el siguiente, se resta (IV = 4)."""
    total = 0
    roman = roman.upper()
    for i, char in enumerate(roman):
        value = ROMAN_VALUES[char]
        if i + 1 < len(roman) and value < ROMAN_VALUES[roman[i + 1]]:
            total -= value
        else:
            total += value
    return total


def article_number(line: Line) -> int | None:
    """Si la línea es un encabezado de ARTICLE, devuelve su número; si no, None."""
    match = ARTICLE_RE.match(line.text)
    if not match:
        return None
    rest = match.group(2)
    # "Article VIII shall survive the Closing" es una frase, no un encabezado:
    # los títulos empiezan en mayúscula, las frases siguen en minúscula.
    if rest[:1].islower():
        return None
    raw = match.group(1)
    return int(raw) if raw.isdigit() else roman_to_int(raw)


def section_number(line: Line) -> tuple[int, int] | None:
    """Si la línea parece un encabezado de Section, devuelve (artículo, sección)."""
    match = SECTION_RE.match(line.text)
    if not match:
        return None
    rest = match.group(3) or ""
    # Un título empieza por mayúscula. Esto descarta referencias cruzadas que
    # caen a principio de línea ("Section 5.3 of this Agreement", "5.3(a)")
    # y cifras ("2.5 billion").
    if rest and not rest[0].isupper():
        return None
    return int(match.group(1)), int(match.group(2))


def is_cross_reference(lines: list[Line], i: int, end: int, article: int, expected: int) -> bool:
    """¿Es la línea i una referencia cruzada disfrazada de encabezado?

    Se llama cuando un candidato se salta números: estamos en la 5.1 y aparece
    "Section 5.3 Termination Fee shall be payable...". Miramos hacia delante
    dentro del mismo artículo: si más abajo aparece la 5.2 (la que tocaba),
    entonces esta 5.3 no era el encabezado real, sino una mención.
    Si la 5.2 no aparece nunca, la aceptamos y check_numbering() avisará
    del hueco.
    """
    for later in lines[i + 1:end]:
        art = article_number(later)
        if art is not None and art > article:
            return False  # hemos llegado al siguiente artículo sin encontrarla
        if section_number(later) == (article, expected):
            return True
    return False


def find_body(lines: list[Line]) -> tuple[int, int]:
    """Devuelve (inicio, fin): los índices entre los que está el cuerpo.

    - fin: la primera línea "IN WITNESS WHEREOF" (después van firmas y anexos,
      que pueden tener sus propios "ARTICLE I" y nos confundirían).
    - inicio: el encabezado "ARTICLE I" del cuerpo. El índice (table of
      contents) también contiene "ARTICLE I", así que cogemos el ÚLTIMO
      "ARTICLE I" antes del fin: el del índice siempre va antes que el real.
    """
    end = len(lines)
    for i, line in enumerate(lines):
        if BACK_MATTER_RE.match(line.text):
            end = i
            break

    firsts = [i for i in range(end) if article_number(lines[i]) == 1]
    if not firsts:
        raise ValueError("No encuentro ningún 'ARTICLE I': ¿es un contrato con artículos?")
    if end < len(lines):
        start = firsts[-1]
    else:
        # Sin "IN WITNESS WHEREOF" no podemos descartar los anexos, así que
        # somos conservadores: el 2º "ARTICLE I" si hay índice, si no el 1º.
        start = firsts[1] if len(firsts) >= 2 else firsts[0]
    return start, end


def split_into_chunks(lines: list[Line]) -> list[Chunk]:
    """Recorre las líneas del cuerpo y abre un chunk nuevo en cada encabezado.

    La regla clave es la numeración MONÓTONA: solo aceptamos un encabezado si
    su número es mayor que el anterior (ARTICLE VI después de ARTICLE V;
    Section 5.4 después de 5.3 y dentro del ARTICLE V). Así una referencia
    cruzada a "Section 2.1" en mitad del artículo 5 nunca abre un chunk.
    Si el número se salta alguno, is_cross_reference() decide.
    """
    start, end = find_body(lines)
    chunks = []

    def make_chunk(kind, chunk_lines, article="", article_title="", number="", title=""):
        text = "\n".join(l.text for l in chunk_lines).strip()
        if not text:
            return
        chunks.append(Chunk(kind, article, article_title, number, title, text,
                            chunk_lines[0].page, chunk_lines[-1].page))

    make_chunk("preamble", lines[:start])

    # Estado mientras recorremos el cuerpo
    current_article = 0        # número del artículo en el que estamos
    current_section = 0        # número de la última section aceptada
    article_label = ""         # "ARTICLE V"
    article_title = ""
    kind, number, title = "", "", ""
    buffer: list[Line] = []    # líneas del chunk que estamos construyendo

    def flush():
        """Cierra el chunk en construcción y lo guarda."""
        if buffer:
            make_chunk(kind, buffer, article_label, article_title, number, title)
        buffer.clear()

    i = start
    while i < end:
        line = lines[i]

        art = article_number(line)
        if art is not None and art > current_article:
            flush()
            current_article, current_section = art, 0
            raw = ARTICLE_RE.match(line.text)
            article_label = f"ARTICLE {raw.group(1).upper()}"
            article_title = raw.group(2).strip()
            # A menudo el título va en la línea siguiente, centrado
            if not article_title and i + 1 < end and section_number(lines[i + 1]) is None:
                article_title = lines[i + 1].text
                i += 1
            kind, number, title = "article_intro", "", ""
            i += 1
            continue

        sec = section_number(line)
        is_heading = (
            sec is not None
            and sec[0] == current_article
            and sec[1] > current_section
            and not (sec[1] > current_section + 1
                     and is_cross_reference(lines, i, end, current_article, current_section + 1))
        )
        if is_heading:
            flush()
            current_section = sec[1]
            raw = SECTION_RE.match(line.text)
            kind = "section"
            number = f"{raw.group(1)}.{raw.group(2)}"
            # Título = lo que va desde el número hasta el primer punto
            title = (raw.group(3) or "").split(". ")[0].rstrip(".")[:120]

        buffer.append(line)
        i += 1

    flush()
    make_chunk("back_matter", lines[end:])
    return chunks


# ---------------------------------------------------------------------------
# Comprobaciones y función principal
# ---------------------------------------------------------------------------

def check_numbering(chunks: list[Chunk]) -> list[str]:
    """Busca huecos en la numeración (5.1, 5.2, 5.4 -> falta 5.3).

    Un hueco casi siempre significa que el troceado se ha saltado un
    encabezado. Preferimos avisar a fallar en silencio.
    """
    warnings = []
    last_article, last_section = 0, 0
    for chunk in chunks:
        if chunk.kind != "section":
            continue
        article, section = (int(n) for n in chunk.number.split("."))
        if article != last_article:
            if article != last_article + 1:
                warnings.append(f"Salto de artículo: del {last_article} al {article}")
            if section != 1:
                warnings.append(f"El artículo {article} empieza en {chunk.number}, no en .1")
        elif section != last_section + 1:
            warnings.append(f"Hueco entre {article}.{last_section} y {chunk.number}")
        last_article, last_section = article, section
    return warnings


def ingest(path: str) -> list[Chunk]:
    """La función que usará el resto del proyecto: archivo -> lista de chunks.

    Elige el lector según la extensión. A partir de ahí el troceado es el
    mismo: split_into_chunks no sabe de qué formato vinieron las líneas.
    """
    extension = Path(path).suffix.lower()
    if extension in (".htm", ".html"):
        lines = load_html(path)
    elif extension == ".pdf":
        lines = clean_lines(load_pdf(path))
    else:
        raise ValueError(f"Formato no soportado: {extension} (usa .htm, .html o .pdf)")
    return split_into_chunks(lines)
