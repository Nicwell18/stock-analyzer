# Deal Term Analyzer

Herramienta en Python que lee contratos de M&A (merger agreements de empresas
cotizadas), extrae las cláusulas que mueven valor y riesgo, y las compara con
un estándar de mercado definido por el usuario. Cada veredicto
(*market / off-market / aggressive*) cita el texto exacto del contrato.

Es un proyecto de aprendizaje: la prioridad es que cada paso sea claro y
trazable, no la escala.

## Estado

| Capa | Qué hace | Estado |
|---|---|---|
| 1. Ingesta | HTML o PDF → una pieza por cada Section del contrato | Hecha. Probada solo con un contrato sintético; falta un contrato real |
| 2. Extracción | Localiza las cláusulas objetivo, con cita y ubicación | Pendiente |
| 3. Red flags | Compara cada cláusula con el playbook | Pendiente |
| 4. Output | Tabla exportable a CSV / Markdown | Pendiente |

## Idea de diseño: motor y conocimiento separados

- `deal_analyzer/` es **el motor**. No contiene nada jurídico.
- `config/` (aún no existe) contendrá **el conocimiento**: la lista de
  cláusulas objetivo y el playbook de estándares de mercado.

Añadir otro tipo de contrato (p. ej. credit agreements) debe ser añadir dos
archivos de configuración, sin tocar el motor.

## Uso

```bash
pip install -r requirements.txt

python main.py data/contracts/contrato.htm              # tabla con todas las sections
python main.py data/contracts/contrato.htm --show 5.3   # texto literal de una section
python main.py data/contracts/contrato.htm --json       # guarda los chunks en output/
```

Acepta `.htm` / `.html` (el formato nativo de EDGAR) y `.pdf`. Para conseguir
un contrato: abrir el Exhibit 2.1 del 8-K en EDGAR y *Guardar página como →
solo HTML*.

## Capa 1: cómo funciona la ingesta

Todo está en `deal_analyzer/ingest.py`, en tres pasos:

1. **`load_html`** o **`load_pdf`**: convierten el archivo en líneas de texto.
   El HTML da un párrafo por línea y es más limpio; el PDF guarda además la
   página de cada línea (para citar "p. 41").
2. **`clean_lines`** (solo PDF): quita cabeceras, pies y números de página.
   Una línea es cabecera o pie si está en el borde de la página y se repite en
   más de la mitad de las páginas.
3. **`split_into_chunks`**: abre una pieza nueva en cada encabezado
   `Section N.M`. No sabe de qué formato vinieron las líneas.

### Por qué trocear por Section y no por tamaño

Un troceado por tamaño fijo (cada 1.000 caracteres) corta las cláusulas por la
mitad y pierde la ubicación. En un contrato, la Section es la unidad con
sentido jurídico y es como se cita. Si la pieza es la Section, la cita y la
ubicación salen gratis.

### Los tres problemas y cómo se resuelven

| Problema | Solución |
|---|---|
| El índice repite todos los encabezados | El cuerpo empieza en el último `ARTICLE I` antes de las firmas |
| Los anexos tienen sus propios `ARTICLE I` | El cuerpo termina en `IN WITNESS WHEREOF`; el resto es `back_matter` |
| Referencias cruzadas a principio de línea ("Section 5.3 of this Agreement") | Un encabezado solo vale si su número es mayor que el anterior, está en el artículo actual y va seguido de un título en mayúscula |

Además, `check_numbering` avisa si falta algún número (5.1, 5.2, 5.4): un hueco
casi siempre es un encabezado que se ha escapado.

### Limitaciones conocidas

- Los PDF deben tener texto (no escaneados). El HTML no tiene números de página.
- Asume la estructura `ARTICLE` + `Section N.M`. Un contrato que numere de otra
  forma (solo "1.", "2.") no se trocea.
- Una referencia a la section *inmediatamente siguiente*, a principio de línea
  y seguida de palabras en mayúscula, se confundiría con su encabezado.
- Las Sections muy largas (p. ej. Definitions) quedan como una sola pieza.

## Estructura

```
deal_analyzer/ingest.py   capa 1
main.py                   enseña el troceado de un contrato
data/contracts/           contratos (.htm o .pdf)
tests/                    pruebas con un contrato sintético
```

## Dependencias

- `pdfplumber`: extrae el texto de los PDF conservando el orden de lectura.
  El HTML se lee con la librería estándar de Python, sin dependencias.
- `pytest` (solo para las pruebas): `python -m pytest`.
