#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原型静态自检（不启浏览器，秒级）：

1. 内联脚本语法：抽出 <script> 内容交给 node --check
2. i18n：zh-CN / en-US 键集合一致 + 各自无重复键
3. i18n 引用：t('k') / tf('k') / data-i18n / DRAWER_CFG 里的键都能在 zh-CN 找到
4. DOM 引用：$('id') / getElementById('id') 指向的 id 在 HTML 或 JS 模板串里存在
5. 标签闭合：div / table / thead / tbody / tr / td / th / aside / main / header / section / button

用法：python3 design/tools/static_check.py [页面路径]
"""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PAGE = os.path.normpath(os.path.join(HERE, "..", "prototypes", "app-shell.html"))
failures = []
notes = []


def check(label, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def script_body(src):
    m = re.search(r"<script>\n(.*)\n</script>", src, re.S)
    return m.group(1) if m else ""


def object_body(src, start_pat):
    """从 I18N 定义中取出某个语言块的内容（按大括号配平）。"""
    m = re.search(start_pat, src)
    if not m:
        return ""
    i = src.index("{", m.end() - 1)
    depth, j = 0, i
    while j < len(src):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i + 1:j]
        j += 1
    return ""


def keys_of(block):
    """取出对象的一级键（跳过字符串里的内容与嵌套对象，支持一行写多个键）。"""
    keys, depth, i, n = [], 0, 0, len(block)
    while i < n:
        ch = block[i]
        if ch in "'\"`":
            quote, i = ch, i + 1
            while i < n:
                if block[i] == "\\":
                    i += 2
                    continue
                if block[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif depth == 0:
            m = re.match(r"([A-Za-z_$][\w$]*)\s*:", block[i:])
            if m and (i == 0 or block[i - 1] in "{,\n\r\t "):
                keys.append(m.group(1))
                i += m.end()
                continue
        i += 1
    return keys


def strip_comments(text):
    """把 // 与 /* */ 注释替换为等长空格（保留偏移），字符串内的内容原样保留。"""
    out, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "'\"`":
            quote = ch
            out.append(ch)
            i += 1
            while i < n:
                if text[i] == "\\":
                    out.append(text[i:i + 2])
                    i += 2
                    continue
                out.append(text[i])
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out.append(" " * (j - i))
            i = j
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            j = n if j == -1 else j
            out.append(" " * (j - i))
            i = j
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def main():
    page = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PAGE
    src = read(page)
    print(f"页面：{page}")

    # 1. 内联脚本语法
    body = script_body(src)
    check("抽到内联脚本", bool(body.strip()), f"{len(body)} 字符")
    if body:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write(body)
            tmp = f.name
        r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
        check("node --check 语法通过", r.returncode == 0, r.stderr.strip()[:200])
        os.unlink(tmp)

    # 2. i18n 键集合与重复键（注释先剔除，避免把注释里的 "xxx:" 当成键）
    zh = keys_of(strip_comments(object_body(src, r"I18N\s*=\s*\{\s*'zh-CN'\s*:")))
    en = keys_of(strip_comments(object_body(src, r"'en-US'\s*:")))
    check("抽到 zh-CN / en-US 键", bool(zh) and bool(en), f"zh {len(zh)} / en {len(en)}")
    dup_zh = sorted({k for k in zh if zh.count(k) > 1})
    dup_en = sorted({k for k in en if en.count(k) > 1})
    check("zh-CN 无重复键", not dup_zh, ", ".join(dup_zh))
    check("en-US 无重复键", not dup_en, ", ".join(dup_en))
    only_zh = sorted(set(zh) - set(en))
    only_en = sorted(set(en) - set(zh))
    check("zh-CN / en-US 键一致", not only_zh and not only_en,
          f"缺 en: {only_zh}  缺 zh: {only_en}")

    zhs = set(zh)
    # 3. i18n 引用
    used = set(re.findall(r"\btf?\('([A-Za-z_$][\w$]*)'", strip_comments(body)))
    # fField('id', 'labelKey') / upField('kind', 'labelKey') 的第二个参数也是 i18n 键
    used |= set(re.findall(r"\b(?:fField|upField)\('[^']*',\s*'([A-Za-z_$][\w$]*)'",
                           strip_comments(body)))
    used |= set(re.findall(r'data-i18n(?:-ph|-title)?="([A-Za-z_$][\w$]*)"', src))
    cfg = strip_comments(object_body(src, r"var DRAWER_CFG\s*="))
    used |= set(re.findall(r":\s*'([A-Za-z_$][\w$]*)'", cfg))
    used |= set(re.findall(r"^\s*(?:title|sub|submit|note):\s*'([A-Za-z_$][\w$]*)'", cfg, re.M))
    used |= set(re.findall(r"titleKey:\s*'([A-Za-z_$][\w$]*)'", strip_comments(body)))
    missing = sorted(k for k in used if k not in zhs)
    check("所有 i18n 引用都有中文键", not missing, ", ".join(missing))

    # 4. DOM id 引用
    #    声明来源：静态 HTML 的 id="..."、JS 模板串里的 id="..."、
    #    以及 switchHTML('x') / fField('x') 这类由辅助函数生成 id 的调用；
    #    兜底：某个字面量在源码里出现 3 次以上（引用 + 生成处）也认为已声明。
    declared = set(re.findall(r'id="([\w-]+)"', src))
    declared |= set(re.findall(r"""id=['"]([\w-]+)['"]""", body))
    declared |= set(re.findall(r"(?:switchHTML|fField|fTextarea|fSelect)\('([\w-]+)'", body))
    declared |= {lit for lit in set(re.findall(r"['\"]([\w-]+)['\"]", body))
                 if body.count(f"'{lit}'") >= 3}
    refs = set(re.findall(r"\$\('([\w-]+)'\)", body))
    refs |= set(re.findall(r"getElementById\('([\w-]+)'\)", body))
    refs |= set(re.findall(r"getElementById\([\"']([\w-]+)[\"']\)", body))
    unknown = sorted(refs - declared)
    check("$() / getElementById() 引用的 id 都存在", not unknown, ", ".join(unknown))

    # 5. 标签闭合
    void = {"br", "hr", "img", "input", "meta", "link", "path", "circle", "rect", "source"}
    stack, bad = [], []
    for m in re.finditer(r"<(/?)([a-zA-Z][\w-]*)([^>]*)>", src):
        closing, tag = m.group(1), m.group(2).lower()
        attrs = m.group(3)
        if tag in void or attrs.rstrip().endswith("/"):
            continue
        if not closing:
            stack.append(tag)
        elif stack and stack[-1] == tag:
            stack.pop()
        elif tag in stack:
            bad.append(f"<{tag}> 交叉闭合于 {stack[-5:]}")
            while stack and stack.pop() != tag:
                pass
    check("标签闭合平衡", not bad and not stack, "; ".join(bad + [f"未闭合 {stack[-5:]}"]))

    print()
    if failures:
        print(f"静态自检未通过：{len(failures)} 项失败")
        return 1
    print("静态自检全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
