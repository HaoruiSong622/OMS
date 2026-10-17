#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""无视觉模型时的替代方案：把渲染结果以 0.25 倍栅格抓下来，
用纯标准库解码 PNG，输出「文本灰度图」+ 关键区域像素统计，用于人工判读版面。"""
import base64, json, os, struct, subprocess, sys, time, urllib.request, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = "file:///root/OMS/design/prototypes/login.html"
CHROME = "/snap/chromium/current/usr/lib/chromium-browser/chrome"
DRIVER = "/snap/chromium/current/usr/lib/chromium-browser/chromedriver"
PORT = 9520
BASE = f"http://127.0.0.1:{PORT}"
SCALE = 0.25


def call(m, p, pl=None):
    d = json.dumps(pl).encode() if pl is not None else None
    r = urllib.request.Request(BASE + p, data=d, method=m,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=90) as x:
        return json.loads(x.read().decode())


def decode_png(blob):
    """返回 (w, h, get(x,y)->(r,g,b))，支持 8bit RGB/RGBA、非隔行、filter 0-4。"""
    assert blob[:8] == b"\x89PNG\r\n\x1a\n", "不是 PNG"
    pos, idat = 8, b""
    w = h = ct = None
    while pos < len(blob):
        ln = struct.unpack(">I", blob[pos:pos + 4])[0]
        typ = blob[pos + 4:pos + 8]
        ch = blob[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, bd, ct, _c, _f, inter = struct.unpack(">IIBBBBB", ch)
            assert bd == 8 and inter == 0, f"不支持的 PNG: depth={bd} interlace={inter}"
        elif typ == b"IDAT":
            idat += ch
        elif typ == b"IEND":
            break
        pos += 12 + ln
    nch = {0: 1, 2: 3, 4: 2, 6: 4}[ct]
    raw = zlib.decompress(idat)
    stride = w * nch
    out = bytearray(h * stride)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]; p += 1
        line = bytearray(raw[p:p + stride]); p += stride
        if f == 1:
            for i in range(nch, stride):
                line[i] = (line[i] + line[i - nch]) & 255
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                a = line[i - nch] if i >= nch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a = line[i - nch] if i >= nch else 0
                b = prev[i]
                c = prev[i - nch] if i >= nch else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return w, h, nch, out


RAMP = " .:-=+*#%@"


def render(w, h, nch, buf, cols=120):
    """按字符宽高比 ~1:2 抽样，输出文本灰度图。"""
    rows = max(1, int(cols * (h / w) * 0.5))
    lines = []
    for ry in range(rows):
        y = min(h - 1, int((ry + 0.5) * h / rows))
        line = []
        for rx in range(cols):
            x = min(w - 1, int((rx + 0.5) * w / cols))
            i = (y * w + x) * nch
            r, g, b = buf[i], buf[i + 1], buf[i + 2]
            lum = (r * 299 + g * 587 + b * 114) // 1000
            line.append(RAMP[(255 - lum) * (len(RAMP) - 1) // 255])
        lines.append("".join(line))
    return lines


def region_stats(w, h, nch, buf, x0, y0, x1, y1, label):
    """统计区域内暗像素占比（文字/线条密度）。"""
    dark = 0; tot = 0; colors = {}
    for y in range(y0, min(y1, h)):
        for x in range(x0, min(x1, w)):
            i = (y * w + x) * nch
            r, g, b = buf[i], buf[i + 1], buf[i + 2]
            lum = (r * 299 + g * 587 + b * 114) // 1000
            if lum < 160:
                dark += 1
            tot += 1
            colors[(r // 24 * 24, g // 24 * 24, b // 24 * 24)] = colors.get(
                (r // 24 * 24, g // 24 * 24, b // 24 * 24), 0) + 1
    top = sorted(colors.items(), key=lambda kv: -kv[1])[:3]
    print(f"  {label:<22} 暗像素 {dark/max(tot,1)*100:5.1f}%  主色 "
          + " ".join(f"#{r:02X}{g:02X}{b:02X}({c*100//max(tot,1)}%)" for (r, g, b), c in top))
    return dark / max(tot, 1)


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "zh"
    page = sys.argv[2] if len(sys.argv) > 2 else PAGE
    if "://" not in page:
        page = "file://" + os.path.abspath(page)
    name = os.path.basename(page)
    drv = subprocess.Popen([DRIVER, f"--port={PORT}", "--allowed-ips="],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                call("GET", "/status"); break
            except Exception:
                time.sleep(0.25)
        caps = {"capabilities": {"alwaysMatch": {
            "browserName": "chrome",
            "goog:chromeOptions": {"binary": CHROME, "args": [
                "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
                "--hide-scrollbars", "--disable-breakpad",
                f"--force-device-scale-factor={SCALE}", "--window-size=1440,900"]}}}}
        sid = call("POST", "/session", caps)["value"]["sessionId"]
        call("POST", f"/session/{sid}/url", {"url": page}); time.sleep(0.9)

        def js(s):
            return call("POST", f"/session/{sid}/execute/sync",
                        {"script": s, "args": []})["value"]

        vw, vh = js("return window.innerWidth"), js("return window.innerHeight")
        state = "初始态"

        if name == "login.html":
            if which == "captcha":
                js("document.getElementById('username').value='admin';"
                   "document.getElementById('password').value='x';"
                   "document.getElementById('loginForm')"
                   ".dispatchEvent(new Event('submit',{cancelable:true,bubbles:true}));")
                time.sleep(1.0)
                js("document.getElementById('loginForm')"
                   ".dispatchEvent(new Event('submit',{cancelable:true,bubbles:true}));")
                time.sleep(1.2)
                state = "验证码态"
            elif which == "en":
                js("document.querySelector('[data-lang=\"en-US\"]').click();"); time.sleep(0.5)
                state = "英文态"
        else:  # app-shell.html
            if which == "settings":
                js("location.hash='#/settings/cert';"); time.sleep(0.6)
                state = "设置·证书管理"
            elif which == "noperm":
                js("document.getElementById('protoToggle').click();"); time.sleep(0.3)
                js("document.querySelector('#permSeg button[data-perm=\"none\"]').click();")
                time.sleep(0.6)
                state = "无菜单权限态"
            elif which == "partial":
                js("document.getElementById('protoToggle').click();"); time.sleep(0.3)
                js("document.querySelector('#permSeg button[data-perm=\"partial\"]').click();")
                time.sleep(0.6)
                state = "部分菜单权限态"
            elif which == "en":
                js("document.querySelector('[data-lang=\"en-US\"]').click();"); time.sleep(0.5)
                state = "英文态"

        b64 = call("GET", f"/session/{sid}/screenshot")["value"]
        blob = base64.b64decode(b64)
        w, h, nch, buf = decode_png(blob)
        print(f"\n页面 {name} 视口 {vw}x{vh} → 光栅 {w}x{h}（scale={SCALE}） 状态：{state}")
        print("=" * 120)
        for line in render(w, h, nch, buf):
            print(line)
        print("=" * 120)
        print("关键区域像素统计（坐标为 0.25 倍光栅坐标）：")
        if name == "login.html":
            region_stats(w, h, nch, buf, 0, 0, int(w * .16), int(h * .10), "左上 Logo")
            region_stats(w, h, nch, buf, int(w * .85), 0, w, int(h * .10), "右上语言切换")
            region_stats(w, h, nch, buf, 0, 0, w // 2, h, "左半区（装饰）")
            region_stats(w, h, nch, buf, w // 2, 0, w, h, "右半区（登录）")
        else:
            region_stats(w, h, nch, buf, 0, 0, int(w * .18), h, "左侧边栏")
            region_stats(w, h, nch, buf, int(w * .18), 0, w, int(h * .08), "顶部导航栏")
            region_stats(w, h, nch, buf, int(w * .18), int(h * .08), w, h, "内容区")
        call("DELETE", f"/session/{sid}")
        return 0
    finally:
        drv.terminate()


if __name__ == "__main__":
    sys.exit(main())
