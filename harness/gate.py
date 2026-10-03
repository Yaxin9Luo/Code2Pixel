#!/usr/bin/env python3
"""Code2Pixel 门槛：任何一条不过，总分归零。

用法：
  python3 harness/gate.py runs/pilot-10_codex_run_xxx            # 检查一次运行，写 gate.json
  python3 harness/gate.py runs/a runs/b --size 1536 1024          # 指定尺寸（不在题库里的运行）
  python3 harness/gate.py --summary runs/*/                      # 汇总已有的 gate.json

运行目录里要有 workspace/（out/final.png、src/、run.sh）；有 result.json 时从题库读这道题的门槛设置。

检查五类：
  1. 输出：final.png 存在、能读、尺寸对
  2. 静态扫描（src/ 和 run.sh 里的文本文件）：嵌入位图（data URI、base64、hex）、大段硬编码数据、
     生图或预训练相关的 import、模型权重文件
  3. 复现：只拷文本代码到干净目录，在断网新容器里用 strace 跟踪着重跑 run.sh，结果必须逐像素一致；
     跟踪记录里查读 /workspace 外的图片（按扩展名和文件头）和联网尝试
  4. 作答过程：run.py 默认用 strace 跟踪 agent 作答全过程（run/trace/），作答时读了 /workspace 外的图片也算违规
  5. 题目约束：reward_model.gate.checks 里的检查项（见 CHECKS）
"""
import argparse
import base64
import binascii
import bz2
import gzip
import json
import lzma
import math
import pathlib
import re
import shutil
import subprocess
import time
import zlib

REPO = pathlib.Path(__file__).resolve().parents[1]
IMAGE = "code2pixel/gate:0.1"   # agent 用的镜像 + strace（env/gate/Dockerfile）
TASKS = REPO / "harness" / "tasks" / "pilot.jsonl"

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".tga", ".exr", ".hdr", ".ico",
             ".svg", ".svgz", ".ktx", ".ktx2", ".dds", ".psd", ".avif", ".heic", ".jxl", ".ppm", ".pgm", ".pnm",
             ".jp2", ".icns")
WEIGHT_EXT = ("pt", "pth", "ckpt", "safetensors", "onnx", "gguf", "h5", "tflite", "mlmodel", "pdparams")
PY_FORBIDDEN = ("diffusers", "torch", "torchvision", "tensorflow", "keras", "transformers", "onnxruntime", "jax",
                "flax", "timm", "open_clip", "clip", "safetensors", "huggingface_hub", "openai", "anthropic",
                "replicate", "stability_sdk", "google.generativeai", "mediapipe", "rembg", "ultralytics", "paddle")
JS_FORBIDDEN = ("@tensorflow/", "onnxruntime", "@huggingface/", "@xenova/transformers", "openai", "@anthropic-ai/",
                "@mediapipe/", "replicate")
# Chromium 自己的网络探测（每次渲染都会连），不是 agent 的代码发起的
NET_ALLOWED = {"127.0.0.1", "::1", "2001:4860:4860::8888", "8.8.8.8"}
# 编码后的图片文件头，能抓到被拆成多段字符串拼接的 base64
B64_MAGIC = ("iVBORw0KGgo", "/9j/4", "R0lGODlh", "R0lGODdh", "UklGR", "SUkqAA", "TU0AKg", "H4sIA")
HEX_MAGIC = ("89504e470d0a1a0a", "ffd8ffe0", "ffd8ffe1", "ffd8ffdb", "474946383961", "474946383761")
NUM_VIOLATION, NUM_WARNING = 20_000, 5_000     # 单个文件里的数字字面量个数


def sh(cmd, **kw):
    return subprocess.run(cmd, text=True, capture_output=True, **kw)


def is_text(p):
    try:
        p.read_text(encoding="utf-8")
        return True
    except (UnicodeDecodeError, ValueError):
        return False


def image_magic(b):
    return (b.startswith(b"\x89PNG\r\n\x1a\n") or b.startswith(b"\xff\xd8\xff") or b[:6] in (b"GIF87a", b"GIF89a")
            or (b[:4] == b"RIFF" and b[8:12] == b"WEBP") or b[:4] in (b"II*\x00", b"MM\x00*") or
            b[:4] == b"v/1\x01" or b.startswith(b"#?RADIANCE") or b.startswith(b"#?RGBE") or b[:4] == b"DDS " or
            b[:12] == b"\xabKTX 11\xbb\r\n\x1a\n" or b[4:12] in (b"ftypavif", b"ftypheic"))


def unpack(b):
    """解压常见的压缩格式；不是压缩数据返回 None。"""
    for f in (zlib.decompress, gzip.decompress, bz2.decompress, lzma.decompress):
        try:
            return f(b)
        except Exception:
            pass
    return None


def blob_kind(b):
    """一段解码出来的二进制是什么：image、packed（压缩的大段数据）或 None。"""
    if image_magic(b):
        return "image"
    u = unpack(b)
    if u is not None:
        return "image" if image_magic(u) else ("packed" if len(u) >= 10_000 else None)
    return None


# ---------------------------------------------------------------- 1. 输出
def check_output(ws, size):
    from PIL import Image
    f = ws / "out" / "final.png"
    if not f.exists():
        return {"ok": False, "why": "没有 out/final.png"}
    try:
        im = Image.open(f)
        im.load()
    except Exception as e:
        return {"ok": False, "why": f"读不了：{e}"}
    ok = size is None or list(im.size) == list(size)
    return {"ok": ok, "size": list(im.size), "expected": size, "why": None if ok else "尺寸不对"}


# ---------------------------------------------------------------- 2. 静态扫描
def scan_text(name, s):
    v, w = [], []

    def add(lst, rule, detail):
        lst.append({"rule": rule, "file": name, "detail": detail})

    for m in re.finditer(r"data:image/(png|jpe?g|gif|webp|bmp|avif|x-icon)[;,]", s, re.I):
        add(v, "embedded_bitmap", f"data URI（{m.group(0)}）")
    compact = re.sub(r"[\s\"'`+,\\]", "", s)
    for mg in B64_MAGIC:
        if mg in s or mg in compact:
            add(v, "embedded_bitmap", f"base64 编码的图片文件头 {mg}")
    for mg in HEX_MAGIC:
        if mg in s.lower() or mg in compact.lower():
            add(v, "embedded_bitmap", f"hex 编码的图片文件头 {mg}")
    for m in re.finditer(r"[A-Za-z0-9+/]{200,}={0,2}", s):
        run = m.group(0)
        try:
            kind = blob_kind(base64.b64decode(run[: len(run) // 4 * 4], validate=True))
        except (binascii.Error, ValueError):
            kind = None
        if kind:
            add(v, "embedded_bitmap" if kind == "image" else "embedded_data", f"base64 数据 {len(run)} 字符（{kind}）")
        elif len(run) >= 4000:
            add(w, "suspicious_blob", f"{len(run)} 字符的 base64 样字符串")
    for m in re.finditer(r"(?:\\x)?(?:[0-9a-fA-F]{2}(?:\\x)?){200,}", s):
        h = m.group(0).replace("\\x", "")
        try:
            kind = blob_kind(bytes.fromhex(h))
        except ValueError:
            kind = None
        if kind:
            add(v, "embedded_bitmap" if kind == "image" else "embedded_data", f"hex 数据 {len(h)} 字符（{kind}）")
        elif len(h) >= 4000:
            add(w, "suspicious_blob", f"{len(h)} 字符的 hex 字符串")
    nums = len(re.findall(r"(?<![\w.])-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?(?![\w.])", s))
    if nums > NUM_VIOLATION:
        add(v, "embedded_data", f"{nums} 个数字字面量，像是硬编码的像素或数据")
    elif nums > NUM_WARNING:
        add(w, "many_numbers", f"{nums} 个数字字面量")
    mods = "|".join(re.escape(x) for x in PY_FORBIDDEN)
    for m in re.finditer(rf"^\s*(?:import|from)\s+({mods})\b|(?:__import__|import_module)\(\s*['\"]({mods})\b", s, re.M):
        add(v, "forbidden_import", m.group(1) or m.group(2))
    pkgs = "|".join(re.escape(x) for x in JS_FORBIDDEN)
    for m in re.finditer(rf"(?:require\(|import\(|from\s+|import\s+)\s*['\"]({pkgs})", s):
        add(v, "forbidden_import", m.group(1))
    for m in re.finditer(rf"['\"][^'\"\n]*\.({'|'.join(WEIGHT_EXT)})['\"]", s):
        add(v, "model_weights", m.group(0)[:120])
    return v, w


def check_static(ws):
    v, w, binaries, scanned = [], [], [], 0
    files = [ws / "run.sh"] if (ws / "run.sh").exists() else []
    files += sorted(p for p in (ws / "src").rglob("*") if p.is_file() and "__pycache__" not in p.parts) \
        if (ws / "src").exists() else []
    for p in files:
        rel = str(p.relative_to(ws))
        if not is_text(p):
            binaries.append(rel)
            if p.suffix.lower() in IMAGE_EXT or image_magic(p.read_bytes()[:16]):
                w.append({"rule": "image_in_src", "file": rel, "detail": "src/ 里有图片（复现时不拷，必须由 run.sh 生成）"})
            if p.suffix.lower().lstrip(".") in WEIGHT_EXT:
                v.append({"rule": "model_weights", "file": rel, "detail": "src/ 里有权重文件"})
            continue
        scanned += 1
        a, b = scan_text(rel, p.read_text(encoding="utf-8"))
        v += a
        w += b
    return {"ok": not v, "scanned_files": scanned, "binary_files": binaries}, v, w


# ---------------------------------------------------------------- 3. 复现 + 运行时跟踪
OPEN_RE = re.compile(r'^(open|openat|openat2)\((?:[^,]*,\s*)?"((?:[^"\\]|\\.)*)",\s*([^,)]*).*?=\s*(-?\d+)(?:<([^>]*)>)?')
CONNECT_RE = re.compile(r'^connect\(.*?sa_family=(AF_INET6?),.*?htons\((\d+)\).*?(?:inet_addr\(|inet_pton\(AF_INET6,\s*)"([^"]+)"')
RENAME_RE = re.compile(r'^(?:rename|renameat2?|link|linkat|symlinkat|symlink)\(.*"([^"]+)"[^"]*\)\s*=\s*0')
EXEC_RE = re.compile(r'^execve\("([^"]+)"')


def parse_trace(trace_dir):
    """返回 (读过、但不是这次运行自己写的文件, 写过的文件, 联网尝试, 执行过的程序)。"""
    reads, written, nets, execs = {}, set(), [], set()
    for f in sorted(trace_dir.glob("t.*")):
        for line in f.read_text(errors="ignore").splitlines():
            m = OPEN_RE.match(line)
            if m:
                _, path, flags, ret, resolved = m.groups()
                if int(ret) < 0:
                    continue
                real = resolved or path
                if any(x in flags for x in ("O_WRONLY", "O_RDWR", "O_CREAT")):
                    written.add(real)
                else:
                    reads.setdefault(real, path)
                continue
            m = RENAME_RE.match(line)
            if m:
                written.add(m.group(1))
                continue
            m = CONNECT_RE.match(line)
            if m:
                nets.append({"family": m.group(1), "port": int(m.group(2)), "addr": m.group(3)})
                continue
            m = EXEC_RE.match(line)
            if m:
                execs.add(m.group(1))
    # 每个进程一个跟踪文件，文件之间没有先后顺序，所以最后统一去掉这次运行自己写过的文件
    reads = {k: v for k, v in reads.items() if k not in written}
    return reads, written, nets, sorted(execs)


def sniff(paths):
    """在同一个镜像里读这些文件的文件头，返回是图片的那些（文件在镜像里，主机上没有）。"""
    if not paths:
        return []
    code = ("import sys\nfor p in sys.stdin.read().split('\\0'):\n    try:\n        b=open(p,'rb').read(16)\n"
            "    except Exception:\n        continue\n    sys.stdout.buffer.write(p.encode()+b'\\0'+b.hex().encode()+b'\\n')\n")
    out = subprocess.run(["docker", "run", "--rm", "-i", "--network", "none", IMAGE, "python3", "-c", code],
                         input="\0".join(paths).encode(), capture_output=True).stdout
    hits = []
    for line in out.splitlines():
        p, _, h = line.partition(b"\0")
        if image_magic(bytes.fromhex(h.decode())):
            hits.append(p.decode())
    return hits


def external_images(reads):
    """读过的文件里，/workspace 以外的图片（按扩展名或文件头）。返回 [(路径, 是否按文件头判出)]。"""
    external = [p for p in reads if p.startswith("/") and not p.startswith(("/workspace/", "/proc/", "/sys/", "/dev/"))]
    by_ext = {p for p in external if p.lower().endswith(IMAGE_EXT)}
    by_magic = set(sniff([p for p in external if p not in by_ext]))
    return [(p, p in by_magic) for p in sorted(by_ext | by_magic)], len(external)


def check_session(run):
    """作答过程的跟踪（run.py 默认打开，记录在 run/trace/）：作答时读了 /workspace 以外的图片，同样算违规。
    没有跟踪记录的旧运行只记警告。"""
    trace = run / "trace"
    if not trace.exists() or not any(trace.glob("t.*")):
        return {"traced": False}, [], [{"rule": "no_session_trace", "detail": "没有作答过程的跟踪记录"}]
    reads, written, nets, execs = parse_trace(trace)
    imgs, n = external_images(reads)
    v = [{"rule": "external_image_answering", "detail": p + ("（按文件头）" if magic else "")} for p, magic in imgs]
    return {"traced": True, "external_files_read": n}, v, []


# 复现允许的极小差异（用户 2026-10-02 定）：Blender Cycles 多线程渲染不完全确定，重跑会差几个到几百个像素。
# 复现是为了证明图是这份代码画的，这种噪声不影响结论；读现成图片、硬编码等作弊由其他检查管。
# 阶段 4 实跑里 Blender 的重跑噪声：差得多的像素也只差 27 级、超过 8 级的不到 0.05%，PSNR 最低 55 dB。
REGEN_MIN_PSNR = 50.0
REGEN_BIG_DIFF = 8            # 某个通道差超过这么多级才算"明显不同"的像素
REGEN_MAX_BIG_FRAC = 0.001    # 明显不同的像素最多占这么多


def check_regen(run, ws, minutes):
    from PIL import Image
    import numpy as np
    final = ws / "out" / "final.png"
    if not (ws / "run.sh").exists():
        return {"ok": False, "status": "no_run_sh"}, [{"rule": "regen", "detail": "没有 run.sh"}], []
    tmp = run / "_gate"
    if tmp.exists():
        shutil.rmtree(tmp)
    (tmp / "workspace" / "out").mkdir(parents=True)
    (tmp / "trace").mkdir()
    if (ws / "src").exists():
        shutil.copytree(ws / "src", tmp / "workspace" / "src",
                        ignore=lambda d, names: [n for n in names if n == "__pycache__" or
                                                 ((pathlib.Path(d) / n).is_file() and not is_text(pathlib.Path(d) / n))])
    else:
        (tmp / "workspace" / "src").mkdir()
    shutil.copy(ws / "run.sh", tmp / "workspace" / "run.sh")
    sh(["chmod", "-R", "a+rwX", str(tmp)])
    name = f"c2p-gate-{run.name}".replace("_", "-").lower()[:60]
    sh(["docker", "rm", "-f", name])
    start = time.time()
    proc = subprocess.Popen(
        ["docker", "run", "--name", name, "--network", "none", "--cpus", "4", "--memory", "6g",
         "-v", f"{tmp / 'workspace'}:/workspace", "-v", f"{tmp / 'trace'}:/trace", "-w", "/workspace", IMAGE,
         "strace", "-ff", "-qq", "-y", "-o", "/trace/t", "-e",
         "trace=open,openat,openat2,connect,execve,rename,renameat,renameat2,link,linkat,symlink,symlinkat",
         "bash", "run.sh"],
        stdout=open(tmp / "stdout.log", "w"), stderr=open(tmp / "stderr.log", "w"))
    timed_out = False
    try:
        proc.wait(timeout=minutes * 60)
    except subprocess.TimeoutExpired:
        timed_out = True
        sh(["docker", "kill", name])
        proc.wait()
    sh(["docker", "rm", "-f", name])
    info = {"seconds": round(time.time() - start), "exit_code": proc.returncode}
    v, w = [], []

    # 运行时：读外部图片、联网
    reads, written, nets, execs = parse_trace(tmp / "trace")
    imgs, n_external = external_images(reads)
    for p, magic in imgs:
        v.append({"rule": "external_image", "detail": p + ("（按文件头）" if magic else "")})
    for n in nets:
        if n["addr"] not in NET_ALLOWED:
            v.append({"rule": "network", "detail": f"{n['family']} {n['addr']}:{n['port']}"})
    info.update(external_files_read=n_external, programs=[pathlib.Path(x).name for x in execs])

    out = tmp / "workspace" / "out" / "final.png"
    if timed_out:
        info["status"] = "timeout"
    elif not out.exists():
        info["status"] = "failed"
    elif not final.exists():
        info["status"] = "no_submitted_image"
    else:
        a, b = Image.open(final).convert("RGB"), Image.open(out).convert("RGB")
        if a.size != b.size:
            info["status"] = "size_mismatch"
        else:
            d = (np.asarray(a, np.float64) - np.asarray(b, np.float64))
            mse = (d ** 2).mean()
            info["status"] = "identical" if mse == 0 else "differs"
            if mse:
                psnr = 10 * math.log10(255 ** 2 / mse)
                n_diff = int((d != 0).any(2).sum())
                n_big = int((np.abs(d) > REGEN_BIG_DIFF).any(2).sum())
                npx = a.size[0] * a.size[1]
                info.update(psnr=round(psnr, 2), diff_pixels=n_diff, big_diff_pixels=n_big,
                            big_diff_frac=round(n_big / npx, 6), max_diff=int(np.abs(d).max()))
                if psnr >= REGEN_MIN_PSNR and n_big <= REGEN_MAX_BIG_FRAC * npx:
                    info["status"] = "near_identical"
    if info["status"] not in ("identical", "near_identical"):
        v.append({"rule": "regen", "detail": info["status"] + (f"（PSNR {info.get('psnr')} dB）" if "psnr" in info else "")})
    info["ok"] = info["status"] in ("identical", "near_identical")
    return info, v, w


# ---------------------------------------------------------------- 4. 题目约束
def _box(im, box):
    W, H = im.size
    return (round(box[0] * W), round(box[1] * H), round(box[2] * W), round(box[3] * H))


def check_region_color(im, c, task_dir):
    """box（0–1 的比例坐标）里的平均颜色和 rgb 的距离不超过 tol。"""
    import numpy as np
    a = np.asarray(im.crop(_box(im, c["box"])), np.float64).reshape(-1, 3).mean(0)
    dist = float(np.linalg.norm(a - np.array(c["rgb"], np.float64)))
    return dist <= c.get("tol", 30), {"mean_rgb": [round(x, 1) for x in a], "dist": round(dist, 1)}


def check_unchanged_region(im, c, task_dir):
    """精确修改题：edit_box 以外的像素和参考图 ref 一致：每个通道差不超过 tol 的像素算没变，
    变了的像素最多占框外的 max_frac（光晕、雨丝这类全局效果可能带出极少量变化）。"""
    import numpy as np
    from PIL import Image
    ref = Image.open(task_dir / c["ref"]).convert("RGB")
    if ref.size != im.size:
        return False, {"why": "和参考图尺寸不同"}
    d = np.abs(np.asarray(im, np.int16) - np.asarray(ref, np.int16)).max(2)
    x0, y0, x1, y1 = _box(im, c["edit_box"])
    d[y0:y1, x0:x1] = 0
    bad = int((d > c.get("tol", 0)).sum())
    frac = bad / max(d.size - (y1 - y0) * (x1 - x0), 1)
    return frac <= c.get("max_frac", 0), {"changed_pixels_outside": bad, "changed_frac": round(frac, 5)}


CHECKS = {"region_color": check_region_color, "unchanged_region": check_unchanged_region}


def check_constraints(ws, checks, task_dir):
    from PIL import Image
    res, v = [], []
    f = ws / "out" / "final.png"
    if not checks or not f.exists():
        return res, v
    im = Image.open(f).convert("RGB")
    for c in checks:
        fn = CHECKS.get(c["type"])
        if fn is None:
            raise ValueError(f"未知的检查项：{c['type']}")
        ok, detail = fn(im, c, task_dir)
        res.append({"type": c["type"], "ok": ok, **detail})
        if not ok:
            v.append({"rule": "constraint", "detail": f"{c['type']} {json.dumps(detail, ensure_ascii=False)}"})
    return res, v


# ---------------------------------------------------------------- 主流程
def gate(run, size=None, tasks_file=TASKS):
    ws = run / "workspace"
    result = json.loads((run / "result.json").read_text()) if (run / "result.json").exists() else {}
    task_gate = {}
    if result.get("task_id"):   # 在 harness/tasks/ 下所有题库里找这道题
        for f in sorted(tasks_file.parent.glob("*.jsonl")):
            for l in open(f, encoding="utf-8"):
                if l.strip() and json.loads(l)["extra_info"]["task_id"] == result["task_id"]:
                    task_gate = json.loads(l)["reward_model"]["gate"]
    size = size or task_gate.get("size")
    minutes = (result.get("limits") or {}).get("minutes", 90)

    out = check_output(ws, size)
    violations = [] if out["ok"] else [{"rule": "output", "detail": out["why"]}]
    static, v, warnings = check_static(ws)
    violations += v
    regen, v, w = check_regen(run, ws, minutes)
    violations += v
    warnings += w
    session, v, w = check_session(run)
    violations += v
    warnings += w
    cons, v = check_constraints(ws, task_gate.get("checks"), tasks_file.parent)
    violations += v
    g = {"pass": not violations, "violations": violations, "warnings": warnings,
         "checks": {"output": out, "static": static, "regen": regen, "session": session, "constraints": cons}}
    (run / "gate.json").write_text(json.dumps(g, ensure_ascii=False, indent=1))
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--size", nargs=2, type=int, default=None)
    ap.add_argument("--summary", action="store_true", help="只汇总已有的 gate.json")
    a = ap.parse_args()
    print("| 运行 | 门槛 | 违规 | 警告 | 复现 |")
    print("|---|---|---|---|---|")
    for r in a.runs:
        run = pathlib.Path(r).resolve()
        if a.summary:
            if not (run / "gate.json").exists():
                continue
            g = json.loads((run / "gate.json").read_text())
        else:
            g = gate(run, a.size)
        rules = sorted({x["rule"] for x in g["violations"]})
        warns = sorted({x["rule"] for x in g["warnings"]})
        print(f"| {run.name} | {'通过' if g['pass'] else '不过'} | {', '.join(rules) or '-'} | {', '.join(warns) or '-'} | "
              f"{g['checks']['regen'].get('status')} |", flush=True)


if __name__ == "__main__":
    main()
