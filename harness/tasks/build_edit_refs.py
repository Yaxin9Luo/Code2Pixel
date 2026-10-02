#!/usr/bin/env python3
"""精确修改题的参考图：在 agent 用的镜像里断网跑每份底稿，生成 edit_bases/<名字>/ref.png（不进仓库，按需重建）。

用法：python3 harness/tasks/build_edit_refs.py
底稿来自阶段 1 验收作品的代码（只拷文本文件），都能逐像素复现。ref.png 就是底稿原样跑出来的图，
门槛的 unchanged_region 检查拿它和 agent 改完的图比：编辑区域以外不该变。
"""
import pathlib
import shutil
import subprocess
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
IMAGE = "code2pixel/env:0.1"


def build(base):
    ref = base / "ref.png"
    if ref.exists():
        return "exists"
    tmp = pathlib.Path(tempfile.mkdtemp(dir=HERE.parents[1] / "runs"))   # colima 只挂载主目录
    shutil.copytree(base / "src", tmp / "src")
    shutil.copy(base / "run.sh", tmp / "run.sh")
    (tmp / "out").mkdir()
    subprocess.run(["chmod", "-R", "a+rwX", str(tmp)], check=True)
    p = subprocess.run(["docker", "run", "--rm", "--network", "none", "-v", f"{tmp}:/workspace", "-w", "/workspace",
                        IMAGE, "bash", "run.sh"], capture_output=True, text=True)
    out = tmp / "out" / "final.png"
    if not out.exists():
        return "failed: " + p.stderr[-300:]
    shutil.copy(out, ref)
    shutil.rmtree(tmp)
    return "built"


if __name__ == "__main__":
    for base in sorted(p for p in (HERE / "edit_bases").iterdir() if p.is_dir()):
        print(base.name, build(base), flush=True)
