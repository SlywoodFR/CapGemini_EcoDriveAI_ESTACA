#!/usr/bin/env python3
"""
convert_md_to_pdf.py

Convertit un fichier Markdown (.md) en PDF.

Usage:
  python convert_md_to_pdf.py input.md [-o output.pdf] [--css style.css]

Le script tente d'abord d'utiliser pandoc (via pypandoc). Si ça échoue
ou si un fichier CSS est fourni, il utilise WeasyPrint (Markdown -> HTML -> PDF)
pour permettre l'application de styles CSS.
"""
import argparse
import os
import sys

DEFAULT_CSS = """
body {
    font-family: "DejaVu Sans", "Arial", sans-serif;
    margin: 1.0in;
    line-height: 1.4;
    color: #222;
}
h1, h2, h3, h4, h5 { color: #1a1a1a; }
pre, code { font-family: "DejaVu Sans Mono", monospace; background: #f6f8fa; padding: .2em .4em; }
img { max-width: 100%; height: auto; }
"""

def convert_with_pandoc(input_path, output_path, pdf_engine="xelatex"):
    try:
        import pypandoc
    except Exception as e:
        raise RuntimeError("pypandoc non installé") from e

    extra_args = ["--pdf-engine=" + pdf_engine]
    try:
        # pypandoc can write directly to output file via outputfile parameter
        pypandoc.convert_file(input_path, "pdf", outputfile=output_path, extra_args=extra_args)
    except Exception as e:
        raise RuntimeError("Erreur lors de la conversion avec pandoc: " + str(e)) from e

def convert_with_weasy(input_path, output_path, css_path=None):
    try:
        import markdown
    except Exception as e:
        raise RuntimeError("Le paquet 'markdown' n'est pas installé") from e
    try:
        from weasyprint import HTML, CSS
    except Exception as e:
        raise RuntimeError("WeasyPrint n'est pas installé ou manque de dépendances système") from e

    with open(input_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    html_body = markdown.markdown(md_text, extensions=["extra", "codehilite", "toc"])
    title = os.path.splitext(os.path.basename(input_path))[0]
    html_full = f"""<!doctype html>
<html><head>
<meta charset="utf-8">
<title>{title}</title>
<style>{DEFAULT_CSS}</style>
</head><body>
{html_body}
</body></html>
"""
    base_url = os.path.dirname(os.path.abspath(input_path)) or "."
    stylesheets = []
    if css_path:
        stylesheets.append(CSS(filename=css_path))
    # If no external CSS provided, default CSS is already embedded in the HTML head.
    HTML(string=html_full, base_url=base_url).write_pdf(output_path, stylesheets=stylesheets or None)

def main():
    parser = argparse.ArgumentParser(description="Convertir un fichier Markdown (.md) en PDF.")
    parser.add_argument("input", help="Fichier d'entrée .md")
    parser.add_argument("-o", "--output", help="Fichier PDF de sortie (défaut: même nom .pdf)", default=None)
    parser.add_argument("--css", help="Fichier CSS optionnel à appliquer (utilise WeasyPrint si fourni)", default=None)
    parser.add_argument("--pdf-engine", help="Moteur PDF pour pandoc (ex: xelatex, pdflatex, wkhtmltopdf)", default="xelatex")
    args = parser.parse_args()

    input_path = args.input
    if not os.path.isfile(input_path):
        print(f"Fichier introuvable: {input_path}", file=sys.stderr)
        sys.exit(2)

    output_path = args.output or os.path.splitext(input_path)[0] + ".pdf"

    # Si CSS fourni -> utiliser WeasyPrint (meilleure prise en charge CSS)
    if args.css:
        try:
            convert_with_weasy(input_path, output_path, css_path=args.css)
            print(f"Converti avec WeasyPrint en appliquant le CSS: {output_path}")
            return
        except Exception as e:
            print("WeasyPrint a échoué:", str(e), file=sys.stderr)
            print("Tentative avec pandoc...", file=sys.stderr)

    # Essayer pandoc d'abord si disponible
    try:
        convert_with_pandoc(input_path, output_path, pdf_engine=args.pdf_engine)
        print(f"Converti avec pandoc: {output_path}")
        return
    except Exception as e:
        print("Pandoc a échoué ou n'est pas disponible:", str(e), file=sys.stderr)
        print("Tentative avec WeasyPrint...", file=sys.stderr)

    # Dernière chance: WeasyPrint without CSS
    try:
        convert_with_weasy(input_path, output_path, css_path=None)
        print(f"Converti avec WeasyPrint (CSS par défaut): {output_path}")
    except Exception as e:
        print("Échec de la conversion avec WeasyPrint:", str(e), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()