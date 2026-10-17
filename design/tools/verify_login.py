#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""登录页原型验证：截图 + 交互断言 + 版面几何断言。
用 --window-size 设定真实视口，并读取 window.innerWidth/innerHeight 作为基准，避免窗口外框/内视口不一致。"""
import base64, json, os, struct, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = "file:///root/OMS/design/prototypes/login.html"
OUT = os.path.normpath(os.path.join(HERE, "..", "prototypes", "screenshots", "login"))
CHROME = "/snap/chromium/current/usr/lib/chromium-browser/chrome"
DRIVER = "/snap/chromium/current/usr/lib/chromium-browser/chromedriver"
PORT = 9519
BASE = f"http://127.0.0.1:{PORT}"
os.makedirs(OUT, exist_ok=True)
checks = []


def call(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


def check(label, ok, detail=""):
    checks.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))


class Session:
    # Chrome 的窗口外框比内容视口高 143px，这里做补偿，保证拿到目标视口尺寸
    CHROME_FRAME_H = 143

    def __init__(self, w, h, name, mobile=False):
        self.name = name
        self.mobile = mobile
        caps = {"capabilities": {"alwaysMatch": {
            "browserName": "chrome",
            "goog:chromeOptions": {"binary": CHROME, "args": [
                "--headless=new", "--no-sandbox", "--disable-gpu",
                "--disable-dev-shm-usage", "--hide-scrollbars",
                "--force-device-scale-factor=1", "--disable-breakpad",
                f"--window-size={w},{h + self.CHROME_FRAME_H}"]}}}}
        self.sid = call("POST", "/session", caps)["value"]["sessionId"]
        call("POST", f"/session/{self.sid}/url", {"url": PAGE})
        time.sleep(0.8)
        if mobile:
            # 窄屏会被 Chrome 的窗口最小宽度撑到 500px，用 CDP 强制设备尺寸
            self.cdp("Emulation.setDeviceMetricsOverride",
                     {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": True})
            time.sleep(0.5)
        self.W = self.js("return window.innerWidth")
        self.H = self.js("return window.innerHeight")
        print(f"\n### 会话 {name}  实际视口 {self.W}x{self.H}")

    def cdp(self, cmd, params=None):
        return call("POST", f"/session/{self.sid}/goog/cdp/execute",
                    {"cmd": cmd, "params": params or {}})

    def js(self, s, _retry=3):
        # 页面跳转瞬间执行脚本可能返回 500，重试即可
        for attempt in range(_retry + 1):
            try:
                return call("POST", f"/session/{self.sid}/execute/sync",
                            {"script": s, "args": []})["value"]
            except Exception:
                if attempt == _retry:
                    raise
                time.sleep(1.0)

    def shot(self, name):
        b64 = call("GET", f"/session/{self.sid}/screenshot")["value"]
        p = os.path.join(OUT, name)
        open(p, "wb").write(base64.b64decode(b64))
        raw = open(p, "rb").read(33)
        pw, ph = struct.unpack(">II", raw[16:24])
        print(f"  saved {name}  {pw}x{ph}  {os.path.getsize(p)} bytes")

    def box(self, sel):
        return self.js(f"var r=document.querySelector({sel!r}).getBoundingClientRect();"
                       "return [r.left,r.top,r.right,r.bottom,r.width,r.height];")

    def close(self):
        call("DELETE", f"/session/{self.sid}")

    def click(self, sel):
        self.js(f"document.querySelector({sel!r}).click();")
        time.sleep(0.35)

    def nav(self, url):
        call("POST", f"/session/{self.sid}/url", {"url": url})
        time.sleep(0.9)


SUBMIT = ("document.getElementById('loginForm')"
          ".dispatchEvent(new Event('submit',{cancelable:true,bubbles:true}));")


def set_login(s, user, pwd):
    s.js(f"document.getElementById('username').value={user!r};"
         f"document.getElementById('password').value={pwd!r};" + SUBMIT)


def main():
    drv = subprocess.Popen([DRIVER, f"--port={PORT}", "--allowed-ips="],
                           cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                call("GET", "/status"); break
            except Exception:
                time.sleep(0.25)

        # ==================== 桌面端 ====================
        s = Session(1440, 900, "桌面")
        W, H = s.W, s.H

        print("\n[1] 版面几何")
        logo = s.box(".logo")
        check("Logo 在左上角", logo[0] < 60 and logo[1] < 60, f"left={logo[0]:.0f} top={logo[1]:.0f}")
        lang = s.box(".lang-switch")
        check("语言切换在右上角", lang[2] > W - 60 and lang[1] < 60, f"right={W-lang[2]:.0f}px 距右 top={lang[1]:.0f}")
        card = s.box(".login-card")
        cx, cy = (card[0] + card[2]) / 2, (card[1] + card[3]) / 2
        check("登录卡在页面右半区", card[0] > W / 2, f"card.left={card[0]:.0f} > {W/2:.0f}")
        check("登录卡水平位于右侧中部", abs(cx / W - 0.75) < 0.08, f"x中心={cx/W*100:.1f}%")
        check("登录卡垂直居中", abs(cy / H - 0.5) < 0.05, f"y中心={cy/H*100:.1f}%（上留白{card[1]:.0f} 下留白{H-card[3]:.0f}）")
        check("登录卡不溢出视口", card[3] <= H and card[2] <= W, f"bottom={card[3]:.0f}/{H}")
        check("左半区无文案残留", s.js("return document.querySelector('.brand').innerText.trim().length") == 0)
        check("左半区装饰图形可见",
              s.js("return getComputedStyle(document.querySelector('.brand-art')).display") != "none")

        print("\n[2] 初始态")
        check("验证码默认隐藏", s.js("return document.getElementById('captchaField').hidden"))
        check("欢迎语文案", s.js("return document.querySelector('.welcome').innerText.trim()") == "欢迎登录 ModelEngine")
        check("欢迎语未溢出卡片",
              s.js("var t=document.querySelector('.welcome');return t.scrollWidth<=t.clientWidth+1"))
        check("登录按钮撑满卡片内宽",
              abs(s.box(".submit-btn")[4] - (card[4] - 82)) < 2, f"按钮宽={s.box('.submit-btn')[4]:.0f}")
        s.shot("01-desktop-zh.png")

        print("\n[3] 中英文切换")
        s.js("document.querySelector('[data-lang=\"en-US\"]').click();"); time.sleep(0.4)
        check("英文欢迎语", s.js("return document.querySelector('.welcome').innerText.trim()") == "Welcome to ModelEngine")
        check("html lang = en-US", s.js("return document.documentElement.lang") == "en-US")
        check("英文按钮文案", s.js("return document.getElementById('submitLabel').textContent") == "Sign In")
        check("英文欢迎语未溢出",
              s.js("var t=document.querySelector('.welcome');return t.scrollWidth<=t.clientWidth+1"))
        check("英文下卡片尺寸不变", abs(s.box(".login-card")[5] - card[5]) < 40,
              f"zh={card[5]:.0f} en={s.box('.login-card')[5]:.0f}")
        s.shot("02-desktop-en.png")
        # 原型说明浮层：所有 data-i18n 标签都要有键值（曾因缺键而显示 protoTitle 之类的原始键名）
        s.js("document.getElementById('protoToggle').click();"); time.sleep(0.3)
        proto_en = s.js("return document.getElementById('protoPanel').innerText")
        check("英文态下原型说明浮层无未翻译键名",
              "proto" not in proto_en and "Prototype notes (demo only)" in proto_en
              and "Demo account:" in proto_en and "admin / Admin@123" in proto_en,
              proto_en.replace("\n", " / ")[:100])
        check("浮层的演示账户仍保留 code 标记（i18n 未吞掉标记）",
              s.js("return !!document.querySelector('#protoPanel p code')"))
        s.js("document.getElementById('protoToggle').click();"); time.sleep(0.2)
        s.js("document.querySelector('[data-lang=\"zh-CN\"]').click();"); time.sleep(0.3)
        check("切回中文", s.js("return document.documentElement.lang") == "zh-CN")
        s.js("document.getElementById('protoToggle').click();"); time.sleep(0.3)
        check("中文态下原型说明浮层同样无未翻译键名",
              "proto" not in s.js("return document.getElementById('protoPanel').innerText")
              and "演示账户：" in s.js("return document.getElementById('protoPanel').innerText"))
        s.js("document.getElementById('protoToggle').click();"); time.sleep(0.2)

        print("\n[4] 字段校验态")
        s.js(SUBMIT); time.sleep(0.4)
        check("用户名必填提示", s.js("return document.getElementById('usernameError').innerText") == "请输入用户名")
        check("密码必填提示", s.js("return document.getElementById('passwordError').innerText") == "请输入密码")
        s.shot("03-validation.png")

        print("\n[5] 连续失败 → 验证码按需出现")
        set_login(s, "admin", "wrong-pass"); time.sleep(1.0)
        check("统一失败话术（不暴露账户是否存在）",
              s.js("return document.getElementById('formMessage').innerText.trim()") == "用户名或密码错误，请重试")
        check("失败 1 次后验证码仍隐藏", s.js("return document.getElementById('captchaField').hidden"))
        s.shot("04-auth-failed.png")
        set_login(s, "admin", "wrong-pass"); time.sleep(1.2)
        check("失败 2 次（达阈值）后验证码出现", not s.js("return document.getElementById('captchaField').hidden"))
        pw, cap, btn = s.box("#password"), s.box("#captchaField"), s.box(".submit-btn")
        check("验证码在密码框下方", cap[1] >= pw[3] - 1, f"captcha.top={cap[1]:.0f} >= pwd.bottom={pw[3]:.0f}")
        check("验证码在登录按钮上方", cap[3] <= btn[1], f"captcha.bottom={cap[3]:.0f} <= btn.top={btn[1]:.0f}")
        ci, im = s.box("#captcha"), s.box("#captchaImg")
        check("验证码输入框与图片同排", abs(ci[1] - im[1]) < 2 and im[0] >= ci[2] - 1,
              f"input.right={ci[2]:.0f} img.left={im[0]:.0f}")
        check("卡片增高后仍居中且不溢出",
              s.box(".login-card")[3] <= H and abs((s.box(".login-card")[1] + s.box(".login-card")[3]) / 2 / H - 0.5) < 0.06,
              f"bottom={s.box('.login-card')[3]:.0f}/{H}")
        s.js("var c=document.getElementById('captcha');c.value='ZZZZ';"
             "c.dispatchEvent(new Event('input',{bubbles:true}));" + SUBMIT); time.sleep(0.5)
        check("验证码错误提示",
              s.js("return document.getElementById('formMessage').innerText.trim()") == "验证码错误，请重新输入")
        check("验证码错误后自动换图",
              s.js("return document.getElementById('captchaImg').innerHTML.length > 200"))
        s.js("var c=document.getElementById('captcha');c.value='AB12';"
             "c.dispatchEvent(new Event('input',{bubbles:true}));"); time.sleep(0.3)
        s.shot("05-captcha.png")

        print("\n[6] 成功态")
        s.js("document.getElementById('protoReset').click();"); time.sleep(0.5)
        check("重置后验证码隐藏", s.js("return document.getElementById('captchaField').hidden"))
        set_login(s, "admin", "Admin@123"); time.sleep(1.0)
        check("成功提示", s.js("return document.getElementById('formMessage').innerText.trim()") == "登录成功，正在进入系统…")
        check("成功态样式", s.js("return document.getElementById('formMessage').classList.contains('is-success')"))
        check("按钮进入 loading", s.js("return document.getElementById('submitBtn').disabled"))
        s.shot("06-success.png")

        # ---------- 7. 首次登录：强制修改密码（FR-AUTH-006） ----------
        print("\n[7] 首次登录：强制修改密码")
        time.sleep(1.0)                       # 认证通过后进入改密步骤
        check("登录表单被「设置新密码」步骤替换",
              s.js("return document.getElementById('loginForm').hidden")
              and not s.js("return document.getElementById('pwdForm').hidden"))
        check("副标题切换为首次登录提示",
              s.js("return document.getElementById('welcomeSub').innerText.trim()")
              == "首次登录，请先设置新密码",
              s.js("return document.getElementById('welcomeSub').innerText.trim()"))
        plabels = s.js("""return Array.from(document.querySelectorAll('#pwdForm .label'))
                            .map(function(e){return e.innerText.trim();});""")
        check("提示输入「新密码」「确认密码」", plabels == ["新密码", "确认密码"], str(plabels))
        check("给出密码策略提示",
              "至少三类" in s.js("return document.querySelector('#pwdForm .f-hint-lite').innerText"))
        check("登录页不再包含协议弹窗（已移至主界面）",
              s.js("return document.getElementById('agrMask') === null"))
        s.shot("07-first-login-password.png")

        s.click("#pwdSubmitBtn")
        errs = s.js("""return Array.from(document.querySelectorAll('#pwdForm .field-error.is-visible'))
                        .map(function(e){return e.innerText.trim();});""")
        check("空密码提交被拦截（2 项）", len(errs) == 2, str(errs))

        s.js("document.getElementById('newPwd').value='abc';"
             "document.getElementById('newPwd2').value='abc';")
        s.click("#pwdSubmitBtn")
        errs = s.js("""return Array.from(document.querySelectorAll('#pwdForm .field-error.is-visible'))
                        .map(function(e){return e.innerText.trim();});""")
        check("弱密码被密码策略拦截", any("复杂度" in e for e in errs), str(errs))

        s.js("document.getElementById('newPwd').value='Admin@2026';"
             "document.getElementById('newPwd2').value='Admin@2027';")
        s.click("#pwdSubmitBtn")
        errs = s.js("""return Array.from(document.querySelectorAll('#pwdForm .field-error.is-visible'))
                        .map(function(e){return e.innerText.trim();});""")
        check("两次密码不一致被拦截", "两次输入的密码不一致" in errs, str(errs))

        s.js("document.getElementById('newPwd2').value='Admin@2026';")
        s.click("#pwdSubmitBtn"); time.sleep(1.1)      # 改密成功提示出现（尚未跳回表单）
        check("改密成功提示要求用新密码重新登录",
              "请使用新密码重新登录" in s.js("return document.getElementById('pwdMessage').innerText"),
              s.js("return document.getElementById('pwdMessage').innerText.trim()"))
        time.sleep(1.6)
        check("改密后回到登录表单（不直接进入系统）",
              not s.js("return document.getElementById('loginForm').hidden")
              and s.js("return document.getElementById('pwdForm').hidden"))
        check("登录表单给出重新登录提示",
              "请使用新密码重新登录" in s.js("return document.getElementById('formMessage').innerText"),
              s.js("return document.getElementById('formMessage').innerText.trim()"))
        check("密码输入框已清空",
              s.js("return document.getElementById('password').value") == "")
        s.shot("08-relogin-required.png")

        # 初始凭据已失效
        set_login(s, "admin", "Admin@123"); time.sleep(1.2)
        check("初始密码已失效，无法再用它登录",
              s.js("return document.getElementById('formMessage').innerText.trim()")
              == "用户名或密码错误，请重试",
              s.js("return document.getElementById('formMessage').innerText.trim()"))

        # 用新密码登录 → 进入主界面
        set_login(s, "admin", "Admin@2026"); time.sleep(2.4)
        check("用新密码登录成功",
              "app-shell.html" in s.js("return location.href"),
              s.js("return location.href.split('/').pop()"))
        check("进入主界面时置「待确认用户协议」标记（FR-AUTH-008 在主界面触发）",
              s.js("return sessionStorage.getItem('oms.pendingAgreement')") == "1",
              str(s.js("return sessionStorage.getItem('oms.pendingAgreement')")))

        s.close()

        # ==================== 移动端 ====================
        m = Session(390, 844, "移动端", mobile=True)
        check("移动端隐藏左半区", m.js("return getComputedStyle(document.querySelector('.brand')).display") == "none")
        mc = m.box(".login-card")
        check("移动端卡片不溢出",
              mc[0] >= 0 and mc[2] <= m.W and mc[3] <= m.H, f"left={mc[0]:.0f} right={mc[2]:.0f}/{m.W} bottom={mc[3]:.0f}/{m.H}")
        check("移动端顶栏 Logo 与语言按钮不重叠",
              m.box(".logo")[2] < m.box(".lang-switch")[0],
              f"logo.right={m.box('.logo')[2]:.0f} lang.left={m.box('.lang-switch')[0]:.0f}")
        m.shot("09-mobile.png")
        m.close()

        print(f"\n=== 断言 {sum(checks)}/{len(checks)} 通过 ===")
        return 0 if all(checks) else 2
    finally:
        drv.terminate()


if __name__ == "__main__":
    sys.exit(main())
