import html as html_mod
import os
import re
from typing import Any, Dict, Optional
from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def render_email_template(template_name: str, context: Optional[Dict[str, Any]] = None) -> str:
    ctx = context or {}
    template = env.get_template(template_name)
    return template.render(**ctx)


def extract_plain_text(html_content: str) -> str:
    """Strip tags and format cleanly for fallback text email body."""
    text = re.sub(r"<style[^>]*>.*?</style>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</h1>|</h2>|</h3>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<a[^>]*href=[\"'](.*?)[\"'][^>]*>(.*?)</a>", r"\2 (\1)", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    # Collapse multiple blank lines
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    # Decode HTML entities (Jinja2 autoescape produces &amp; &lt; etc.)
    return html_mod.unescape(text).strip()
