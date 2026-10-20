import os, pathlib, json, re, subprocess, sys
from functools import lru_cache

ROOT = pathlib.Path(os.environ.get("CD_ROOT", ".")).resolve()
B = (ROOT / "an2.js").read_text(encoding="utf-8", errors="ignore")


# ---------- 字符串遮罩：标记哪些位置在字符串/模板内 ----------

def skip_regex(s, i):
    """i 指向起始 '/'，跳过正则字面量（含字符类与转义）"""
    i += 1
    in_class = False
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2; continue
        if c == "[":
            in_class = True; i += 1; continue
        if c == "]":
            in_class = False; i += 1; continue
        if c == "/" and not in_class:
            i += 1
            while i < len(s) and (s[i].isalnum() or s[i] in "_$"):
                i += 1
            return i
        if c == "\n":
            return i
        i += 1
    return i


def build_mask(s):
    mask = bytearray(len(s))
    i = 0
    prev = ""
    while i < len(s):
        c = s[i]
        if c == "/" and (prev in "=(:,![&|?{};+-*%^~<>" or prev == ""):
            j = skip_regex(s, i)
            for k in range(i, min(j, len(s))):
                mask[k] = 1
            prev = "/"; i = j; continue
        if c == "`":
            j = skip_template(s, i)
            for k in range(i, min(j, len(s))):
                mask[k] = 1
            i = j
            continue
        if c in "\"'":
            j = skip_string(s, i)
            for k in range(i, min(j, len(s))):
                mask[k] = 1
            i = j
            continue
        if not c.isspace():
            prev = c
        i += 1
    return mask


def outside(pos):
    return not _MASK[pos]


def skip_string(s, i):
    q = s[i]
    i += 1
    while i < len(s):
        if s[i] == "\\":
            i += 2
            continue
        if s[i] == q:
            return i + 1
        i += 1
    return i


def skip_interp(s, i):
    depth = 1
    while i < len(s):
        c = s[i]
        if c == "}":
            depth -= 1
            i += 1
            if depth == 0:
                return i
            continue
        if c == "{":
            depth += 1
            i += 1
            continue
        if c == "`":
            i = skip_template(s, i)
            continue
        if c in "\"'":
            i = skip_string(s, i)
            continue
        i += 1
    return len(s)


def skip_template(s, i):
    i += 1
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "`":
            return i + 1
        if c == "$" and i + 1 < len(s) and s[i + 1] == "{":
            i = skip_interp(s, i + 2)
            continue
        i += 1
    return len(s)


_MASK = build_mask(B)
_k = 666762
while _k > 0 and _MASK[_k]: _k -= 1
print("RUNSTART", _k, repr(B[_k:_k+60]))

HELPERS = {
    "Z": 'var Z = (a, ...v) => (typeof a === "string" ? a : Array.prototype.reduce.call(a, (acc, seg, i) => acc + seg + (i < v.length ? v[i] : ""), ""));',
    "Bk": 'var Bk = a => Array.isArray(a) ? a.join("") : (a == null ? "" : String(a));',
    "V": 'var V = () => "v3";',
    "gh": "var gh = () => true;",
    "Vt": "var Vt = () => true;",
    "Sn": "var Sn = () => true;",
}


def match_paren(s, i):
    depth = 0
    while i < len(s):
        c = s[i]
        if c in "\"'`":
            i = skip_template(s, i) if c == "`" else skip_string(s, i)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def capture_rhs(s, i):
    while i < len(s) and s[i] in " \n\t":
        i += 1
    if i >= len(s):
        return ""
    c = s[i]
    if c == "`":
        j = skip_template(s, i)
        return s[i:j]
    if c in "\"'":
        j = skip_string(s, i)
        return s[i:j]
    depth = 0
    j = i
    while j < len(s):
        ch = s[j]
        if ch in "\"'`":
            j = skip_template(s, j) if ch == "`" else skip_string(s, j)
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif ch in ",;" and depth == 0:
            break
        j += 1
    return s[i:j].strip()


def dec(t):
    out = []
    k = 0
    while k < len(t):
        if t[k] == "\\" and k + 1 < len(t):
            c = t[k + 1]
            if c == "n":
                out.append("\n")
            elif c == "t":
                out.append("\t")
            elif c == "r":
                out.append("\r")
            elif c == "u":
                try:
                    out.append(chr(int(t[k + 2 : k + 6], 16)))
                    k += 6
                    continue
                except Exception:
                    out.append(c)
            else:
                out.append(c)
            k += 2
        else:
            out.append(t[k])
            k += 1
    return "".join(out)


# ---------- FA ----------
m = re.search(r"\bFA=\[", B)
start = m.end() - 1
end = match_paren(B, start)
arr = B[start + 1 : end]


def split_top(s, sep=","):
    out, st, i, d = [], 0, 0, 0
    while i < len(s):
        c = s[i]
        if c in "\"'`":
            i = skip_template(s, i) if c == "`" else skip_string(s, i)
            continue
        if c in "([{":
            d += 1
        elif c in ")]}":
            d -= 1
        elif c == sep and d == 0:
            out.append(s[st:i])
            st = i + 1
        i += 1
    out.append(s[st:])
    return out


items = [x.strip() for x in split_top(arr) if x.strip().startswith("{")]


def field(obj, name):
    mm = re.search(r"(?<![\w$])" + name + r":", obj)
    if not mm:
        return None
    i = mm.end()
    while i < len(obj) and obj[i] in " \n\t":
        i += 1
    c = obj[i]
    if c == "`":
        j = skip_template(obj, i)
        return dec(obj[i + 1 : j - 1])
    if c in "\"'":
        j = skip_string(obj, i)
        return dec(obj[i + 1 : j - 1])
    mm2 = re.match(r"[A-Za-z_$][\w$]*", obj[i:])
    return ("@ref:" + mm2.group(0)) if mm2 else None


skills = []
for it in items:
    e = {
        "id": field(it, "id"),
        "name": field(it, "name"),
        "group": field(it, "group"),
        "subtitle": field(it, "subtitle"),
        "visibility": field(it, "visibility"),
    }
    gm2 = re.search(r"get\s+dcPrompt\s*\(\s*\)\s*\{", it)
    if gm2:
        _bs = gm2.end() - 1
        _be = match_paren(it, _bs)
        _body = it[_bs + 1:_be]
        _rm = re.search(r"\breturn\b\s*", _body)
        e["expr2"] = _body[_rm.end():].strip().rstrip(";") if _rm else ""
    else:
        e["expr2"] = None
    gm = re.search(r"get\s+prompt\s*\(\s*\)\s*\{", it)
    if gm:
        bs = gm.end() - 1
        be = match_paren(it, bs)
        body = it[bs + 1 : be]
        rm = re.search(r"\breturn\b\s*", body)
        e["expr"] = body[rm.end() :].strip().rstrip(";") if rm else ""
    else:
        mm = re.search(r"(?<![\w$])prompt:", it)
        if mm:
            i = mm.end()
            while i < len(it) and it[i] in " \n\t":
                i += 1
            e["expr"] = capture_rhs(it, i)
        else:
            e["expr"] = None
    skills.append(e)


# ---------- 定义查找（只接受字符串外的匹配） ----------
VALID = {}


_SPAWNS = [0]


def _valid(js):
    if js in VALID:
        return VALID[js]
    if _SPAWNS[0] > 600:
        VALID[js] = True
        return True
    _SPAWNS[0] += 1
    try:
        r = subprocess.run(
            ["node", "--check", "-"],
            input="var __x = (" + js + ");",
            capture_output=True,
            text=True,
            timeout=20,
        )
        ok = r.returncode == 0
    except Exception:
        ok = False
    VALID[js] = ok
    return ok


@lru_cache(maxsize=None)
def find_def(name):
    _n = 0
    for mm in re.finditer(r"(?<![\w$.])" + re.escape(name) + r"\s*=", B):
        _n += 1
        if _n > 40:
            break
        if not outside(mm.start()):
            continue
        j = mm.end()
        while j < len(B) and B[j] in " \n\t":
            j += 1
        if j < len(B) and B[j] in "=>":
            continue
        rhs = capture_rhs(B, mm.end())
        if not rhs:
            continue
        if rhs.lstrip().startswith("function"):
            return rhs
        if _valid(rhs):
            return rhs
    for mm in re.finditer(r"function\s+" + re.escape(name) + r"\s*\(", B):
        if not outside(mm.start()):
            continue
        j = mm.end() - 1
        k = match_paren(B, j)
        if k < 0:
            continue
        b = B.find("{", k)
        e = match_paren(B, b)
        if e > 0:
            return B[mm.start() : e + 1]
    return None


BUILTINS = set(
    "Object Array String Number Boolean JSON Math Date RegExp Error TypeError Promise Map Set WeakMap WeakSet Symbol Reflect Proxy Buffer console window document navigator location localStorage sessionStorage fetch setTimeout setInterval clearTimeout clearInterval requestAnimationFrame crypto URL URLSearchParams TextEncoder TextDecoder structuredClone queueMicrotask performance Uint8Array Int8Array Float32Array Float64Array BigInt globalThis".split()
)

RESERVED = set(
    "break case catch class const continue debugger default delete do else export extends finally for function if import in instanceof let new return super switch this throw try typeof var void while with yield await async of static get set true false null undefined NaN Infinity arguments eval".split()
)

LOCAL = set(
    [
        "e",
        "t",
        "n",
        "r",
        "o",
        "i",
        "a",
        "s",
        "u",
        "c",
        "l",
        "d",
        "f",
        "p",
        "m",
        "g",
        "h",
        "v",
        "y",
        "b",
        "x",
        "w",
        "k",
        "j",
        "q",
        "z",
    ]
)


def template_exprs(s, i):
    i += 1
    exprs = []
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "`":
            return i + 1, exprs
        if c == "$" and i + 1 < len(s) and s[i + 1] == "{":
            j = skip_interp(s, i + 2)
            exprs.append(s[i + 2:j - 1])
            i = j
            continue
        i += 1
    return len(s), exprs


def idents(expr):
    out = set()
    i = 0
    while i < len(expr):
        c = expr[i]
        if c == "`":
            j, ex = template_exprs(expr, i)
            for e in ex:
                out |= idents(e)
            i = j
            continue
        if c in "\"'":
            i = skip_string(expr, i)
            continue
        if c.isalpha() or c in "_$":
            j = i
            while j < len(expr) and (expr[j].isalnum() or expr[j] in "_$"):
                j += 1
            w = expr[i:j]
            if w not in RESERVED and (i == 0 or expr[i - 1] != ".") and not re.fullmatch(r"[a-z]", w):
                out.add(w)
            i = j
            continue
        i += 1
    return out


defs = {}
need = set()
for s in skills:
    if s["expr"]:
        need |= idents(s["expr"])
# 只做两层
lvl1 = {n for n in need if find_def(n)}
for n in lvl1:
    d = find_def(n)
    defs[n] = d
    if d and not d.lstrip().startswith("function") and len(d) < 4000:
        pass
_extra = set()
for _n, _d in list(defs.items()):
    if _d and _d.lstrip().startswith("function"):
        for _x in idents(_d):
            if _x not in defs and _x not in HELPERS and _x not in RESERVED and _x not in BUILTINS and len(_x) > 1:
                _extra.add(_x)
for _x in sorted(_extra):
    _dd = find_def(_x)
    if _dd:
        defs[_x] = _dd
for _q in []:
    _r = find_def(_q)
    print("Q", _q, "->", (repr(_r[:45]) + " len=%d" % len(_r)) if _r else "None")
for _round in range(3):
    _want = set()
    for _d in defs.values():
        if _d:
            _want |= idents(_d)
    _new = [x for x in _want if x not in defs and x not in HELPERS and x not in RESERVED and x not in BUILTINS and len(x) > 1]
    _added = False
    for x in _new:
        dd = find_def(x)
        if dd:
            defs[x] = dd
            _added = True
    if not _added:
        break
print("skills", len(skills), "defs", len(defs))
print("DEBUG need:", sorted(need))
for _n in ["Jk", "Yk", "Xk", "Zk", "Dk"]:
    print("DEBUG", _n, "in need:", _n in need, "->", repr((find_def(_n) or "")[:40]))

lines = ["const __out={};"]
def _rank(d):
    t = d.strip()
    if t[:1] in "`\"'" and "${" not in t:
        return 0
    if "${" not in t:
        return 1
    return 2

_nonfn = [(n, d) for n, d in defs.items() if d and not d.lstrip().startswith("function")]
_rankmap = {n: _rank(d) for n, d in _nonfn}
_depmap = {n: (idents(d) & set(defs)) for n, d in _nonfn}
_order, _done = [], set()

def _visit(n, stack=()):
    if n in _done or n in stack:
        return
    for m in sorted(_depmap.get(n, ())):
        if m != n:
            _visit(m, stack + (n,))
    _done.add(n)
    _order.append(n)

for n, _ in sorted(_nonfn, key=lambda kv: (_rankmap[kv[0]], kv[0])):
    _visit(n)
_pos = {n: i for i, n in enumerate(_order)}
_nonfn.sort(key=lambda kv: (_pos.get(kv[0], 10**9), _rankmap[kv[0]], kv[0]))
lines += [
    f"var {n}; try {{ with(__sb) {{ {n} = ({d}); }} }} catch (__e) {{}}"
    for n, d in _nonfn
]
lines += [d for n, d in defs.items() if d and d.lstrip().startswith("function")]
lines += [h for n, h in HELPERS.items()]
# 未解析标识符：预声明，避免 ReferenceError（含 ||= 记忆化）
_allids = set()
for n, d in defs.items():
    if d:
        _allids |= idents(d)
for s in skills:
    if s.get("expr"):
        _allids |= idents(s["expr"])
_undefined = sorted(
    x
    for x in _allids
    if x not in defs
    and x not in HELPERS
    and x not in ("__out",)
    and x not in RESERVED
    and x not in BUILTINS
)
_src_all = "\n".join(
    [d for d in defs.values() if d] + [s["expr"] for s in skills if s.get("expr")]
)
for x in _undefined:
    if re.search(r"(?<![\w$.])" + re.escape(x) + r"\s*\(", _src_all):
        lines.append(f'var {x} = __mk();')
    else:
        lines.append(f'var {x} = "";')
__known = (
    set(defs)
    | set(HELPERS)
    | set(_undefined)
    | {"__out", "__v", "__known", "__sb", "__e"}
)
lines.append('function __mk(){ const o = new Proxy(function(){}, {get:(t,k)=> k===Symbol.toPrimitive ? (()=> "") : (k==="length" ? 0 : ""), apply: () => __mk()}); return o; }')
lines.append("const __known = new Set(%s);" % json.dumps(sorted(__known)))
lines.append(
    'const __sb=new Proxy({},{has:(t,k)=>!(typeof k==="string"&&__known.has(k)),get:(t,k)=>{if(typeof k==="symbol")return undefined;if(k==="length")return 0;const f=function(){return ""};f.length=0;f.toString=function(){return ""};return f;}});'
)
for s in skills:
    for _key, _slot in (("id", "expr"), ("id_dc", "expr2")):
        if not s.get(_slot):
            continue
        _outkey = s["id"] if _slot == "expr" else s["id"] + ":dc"
        lines.append(
            'try{var __v;with(__sb){__v=(%s);}__out[%s]=__v;}catch(e){__out[%s]="__ERR__:"+e.message;}'
            % (s[_slot], json.dumps(_outkey), json.dumps(_outkey))
        )
_kn = [x for x in lines if x.startswith("const __known")]
_sb = [x for x in lines if x.startswith("const __sb")]
_rest = [
    x
    for x in lines
    if not (x.startswith("const __known") or x.startswith("const __sb"))
]
lines = _rest[:1] + _kn + _sb + _rest[1:]
lines.append("console.log(JSON.stringify(__out));")
script = "\n".join(lines)
(ROOT / "eval2.cjs").write_text(script, encoding="utf-8")
r = subprocess.run(
    ["node", str(ROOT / "eval2.cjs")], capture_output=True, text=True, timeout=180
)
print("rc", r.returncode)
if r.returncode != 0:
    print(r.stderr[:1500])
    sys.exit(1)
res = json.loads(r.stdout)
ok = 0
for s in skills:
    p = res.get(s["id"])
    if isinstance(p, list):
        p = "".join(str(x) for x in p)
    s["dcPrompt"] = res.get(s["id"] + ":dc")
    if isinstance(s.get("dcPrompt"), list):
        s["dcPrompt"] = "".join(str(x) for x in s["dcPrompt"])
    if isinstance(s.get("dcPrompt"), str) and s["dcPrompt"].startswith("__ERR__"):
        s["dcPrompt"] = None
    if isinstance(p, str) and p.startswith("__ERR__"):
        s["err"] = p
        p = None
    s["prompt"] = p if isinstance(p, str) else None
    if s.get("prompt") and s["prompt"].strip():
        ok += 1
print(f"non-empty {ok}/{len(skills)}")
for s in skills:
    p = s.get("prompt") or ""
    print(
        f"  {'OK ' if p and not p.startswith('__ERR__') else '-- '}{str(s['id']):24s}{len(p):7d}  {s.get('name')}"
    )
for s in skills:
    nm = s.get("name")
    if isinstance(nm, str) and nm.startswith("@ref:"):
        d = find_def(nm[5:])
        if d:
            try:
                s["name"] = dec(d.strip()[1:-1]) if d.strip()[:1] in "\"'" else nm
            except Exception:
                pass

(ROOT / "skills-current.json").write_text(
    json.dumps(skills, ensure_ascii=False, indent=1), encoding="utf-8"
)
