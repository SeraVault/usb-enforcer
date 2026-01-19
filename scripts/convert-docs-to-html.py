#!/usr/bin/env python3
"""
Convert markdown documentation to HTML for the admin GUI.
This script is run during package build to create HTML versions of all docs.
"""

import sys
import os
from pathlib import Path

try:
    import markdown
except ImportError:
    print("Error: python3-markdown not found. Install it:", file=sys.stderr)
    print("  Debian/Ubuntu: sudo apt install python3-markdown", file=sys.stderr)
    print("  RHEL/Fedora: sudo dnf install python3-markdown", file=sys.stderr)
    sys.exit(1)


HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: #fff;
        }}
        h1, h2, h3, h4, h5, h6 {{
            margin-top: 24px;
            margin-bottom: 16px;
            font-weight: 600;
            line-height: 1.25;
        }}
        h1 {{ font-size: 2em; border-bottom: 1px solid #eaecef; padding-bottom: 0.3em; }}
        h2 {{ font-size: 1.5em; border-bottom: 1px solid #eaecef; padding-bottom: 0.3em; }}
        h3 {{ font-size: 1.25em; }}
        h4 {{ font-size: 1em; }}
        code {{
            background-color: rgba(27, 31, 35, 0.05);
            border-radius: 3px;
            font-size: 85%;
            margin: 0;
            padding: 0.2em 0.4em;
            font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
        }}
        pre {{
            background-color: #f6f8fa;
            border-radius: 3px;
            font-size: 85%;
            line-height: 1.45;
            overflow: auto;
            padding: 16px;
        }}
        pre code {{
            background-color: transparent;
            border: 0;
            display: inline;
            line-height: inherit;
            margin: 0;
            overflow: visible;
            padding: 0;
            word-wrap: normal;
        }}
        a {{
            color: #0366d6;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        blockquote {{
            border-left: 4px solid #dfe2e5;
            color: #6a737d;
            padding-left: 16px;
            margin-left: 0;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 16px 0;
        }}
        table th, table td {{
            border: 1px solid #dfe2e5;
            padding: 6px 13px;
        }}
        table th {{
            background-color: #f6f8fa;
            font-weight: 600;
        }}
        ul, ol {{
            padding-left: 2em;
        }}
        li {{
            margin: 0.25em 0;
        }}
        hr {{
            border: 0;
            border-top: 1px solid #eaecef;
            margin: 24px 0;
        }}
    </style>
</head>
<body>
{content}
</body>
</html>
"""


def convert_markdown_to_html(md_path: Path, html_path: Path):
    """Convert a single markdown file to HTML."""
    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
        
        # Rewrite internal links from .md to .html
        # Matches [text](filename.md) and converts to [text](filename.html)
        import re
        md_content = re.sub(r'\[([^\]]+)\]\(([^)]+\.md)(#[^)]+)?\)', r'[\1](\2.html\3)', md_content)
        # Also handle plain .md references without the .md extension in the replacement
        md_content = re.sub(r'\[([^\]]+)\]\(([^)]+)\.md(\.html)(#[^)]+)?\)', r'[\1](\2.html\4)', md_content)
        # Fix double .md.html -> .html
        md_content = re.sub(r'\.md\.html', '.html', md_content)
        
        # Configure markdown with common extensions
        md = markdown.Markdown(extensions=[
            'extra',          # Tables, fenced code, etc.
            'codehilite',     # Syntax highlighting
            'toc',            # Table of contents
            'nl2br',          # Newline to <br>
            'sane_lists',     # Better list handling
        ])
        
        html_content = md.convert(md_content)
        
        # Extract title from first h1 or use filename
        title = md_path.stem.replace('-', ' ').title()
        if html_content.startswith('<h1>'):
            title_end = html_content.find('</h1>')
            if title_end > 0:
                title = html_content[4:title_end]
        
        # Wrap in HTML template
        full_html = HTML_TEMPLATE.format(title=title, content=html_content)
        
        # Write HTML file
        html_path.parent.mkdir(parents=True, exist_ok=True)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(full_html)
        
        return True
    except Exception as e:
        print(f"Error converting {md_path}: {e}", file=sys.stderr)
        return False


def main():
    if len(sys.argv) < 3:
        print("Usage: convert-docs-to-html.py <source_dir> <output_dir>")
        print("Example: convert-docs-to-html.py docs build/docs-html")
        sys.exit(1)
    
    source_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    
    if not source_dir.exists():
        print(f"Error: Source directory not found: {source_dir}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Converting markdown files from {source_dir} to {output_dir}")
    
    # Find all markdown files
    md_files = list(source_dir.glob("*.md"))
    
    if not md_files:
        print(f"Warning: No markdown files found in {source_dir}")
        sys.exit(0)
    
    success_count = 0
    for md_file in md_files:
        html_file = output_dir / f"{md_file.stem}.html"
        print(f"  {md_file.name} -> {html_file.name}")
        if convert_markdown_to_html(md_file, html_file):
            success_count += 1
    
    print(f"\nConverted {success_count}/{len(md_files)} files successfully")
    
    if success_count < len(md_files):
        sys.exit(1)


if __name__ == "__main__":
    main()
