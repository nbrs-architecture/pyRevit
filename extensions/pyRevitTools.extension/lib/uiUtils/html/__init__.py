# -*- coding: utf-8 -*-
"""uiUtils.html - reusable, engine-agnostic HTML dialogs for pyRevit tools.

This package generalises the "HTML page hosted in a WinForms WebBrowser" pattern
into a small shared library so every future tool gets the same UI plumbing and
only has to write:

  * a plain ``.html`` file next to the script (easy to edit / restyle), and
  * a few Python handlers wired to buttons via ``@action`` / ``dialog.route``.

It works under BOTH IronPython 2.7 (Revit <= 2024) and CPython (Revit 2025+,
via pythonnet) because it does not depend on pyRevit's IronPython-only
``forms`` module.

Typical usage in a tool (``<bundle>.pushbutton/script.py``)::

    from uiUtils.html import HtmlDialog, action

    @action('hello')
    def on_hello(dlg, payload):
        dlg.respond({'message': 'Hello, ' + payload.get('name', 'World')})

    def main():
        dlg = HtmlDialog(title='My Tool', html='tool.html', data={'x': 1})
        dlg.register_module(globals())
        result = dlg.show()   # dict from pyrevit.close(), or None on cancel

In ``tool.html``, buttons call::

    pyrevit.action('hello', {name: 'Revit'}, function (result) { ... });
    pyrevit.close({done: true});   // or pyrevit.cancel();
"""
from uiUtils.html.dialog import HtmlDialog, action

__all__ = ['HtmlDialog', 'action']
__version__ = '0.1.0'
