#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 CDP CSS.getPlatformFontsForNode 查出浏览器【实际】用哪个字体渲染中文，
用于确认页面中文没有回退成豆腐块（.notdef）。"""
import json, os, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = "file:///root/OMS/design/prototypes/login.html"
CHROME = "/snap/chromium/current/usr/lib/chromium-browser/chrome"
DRIVER = "/snap/chromium/current/usr/lib/chromium-browser/chromedriver"
PORT = 9522
BASE = f"http://127.0.0.1:{PORT}"


def call(m, p, pl=None):
    d = json.dumps(pl).encode() if pl is not None else None
    r = urllib.request.Request(BASE + p, data=d, method=m,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=90) as x:
        return json.loads(x.read().decode())


TARGETS = [
    (".welcome", "欢迎登录 ModelEngine（H1 欢迎语）"),
    ("#username", "请输入用户名（占位符）"),
    (".label[for=username]", "用户名（字段标签）"),
    ("#submitLabel", "登 录（按钮）"),
]


TARGETS_SHELL = [
    ("#navHome .nav-text", "首页（侧边栏）"),
    ("#settingsGroup .nav-group-head .nav-text", "设置（侧边栏分组）"),
    ("#settingsGroup .nav-child", "证书管理（侧边栏子条目）"),
    ("#crumb .crumb-item.is-current", "面包屑当前项"),
    (".page-title", "内容区标题"),
    (".placeholder-title", "占位提示文案"),
]


def main():
    page = sys.argv[1] if len(sys.argv) > 1 else PAGE
    if "://" not in page:
        page = "file://" + os.path.abspath(page)
    targets = TARGETS_SHELL if "app-shell" in page else TARGETS
    drv = subprocess.Popen([DRIVER, f"--port={PORT}", "--allowed-ips="],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    fail = 0
    try:
        for _ in range(60):
            try:
                call("GET", "/status"); break
            except Exception:
                time.sleep(0.25)
        caps = {"capabilities": {"alwaysMatch": {
            "browserName": "chrome",
            "goog:chromeOptions": {"binary": CHROME, "args": [
                "--headless=new", "--no-sandbox", "--disable-gpu",
                "--disable-dev-shm-usage", "--hide-scrollbars",
                "--force-device-scale-factor=1", "--disable-breakpad",
                "--window-size=1440,1043"]}}}}
        sid = call("POST", "/session", caps)["value"]["sessionId"]
        call("POST", f"/session/{sid}/url", {"url": page}); time.sleep(0.9)

        def cdp(cmd, params=None):
            return call("POST", f"/session/{sid}/goog/cdp/execute",
                        {"cmd": cmd, "params": params or {}})["value"]

        cdp("DOM.enable"); cdp("CSS.enable")
        root = cdp("DOM.getDocument", {"depth": -1})["root"]["nodeId"]

        print(f"页面：{page}\n")
        for sel, desc in targets:
            nid = cdp("DOM.querySelector", {"nodeId": root, "selector": sel}).get("nodeId")
            if not nid:
                print(f"  [FAIL] 找不到选择器 {sel}"); fail += 1; continue
            fonts = cdp("CSS.getPlatformFontsForNode", {"nodeId": nid}).get("fonts", [])
            used = ", ".join(f"{f['familyName']}({f['glyphCount']}字形)" for f in fonts)
            # 判定：必须真的由某个 CJK 字体提供字形，而不是回退成 .notdef
            ok = any(("CJK" in f["familyName"] or "Source Han" in f["familyName"]
                      or "WenQuanYi" in f["familyName"] or "Noto Sans SC" in f["familyName"])
                     for f in fonts)
            if not ok:
                fail += 1
            print(f"  [{'PASS' if ok else 'FAIL'}] {desc}\n          选择器 {sel} → 实际字体：{used}")

        call("DELETE", f"/session/{sid}")
        print(f"\n=== 中文字体检查：{'全部通过' if fail == 0 else str(fail) + ' 项失败'} ===")
        return 0 if fail == 0 else 2
    finally:
        drv.terminate()


if __name__ == "__main__":
    sys.exit(main())
