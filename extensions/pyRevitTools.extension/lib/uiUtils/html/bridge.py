# -*- coding: utf-8 -*-
"""The JavaScript bridge injected into every ``uiUtils.html`` dialog page.

The bridge exposes a global ``pyrevit`` object that HTML pages use to talk to
the hosting Python process:

* ``pyrevit.data``            - the initial data dict injected from Python.
* ``pyrevit.action(name, payload, onSuccess, onError)``
                              - invoke a Python handler; the response (a dict
                                returned/``dlg.respond``-ed by the handler) is
                                delivered to ``onSuccess`` (parsed JSON), or an
                                error payload to ``onError``.
* ``pyrevit.on(name, handler)`` - register a handler for ``dialog.push()``
                                updates sent from Python at any time.
* ``pyrevit.close(result)``   - finish the dialog; ``dialog.show()`` returns
                                ``result`` (defaults to ``{}``).
* ``pyrevit.cancel()``        - finish the dialog; ``dialog.show()`` returns
                                ``None``.

Transport: the page writes each outgoing message (JSON) into a hidden element
(``#pyrevit-bridge``) that the host polls from a WinForms ``Timer`` - no custom
URL scheme is involved, so it works reliably in the ``WebBrowser`` control under
both IronPython and CPython. The host replies by calling the global
``pyrevitRespond`` / ``pyrevitRespondError`` / ``pyrevitPush`` functions through
``WebBrowser.Document.InvokeScript``.

The code is deliberately ES5 (``var``, no arrow functions / template literals)
so it runs on the mshtml / EdgeHTML engine inside ``WebBrowser`` on all
supported Windows versions.
"""
BRIDGE_JS = """(function () {
  'use strict';
  var seq = 0;
  var pending = {};
  var OUT_ID = 'pyrevit-bridge';

  function parseJSON(s) {
    if (!s) { return null; }
    try { return JSON.parse(s); } catch (e) { return null; }
  }

  // Called by the host (Python) to deliver an action response.
  window.pyrevitRespond = function (id, json) {
    var entry = pending[id];
    if (!entry) { return; }
    delete pending[id];
    if (entry.ok) { entry.ok(parseJSON(json)); }
  };

  // Called by the host (Python) to deliver an action error.
  window.pyrevitRespondError = function (id, json) {
    var entry = pending[id];
    if (!entry) { return; }
    delete pending[id];
    if (entry.err) { entry.err(parseJSON(json)); }
  };

  // Called by the host (Python) to push an unrequested update.
  window.pyrevitPush = function (name, json) {
    var h = window.pyrevit && window.pyrevit._pushes;
    if (h && h[name]) { h[name](parseJSON(json)); }
  };

  // page -> host: write the message into a hidden element that the host polls
  // from a WinForms Timer. No custom URL scheme - reliable in WebBrowser.
  function send(msg) {
    var el = document.getElementById(OUT_ID);
    if (!el) {
      el = document.createElement('input');
      el.type = 'hidden';
      el.id = OUT_ID;
      document.body.appendChild(el);
    }
    el.setAttribute('value', JSON.stringify(msg));
    el.setAttribute('data-pending', '1');
  }

  window.pyrevit = {
    data: window.PYREVIT_DATA || null,
    _pushes: {},
    action: function (name, payload, ok, err) {
      seq += 1;
      var id = String(seq);
      pending[id] = { ok: ok, err: err };
      send({kind: 'action', name: name, id: id, payload: payload || {}});
    },
    on: function (name, handler) {
      window.pyrevit._pushes[name] = handler;
    },
    close: function (result) {
      send({kind: 'close', result: result || {}});
    },
    cancel: function () {
      send({kind: 'cancel'});
    }
  };
})();
"""
