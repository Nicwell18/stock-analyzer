"""Enseña cómo queda troceado un contrato.

Uso:
    python main.py data/contracts/mi_contrato.htm              tabla resumen
    python main.py data/contracts/mi_contrato.htm --show 5.3   texto de una section
    python main.py data/contracts/mi_contrato.htm --json       guarda output/<nombre>.json
"""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from deal_analyzer.ingest import check_numbering, ingest


def main():
    parser = argparse.ArgumentParser(description="Trocea un contrato por Sections.")
    parser.add_argument("contract", help="ruta al contrato (.htm, .html o .pdf)")
    parser.add_argument("--show", metavar="N.M", help="imprime el texto de esa section")
    parser.add_argument("--json", action="store_true", help="guarda los chunks en output/")
    args = parser.parse_args()

    chunks = ingest(args.contract)

    if args.show:
        for chunk in chunks:
            if chunk.number == args.show:
                print(f"{chunk.location} - {chunk.title}\n")
                print(chunk.text)
                return
        print(f"No existe la section {args.show}")
        return

    # Tabla resumen: una fila por chunk
    print(f"{'Ubicación':<32} {'Chars':>7}  Título")
    print("-" * 80)
    current_article = None
    for chunk in chunks:
        if chunk.article and chunk.article != current_article:
            current_article = chunk.article
            print(f"\n{chunk.article} - {chunk.article_title}")
        print(f"  {chunk.location:<30} {len(chunk.text):>7}  {chunk.title}")

    sections = [c for c in chunks if c.kind == "section"]
    print(f"\n{len(sections)} sections en {len({c.article for c in sections})} artículos.")

    warnings = check_numbering(chunks)
    for warning in warnings:
        print(f"AVISO: {warning}")
    if not warnings:
        print("Numeración continua: no falta ninguna section.")

    if args.json:
        out_path = Path("output") / (Path(args.contract).stem + ".json")
        out_path.parent.mkdir(exist_ok=True)
        out_path.write_text(json.dumps([asdict(c) for c in chunks], indent=2, ensure_ascii=False))
        print(f"Guardado en {out_path}")


if __name__ == "__main__":
    main()
