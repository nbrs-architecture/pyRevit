# -*- coding: utf-8 -*-
"""Engine-agnostic HTML dialog host for pyRevit tools.

Hosts an HTML page in a WinForms ``WebBrowser`` and bridges JavaScript <-> Python
over the ``revit://`` custom protocol (navigations to ``revit://`` URLs are
intercepted and cancelled in the ``Navigating`` event - the URL is the message).

Works under IronPython 2.7 (Revit <= 2024) and CPython (Revit 2025+, via
pythonnet). It deliberately does NOT depend on pyRevit's IronPython-only
``forms`` module.

See the package docstring (``__init__.py``) for a full usage example.
"""
import io
import json
import os

import clr
clr.AddReference('System.Windows.Forms')
clr.AddReference('System.Drawing')

from System.Windows.Forms import (  # noqa: E402
    Form, WebBrowser, DockStyle, FormStartPosition, FormBorderStyle, Timer)
from System.Drawing import Size  # noqa: E402
from System import Uri  # noqa: E402

from pyrevit import script  # noqa: E402

from uiUtils.html import bridge as _bridge  # noqa: E402
from uiUtils.html import templating as _templating  # noqa: E402


def action(name):
    """Decorator that marks a module-level function as an HTML action.

    The decorated function is picked up by ``HtmlDialog.register_module``.
    Signature: ``func(dialog, payload)``. Its return value (a dict) is
    delivered back to the JS caller; the handler may also call
    ``dialog.respond(...)`` explicitly (in which case the return value is
    ignored if it is ``None``).
    """
    def _deco(func):
        func.__htmlui_action__ = name
        return func
    return _deco


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
_DEFAULT_CSS_CACHE = None


def _read_text(path_or_file):
    if hasattr(path_or_file, 'read'):
        data = path_or_file.read()
        if isinstance(data, bytes):
            data = data.decode('utf-8')
        return data
    with io.open(path_or_file, 'r', encoding='utf-8') as fh:
        return fh.read()


def _load_bundle_text(path):
    """Return the text of a file, resolved relative to the current bundle.

    ``pyrevit.script.get_bundle_file`` returns the full path to ``path`` inside
    the bundle directory of the currently running tool.
    """
    try:
        resolved = script.get_bundle_file(path)
    except Exception:
        resolved = path
    if resolved is None:
        resolved = path
    return _read_text(resolved)


def _load_default_css():
    global _DEFAULT_CSS_CACHE
    if _DEFAULT_CSS_CACHE is None:
        css_path = os.path.join(os.path.dirname(__file__), 'default.css')
        try:
            _DEFAULT_CSS_CACHE = _read_text(css_path)
        except Exception:
            _DEFAULT_CSS_CACHE = ''
    return _DEFAULT_CSS_CACHE


def _unquote(value):
    # Cross-engine percent-decoding via the .NET framework (available in both
    # IronPython and CPython + pythonnet).
    return Uri.UnescapeDataString(value)


def _parse_revit_url(url):
    """Parse a ``revit://cmd?k=v&...`` url into ``(cmd, {key: value})``."""
    body = url[len('revit://'):]
    cmd, _, qs = body.partition('?')
    params = {}
    if qs:
        for part in qs.split('&'):
            if not part:
                continue
            if '=' in part:
                key, _, value = part.partition('=')
                params[key] = _unquote(value)
            else:
                params[part] = ''
    return cmd.lower(), params


# ---------------------------------------------------------------------------
# the dialog
# ---------------------------------------------------------------------------
class HtmlDialog(object):
    """Modal HTML dialog hosted in a WinForms WebBrowser."""

    def __init__(self, title, html=None, html_text=None, width=800, height=600,
                 data=None, include_default_css=True):
        self.title = title
        self.width = width
        self.height = height
        self.data = data or {}
        self.include_default_css = include_default_css
        self.result = None

        self._actions = {}
        self._req_stack = []
        self._responded = False
        self._form = None
        self._browser = None
        self._timer = None
        self.document_text = ''

        if html is not None:
            self.html_text = _load_bundle_text(html)
        else:
            self.html_text = html_text or ''
        self._build_document()

    # -- public API ---------------------------------------------------------
    def route(self, name, func):
        """Bind ``func(dialog, payload)`` to the HTML action ``name``."""
        self._actions[name] = func

    def register_module(self, module_globals):
        """Register every ``@action``-decorated function in ``module_globals``.

        Call with ``dialog.register_module(globals())``.
        """
        for value in list(module_globals.values()):
            name = getattr(value, '__htmlui_action__', None)
            if name:
                self._actions[name] = value

    def respond(self, payload):
        """Deliver ``payload`` to the JS caller of the currently running action."""
        if not self._req_stack:
            return
        self._responded = True
        self._send('pyrevitRespond', self._req_stack[-1], payload)

    def respond_to(self, req_id, payload):
        """Deliver ``payload`` to an explicit request id."""
        self._responded = True
        self._send('pyrevitRespond', req_id, payload)

    def push(self, action_name, payload):
        """Push an unrequested update to JS (see ``pyrevit.on(name, handler)``)."""
        self._send('pyrevitPush', action_name, payload)

    def run_script(self, name, *args):
        """Call a global JS function via ``InvokeScript`` (returns its value)."""
        if self._browser is None or self._browser.Document is None:
            return None
        try:
            return self._browser.Document.InvokeScript(name, list(args))
        except Exception:
            return None

    def close_with(self, result):
        """Programmatically finish the dialog, returning ``result``."""
        self._finish(result)

    def show(self):
        """Show the modal dialog; returns the close result (``None`` on cancel)."""
        self._form = Form()
        self._form.Text = self.title
        self._form.Width = self.width
        self._form.Height = self.height
        self._form.FormBorderStyle = FormBorderStyle.Sizable
        self._form.MinimumSize = Size(560, 380)
        self._form.StartPosition = FormStartPosition.CenterScreen

        self._browser = WebBrowser()
        self._browser.Dock = DockStyle.Fill
        self._browser.Navigating += self._on_navigating
        self._form.Controls.Add(self._browser)

        self._browser.DocumentText = self.document_text

        # Poll the hidden bridge element for JS -> Python messages. A WinForms
        # Timer (not navigation to a custom scheme) is the reliable transport.
        self._timer = Timer()
        self._timer.Interval = 50
        self._timer.Tick += self._on_poll
        self._timer.Start()

        self._form.ShowDialog()

        try:
            self._timer.Stop()
            self._timer.Dispose()
        except Exception:
            pass
        self._timer = None

        browser = self._browser
        self._browser = None
        self._form = None
        try:
            browser.Dispose()
        except Exception:
            pass
        return self.result

    # -- internals ----------------------------------------------------------
    def _build_document(self):
        css = _load_default_css() if self.include_default_css else None
        self.document_text = _templating.inject(
            self.html_text, self.data, _bridge.BRIDGE_JS, css)

    def _send(self, js_func, arg1, payload):
        self.run_script(js_func, str(arg1), _templating.safe_json(payload))

    def _finish(self, result):
        self.result = result
        if self._form is not None:
            self._form.Close()

    def _on_navigating(self, sender, args):
        # Fallback channel for legacy ``revit://`` links in tool HTML. The JS
        # bridge no longer navigates; messages arrive via _on_poll instead.
        url = args.Url.ToString()
        if not url.lower().startswith('revit://'):
            return
        args.Cancel = True
        try:
            cmd, params = _parse_revit_url(url)
            if cmd == 'action':
                raw = params.get('payload')
                self._dispatch_action(params.get('name'), params.get('id'),
                                      json.loads(raw) if raw else {})
            elif cmd == 'close':
                self._finish(json.loads(params.get('result') or 'null'))
            elif cmd == 'cancel':
                self._finish(None)
        except Exception:
            import traceback
            traceback.print_exc()

    def _on_poll(self, sender, args):
        """WinForms Timer tick: consume one pending JS -> Python message."""
        try:
            doc = self._browser.Document
            if doc is None:
                return
            el = doc.GetElementById('pyrevit-bridge')
            if el is None or el.GetAttribute('data-pending') != '1':
                return
            raw = el.GetAttribute('value')
            el.SetAttribute('data-pending', '0')
            el.SetAttribute('value', '')
            if not raw:
                return
            msg = json.loads(raw)
            kind = msg.get('kind')
            if kind == 'action':
                self._dispatch_action(msg.get('name'), msg.get('id'),
                                      msg.get('payload') or {})
            elif kind == 'close':
                self._finish(msg.get('result'))
            elif kind == 'cancel':
                self._finish(None)
        except Exception:
            import traceback
            traceback.print_exc()

    def _dispatch_action(self, name, rid, payload):
        handler = self._actions.get(name)
        if handler is None:
            self._send('pyrevitRespondError', rid,
                       {'message': 'No handler registered for action: %s' % name})
            return

        self._req_stack.append(rid)
        self._responded = False
        try:
            result = handler(self, payload)
        except Exception:
            import traceback
            traceback.print_exc()
            self._send('pyrevitRespondError', rid, {'message': 'handler error'})
            self._req_stack.pop()
            return
        self._req_stack.pop()
        if not self._responded and result is not None:
            self._send('pyrevitRespond', rid, result)
