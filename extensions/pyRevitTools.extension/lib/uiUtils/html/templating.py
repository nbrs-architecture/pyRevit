# -*- coding: utf-8 -*-
"""Dependency-free string helpers for assembling the final HTML document.

The host injects three things into every page:

* ``window.PYREVIT_DATA = <json>``  - the initial Python -> JS data dict.
* the bridge script (see ``bridge.py``) - the ``pyrevit`` JS API.
* an optional shared stylesheet (``default.css``).

Everything is injected at the top of ``<head>`` so it is available before any
tool script runs, and the tool's own ``<style>``/``<script>`` (which come later
in the document) still win by cascade.
"""
import json


def _strip_nonascii(value):
    """ASCII-only version of a text value (non-ASCII chars become '?').

    Iterates characters directly instead of calling .decode()/.encode(), so it
    never raises IronPython's 'Unable to translate bytes [B0] from specified
    code page' UnicodeDecodeError that json.dumps hits on non-ASCII bytes.
    """
    out = []
    for ch in value:
        try:
            code = ord(ch)
        except TypeError:
            code = ch  # already an int (CPython bytes iteration)
        out.append(chr(code) if code < 128 else '?')
    return ''.join(out)


def _coerce(value):
    """Recursively normalize a payload into ASCII-safe, JSON-able values."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {_coerce(k): _coerce(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_coerce(v) for v in value]
    if isinstance(value, (bool, int, float)):
        return value
    try:
        return _strip_nonascii(value)
    except Exception:
        try:
            return str(value)
        except Exception:
            return ''


def safe_json(payload):
    """JSON-encode ``payload`` so it is safe to embed inside a ``<script>`` tag.

    ``ensure_ascii=True`` keeps the output ASCII; ``<``/``>``/``&`` are escaped
    so a value can never break out of the script tag or inject markup.
    """
    text = json.dumps(_coerce(payload), ensure_ascii=True, default=str)
    return (text.replace('<', '\\u003c')
                .replace('>', '\\u003e')
                .replace('&', '\\u0026'))


def inject(html_text, data, bridge_js, css=None):
    """Return ``html_text`` with the data blob, bridge, and optional css added.

    Args:
        html_text (str): the tool's page (a full ``<!DOCTYPE html>`` document).
        data (dict): initial data exposed to JS as ``pyrevit.data``.
        bridge_js (str): the bridge script source (see ``bridge.BRIDGE_JS``).
        css (str or None): optional shared stylesheet source.

    Returns:
        (str): the final document string ready for ``WebBrowser.DocumentText``.
    """
    head = '<script>window.PYREVIT_DATA = %s;</script>' % safe_json(data)
    head += '<script>%s</script>' % bridge_js
    if css:
        head += '<style>%s</style>' % css

    if '</head>' in html_text.lower():
        return html_text.replace('</head>', head + '</head>', 1)
    return head + html_text
