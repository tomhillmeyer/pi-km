#!/usr/bin/env python3
"""
HID Controller — reads physical keyboard + mouse via evdev,
forwards events to the currently active HID node over TCP.
Switch targets and manage nodes via HTTP on port 80.
"""

import socket
import struct
import threading
import time
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import evdev
from evdev import InputDevice, categorize, ecodes
from collections import deque

# --- Configuration ---
CONFIG_FILE = "/etc/pikm/nodes.json"
NODE_PORT = 9876
HTTP_PORT = 80

config_lock = threading.Lock()
active_node = None
config = {"nodes": {}, "active": None}


def load_config():
    global config, active_node
    try:
        with open(CONFIG_FILE) as f:
            config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        config = {"nodes": {}, "active": None}
    if "node_order" not in config:
        config["node_order"] = list(config.get("nodes", {}).keys())
    active_node = config.get("active")


def save_config():
    config["active"] = active_node
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)




def ensure_config_dir():
    global CONFIG_FILE
    d = os.path.dirname(CONFIG_FILE)
    try:
        os.makedirs(d, exist_ok=True)
    except PermissionError:
        d = os.path.expanduser("~/.pikm")
        os.makedirs(d, exist_ok=True)
        CONFIG_FILE = os.path.join(d, "nodes.json")
        load_config()
        return
    except OSError:
        pass


ensure_config_dir()
load_config()
active_lock = threading.Lock()

# --- Logo loading ---

LOGO_DATA_URI = ""
logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pi-km-logo.png")
if os.path.exists(logo_path):
    try:
        with open(logo_path, "rb") as f:
            import base64
            b64 = base64.b64encode(f.read()).decode()
            LOGO_DATA_URI = f"data:image/png;base64,{b64}"
    except Exception:
        pass

# --- HID helpers ---

KEY_MAP = {
    ecodes.KEY_A: 0x04, ecodes.KEY_B: 0x05, ecodes.KEY_C: 0x06,
    ecodes.KEY_D: 0x07, ecodes.KEY_E: 0x08, ecodes.KEY_F: 0x09,
    ecodes.KEY_G: 0x0a, ecodes.KEY_H: 0x0b, ecodes.KEY_I: 0x0c,
    ecodes.KEY_J: 0x0d, ecodes.KEY_K: 0x0e, ecodes.KEY_L: 0x0f,
    ecodes.KEY_M: 0x10, ecodes.KEY_N: 0x11, ecodes.KEY_O: 0x12,
    ecodes.KEY_P: 0x13, ecodes.KEY_Q: 0x14, ecodes.KEY_R: 0x15,
    ecodes.KEY_S: 0x16, ecodes.KEY_T: 0x17, ecodes.KEY_U: 0x18,
    ecodes.KEY_V: 0x19, ecodes.KEY_W: 0x1a, ecodes.KEY_X: 0x1b,
    ecodes.KEY_Y: 0x1c, ecodes.KEY_Z: 0x1d,
    ecodes.KEY_1: 0x1e, ecodes.KEY_2: 0x1f, ecodes.KEY_3: 0x20,
    ecodes.KEY_4: 0x21, ecodes.KEY_5: 0x22, ecodes.KEY_6: 0x23,
    ecodes.KEY_7: 0x24, ecodes.KEY_8: 0x25, ecodes.KEY_9: 0x26,
    ecodes.KEY_0: 0x27,
    ecodes.KEY_MINUS: 0x2d, ecodes.KEY_EQUAL: 0x2e,
    ecodes.KEY_LEFTBRACE: 0x2f, ecodes.KEY_RIGHTBRACE: 0x30,
    ecodes.KEY_BACKSLASH: 0x31,
    ecodes.KEY_SEMICOLON: 0x33, ecodes.KEY_APOSTROPHE: 0x34,
    ecodes.KEY_GRAVE: 0x35,
    ecodes.KEY_COMMA: 0x36, ecodes.KEY_DOT: 0x37, ecodes.KEY_SLASH: 0x38,
    ecodes.KEY_KP7: 0x5f, ecodes.KEY_KP8: 0x60, ecodes.KEY_KP9: 0x61,
    ecodes.KEY_KP4: 0x5c, ecodes.KEY_KP5: 0x5d, ecodes.KEY_KP6: 0x5e,
    ecodes.KEY_KP1: 0x59, ecodes.KEY_KP2: 0x5a, ecodes.KEY_KP3: 0x5b,
    ecodes.KEY_KP0: 0x62,
    ecodes.KEY_KPDOT: 0x63, ecodes.KEY_KPENTER: 0x58,
    ecodes.KEY_KPSLASH: 0x54, ecodes.KEY_KPASTERISK: 0x55,
    ecodes.KEY_KPMINUS: 0x56, ecodes.KEY_KPPLUS: 0x57,
    ecodes.KEY_KPEQUAL: 0x67,
    ecodes.KEY_ENTER: 0x28, ecodes.KEY_ESC: 0x29,
    ecodes.KEY_BACKSPACE: 0x2a, ecodes.KEY_TAB: 0x2b, ecodes.KEY_SPACE: 0x2c,
    ecodes.KEY_CAPSLOCK: 0x39,
    ecodes.KEY_INSERT: 0x49, ecodes.KEY_HOME: 0x4a, ecodes.KEY_PAGEUP: 0x4b,
    ecodes.KEY_DELETE: 0x4c, ecodes.KEY_END: 0x4d, ecodes.KEY_PAGEDOWN: 0x4e,
    ecodes.KEY_RIGHT: 0x4f, ecodes.KEY_LEFT: 0x50, ecodes.KEY_DOWN: 0x51,
    ecodes.KEY_UP: 0x52,
    ecodes.KEY_NUMLOCK: 0x53, ecodes.KEY_SCROLLLOCK: 0x47,
    ecodes.KEY_SYSRQ: 0x46, ecodes.KEY_PAUSE: 0x48,
    ecodes.KEY_F1: 0x3a, ecodes.KEY_F2: 0x3b, ecodes.KEY_F3: 0x3c,
    ecodes.KEY_F4: 0x3d, ecodes.KEY_F5: 0x3e, ecodes.KEY_F6: 0x3f,
    ecodes.KEY_F7: 0x40, ecodes.KEY_F8: 0x41, ecodes.KEY_F9: 0x42,
    ecodes.KEY_F10: 0x43, ecodes.KEY_F11: 0x44, ecodes.KEY_F12: 0x45,
    ecodes.KEY_LEFTCTRL: 0xe0, ecodes.KEY_LEFTSHIFT: 0xe1,
    ecodes.KEY_LEFTALT: 0xe2, ecodes.KEY_LEFTMETA: 0xe3,
    ecodes.KEY_RIGHTCTRL: 0xe4, ecodes.KEY_RIGHTSHIFT: 0xe5,
    ecodes.KEY_RIGHTALT: 0xe6, ecodes.KEY_RIGHTMETA: 0xe7,
}

MODIFIER_KEYS = {
    ecodes.KEY_LEFTCTRL:  0x01,
    ecodes.KEY_LEFTSHIFT: 0x02,
    ecodes.KEY_LEFTALT:   0x04,
    ecodes.KEY_LEFTMETA:  0x08,
    ecodes.KEY_RIGHTCTRL: 0x10,
    ecodes.KEY_RIGHTSHIFT: 0x20,
    ecodes.KEY_RIGHTALT:  0x40,
    ecodes.KEY_RIGHTMETA: 0x80,
}

# --- Persistent connection with heartbeat ---


class NodeConnection:
    def __init__(self):
        self.sock = None
        self.lock = threading.Lock()
        self.target = None
        threading.Thread(target=self._heartbeat, daemon=True).start()

    def _resolve_target(self):
        with active_lock:
            ip = config.get("nodes", {}).get(active_node)
            return ip

    def _try_connect(self):
        target = self._resolve_target()
        if not target:
            return None
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.settimeout(2.0)
        try:
            s.connect((target, NODE_PORT))
            print(f"[conn] Connected to {target}:{NODE_PORT}", flush=True)
            return s
        except Exception as e:
            print(f"[conn] Failed to connect to {target}:{NODE_PORT} — {e}", flush=True)
            try:
                s.close()
            except Exception:
                pass
            return None

    def _close(self):
        try:
            self.sock.close()
        except Exception:
            pass
        self.sock = None

    def send(self, msg_type: int, report: bytes):
        if not self._resolve_target():
            return
        with self.lock:
            if self.sock is not None:
                try:
                    self.sock.sendall(bytes([msg_type]) + report)
                except Exception:
                    self._close()

    def _heartbeat(self):
        while True:
            time.sleep(1)
            target = self._resolve_target()
            if not target:
                if self.sock is not None:
                    self._close()
                continue
            with self.lock:
                if self.sock is not None:
                    try:
                        self.sock.sendall(b'\x00')
                    except Exception:
                        self._close()
            if self.sock is None:
                s = self._try_connect()
                if s is not None:
                    with self.lock:
                        if self.sock is None:
                            self.sock = s
                        else:
                            try:
                                s.close()
                            except Exception:
                                pass

    def switch(self, name: str):
        global active_node
        with active_lock:
            active_node = name
            save_config()
        with self.lock:
            self._close()
        print(f"[switch] Active node: {name}", flush=True)


node_conn = NodeConnection()
send_to_node = node_conn.send

# --- Periodic node connectivity checker ---

node_online = {}
node_online_lock = threading.Lock()
_probe_history = {}
_PROBE_HISTORY_LEN = 2
_PROBE_FAIL_THRESHOLD = 1  # declare offline if >= N of last _PROBE_HISTORY_LEN probes failed


def _check_node_port(ip: str) -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        r = s.connect_ex((ip, NODE_PORT))
        s.close()
        return r == 0
    except Exception:
        return False


def _check_all_nodes():
    global _probe_history
    while True:
        with config_lock:
            nodes = dict(config.get("nodes", {}))
        fresh = {}
        for name, ip in nodes.items():
            ok = _check_node_port(ip)
            hist = _probe_history.setdefault(name, deque(maxlen=_PROBE_HISTORY_LEN))
            hist.append(ok)
            fresh[name] = sum(hist) >= (_PROBE_HISTORY_LEN - _PROBE_FAIL_THRESHOLD + 1)
        with node_online_lock:
            node_online.clear()
            node_online.update(fresh)
        time.sleep(3)


threading.Thread(target=_check_all_nodes, daemon=True).start()


def build_keyboard_report(modifiers, keys) -> bytes:
    keys_list = list(keys)[:6]
    keys_list += [0x00] * (6 - len(keys_list))
    return struct.pack("8B", modifiers, 0x00, *keys_list)


CONSUMER_KEYS = {
    ecodes.KEY_PLAYPAUSE: 0x00CD,
    ecodes.KEY_NEXTSONG: 0x00B5,
    ecodes.KEY_PREVIOUSSONG: 0x00B6,
    ecodes.KEY_STOPCD: 0x00B7,
    ecodes.KEY_VOLUMEUP: 0x00E9,
    ecodes.KEY_VOLUMEDOWN: 0x00EA,
    ecodes.KEY_MUTE: 0x00E2,
    ecodes.KEY_BRIGHTNESSUP: 0x006F,
    ecodes.KEY_BRIGHTNESSDOWN: 0x0070,
}


# --- Per-device reader ---


def read_device(dev, name):
    pressed_keys = set()
    pressed_modifiers = 0
    buttons = 0
    dx = dy = scroll = 0

    try:
        for event in dev.read_loop():
            try:
                if event.type == ecodes.EV_KEY:
                    key = event.code
                    state = event.value

                    if key in MODIFIER_KEYS:
                        if state == 1:
                            pressed_modifiers |= MODIFIER_KEYS[key]
                        elif state == 0:
                            pressed_modifiers &= ~MODIFIER_KEYS[key]
                        report = build_keyboard_report(pressed_modifiers, pressed_keys)
                        send_to_node(0x01, report)
                    elif key in KEY_MAP:
                        hid = KEY_MAP[key]
                        if state == 1:
                            pressed_keys.add(hid)
                            report = build_keyboard_report(pressed_modifiers, pressed_keys)
                            send_to_node(0x01, report)
                        elif state == 0:
                            pressed_keys.discard(hid)
                            report = build_keyboard_report(pressed_modifiers, pressed_keys)
                            send_to_node(0x01, report)
                        elif state == 2:
                            null_report = build_keyboard_report(pressed_modifiers, set())
                            report = build_keyboard_report(pressed_modifiers, pressed_keys)
                            send_to_node(0x01, null_report)
                            send_to_node(0x01, report)
                    elif key == ecodes.BTN_LEFT:
                        if state:
                            buttons |= 0x01
                        else:
                            buttons &= ~0x01
                    elif key == ecodes.BTN_RIGHT:
                        if state:
                            buttons |= 0x02
                        else:
                            buttons &= ~0x02
                    elif key == ecodes.BTN_MIDDLE:
                        if state:
                            buttons |= 0x04
                        else:
                            buttons &= ~0x04
                    elif key in CONSUMER_KEYS:
                        if state == 1:
                            usage = CONSUMER_KEYS[key]
                            send_to_node(0x03, struct.pack("<H", usage))
                            send_to_node(0x03, struct.pack("<H", 0))

                elif event.type == ecodes.EV_REL:
                    if event.code == ecodes.REL_X:
                        dx = max(-127, min(127, event.value))
                    elif event.code == ecodes.REL_Y:
                        dy = max(-127, min(127, event.value))
                    elif event.code == ecodes.REL_WHEEL:
                        scroll = max(-127, min(127, event.value))
                    elif event.code == ecodes.REL_WHEEL_HI_RES:
                        scroll = max(-127, min(127, event.value // 120))

                elif event.type == ecodes.EV_SYN:
                    report = struct.pack("4b", buttons, dx, dy, scroll)
                    send_to_node(0x02, report)
                    dx = dy = scroll = 0

            except Exception as e:
                print(f"[{name}] event error: {e}")
    except Exception as e:
        print(f"[{name}] device error: {e}")

# --- HTTP switch server ---


PAGE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PiKM</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:ui-monospace,"SF Mono","Fira Code","Consolas",monospace;background:#000;color:#bbb;padding:24px;font-size:14px;line-height:1.6}

  table{border-collapse:collapse;font-size:13px;margin-bottom:16px}
  th,td{padding:4px 16px 4px 0;text-align:left;border-bottom:1px solid #222;white-space:nowrap}
  th{color:#555;font-weight:400;font-size:12px}
  td:last-child{padding-right:0}
  .num{color:#444;font-size:12px;width:24px;padding-right:4px}
  .nm{cursor:pointer}
  .nm:hover{color:#eee}
  .act{color:#eee}
  .idle{color:#444}
  .df{color:#933}
  .logo{display:block;margin-bottom:16px;max-width:180px}
  .add-form{display:flex;gap:8px;margin-bottom:16px}
  .add-form input{background:#111;border:1px solid #333;color:#bbb;padding:4px 8px;font-family:inherit;font-size:13px;outline:0;width:140px}
  .add-form input:focus{border-color:#666}
  .add-form button{background:0 0;border:1px solid #555;color:#bbb;padding:4px 12px;font-family:inherit;font-size:13px;cursor:pointer}
  .add-form button:hover{background:#222;color:#eee}
  .btn{background:0 0;border:0;color:#666;cursor:pointer;font-family:inherit;font-size:13px;padding:0 2px}
  .btn:hover{color:#eee}
  .btn:disabled{color:#333;cursor:default}
  .inline-edit{background:#111;border:1px solid #555;color:#bbb;padding:2px 4px;font-family:inherit;font-size:13px;outline:0;width:100px}
  .msg{font-size:12px;margin-bottom:12px;display:none}
  .msg.error{display:block;color:#eee}
  .msg.success{display:block;color:#888}
  .api{border-top:1px solid #222;padding-top:12px;font-size:12px;color:#555}
  .api code{color:#777}
</style>
</head>
<body>
<img class="logo" src="{{LOGO}}" alt="PiKM">
<div id="msg" class="msg"></div>
<form class="add-form" id="addForm">
  <input type="text" id="nodeName" placeholder="name" required>
  <input type="text" id="nodeIp" placeholder="ip" required>
  <button type="submit">+ add</button>
</form>
<table id="nodesTable">
  <tr><th></th><th>#</th><th>node</th><th>ip</th><th></th><th></th><th></th></tr>
  <tbody id="rows"></tbody>
</table>
<div class="api">
  <code>GET /status</code><br>
  <code>GET /switch?target=&lt;node&gt;</code><br>
  <code>POST /nodes</code> {"name":"...","ip":"..."}<br>
  <code>DELETE /nodes?name=&lt;node&gt;</code>
</div>
<script>
const NODES = {{NODES}};
let ORDER = {{ORDER}};
let editingName = false;

function showMsg(text, type){
  const el = document.getElementById('msg');
  el.textContent = text;
  el.className = 'msg ' + type;
  setTimeout(()=>{el.className='msg';},3000);
}

function editName(span, name) {
  editingName = true;
  const input = document.createElement('input');
  input.type = 'text';
  input.value = name;
  input.className = 'inline-edit';
  span.replaceWith(input);
  input.focus();
  input.select();
  function done() {
    editingName = false;
    const newName = input.value.trim();
    if (newName && newName !== name) {
      fetch('/nodes/rename', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name, new_name: newName})})
        .then(r => {
          if (r.ok) {
            NODES[newName] = NODES[name];
            delete NODES[name];
            const i = ORDER.indexOf(name);
            if (i !== -1) ORDER[i] = newName;
            update();
          } else r.text().then(t => showMsg(t, 'error'));
        });
    } else { update(); }
  }
  input.addEventListener('blur', done);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') input.blur();
    if (e.key === 'Escape') { editingName = false; update(); }
  });
}

function moveUp(idx) {
  if (idx === 0) return;
  ORDER = [...ORDER];
  [ORDER[idx-1], ORDER[idx]] = [ORDER[idx], ORDER[idx-1]];
  fetch('/nodes/reorder', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({names: ORDER})})
    .then(r => { if (r.ok) update(); else r.text().then(t => showMsg(t, 'error')); });
}

function moveDown(idx) {
  if (idx >= ORDER.length - 1) return;
  ORDER = [...ORDER];
  [ORDER[idx], ORDER[idx+1]] = [ORDER[idx+1], ORDER[idx]];
  fetch('/nodes/reorder', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({names: ORDER})})
    .then(r => { if (r.ok) update(); else r.text().then(t => showMsg(t, 'error')); });
}

function update() {
  fetch('/status').then(r=>r.json()).then(d=>{
    const active = d.active || '';
    document.title = active ? active + ' - PiKM' : 'PiKM';
    if (editingName) return;
    const online = d.online || {};
    const rows = document.getElementById('rows');
    rows.innerHTML = '';
    ORDER.forEach((name, idx) => {
      const obj = NODES[name];
      if (!obj) return;
      const ip = typeof obj === 'string' ? obj : obj.ip;
      const tr = document.createElement('tr');
      const isActive = name === active;
      const isOnline = online[name] === true;
      let status, cls;
      if (!isOnline) { status = 'OFFLINE'; cls = 'df'; }
      else if (isActive) { status = 'ACTIVE'; cls = 'act'; }
      else { status = '\u2014\u2014'; cls = 'idle'; }
      tr.innerHTML = '<td><button class="btn" onclick="moveUp('+idx+')" '+(idx===0?'disabled':'')+'>&#9650;</button>'
        + '<button class="btn" onclick="moveDown('+idx+')" '+(idx>=ORDER.length-1?'disabled':'')+'>&#9660;</button></td>'
        + '<td class="num">'+(idx+1)+'.</td>'
        + '<td><span class="nm" onclick="editName(this,\\''+name+'\\')">'+name+'</span></td>'
        + '<td>'+ip+'</td>'
        + '<td class="'+cls+'">'+status+'</td>'
        + '<td>'+(isOnline ? '<button class="btn" onclick="switchTo(\\''+name+'\\',this)">switch</button>' : '')+'</td>'
        + '<td><button class="btn" onclick="removeNode(\\''+name+'\\',\\''+ip+'\\',this)">remove</button></td>';
      rows.appendChild(tr);
    });
  });
}

function switchTo(name,btn){
  btn.disabled = true;
  fetch('/switch?target='+name).then(()=>update());
}

function removeNode(name,ip,btn){
  if(!confirm('Remove \\''+name+'\\' ('+ip+')?')) return;
  btn.disabled = true;
  fetch('/nodes?name='+name,{method:'DELETE'}).then(r=>{
    if(r.ok) {
      delete NODES[name];
      ORDER = ORDER.filter(n => n !== name);
      update();
      showMsg('Removed '+name,'success');
    } else r.text().then(t=>showMsg(t,'error'));
  });
}

document.getElementById('addForm').addEventListener('submit',function(e){
  e.preventDefault();
  const name = document.getElementById('nodeName').value.trim();
  const ip = document.getElementById('nodeIp').value.trim();
  fetch('/nodes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,ip})}).then(r=>{
    if(r.ok){
      if (!(name in NODES)) ORDER.push(name);
      NODES[name] = ip;
      update();
      showMsg('Added '+name,'success');
      document.getElementById('nodeName').value='';
      document.getElementById('nodeIp').value='';
    } else r.text().then(t=>showMsg(t,'error'));
  });
});

update();
setInterval(update,2000);
</script>
</body>
</html>"""

STATUS_PAGE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PiKM</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:ui-monospace,"SF Mono","Fira Code","Consolas",monospace;background:#000;color:#bbb;padding:24px;font-size:14px;line-height:1.6}
  p{margin-bottom:12px}
  a{color:#888}
  a:hover{color:#eee}
</style>
</head>
<body>
<p>{{MSG}}</p>
<p><a href="/">&larr; back</a></p>
</body>
</html>"""


class SwitchHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/":
            with config_lock:
                nodes_dict = config.get("nodes", {})
                order = config.get("node_order", [])
            page = PAGE.replace("{{NODES}}", json.dumps(nodes_dict)).replace("{{ORDER}}", json.dumps(order)).replace("{{LOGO}}", LOGO_DATA_URI)
            self._html(200, page)

        elif parsed.path == "/switch":
            target = params.get("target", [None])[0]
            if not target:
                self._text(400, "target required")
                return
            with config_lock:
                nodes = config.get("nodes", {})
                order = config.get("node_order", [])
            name = None
            if target in nodes:
                name = target
            elif target.isdigit():
                idx = int(target) - 1
                if 0 <= idx < len(order):
                    name = order[idx]
            else:
                for n, ip in nodes.items():
                    if ip == target:
                        name = n
                        break
            if name:
                node_conn.switch(name)
                self._text(200, f"Switched to {name}")
            else:
                self._text(400, "Unknown target")

        elif parsed.path == "/status":
            with active_lock:
                current = active_node or ""
            with node_conn.lock:
                connected = node_conn.sock is not None
            with node_online_lock:
                online = dict(node_online)
            self._json(200, {"active": current, "connected": connected, "online": online})

        elif parsed.path == "/nodes":
            self._json(200, config.get("nodes", {}))

        elif parsed.path == "/restart":
            page = STATUS_PAGE.replace("{{MSG}}", "Controller restarted")
            self._html(200, page)
            threading.Thread(target=self._do_restart, daemon=True).start()

        else:
            self._text(404, "Not found")

    def do_POST(self):
        global active_node
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body) if length else {}
        except json.JSONDecodeError:
            self._text(400, "Bad JSON")
            return

        if parsed.path == "/nodes":
            name = data.get("name", "").strip()
            ip = data.get("ip", "").strip()
            if not name or not ip:
                self._text(400, "name and ip required")
                return
            with config_lock:
                nodes = config.setdefault("nodes", {})
                if name not in nodes:
                    config.setdefault("node_order", []).append(name)
                nodes[name] = ip
                save_config()
            if not active_node:
                node_conn.switch(name)
            self._text(201, f"Added {name}")
        elif parsed.path == "/nodes/reorder":
            names = data.get("names", [])
            with config_lock:
                config["node_order"] = names
                save_config()
            self._text(200, "Reordered")
        elif parsed.path == "/nodes/rename":
            old = data.get("name", "").strip()
            new = data.get("new_name", "").strip()
            if not old or not new:
                self._text(400, "name and new_name required")
                return
            with config_lock:
                nodes = config.get("nodes", {})
                order = config.get("node_order", [])
                if old not in nodes:
                    self._text(404, "Node not found")
                    return
                if new in nodes:
                    self._text(400, "Name already exists")
                    return
                nodes[new] = nodes.pop(old)
                if old in order:
                    order[order.index(old)] = new
                with active_lock:
                    if active_node == old:
                        active_node = new
                save_config()
            self._text(200, f"Renamed {old} to {new}")
        else:
            self._text(404, "Not found")

    def do_DELETE(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if parsed.path == "/nodes":
            name = params.get("name", [None])[0]
            if not name:
                self._text(400, "name required")
                return
            with config_lock:
                nodes = config.get("nodes", {})
                order = config.get("node_order", [])
                if name in nodes:
                    del nodes[name]
                    if name in order:
                        order.remove(name)
                    global active_node
                    with active_lock:
                        if active_node == name:
                            active_node = next(iter(nodes)) if nodes else None
                    save_config()
                    node_conn.switch(active_node or "")
                    self._text(200, f"Removed {name}")
                else:
                    self._text(404, "Node not found")
        else:
            self._text(404, "Not found")

    def _do_restart(self):
        time.sleep(0.5)
        os.execv(__file__, sys.argv)

    def _html(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def _text(self, code, body):
        self.send_response(code)
        self.end_headers()
        self.wfile.write(body.encode())

    def _json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, *args):
        pass


def start_http_server():
    server = HTTPServer(("0.0.0.0", HTTP_PORT), SwitchHandler)
    print(f"Switch server listening on port {HTTP_PORT}")
    server.serve_forever()

# --- Main ---


def is_relevant_device(dev):
    name = dev.name.lower()
    if "vc4" in name or "hdmi" in name:
        return False
    return True


def find_devices():
    devices = []
    for path in evdev.list_devices():
        dev = InputDevice(path)
        if not is_relevant_device(dev):
            continue
        caps = dev.capabilities()
        has_keyboard_keys = ecodes.EV_KEY in caps and ecodes.KEY_A in caps.get(ecodes.EV_KEY, [])
        has_relative_axes = ecodes.EV_REL in caps
        if has_keyboard_keys or has_relative_axes:
            devices.append(dev)
    return devices


if __name__ == "__main__":
    devices = find_devices()
    print(f"Found {len(devices)} device(s):")
    for dev in devices:
        caps = dev.capabilities()
        kbd = ecodes.EV_KEY in caps and ecodes.KEY_A in caps.get(ecodes.EV_KEY, [])
        mse = ecodes.EV_REL in caps
        print(f"  {dev.name}  (kbd={kbd}, mouse={mse})")

    threads = []
    for dev in devices:
        print(f"Reading: {dev.name}")
        t = threading.Thread(target=read_device, args=(dev, dev.name), daemon=True)
        t.start()
        threads.append(t)

    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()

    with active_lock:
        current = active_node
    print(f"Controller running. Active node: {current}")

    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("Shutting down...")
