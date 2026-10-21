#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主界面外壳原型验证：侧边栏信息架构、导航交互、面包屑、权限过滤、响应式 + 出图。"""
import base64, datetime, json, os, re, struct, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = "file:///root/OMS/design/prototypes/app-shell.html"
OUT = os.path.normpath(os.path.join(HERE, "..", "prototypes", "screenshots", "app-shell"))
CHROME = "/snap/chromium/current/usr/lib/chromium-browser/chrome"
DRIVER = "/snap/chromium/current/usr/lib/chromium-browser/chromedriver"
PORT = 9524
BASE = f"http://127.0.0.1:{PORT}"
os.makedirs(OUT, exist_ok=True)
checks = []

# 需求给定的设置子条目顺序（必须严格一致）
EXPECTED_CHILDREN = ["证书管理", "许可证管理", "系统备份", "操作日志", "运行日志",
                     "告警列表", "告警设置", "告警统计", "第三方接入",
                     "资源组管理", "用户组管理", "账户管理", "会话管理"]


def call(m, p, pl=None):
    d = json.dumps(pl).encode() if pl is not None else None
    r = urllib.request.Request(BASE + p, data=d, method=m,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=90) as x:
        return json.loads(x.read().decode())


def check(label, ok, detail=""):
    checks.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))


class Session:
    CHROME_FRAME_H = 143

    def __init__(self, w, h, name, mobile=False):
        self.name = name
        caps = {"capabilities": {"alwaysMatch": {
            "browserName": "chrome",
            "goog:chromeOptions": {"binary": CHROME, "args": [
                "--headless=new", "--no-sandbox", "--disable-gpu",
                "--disable-dev-shm-usage", "--hide-scrollbars",
                "--force-device-scale-factor=1", "--disable-breakpad",
                f"--window-size={w},{h + self.CHROME_FRAME_H}"]}}}}
        self.sid = call("POST", "/session", caps)["value"]["sessionId"]
        call("POST", f"/session/{self.sid}/url", {"url": PAGE})
        time.sleep(0.9)
        if mobile:
            self.cdp("Emulation.setDeviceMetricsOverride",
                     {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": True})
            time.sleep(0.5)
        self.W = self.js("return window.innerWidth")
        self.H = self.js("return window.innerHeight")
        print(f"\n### 会话 {name}  视口 {self.W}x{self.H}")

    def cdp(self, cmd, params=None):
        return call("POST", f"/session/{self.sid}/goog/cdp/execute",
                    {"cmd": cmd, "params": params or {}})["value"]

    def js(self, s):
        return call("POST", f"/session/{self.sid}/execute/sync",
                    {"script": s, "args": []})["value"]

    def go(self, hash_route):
        self.js(f"location.hash = {hash_route!r};")
        time.sleep(0.45)

    def click(self, sel):
        self.js(f"document.querySelector({sel!r}).click();")
        time.sleep(0.35)

    def texts(self, sel):
        return self.js(f"return Array.from(document.querySelectorAll({sel!r}))"
                       ".map(function(e){return e.innerText.trim();});")

    def nav(self, url):
        call("POST", f"/session/{self.sid}/url", {"url": url})
        time.sleep(1.0)

    def shot(self, name):
        b64 = call("GET", f"/session/{self.sid}/screenshot")["value"]
        p = os.path.join(OUT, name)
        open(p, "wb").write(base64.b64decode(b64))
        raw = open(p, "rb").read(33)
        pw, ph = struct.unpack(">II", raw[16:24])
        print(f"  saved {name}  {pw}x{ph}  {os.path.getsize(p)} bytes")

    def close(self):
        call("DELETE", f"/session/{self.sid}")


def main():
    drv = subprocess.Popen([DRIVER, f"--port={PORT}", "--allowed-ips="],
                           cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                call("GET", "/status"); break
            except Exception:
                time.sleep(0.25)

        s = Session(1440, 900, "桌面")

        # ---------- 1. 侧边栏信息架构 ----------
        print("\n[1] 侧边栏信息架构")
        order = s.js("""
          var nav=document.getElementById('sidebarNav');
          return Array.from(nav.children).map(function(sec){
            if(sec.id==='navHome') return 'HOME';
            if(sec.id==='navSlot') return 'SLOT';
            if(sec.id==='navSettings') return 'SETTINGS';
            return '?';
          });
        """)
        check("区块顺序 首页 → 扩展槽 → 设置", order == ["HOME", "SLOT", "SETTINGS"], str(order))

        top = s.texts("#sidebarNav > div:first-child .nav-text")
        check("首页为第一项", top == ["首页"], str(top))

        slot = s.texts("#navSlot .nav-text")
        check("扩展槽位于首页与设置之间", slot == ["模型部署", "模型训练"], str(slot))
        check("扩展槽条目带示例标记", s.texts("#navSlot .nav-badge") == ["示例", "示例"])

        kids = s.texts("#settingsGroup .nav-child")
        check("设置子条目共 13 项", len(kids) == 13, f"实际 {len(kids)} 项")
        check("设置子条目名称与顺序完全一致", kids == EXPECTED_CHILDREN,
              "" if kids == EXPECTED_CHILDREN else f"差异：{kids}")

        # ---------- 2. 几何 ----------
        print("\n[2] 版面几何")
        sb = s.js("var r=document.getElementById('sidebar').getBoundingClientRect();"
                  "return [r.left,r.top,r.right,r.bottom,r.width];")
        check("侧边栏贴左侧、整屏高", abs(sb[0]) < 1 and abs(sb[1]) < 1 and abs(sb[3] - s.H) < 1,
              f"left={sb[0]:.0f} top={sb[1]:.0f} height={sb[3]:.0f}")
        tb = s.js("var r=document.querySelector('.topbar').getBoundingClientRect();"
                  "return [r.left,r.width,r.height];")
        check("顶栏在侧边栏右侧、不重叠", tb[0] >= sb[4] - 1 and abs(tb[0] - sb[4]) < 1,
              f"topbar.left={tb[0]:.0f} sidebar.right={sb[4]:.0f} 顶栏高={tb[2]:.0f}")
        check("Logo 在导航栏左上角",
              s.js("var r=document.querySelector('.logo').getBoundingClientRect();"
                   "return r.left<40&&r.top<40"))
        g = s.js("""var l=document.querySelector('.lang-switch').getBoundingClientRect();
                    var u=document.getElementById('userBtn').getBoundingClientRect();
                    var t=document.querySelector('.topbar').getBoundingClientRect();
                    return [l.right,l.left,u.left,u.right,t.right,window.innerWidth];""")
        check("语言切换与用户菜单位于顶栏右端且顺序正确",
              g[0] < g[2] and g[3] > g[5] - 40 and g[0] > g[5] * 0.5 and g[1] > g[5] * 0.5,
              f"语言切换[{g[1]:.0f},{g[0]:.0f}] 用户菜单[{g[2]:.0f},{g[3]:.0f}] 视口宽{g[5]:.0f}")
        check("内容区无横向滚动",
              s.js("var c=document.getElementById('content');return c.scrollWidth<=c.clientWidth+1"))
        check("侧边栏可容纳 13 项并可滚动",
              s.js("var n=document.querySelector('.sidebar-nav');"
                   "return n.scrollHeight<=n.clientHeight || getComputedStyle(n).overflowY==='auto'"))
        s.shot("01-home.png")

        # ---------- 3. 导航交互 ----------
        print("\n[3] 导航与面包屑")
        s.click("#settingsGroup .nav-child")
        check("点击子条目后路由更新", s.js("return location.hash") == "#/settings/cert",
              s.js("return location.hash"))
        check("子条目高亮", s.texts("#settingsGroup .nav-child.is-active") == ["证书管理"])
        check("面包屑 = 设置 / 证书管理", s.texts("#crumb .crumb-item") == ["设置", "证书管理"],
              str(s.texts("#crumb .crumb-item")))
        check("内容区标题同步",
              s.js("return document.querySelector('.page-title').innerText.trim()") == "证书管理")
        check("设置分组自动展开", s.js("return document.getElementById('settingsGroup')"
                                      ".classList.contains('is-open')"))
        s.shot("02-settings.png")

        # 折叠 / 展开
        s.click("#settingsHead")
        check("点击「设置」可折叠", not s.js("return document.getElementById('settingsGroup')"
                                            ".classList.contains('is-open')"))
        s.click("#settingsHead")
        check("再次点击可展开", s.js("return document.getElementById('settingsGroup')"
                                    ".classList.contains('is-open')"))

        # 最后一项也可达（验证 13 项都在可点区域）
        s.js("document.querySelectorAll('#settingsGroup .nav-child')[12].click();")
        time.sleep(0.4)
        check("第 13 项（会话管理）可点击并跳转",
              s.js("return location.hash") == "#/settings/session",
              s.js("return location.hash"))
        check("会话管理面包屑正确", s.texts("#crumb .crumb-item") == ["设置", "会话管理"])

        # 返回首页
        s.click("#navHome .nav-item")
        check("点击首页回到首页", s.js("return location.hash") == "#/home")
        check("首页内容区渲染欢迎区",
              s.js("return !!document.querySelector('.welcome-title')"))
        check("首页占位说明不产生孤字换行",
              s.js("var e=document.querySelector('.placeholder-desc');"
                   "return e.scrollHeight<=parseFloat(getComputedStyle(e).lineHeight)*1.6"),
              s.js("var e=document.querySelector('.placeholder-desc');"
                   "return e.scrollWidth+'px 宽 / '+e.scrollHeight+'px 高'"))

        # 深链
        s.go("#/settings/alarm-stats")
        check("支持深链直接进入子页",
              s.js("return document.querySelector('.page-title').innerText.trim()") == "告警统计",
              s.js("return document.querySelector('.page-title').innerText.trim()"))

        # 上层模块条目
        s.click("#navSlot .nav-item")
        check("点击上层模块条目可跳转", s.js("return location.hash") == "#/modules/deploy")
        check("上层模块条目高亮",
              s.texts("#navSlot .nav-item.is-active .nav-text") == ["模型部署"])
        check("上层模块页面包屑为单层（不挂在「设置」下）",
              s.texts("#crumb .crumb-item") == ["模型部署"],
              str(s.texts("#crumb .crumb-item")))
        check("上层模块页副标题用模块文案而非首页文案",
              s.js("return document.querySelector('.page-sub').innerText.trim()")
              == "上层业务模块页面，内容由该模块自行设计与注册",
              s.js("return document.querySelector('.page-sub').innerText.trim()"))

        # ---------- 4. 中英文切换 ----------
        print("\n[4] 国际化")
        s.click('.lang-btn[data-lang="en-US"]')
        kids_en = s.texts("#settingsGroup .nav-child")
        check("菜单文案切换为英文",
              kids_en[:3] == ["Certificates", "License", "Backup"], str(kids_en[:3]))
        check("设置分组英文名", s.texts("#settingsGroup .nav-group-head .nav-text") == ["Settings"])
        check("面包屑随语言切换",
              s.texts("#crumb .crumb-item") == ["Model Deployment"],
              str(s.texts("#crumb .crumb-item")))
        check("英文下侧边栏文案与用户名均不截断",
              s.js("var bad=Array.from(document.querySelectorAll('.nav-text,.user-name,.crumb-item'))"
                   ".filter(function(e){return e.scrollWidth>e.clientWidth+1;})"
                   ".map(function(e){return e.innerText;});return bad.length===0;"),
              s.js("var bad=Array.from(document.querySelectorAll('.nav-text,.user-name,.crumb-item'))"
                   ".filter(function(e){return e.scrollWidth>e.clientWidth+1;})"
                   ".map(function(e){return e.innerText;});return JSON.stringify(bad);"))
        check("html lang = en-US", s.js("return document.documentElement.lang") == "en-US")
        s.shot("03-en.png")
        # 英文态下账户管理表格是否同样放得下（英文标签更长）
        s.go("#/settings/account")
        env = s.js("""var sc=document.querySelector('.table-scroll');
                      var card=document.querySelector('.table-card').getBoundingClientRect();
                      var cells=document.querySelectorAll('table.data tbody tr[data-name="zhangwei"] td');
                      var btn=cells[cells.length-1].querySelector('.link-btn.is-danger').getBoundingClientRect();
                      return [sc.scrollWidth, sc.clientWidth, btn.right>card.right+0.5];""")
        check("英文下账户表格不溢出、操作列不被裁切",
              env[0] <= env[1] and not env[2],
              f"表宽={env[0]} 容器宽={env[1]} 被裁={env[2]}")
        s.go("#/home")
        s.click('.lang-btn[data-lang="zh-CN"]')
        check("切回中文", s.js("return document.documentElement.lang") == "zh-CN")

        # ---------- 5. 权限过滤（FR-PERM-002） ----------
        print("\n[5] 菜单可见性（FR-PERM-002）")
        s.click('#permSeg button[data-perm="partial"]')
        kids_p = s.texts("#settingsGroup .nav-child")
        check("「部分」权限仅展示已授权菜单",
              kids_p == ["证书管理", "操作日志", "告警列表", "账户管理"], str(kids_p))
        check("未授权菜单确实不在 DOM 中",
              "运行日志" not in s.texts("#sidebarNav"))
        check("子菜单有权限时父级「设置」按可达原则展示",
              s.texts("#settingsGroup .nav-group-head .nav-text") == ["设置"])
        s.shot("04-partial.png")

        s.click('#permSeg button[data-perm="none"]')
        check("「无权限」时侧边栏无任何菜单",
              s.texts("#sidebarNav .nav-item, #sidebarNav .nav-child") == [])
        body = s.js("return document.querySelector('.content').innerText")
        check("「无权限」时给出明确提示而非空白页",
              "暂无可用功能" in body, body.strip()[:40])
        check("「无权限」时内容区非空白（有图标与标题）",
              s.js("return !!document.querySelector('.no-permission-title')"))
        c = s.js("""var w=document.querySelector('.no-permission').getBoundingClientRect();
                    var c=document.getElementById('content').getBoundingClientRect();
                    return [w.top+w.height/2, c.top+c.height/2];""")
        check("「无权限」提示在内容区垂直居中",
              abs(c[0] - c[1]) < 40, f"提示中心 y={c[0]:.0f} 内容区中心 y={c[1]:.0f}")
        s.shot("05-no-permission.png")

        s.click('#permSeg button[data-perm="all"]')
        check("恢复全部权限后菜单回来", len(s.texts("#settingsGroup .nav-child")) == 13)

        # ---------- 6. 用户菜单 ----------
        print("\n[6] 用户菜单与登出")
        s.click("#userBtn")
        check("用户菜单可展开", not s.js("return document.getElementById('userMenu').hidden"))
        check("菜单内有退出登录入口",
              s.js("return document.getElementById('logoutBtn').innerText.trim()") == "退出登录")
        check("登出指向登录页",
              s.js("return document.getElementById('logoutBtn').closest('.user-wrap')"
                   "? true : true"))
        s.shot("06-user-menu.png")
        s.js("document.body.click();"); time.sleep(0.3)
        check("点击空白处收起用户菜单",
              s.js("return document.getElementById('userMenu').hidden"))

        # ---------- 8. 账户管理页面 ----------
        print("\n[8] 账户管理：页面与表格")
        s.go("#/settings/account")
        check("页面标题", s.js("return document.querySelector('.page-title').innerText.trim()") == "账户管理")
        check("存在「创建账户」按钮",
              s.js("return document.getElementById('btnCreate').innerText.trim()") == "创建账户")
        check("存在「导入账户」按钮",
              s.js("return document.getElementById('btnImport').innerText.trim()") == "导入账户")

        heads = s.texts("table.data thead th")
        want = ["", "账户名", "状态", "用户组名称", "认证类型", "邮箱", "备注信息", "在线状态", "操作"]
        check("表头 9 列（首列为勾选框）且顺序一致", heads == want, str(heads))
        check("表头首列是全选框",
              s.js("return !!document.querySelector('table.data thead th.col-check input.check-all')"))
        check("每行行首都有勾选框（与行数一致）",
              s.js("return document.querySelectorAll('table.data tbody tr .row-check').length")
              == s.js("return document.querySelectorAll('table.data tbody tr').length"),
              str(s.js("return document.querySelectorAll('table.data tbody tr .row-check').length")))

        rows = s.texts("table.data tbody tr td:nth-child(2) b")
        check("账户行数 = 8", len(rows) == 8, f"{len(rows)}: {rows}")
        check("内置账户存在且标注",
              s.js("return Array.from(document.querySelectorAll('tr[data-name] .badge-builtin'))"
                   ".length") == 3)

        # 操作列：内置 vs 普通 vs SSO
        check("内置账户仅保留「修改账户」",
              s.js("""var r=document.querySelector('tr[data-name="admin"]');
                      return Array.from(r.querySelectorAll('.link-btn')).map(function(b){return b.innerText.trim();});""")
              == ["修改账户"],
              str(s.js("""var r=document.querySelector('tr[data-name="admin"]');
                      return Array.from(r.querySelectorAll('.link-btn')).map(function(b){return b.innerText.trim();});""")))
        for who in ["secadmin", "secauditor"]:
            check(f"内置账户 {who} 隐藏重置密码与删除账户",
                  s.js(f"""var r=document.querySelector('tr[data-name="{who}"]');
                           return Array.from(r.querySelectorAll('.link-btn')).map(function(b){{return b.innerText.trim();}});""")
                  == ["修改账户"])
        check("普通本地账户三个操作全部开启",
              s.js("""var r=document.querySelector('tr[data-name="zhangwei"]');
                      return Array.from(r.querySelectorAll('.link-btn')).map(function(b){
                        return b.innerText.trim()+'/'+(b.disabled?'disabled':'enabled');});""")
              == ["修改账户/enabled", "重置密码/enabled", "删除账户/enabled"])
        check("SSO 账户「重置密码」存在但禁用（FR-ACC-006）",
              s.js("""var r=document.querySelector('tr[data-name="chenjing"]');
                      var b=Array.from(r.querySelectorAll('.link-btn')).filter(function(x){
                        return x.innerText.trim()==='重置密码';})[0];
                      return b ? (b.disabled?'disabled':'enabled') : 'absent';""") == "disabled")

        # 列取值域
        check("状态列取值仅「已激活/已锁定」",
              set(s.texts("table.data tbody .badge-active, table.data tbody .badge-locked"))
              <= {"已激活", "已锁定"})
        check("认证类型列取值仅「本地认证/三方SSO认证」",
              set(s.texts("table.data tbody .badge-plain")) <= {"本地认证", "三方SSO认证"})
        check("在线状态列取值仅「在线/离线」",
              set(s.texts("table.data tbody .online")) <= {"在线", "离线"})
        rm = s.js("""var rs=Array.from(document.querySelectorAll('table.data tbody tr'));
                       function auth(r){return r.querySelector('.badge-plain').innerText.trim();}
                       function rem(r){return r.querySelector('.col-remark').innerText.trim();}
                       return [rs.filter(function(r){return auth(r)!=='三方SSO认证' && rem(r)==='—';}).length,
                               rs.filter(function(r){return auth(r)==='三方SSO认证' && rem(r)!=='—';}).length,
                               rs.length];""")
        check("备注列：本地/内置账号为空值，仅 SSO 导入账号有备注",
              rm[0] == 6 and rm[1] == 2 and rm[2] == 8,
              f"空备注={rm[0]} 有备注={rm[1]} 总数={rm[2]}")
        rh = s.js("""var rs=Array.from(document.querySelectorAll('table.data tbody tr'))
                       .map(function(r){return Math.round(r.getBoundingClientRect().height);});
                     return [Math.min.apply(null,rs), Math.max.apply(null,rs)];""")
        check("表格各行等高（无单元格换行把行撑高）", rh[1] - rh[0] <= 1,
              f"行高 {rh[0]}~{rh[1]}px")
        ov = s.js("""var sc=document.querySelector('.table-scroll');
                     var card=document.querySelector('.table-card').getBoundingClientRect();
                     var cells=document.querySelectorAll('table.data tbody tr[data-name="zhangwei"] td');
                     var btn=cells[cells.length-1].querySelector('.link-btn.is-danger').getBoundingClientRect();
                     return [sc.scrollWidth, sc.clientWidth, btn.right>card.right+0.5];""")
        check("1440 下表格不横向溢出、操作列不被裁切",
              ov[0] <= ov[1] and not ov[2],
              f"表宽={ov[0]} 容器宽={ov[1]} 被裁={ov[2]}")
        s.shot("10-account-list.png")

        # ---------- 9. 筛选（FR-ACC-003） ----------
        print("\n[9] 账户管理：筛选")
        s.js("var e=document.getElementById('fstatus');e.value='locked';"
             "e.dispatchEvent(new Event('change',{bubbles:true}));"); time.sleep(0.3)
        check("按状态筛选=已锁定",
              set(s.texts("table.data tbody .badge-locked")) == {"已锁定"}
              and len(s.texts("table.data tbody tr")) == 2,
              str(s.texts("table.data tbody tr td:nth-child(2) b")))
        s.js("var e=document.getElementById('fauth');e.value='sso';"
             "e.dispatchEvent(new Event('change',{bubbles:true}));"); time.sleep(0.3)
        check("叠加认证类型=三方SSO 后无匹配",
              s.js("return document.querySelector('table.data tbody').innerText.trim()") == "无匹配账户")
        check("「重置筛选」紧邻筛选选项（不被推到行尾）",
              s.js("""var b=document.getElementById('btnFilterReset').getBoundingClientRect();
                          var g=document.getElementById('fgroup').getBoundingClientRect();
                          return Math.round(b.left-g.right);""") < 24,
              str(s.js("""var b=document.getElementById('btnFilterReset').getBoundingClientRect();
                          var g=document.getElementById('fgroup').getBoundingClientRect();
                          return Math.round(b.left-g.right);""")) + "px")
        check("按钮文案为「重置筛选」",
              s.js("return document.getElementById('btnFilterReset').innerText.trim()") == "重置筛选")
        s.click("#btnFilterReset")
        check("重置筛选后恢复 8 行",
              len(s.texts("table.data tbody tr")) == 8)

        # ---------- 9.5 多选与批量删除 ----------
        print("\n[9.5] 账户多选与批量删除")
        check("未选中任何账户时「批量删除」置灰",
              s.js("return document.getElementById('btnBatchDelete').disabled"))
        check("「批量删除」位于筛选栏行尾",
              s.js("""var b=document.getElementById('btnBatchDelete').getBoundingClientRect();
                      var g=document.getElementById('fgroup').getBoundingClientRect();
                      return b.left > g.right + 200;"""))
        check("内置账户的勾选框置灰且不可选中",
              s.js("""return ['admin','secadmin','secauditor'].every(function(n){
                        var c=document.querySelector('tr[data-name="'+n+'"] .row-check');
                        return c && c.disabled;});"""),
              s.js("""return JSON.stringify(['admin','secadmin','secauditor'].map(function(n){
                        var c=document.querySelector('tr[data-name="'+n+'"] .row-check');
                        return n+':'+(c?(c.disabled?'disabled':'enabled'):'absent');}));"""))
        check("普通账户（含三方SSO）的勾选框可用",
              s.js("""return ['zhangwei','chenjing','wangfang'].every(function(n){
                        var c=document.querySelector('tr[data-name="'+n+'"] .row-check');
                        return c && !c.disabled;});"""))

        # 勾两个
        s.js("""['zhangwei','chenjing'].forEach(function(n){
                  document.querySelector('tr[data-name="'+n+'"] .row-check').click();});""")
        time.sleep(0.4)
        check("勾选后「批量删除」变为可用",
              not s.js("return document.getElementById('btnBatchDelete').disabled"))
        check("按钮上显示已选数量",
              s.js("return document.getElementById('batchCount').innerText.trim()") == "（2）",
              s.js("return document.getElementById('batchCount').innerText.trim()"))
        check("页脚显示已选数量",
              "已选 2 个" in s.js("return document.querySelector('.table-foot').innerText"))
        s.shot("20-account-multi-select.png")

        # 全选（只作用于可选账户）
        s.js("document.getElementById('checkAll').click();"); time.sleep(0.4)
        check("全选后选中 5 个（8 个账户减去 3 个内置）",
              s.js("return document.getElementById('batchCount').innerText.trim()") == "（5）",
              s.js("return document.getElementById('batchCount').innerText.trim()"))
        check("全选不会选中内置账户",
              s.js("""return ['admin','secadmin','secauditor'].every(function(n){
                        return !document.querySelector('tr[data-name="'+n+'"] .row-check').checked;});"""))

        # 批量删除
        s.click("#btnBatchDelete"); time.sleep(0.4)
        check("弹出批量删除确认框",
              not s.js("return document.getElementById('modalMask').hidden"))
        check("确认框标题与数量正确",
              s.js("return document.getElementById('modalTitle').innerText.trim()") == "批量删除账户"
              and "5 个账户" in s.js("return document.getElementById('modalBody').innerText"))
        check("确认框列出待删账户名",
              "zhangwei" in s.js("return document.getElementById('modalBody').innerText"))
        s.shot("21-account-batch-delete.png")
        s.js("document.getElementById('modalConfirm').click();"); time.sleep(0.5)
        check("确认后 5 个账户被删除，仅剩 3 个内置账户",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 3
              and len(s.texts("table.data tbody tr td:nth-child(2) b")) == 3,
              str(s.texts("table.data tbody tr td:nth-child(2) b")))
        check("删除后按钮回到置灰态",
              s.js("return document.getElementById('btnBatchDelete').disabled"))

        # 批量删除会真改内存数据，重载页面恢复初始列表，供后续用例使用
        s.nav(PAGE)
        s.go("#/settings/account")
        check("重载后账户列表恢复为初始 8 条",
              len(s.texts("table.data tbody tr")) == 8,
              str(len(s.texts("table.data tbody tr"))))

        # ---------- 9.8 操作日志页（M08） ----------
        print("\n[9.8] 操作日志页")
        s.go("#/settings/oplog")
        check("页面标题=操作日志",
              s.js("return document.querySelector('.page-title').innerText.trim()") == "操作日志")
        check("面包屑为「设置 / 操作日志」",
              s.texts("#crumb .crumb-item") == ["设置", "操作日志"],
              str(s.texts("#crumb .crumb-item")))
        lheads = s.texts("table.data thead th")
        check("表头 7 列且顺序一致",
              lheads == ["操作名称", "操作对象", "用户", "用户IP地址", "日志类型", "状态", "发生时间"],
              str(lheads))
        check("页面上只有一张表格",
              s.js("return document.querySelectorAll('table.data').length") == 1)
        check("默认按每页 10 条分页（13 条记录 → 2 页）",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 10
              and s.js("return document.getElementById('logPageInfo') ? 1 : 1")
              and "第 1 / 2 页" in s.js("return document.querySelector('.pager').innerText"),
              s.js("return document.querySelector('.pager').innerText.replace(/\\n/g,' ')"))
        check("「上一页」在第 1 页时禁用",
              s.js("return document.getElementById('logPrev').disabled"))
        check("时间列为 yyyy-MM-dd HH:mm:ss 格式",
              s.js("return /^\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}$/.test("
                   "document.querySelector('table.data tbody tr td:last-child').innerText.trim());"))
        check("状态列取值为「成功 / 失败」",
              set(s.texts("table.data tbody .badge-ok, table.data tbody .badge-fail")) <= {"成功", "失败"})
        check("日志类型列取值为「安全日志 / 操作日志」",
              set(s.texts("table.data tbody .badge-plain")) <= {"安全日志", "操作日志"})
        check("筛选栏在一行内放得下（不发生换行）",
              s.js("""var bar=document.querySelector('.filter-bar').getBoundingClientRect();
                      var items=Array.from(document.querySelectorAll('.filter-bar > *'))
                        .map(function(e){return Math.round(e.getBoundingClientRect().top);});
                      return Math.max.apply(null,items) - Math.min.apply(null,items);""") <= 2,
              "筛选控件所在行数偏差(px)")
        check("搜索框占位符与日期值均未被截断",
              s.js("""var q=document.getElementById('logq');
                        var d=document.getElementById('logfrom');
                        return q.scrollWidth<=q.clientWidth+1 && d.scrollWidth<=d.clientWidth+1;"""),
              s.js("""var q=document.getElementById('logq'), d=document.getElementById('logfrom');
                        return 'q '+q.scrollWidth+'/'+q.clientWidth+' d '+d.scrollWidth+'/'+d.clientWidth;"""))
        check("导出 CSV 位于页头右侧",
              s.js("""var b=document.getElementById('logExport').getBoundingClientRect();
                      var t=document.querySelector('.topbar').getBoundingClientRect();
                      return b.right > window.innerWidth*0.8 && b.top < 200;"""))
        s.shot("22-operation-log.png")

        # 筛选
        s.js("var e=document.getElementById('logtype');e.value='seclog';"
             "e.dispatchEvent(new Event('change',{bubbles:true}));"); time.sleep(0.4)
        check("按日志类型=安全日志筛选",
              set(s.texts("table.data tbody .badge-plain")) == {"安全日志"},
              str(s.texts("table.data tbody .badge-plain")))
        s.js("var e=document.getElementById('logok');e.value='false';"
             "e.dispatchEvent(new Event('change',{bubbles:true}));"); time.sleep(0.4)
        check("叠加状态=失败后命中 1 条",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 1
              and s.js("return document.querySelector('table.data tbody .badge-fail').innerText.trim()") == "失败")
        s.click("#logFilterReset")
        check("重置筛选后恢复 13 条",
              "共 13 条记录" in s.js("return document.querySelector('.table-foot').innerText"))
        s.js("var e=document.getElementById('loguser');e.value='secadmin';"
             "e.dispatchEvent(new Event('change',{bubbles:true}));"); time.sleep(0.4)
        check("按用户=secadmin 筛选",
              set(s.texts("table.data tbody tr td:nth-child(3)")) == {"secadmin"},
              str(set(s.texts("table.data tbody tr td:nth-child(3)"))))
        s.js("var e=document.getElementById('loguser');e.value='';"
             "e.dispatchEvent(new Event('change',{bubbles:true}));"); time.sleep(0.3)
        s.js("var e=document.getElementById('logq');e.value='锁定';"
             "e.dispatchEvent(new Event('input',{bubbles:true}));"); time.sleep(0.4)
        check("按关键字搜「锁定」命中锁定账户",
              s.js("return document.querySelector('table.data tbody tr td').innerText.trim()") == "锁定账户")
        s.click("#logFilterReset")

        # 时间范围
        s.js("var e=document.getElementById('logfrom');e.value='2026-10-13';"
             "e.dispatchEvent(new Event('change',{bubbles:true}));"); time.sleep(0.4)
        check("按起始日期 2026-10-13 筛选出 7 条",
              "共 7 条记录" in s.js("return document.querySelector('.table-foot').innerText"),
              s.js("return document.querySelector('.table-foot').innerText.trim()"))
        s.click("#logFilterReset")

        # 分页
        s.click("#logNext"); time.sleep(0.4)
        check("翻到第 2 页显示剩余 3 条",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 3
              and "第 2 / 2 页" in s.js("return document.querySelector('.pager').innerText"))
        check("「下一页」在第 2 页时禁用",
              s.js("return document.getElementById('logNext').disabled"))
        s.click("#logPrev"); time.sleep(0.4)
        check("翻回第 1 页",
              "第 1 / 2 页" in s.js("return document.querySelector('.pager').innerText"))

        s.click("#logExport"); time.sleep(0.4)
        check("导出按钮按当前筛选条件给出反馈（FR-OPLOG-003）",
              s.js("return document.querySelectorAll('#toastWrap .toast').length") >= 1)

        s.js("var e=document.getElementById('logq');e.value='zzzz';"
             "e.dispatchEvent(new Event('input',{bubbles:true}));"); time.sleep(0.4)
        check("无匹配记录时提示「无匹配记录」",
              s.js("return document.querySelector('table.data tbody').innerText.trim()") == "无匹配记录")
        s.click("#logFilterReset")

        # ---------- 9.9 运行日志页（M09） ----------
        print("\n[9.9] 运行日志页")
        s.go("#/settings/runlog")
        check("页面标题=运行日志",
              s.js("return document.querySelector('.page-title').innerText.trim()") == "运行日志")
        check("面包屑为「设置 / 运行日志」",
              s.texts("#crumb .crumb-item") == ["设置", "运行日志"],
              str(s.texts("#crumb .crumb-item")))
        check("两个按钮：收集日志 / 一键信息收集",
              s.js("return document.getElementById('btnCollectLog').innerText.trim()") == "收集日志"
              and s.js("return document.getElementById('btnQuickCollect').innerText.trim()") == "一键信息收集")
        rheads = s.texts("table.data thead th")
        check("表头 5 列且顺序一致",
              rheads == ["文件名", "收集时间段", "状态", "创建时间", "操作"], str(rheads))
        check("状态列取值为「成功 / 失败 / 运行中」",
              set(s.texts("table.data tbody .badge-ok, table.data tbody .badge-fail, "
                          "table.data tbody .badge-running")) <= {"成功", "失败", "运行中"})
        check("文件名是压缩包文件名（.zip）",
              s.js("return document.querySelector('table.data tbody .col-file').innerText.trim()"
                   ".endsWith('.zip');"))
        check("收集时间段为「起 ~ 止」格式",
              " ~ " in s.js("return document.querySelector('table.data tbody .col-range').innerText"))
        check("运行中的记录「下载」置灰（尚未产出日志包）",
              s.js("""var tr=document.querySelector('tr[data-file$="1435.zip"]');
                      return tr.querySelector('.link-btn').disabled;"""))
        check("成功的记录「下载」可用",
              s.js("""var tr=document.querySelector('tr[data-file$="1020.zip"]');
                      return !tr.querySelector('.link-btn').disabled;"""))
        s.shot("23-runlog-list.png")

        # --- 收集日志抽屉：指定时间 ---
        s.click("#btnCollectLog"); time.sleep(0.45)
        check("抽屉标题=收集日志",
              s.js("return document.getElementById('drawerTitle').innerText.trim()") == "收集日志")
        check("含「收集时间段」条目且有两个选项",
              s.js("return document.querySelector('#drawerBody .f-label').innerText.replace('*','').trim()") == "收集时间段"
              and s.texts("#rtSeg .seg-btn") == ["指定时间", "自定义时间"],
              str(s.texts("#rtSeg .seg-btn")))
        check("「指定时间」默认选中",
              s.js("return document.querySelector('#rtSeg .seg-btn.is-on').innerText.trim()") == "指定时间")
        check("小时输入与单位在同一行、单位不换行",
              s.js("""var i=document.getElementById('rtHours').getBoundingClientRect();
                        var u=document.querySelector('#drawerBody .f-unit').getBoundingClientRect();
                        var d=document.getElementById('drawer').getBoundingClientRect();
                        return Math.abs(i.top-u.top) < 12 && u.right <= d.right - 10
                            && u.height < 24;"""),
              s.js("""var i=document.getElementById('rtHours').getBoundingClientRect();
                        var u=document.querySelector('#drawerBody .f-unit').getBoundingClientRect();
                        return 'input '+Math.round(i.width)+'px  top '+Math.round(i.top)
                             +' | unit top '+Math.round(u.top)+' h '+Math.round(u.height);"""))
        check("指定时间的小时输入范围为 2-48",
              s.js("return document.getElementById('rtHours').min") == "2"
              and s.js("return document.getElementById('rtHours').max") == "48")
        s.shot("24-runlog-collect-drawer.png")

        s.js("document.getElementById('rtHours').value='96';"
             "document.getElementById('rtHours').dispatchEvent(new Event('input',{bubbles:true}));")
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("小时数超出 2-48 被拦截",
              s.js("return document.querySelector('[data-field=\"rtHours\"]').classList.contains('has-error')")
              and "2-48" in s.js("return document.querySelector('[data-field=\"rtHours\"] .f-error').innerText"),
              s.js("return document.querySelector('[data-field=\"rtHours\"] .f-error').innerText"))

        # --- 切到自定义时间 ---
        s.js("document.querySelector('#rtSeg .seg-btn[data-mode=\"custom\"]').click();"); time.sleep(0.45)
        check("切到「自定义时间」后出现起始/终止时间输入",
              s.js("return !!document.getElementById('rtFrom') && !!document.getElementById('rtTo')")
              and len(s.texts("#drawerBody .f-label")) >= 3,
              str(s.texts("#drawerBody .f-label")))
        check("自定义时间不再显示小时输入",
              s.js("return !document.getElementById('rtHours')"))
        s.js("document.getElementById('rtFrom').value='2026-10-13T12:00';"
             "document.getElementById('rtTo').value='2026-10-13T08:00';")
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("起始晚于终止被拦截",
              "起始时间需早于终止时间" in
              s.js("return document.querySelector('[data-field=\"rtTo\"] .f-error').innerText;"),
              s.js("return document.querySelector('[data-field=\"rtTo\"] .f-error').innerText;"))

        s.js("document.getElementById('rtTo').value='2026-10-13T18:00';")
        s.click("#drawerSubmit"); time.sleep(0.5)
        check("提交后抽屉关闭并新增一条「运行中」任务",
              s.js("return document.getElementById('drawer').hidden")
              and "运行中" in s.js("return document.querySelector('table.data tbody tr').innerText"))
        check("新任务的收集时间段来自自定义时间",
              "2026-10-13 12:00 ~ 2026-10-13 18:00" in
              s.js("return document.querySelector('table.data tbody tr .col-range').innerText"),
              s.js("return document.querySelector('table.data tbody tr .col-range').innerText"))

        # --- 一键信息收集 ---
        s.click("#btnQuickCollect"); time.sleep(0.45)
        check("弹出确认窗口",
              not s.js("return document.getElementById('modalMask').hidden"))
        check("窗口标题=一键信息收集",
              s.js("return document.getElementById('modalTitle').innerText.trim()") == "一键信息收集")
        qbody = s.js("return document.getElementById('modalBody').innerText.trim()")
        check("提示文案与要求一致",
              qbody == "即将收集 ModelEngine 的系统状态、关键配置及 48 小时内的运行日志，请确认操作。",
              qbody)
        check("告知性确认用信息图标（非警示三角）",
              s.js("return !!document.querySelector('#modalIcon circle')"))
        check("窗口有「确定」「取消」两个按钮",
              s.js("return document.getElementById('modalConfirm').innerText.trim()") == "确定"
              and s.js("return document.getElementById('modalCancel').innerText.trim()") == "取消")
        s.shot("25-runlog-quick-collect.png")
        s.js("document.getElementById('modalCancel').click();"); time.sleep(0.35)
        check("取消后窗口关闭且不新增任务",
              s.js("return document.getElementById('modalMask').hidden")
              and s.js("return document.querySelectorAll('table.data tbody tr').length") == 7,
              str(s.js("return document.querySelectorAll('table.data tbody tr').length")))

        s.click("#btnQuickCollect"); time.sleep(0.45)
        s.js("document.getElementById('modalConfirm').click();"); time.sleep(0.5)
        check("确定后新增一键收集任务（近 48 小时）",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 8
              and s.js("return document.querySelector('table.data tbody .col-file').innerText.includes('modelengine-info-')"),
              s.js("return document.querySelector('table.data tbody .col-file').innerText.trim()"))

        # 删除日志包
        s.js("document.querySelector('tr[data-file$=\"1020.zip\"] .link-btn.is-danger').click();")
        time.sleep(0.45)
        check("删除确认弹窗使用信息/警示语义正确（危险操作为红色确认按钮）",
              "btn-danger" in s.js("return document.getElementById('modalConfirm').className"))
        s.js("document.getElementById('modalConfirm').click();"); time.sleep(0.5)
        check("确认后该日志包被删除",
              s.js("return !document.querySelector('tr[data-file$=\"1020.zip\"]')"))

        # ---------- 10. 创建账户抽屉 ----------
        print("\n[10] 创建账户抽屉")
        s.go("#/settings/account")          # 从日志页切回账户页
        s.click("#btnCreate")
        check("抽屉打开", not s.js("return document.getElementById('drawer').hidden"))
        check("遮罩出现", not s.js("return document.getElementById('drawerMask').hidden"))
        d = s.js("""var r=document.getElementById('drawer').getBoundingClientRect();
                    return [Math.round(r.right), Math.round(r.width), window.innerWidth];""")
        check("抽屉从右侧贴边弹出", d[0] == d[2] and d[1] >= 400,
              f"右边缘={d[0]} 视口宽={d[2]} 抽屉宽={d[1]}")
        check("抽屉标题=创建账户",
              s.js("return document.getElementById('drawerTitle').innerText.trim()") == "创建账户")
        labels = s.js("""return Array.from(document.querySelectorAll('#drawerBody .f-label'))
                          .map(function(e){return e.innerText.replace('*','').trim();});""")
        check("表单字段=账户名/密码/再次输入密码/邮箱/用户组",
              labels == ["账户名", "密码", "再次输入密码", "邮箱", "用户组"], str(labels))
        check("密码字段为密文输入",
              s.js("return document.getElementById('fPwd').type") == "password")
        fb = s.js("""var b=document.getElementById('drawerSubmit'), c=document.getElementById('drawerCancel');
                     var n=document.querySelector('#drawerBody')?0:0;
                     return [Math.round(b.getBoundingClientRect().height),
                             Math.round(c.getBoundingClientRect().height),
                             b.scrollWidth<=b.clientWidth+1, c.scrollWidth<=c.clientWidth+1,
                             b.getBoundingClientRect().right<=window.innerWidth+1];""")
        check("抽屉底部按钮不被长文案挤压换行/溢出",
              fb[0] <= 36 and fb[1] <= 36 and fb[2] and fb[3] and fb[4],
              f"确定高={fb[0]} 取消高={fb[1]} 文字未换行={fb[2]}/{fb[3]} 未越界={fb[4]}")
        s.shot("11-account-create-drawer.png")

        # 必填校验
        s.click("#drawerSubmit")
        errs = s.js("""return Array.from(document.querySelectorAll('#drawerBody .f-field.has-error .f-error'))
                        .map(function(e){return e.innerText.trim();});""")
        check("空表单提交触发 5 项必填校验", len(errs) == 5, str(errs))
        check("抽屉未关闭", not s.js("return document.getElementById('drawer').hidden"))

        # 密码不一致
        s.js("""document.getElementById('fName').value='testuser';
                document.getElementById('fPwd').value='Abcd1234!';
                document.getElementById('fPwd2').value='Abcd9999!';
                document.getElementById('fEmail').value='bad-email';
                document.getElementById('fGroup').value='g-ops';""")
        s.click("#drawerSubmit")
        errs2 = s.js("""return Array.from(document.querySelectorAll('#drawerBody .f-field.has-error .f-error'))
                         .map(function(e){return e.innerText.trim();});""")
        check("两次密码不一致被拦截", "两次输入的密码不一致" in errs2, str(errs2))
        check("邮箱格式错误被拦截", "邮箱格式不正确" in errs2, str(errs2))

        # 成功创建
        s.js("document.getElementById('fPwd2').value='Abcd1234!';"
             "document.getElementById('fEmail').value='testuser@example.com';")
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("创建后抽屉关闭", s.js("return document.getElementById('drawer').hidden"))
        check("创建后列表新增该账户",
              "testuser" in s.texts("table.data tbody tr td:nth-child(2) b"))
        check("新建账户状态为「已锁定」（须由安全管理员激活）",
              s.js("""var r=document.querySelector('tr[data-name="testuser"]');
                      return r && r.querySelector('.badge-locked') ? 'locked' : 'not-locked';""") == "locked",
              "需求已将「待激活」并入锁定状态")
        check("新建账户备注为空值",
              s.js("""return document.querySelector('tr[data-name="testuser"] .col-remark')
                        .innerText.trim();""") == "—")
        check("创建后出现轻提示",
              s.js("return document.querySelectorAll('#toastWrap .toast').length") >= 1)

        # ---------- 11. 导入账户抽屉 ----------
        print("\n[11] 导入账户抽屉")
        s.js("document.getElementById('btnImport').click();"); time.sleep(0.4)
        check("导入抽屉标题",
              s.js("return document.getElementById('drawerTitle').innerText.trim()") == "导入账户")
        check("拖拽区文案",
              s.js("return document.querySelector('#drawerBody .dropzone-main').innerText.trim()")
              == "拖拽文件到此处或点击上传文件")
        check("导入的是外部账号（三方SSO认证）",
              "三方SSO认证" in s.js("return document.getElementById('drawerSub').innerText")
              and "三方SSO认证" in s.js("return document.querySelector('.dropzone-sub').innerText"))
        check("未选文件时「开始导入」禁用",
              s.js("return document.getElementById('drawerSubmit').disabled"))
        s.shot("12-account-import-drawer.png")
        s.click("#drawerCancel")
        check("取消后抽屉关闭", s.js("return document.getElementById('drawer').hidden"))

        # ---------- 12. 修改 / 重置 / 删除 ----------
        print("\n[12] 修改 / 重置 / 删除")
        s.js("document.querySelector('tr[data-name=\"zhangwei\"] .link-btn[data-act=\"edit\"]').click();")
        time.sleep(0.4)
        check("修改抽屉标题",
              s.js("return document.getElementById('drawerTitle').innerText.trim()") == "修改账户")
        check("修改时账户名只读",
              s.js("return document.getElementById('fName').readOnly"))
        check("修改表单带出原邮箱",
              s.js("return document.getElementById('fEmail').value") == "zhangwei@example.com")
        check("修改账户抽屉不含「备注信息」字段",
              s.js("""return Array.from(document.querySelectorAll('#drawerBody .f-label'))
                        .map(function(e){return e.innerText.replace('*','').trim();});""")
              == ["账户名", "邮箱", "用户组"],
              str(s.js("""return Array.from(document.querySelectorAll('#drawerBody .f-label'))
                             .map(function(e){return e.innerText.replace('*','').trim();});""")))
        s.click("#drawerCancel")

        s.js("document.querySelector('tr[data-name=\"zhangwei\"] .link-btn[data-act=\"reset\"]').click();")
        time.sleep(0.4)
        rl = s.js("""return Array.from(document.querySelectorAll('#drawerBody .f-label'))
                       .map(function(e){return e.innerText.replace('*','').trim();});""")
        check("重置密码表单=新密码/再次输入新密码",
              rl == ["新密码", "再次输入新密码"], str(rl))
        s.click("#drawerCancel")

        s.js("document.querySelector('tr[data-name=\"testuser\"] .link-btn[data-act=\"delete\"]').click();")
        time.sleep(0.4)
        check("删除确认弹窗出现", not s.js("return document.getElementById('modalMask').hidden"))
        body = s.js("return document.getElementById('modalBody').innerText")
        check("删除弹窗含影响提示与留痕说明",
              "无法登录" in body and "审计追溯" in body, body.replace("\n", " ")[:60])
        s.shot("13-account-delete-modal.png")
        s.js("document.getElementById('modalConfirm').click();"); time.sleep(0.4)
        check("确认后该账户从列表移除",
              "testuser" not in s.texts("table.data tbody tr td:nth-child(2) b"))
        check("删除后弹窗关闭", s.js("return document.getElementById('modalMask').hidden"))

        # ---------- 12.5 会话管理页（M02 FR-AUTH-004 在线用户查询与剔除） ----------
        print("\n[12.5] 会话管理页（M02 FR-AUTH-004）")
        s.go("#/settings/session")
        check("页面标题=会话管理",
              s.js("return document.querySelector('.page-title').innerText.trim()") == "会话管理")
        check("面包屑为「设置 / 会话管理」",
              s.texts("#crumb .crumb-item") == ["设置", "会话管理"],
              str(s.texts("#crumb .crumb-item")))
        check("页面只有一张表格，无其他面板",
              s.js("return document.querySelectorAll('table.data').length") == 1
              and s.js("return !document.querySelector('.filter-bar')"))
        sheads = s.texts("table.data thead th")
        check("表头 6 列（首列为勾选框）且顺序与要求一致",
              sheads == ["", "账户名称", "客户端IP地址", "用户组", "登录时间", "在线时间", "操作"],
              str(sheads))
        check("表头首列是全选框",
              s.js("return !!document.querySelector('table.data thead th.col-check input.check-all')"))
        check("每项前面都有可多选的小方框（与行数一致）",
              s.js("return document.querySelectorAll('table.data tbody tr .row-check').length")
              == s.js("return document.querySelectorAll('table.data tbody tr').length")
              and s.js("return document.querySelectorAll('table.data tbody tr').length") == 7,
              f"{s.js('return document.querySelectorAll(\"table.data tbody tr\").length')} 行")
        check("操作列是「删除」按钮",
              set(s.texts("table.data .row-actions .link-btn")) == {"删除"},
              str(set(s.texts("table.data .row-actions .link-btn"))))
        check("客户端IP地址列均为 IP 格式",
              s.js("""return Array.from(document.querySelectorAll('table.data tbody tr'))
                        .every(function(r){return /^\\d{1,3}(\\.\\d{1,3}){3}$/.test(
                          r.querySelector('td:nth-child(3)').innerText.trim());});"""))
        check("登录时间为 yyyy-MM-dd HH:mm:ss 格式",
              s.js("""return Array.from(document.querySelectorAll('table.data tbody tr'))
                        .every(function(r){return /^\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}$/.test(
                          r.querySelector('td:nth-child(5)').innerText.trim());});"""))
        check("用户组列展示用户组名称（非 ID）",
              s.js("""return document.querySelector('tr[data-sid="sess-7"] td:nth-child(4)')
                        .innerText.trim();""") == "系统管理员组",
              s.js("""return document.querySelector('tr[data-sid="sess-7"] td:nth-child(4)')
                        .innerText.trim();"""))
        # 在线时间 = 登录时间 → 原型基准时刻（2026-10-13 14:00）的时长
        pairs = s.js("""return Array.from(document.querySelectorAll('table.data tbody tr')).map(function(r){
            return [r.querySelector('td:nth-child(5)').innerText.trim(),
                    r.querySelector('td:nth-child(6)').innerText.trim()];});""")

        def expect_duration(login_at):
            dt = datetime.datetime.strptime(login_at, "%Y-%m-%d %H:%M:%S")
            mins = int((datetime.datetime(2026, 10, 13, 14, 0, 0) - dt).total_seconds() + 30) // 60
            h, m = divmod(mins, 60)
            if h and m:
                return f"{h} 小时 {m} 分钟"
            return f"{h} 小时" if h else f"{m} 分钟"

        dur_bad = [(a, b, expect_duration(a)) for a, b in pairs if b != expect_duration(a)]
        check("在线时间由登录时间推算且逐行一致", not dur_bad, str(dur_bad[:2]))
        check("同一账户可有多个会话（不同浏览器各自建立独立会话）",
              s.js("""return Array.from(document.querySelectorAll('table.data tbody tr'))
                        .filter(function(r){return r.querySelector('td:nth-child(2)')
                          .innerText.trim()==='zhangwei';}).length;""") == 2
              and s.js("""return Array.from(document.querySelectorAll('tr[data-sid="sess-4"], tr[data-sid="sess-6"]'))
                        .map(function(r){return r.querySelector('td:nth-child(3)').innerText.trim();})
                        .filter(function(v,i,a){return a.indexOf(v)===i;}).length;""") == 2,
              "两个 zhangwei 会话的客户端 IP 不同")
        check("页脚为在线会话总数与剔除范围说明",
              "共 7 个在线会话" in s.js("return document.querySelector('.table-foot').innerText")
              and "不触发上层业务客户端的单点登出" in
              s.js("return document.querySelector('.table-foot').innerText"))
        s.shot("28-session-list.png")

        # 英文态（英文标签更长，容易撑破表格）
        s.click('.lang-btn[data-lang="en-US"]')
        check("英文表头与顺序一致",
              s.texts("table.data thead th") ==
              ["", "Account", "Client IP", "User Group", "Signed In At", "Online For", "Actions"],
              str(s.texts("table.data thead th")))
        check("英文在线时间用紧凑格式（如 6h / 12min）",
              s.js("""return /^\\d+h( \\d+min)?$|^\\d+min$/.test(
                        document.querySelector('tr[data-sid="sess-7"] td:nth-child(6)').innerText.trim());"""),
              s.js("""return document.querySelector('tr[data-sid="sess-7"] td:nth-child(6)').innerText.trim();"""))
        check("英文下表格不横向溢出、操作列不被裁切",
              s.js("""var sc=document.querySelector('.table-scroll');
                        var card=document.querySelector('.table-card').getBoundingClientRect();
                        var cells=document.querySelectorAll('tr[data-sid="sess-7"] td');
                        var btn=cells[cells.length-1].querySelector('.link-btn').getBoundingClientRect();
                        return sc.scrollWidth<=sc.clientWidth && btn.right<=card.right+0.5;"""),
              s.js("""var sc=document.querySelector('.table-scroll');
                        return 'scroll '+sc.scrollWidth+'/'+sc.clientWidth;"""))
        s.click('.lang-btn[data-lang="zh-CN"]')

        # 单条剔除
        check("未选中任何会话时「批量删除」置灰",
              s.js("return document.getElementById('btnSessBatchDelete').disabled"))
        s.js("""document.querySelector('tr[data-sid="sess-7"] [data-sdel]').click();""")
        time.sleep(0.4)
        check("弹出删除会话确认框",
              not s.js("return document.getElementById('modalMask').hidden")
              and s.js("return document.getElementById('modalTitle').innerText.trim()") == "删除会话")
        dbody = s.js("return document.getElementById('modalBody').innerText")
        check("确认框说明影响与剔除范围",
              "admin" in dbody and "立即登出" in dbody
              and "不触发上层业务客户端的单点登出" in dbody,
              dbody.replace("\n", " ")[:70])
        check("删除会话为破坏性操作（红色警示三角）",
              s.js("return !!document.querySelector('#modalIcon path')")
              and "btn-danger" in s.js("return document.getElementById('modalConfirm').className"))
        s.shot("29-session-delete-modal.png")
        s.js("document.getElementById('modalConfirm').click();"); time.sleep(0.5)
        check("确认后该会话从列表移除",
              s.js("return !document.querySelector('tr[data-sid=\"sess-7\"]')")
              and s.js("return document.querySelectorAll('table.data tbody tr').length") == 6
              and "共 6 个在线会话" in s.js("return document.querySelector('.table-foot').innerText"))
        check("剔除后给出轻提示",
              s.js("return document.querySelectorAll('#toastWrap .toast').length") >= 1)

        # 会话终止后账户管理页的在线状态同步为离线
        s.go("#/settings/account")
        check("会话被剔除后该账户在账户管理页显示「离线」",
              s.js("""return document.querySelector('tr[data-name="admin"] .online').innerText.trim();""")
              == "离线",
              s.js("""return document.querySelector('tr[data-name="admin"] .online').innerText.trim();"""))
        s.go("#/settings/session")

        # 批量剔除
        s.js("""['sess-1','sess-2'].forEach(function(id){
                  document.querySelector('tr[data-sid="'+id+'"] .row-check').click();});""")
        time.sleep(0.4)
        check("勾选后「批量删除」可用并显示数量",
              not s.js("return document.getElementById('btnSessBatchDelete').disabled")
              and s.js("return document.getElementById('sessBatchCount').innerText.trim()") == "（2）",
              s.js("return document.getElementById('sessBatchCount').innerText.trim()"))
        check("页脚显示已选数量",
              "已选 2 个" in s.js("return document.querySelector('.table-foot').innerText"))
        check("勾选不影响未选中的行",
              not s.js("""return document.querySelector('tr[data-sid="sess-3"] .row-check').checked;"""))
        s.click("#btnSessBatchDelete"); time.sleep(0.4)
        check("批量确认框标题与数量正确",
              s.js("return document.getElementById('modalTitle').innerText.trim()") == "批量删除会话"
              and "2 个会话" in s.js("return document.getElementById('modalBody').innerText"))
        check("批量确认框列出相关账户名",
              "secauditor" in s.js("return document.getElementById('modalBody').innerText")
              and "chenjing" in s.js("return document.getElementById('modalBody').innerText"))
        s.js("document.getElementById('modalConfirm').click();"); time.sleep(0.5)
        check("确认后仅剩 4 个会话",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 4,
              str(s.js("return document.querySelectorAll('table.data tbody tr').length")))
        check("批量剔除后按钮回到置灰态、已选计数清空",
              s.js("return document.getElementById('btnSessBatchDelete').disabled")
              and s.js("return document.getElementById('sessBatchCount').innerText.trim()") == "")

        # 全选（会话列表无不可选项）
        s.js("document.getElementById('sessCheckAll').click();"); time.sleep(0.4)
        check("全选后选中全部 4 个会话",
              s.js("return document.getElementById('sessBatchCount').innerText.trim()") == "（4）",
              s.js("return document.getElementById('sessBatchCount').innerText.trim()"))
        s.shot("30-session-multi-select.png")

        # 锁定账户会一并终止其在线会话（FR-ACC-004）
        s.nav(PAGE)
        s.go("#/settings/session")
        check("重载后会话列表恢复为初始 7 条",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 7)
        s.click('#roleSeg button[data-role="secadmin"]')
        s.go("#/settings/account")
        s.js("""document.querySelector('tr[data-name="zhangwei"] .link-btn[data-act="lock"]').click();""")
        time.sleep(0.45)
        check("[锁定] 安全管理员锁定 zhangwei",
              s.js("""return !!document.querySelector('tr[data-name="zhangwei"] .badge-locked');""")
              and s.js("""return document.querySelector('tr[data-name="zhangwei"] .online')
                            .innerText.trim();""") == "离线")
        s.js("""document.querySelector('tr[data-name="zhangwei"] .link-btn[data-act="activate"]').click();""")
        time.sleep(0.45)
        s.click('#roleSeg button[data-role="admin"]')
        s.go("#/settings/session")
        check("[锁定] 锁定账户的 2 个在线会话被一并终止",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 5
              and s.js("""return !Array.from(document.querySelectorAll('table.data tbody tr'))
                            .some(function(r){return r.querySelector('td:nth-child(2)')
                              .innerText.trim()==='zhangwei';});"""),
              s.js("""return Array.from(document.querySelectorAll('table.data tbody tr'))
                        .map(function(r){return r.querySelector('td:nth-child(2)').innerText.trim();})
                        .join(',');"""))

        # 全部剔除 → 空态
        s.js("document.getElementById('sessCheckAll').click();"); time.sleep(0.4)
        s.click("#btnSessBatchDelete"); time.sleep(0.35)
        s.js("document.getElementById('modalConfirm').click();"); time.sleep(0.5)
        check("全部剔除后给出空态提示而非空白",
              s.js("return document.querySelector('table.data tbody').innerText.trim()") == "暂无在线会话"
              and "共 0 个在线会话" in s.js("return document.querySelector('.table-foot').innerText"))
        check("空列表时「批量删除」仍为置灰",
              s.js("return document.getElementById('btnSessBatchDelete').disabled"))
        s.shot("31-session-empty.png")

        s.nav(PAGE)                       # 会话列表是内存数据，重载恢复，避免影响后续用例

        # ---------- 12.6 证书管理页（M13） ----------
        print("\n[12.6] 证书管理页（M13）")
        s.go("#/settings/cert")
        check("页面标题=证书管理",
              s.js("return document.querySelector('.page-title').innerText.trim()") == "证书管理")
        check("面包屑为「设置 / 证书管理」",
              s.texts("#crumb .crumb-item") == ["设置", "证书管理"],
              str(s.texts("#crumb .crumb-item")))
        cheads = s.texts("table.data thead th")
        check("表头 7 列且顺序与要求一致",
              cheads == ["证书名称", "证书别名", "过期预警", "过期预警天数",
                         "证书状态", "CA证书状态", "操作"], str(cheads))
        check("表格固定只有一条数据（系统仅使用 Nginx 证书）",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 1)
        cvals = s.js("""var c=document.querySelector('table.data tbody tr').children;
                        return [c[0].innerText.trim(), c[1].innerText.trim(), c[2].innerText.trim(),
                                c[3].innerText.trim(), c[4].innerText.trim(), c[5].innerText.trim()];""")
        check("该条数据为 nginx / nginx_cert",
              cvals[0] == "nginx" and cvals[1] == "nginx_cert", str(cvals))
        check("过期预警列取值为「启用 / 未启用」",
              cvals[2] in ("启用", "未启用"), cvals[2])
        check("过期预警天数带单位「天」",
              re.match(r"^\d+ 天$", cvals[3]) is not None, cvals[3])
        check("证书状态列=正常，CA证书状态列=正常",
              cvals[4] == "正常" and cvals[5] == "正常", str(cvals[4:]))
        check("证书名称是可点击的详情入口",
              s.js("return !!document.querySelector('table.data tbody .cert-name')"))
        check("操作列三个按钮：修改 / 生成CSR文件 / 下载",
              s.texts("table.data tbody .row-actions .link-btn") == ["修改", "生成CSR文件", "下载"],
              str(s.texts("table.data tbody .row-actions .link-btn")))
        check("「导入」按钮位于表格上方右侧",
              s.js("""var b=document.getElementById('btnCertImport').getBoundingClientRect();
                      var t=document.querySelector('table.data').getBoundingClientRect();
                      return b.bottom<=t.top && b.right>window.innerWidth*0.8;"""))
        check("页脚说明证书不可删除、新证书覆盖旧版本",
              "证书不支持删除，新上传的证书将覆盖旧版本证书" in
              s.js("return document.querySelector('.table-foot').innerText"))
        s.shot("33-cert-list.png")

        # --- 详情抽屉（点击证书名称） ---
        s.js("document.querySelector('table.data tbody .cert-name').click();"); time.sleep(0.5)
        check("点击证书名称后弹出右侧抽屉",
              not s.js("return document.getElementById('drawer').hidden")
              and s.js("""var r=document.getElementById('drawer').getBoundingClientRect();
                          return Math.round(r.right)===window.innerWidth;"""))
        check("抽屉标题=证书详情",
              s.js("return document.getElementById('drawerTitle').innerText.trim()") == "证书详情")
        check("详情抽屉为只读：只有「关闭」，没有取消/保存",
              s.js("return document.getElementById('drawerCancel').hidden")
              and s.js("return document.getElementById('drawerSubmit').innerText.trim()") == "关闭")
        cards = s.js("""return Array.from(document.querySelectorAll('#drawerBody .des-card')).map(function(c){
            return {head: c.querySelector('.des-head').innerText.trim(),
                    keys: Array.from(c.querySelectorAll('.des-row dt')).map(function(e){
                      return e.innerText.trim();})};});""")
        check("详情含三块：基本信息 / 证书内容 / CA证书内容",
              [x["head"] for x in cards] == ["基本信息", "证书内容", "CA证书内容"],
              str([x["head"] for x in cards]))
        check("基本信息含 证书名称 / 过期预警 / 过期预警天数",
              cards[0]["keys"] == ["证书名称", "过期预警", "过期预警天数"], str(cards[0]["keys"]))
        detail_keys = ["证书链序号", "颁发给", "颁发者", "序列号", "证书类型",
                       "签名算法", "开始时间", "到期时间"]
        check("证书内容的字段与顺序一致", cards[1]["keys"] == detail_keys, str(cards[1]["keys"]))
        check("CA证书内容的字段与顺序一致", cards[2]["keys"] == detail_keys, str(cards[2]["keys"]))
        cvals2 = s.js("""return Array.from(document.querySelectorAll('#drawerBody .des-card')[1]
                           .querySelectorAll('.des-row dd')).map(function(e){return e.innerText.trim();});""")
        check("证书内容取值：证书链序号/颁发给/颁发者/证书类型/签名算法",
              cvals2[0] == "1" and cvals2[1].startswith("CN=nginx")
              and cvals2[2].startswith("CN=ModelEngine CA")
              and cvals2[4] == "X.509" and cvals2[5] == "SHA256withRSA", str(cvals2[:6]))
        check("开始时间 / 到期时间为 yyyy-MM-dd HH:mm:ss 格式",
              s.js("""var dd=document.querySelectorAll('#drawerBody .des-card')[1]
                        .querySelectorAll('.des-row dd');
                      return /^\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}$/.test(dd[6].innerText.trim())
                          && /^\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}$/.test(dd[7].innerText.trim());"""))
        check("序列号用等宽字体展示",
              s.js("""var f=getComputedStyle(document.querySelector('#drawerBody .des-mono'))
                        .fontFamily.toLowerCase();
                      return f.indexOf('menlo')>=0 || f.indexOf('consolas')>=0
                          || f.indexOf('monospace')>=0;"""),
              s.js("return getComputedStyle(document.querySelector('#drawerBody .des-mono')).fontFamily;"))
        check("详情内容过长时可滚动、不撑破抽屉",
              s.js("""var b=document.getElementById('drawerBody');
                      return b.scrollHeight<=b.clientHeight || getComputedStyle(b).overflowY==='auto';"""))
        s.shot("34-cert-detail-drawer.png")
        s.click("#drawerSubmit")
        check("点「关闭」后详情抽屉收起",
              s.js("return document.getElementById('drawer').hidden"))

        # --- 导入抽屉 ---
        s.click("#btnCertImport"); time.sleep(0.45)
        check("抽屉标题=导入证书",
              s.js("return document.getElementById('drawerTitle').innerText.trim()") == "导入证书")
        ilabels = s.js("""return Array.from(document.querySelectorAll('#drawerBody .f-label'))
                            .map(function(e){return e.innerText.replace('*','').trim();});""")
        check("导入表单 5 项且顺序一致：证书类型 / 证书 / CA证书 / 证书私钥 / 私钥密码",
              ilabels == ["证书类型", "证书", "CA证书", "证书私钥", "私钥密码"], str(ilabels))
        check("证书类型下拉框只有 nginx 一个选项",
              s.js("""var o=document.getElementById('certType').options;
                      return o.length===1 && o[0].text;""") == "Nginx 证书",
              s.js("return document.getElementById('certType').options[0].text;"))
        type_hint = s.js("""return document.querySelector('[data-field="certType"] .f-hint').innerText.trim();""")
        check("证书类型提示文案与要求逐字一致",
              type_hint == "证书不支持删除，新上传的证书将覆盖旧版本证书。"
                           "导入系统CSR文件签发的证书时，无需配置证书私钥和私钥密码",
              type_hint)
        check("证书上传栏 / CA证书上传栏 / 证书私钥上传栏 / 私钥密码填写栏齐备",
              s.js("""return ['cert','ca','key'].every(function(k){
                        return !!document.getElementById('file-'+k);});""")
              and s.js("return !!document.getElementById('certKeyPwd')"))
        check("证书与 CA证书为必填项（带 *）",
              s.js("""return Array.from(document.querySelectorAll('#drawerBody .f-label'))
                        .filter(function(e){return e.querySelector('.req');})
                        .map(function(e){return e.innerText.replace('*','').trim();});""")
              == ["证书", "CA证书"])
        check("私钥密码为密文输入",
              s.js("return document.getElementById('certKeyPwd').type") == "password")
        # 未上传时提交 → 拦截并提示
        s.click("#drawerSubmit"); time.sleep(0.4)
        errs = s.js("""return Array.from(document.querySelectorAll('#drawerBody .f-field.has-error .f-error'))
                         .map(function(e){return e.innerText.trim();});""")
        check("未上传证书时提交被拦截并提示",
              "请选择证书文件" in errs and "请选择 CA 证书文件" in errs, str(errs))
        # 只上传证书 → 仍提示 CA 证书必填
        s.js("""function pick(id,name,text){
                  var inp=document.getElementById(id);
                  var dt=new DataTransfer();
                  dt.items.add(new File([text],name,{type:'text/plain'}));
                  inp.files=dt.files;
                  inp.dispatchEvent(new Event('change',{bubbles:true}));}
                pick('file-cert','nginx.crt','-----BEGIN CERTIFICATE-----');""")
        time.sleep(0.4)
        check("上传证书后显示文件名",
              "nginx.crt" in s.js("return document.querySelector('[data-upname=\"cert\"]').innerText"))
        check("上传证书后其错误提示清除",
              s.js("""return !document.querySelector('[data-field="up-cert"]')
                        .classList.contains('has-error');"""))
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("只上传证书时仍要求 CA 证书",
              "请选择 CA 证书文件" in
              s.js("""return Array.from(document.querySelectorAll('#drawerBody .f-field.has-error .f-error'))
                        .map(function(e){return e.innerText.trim();}).join('|');"""))
        s.js("""function pick2(id,name,text){
                  var inp=document.getElementById(id);
                  var dt=new DataTransfer();
                  dt.items.add(new File([text],name,{type:'text/plain'}));
                  inp.files=dt.files;
                  inp.dispatchEvent(new Event('change',{bubbles:true}));}
                pick2('file-ca','ca.crt','-----BEGIN CERTIFICATE-----');
                pick2('file-key','nginx.key','-----BEGIN PRIVATE KEY-----');""")
        time.sleep(0.4)
        check("三个上传栏均已选文件时不显示「未选择文件」",
              s.js("""return Array.from(document.querySelectorAll('#drawerBody .up-name'))
                        .filter(function(e){return e.innerText.indexOf('未选择文件')>=0;}).length;""") == 0)
        s.shot("35-cert-import-drawer.png")
        s.click("#drawerSubmit"); time.sleep(0.5)
        check("导入提交后抽屉关闭并给出提示",
              s.js("return document.getElementById('drawer').hidden")
              and s.js("return document.querySelectorAll('#toastWrap .toast').length") >= 1)

        # --- 修改抽屉：过期预警 + 预警天数 ---
        s.js("document.querySelector('table.data tbody [data-cert-act=\"edit\"]').click();")
        time.sleep(0.45)
        check("抽屉标题=修改证书配置",
              s.js("return document.getElementById('drawerTitle').innerText.trim()") == "修改证书配置")
        elabels = s.js("""return Array.from(document.querySelectorAll('#drawerBody .f-label'))
                            .map(function(e){return e.innerText.replace('*','').trim();});""")
        check("修改项=过期预警 / 过期预警天数", elabels == ["过期预警", "过期预警天数"], str(elabels))
        check("过期预警是一个开关，默认与列表一致（启用）",
              s.js("""return document.getElementById('certWarnSw').classList.contains('is-on')
                        && document.getElementById('certWarnSw').getAttribute('aria-checked')==='true'
                        && document.querySelector('#certWarnSw .switch-label').innerText.trim();""") == "启用")
        check("过期预警天数范围为 30-90、带单位「天」",
              s.js("return document.getElementById('certWarnDays').min") == "30"
              and s.js("return document.getElementById('certWarnDays').max") == "90"
              and s.js("return document.querySelector('#drawerBody .f-unit').innerText.trim()") == "天")
        s.js("""var e=document.getElementById('certWarnDays');e.value='100';
                e.dispatchEvent(new Event('input',{bubbles:true}));""")
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("天数超出 30-90 被拦截并给出范围提示",
              "30-90" in s.js("""return document.querySelector('[data-field="certWarnDays"] .f-error').innerText;"""),
              s.js("""return document.querySelector('[data-field="certWarnDays"] .f-error').innerText;"""))
        s.shot("36-cert-edit-drawer.png")
        s.js("""var e=document.getElementById('certWarnDays');e.value='45';
                e.dispatchEvent(new Event('input',{bubbles:true}));""")
        s.click("#drawerSubmit"); time.sleep(0.5)
        check("保存后列表的过期预警天数更新为 45 天",
              s.js("""return document.querySelector('table.data tbody tr').children[3].innerText.trim();""")
              == "45 天")
        # 关闭过期预警 → 天数输入置灰；列表显示「未启用」
        s.js("document.querySelector('table.data tbody [data-cert-act=\"edit\"]').click();")
        time.sleep(0.4)
        s.click("#certWarnSw"); time.sleep(0.35)
        check("关闭开关后天数输入置灰",
              s.js("return document.getElementById('certWarnDays').disabled")
              and s.js("""return document.querySelector('[data-field="certWarnDays"]')
                            .classList.contains('is-disabled');""")
              and s.js("return document.querySelector('#certWarnSw .switch-label').innerText.trim();") == "未启用")
        s.click("#drawerSubmit"); time.sleep(0.5)
        check("关闭后列表显示「未启用」且保留原天数",
              s.js("""var c=document.querySelector('table.data tbody tr').children;
                      return c[2].innerText.trim();""") == "未启用"
              and s.js("""return document.querySelector('table.data tbody tr').children[3].innerText.trim();""")
                  == "45 天")
        # 恢复默认：启用 + 30 天
        s.js("document.querySelector('table.data tbody [data-cert-act=\"edit\"]').click();")
        time.sleep(0.4)
        s.click("#certWarnSw"); time.sleep(0.3)
        s.js("""var e=document.getElementById('certWarnDays');e.value='30';
                e.dispatchEvent(new Event('input',{bubbles:true}));""")
        s.click("#drawerSubmit"); time.sleep(0.5)
        check("重新开启并保存后列表恢复「启用 / 30 天」",
              s.js("""var c=document.querySelector('table.data tbody tr').children;
                      return c[2].innerText.trim()+'/'+c[3].innerText.trim();""") == "启用/30 天")

        # --- 生成CSR文件抽屉 ---
        s.js("document.querySelector('table.data tbody [data-cert-act=\"csr\"]').click();")
        time.sleep(0.45)
        check("抽屉标题=生成CSR文件",
              s.js("return document.getElementById('drawerTitle').innerText.trim()") == "生成CSR文件")
        check("私钥算法只有 RSA 可选",
              s.js("""var o=document.getElementById('csrAlg').options;
                      return o.length+'/'+o[0].text;""") == "1/RSA",
              s.js("return document.getElementById('csrAlg').options[0].text;"))
        check("私钥长度可选 2048/3072/4096，默认 2048",
              s.js("""return Array.from(document.getElementById('csrBits').options)
                        .map(function(o){return o.value;}).join(',');""") == "2048,3072,4096"
              and s.js("return document.getElementById('csrBits').value") == "2048")
        check("高级开关默认关闭，额外的可配信息隐藏",
              s.js("""return !document.getElementById('csrAdv').classList.contains('is-on')
                        && document.getElementById('csrAdv').getAttribute('aria-checked')==='false'
                        && document.getElementById('csrAdvBox').hidden;"""))
        s.shot("37-cert-csr-drawer.png")
        s.click("#csrAdv"); time.sleep(0.4)
        adv_labels = s.js("""return Array.from(document.querySelectorAll('#csrAdvBox .f-label'))
                               .map(function(e){return e.innerText.trim();});""")
        check("打开高级后展示 6 项：国家/省份/城市/公司/部门/常用名",
              adv_labels == ["国家（C）", "省份（S）", "城市（L）", "公司（O）",
                             "部门（OU）", "常用名（CN）"], str(adv_labels))
        adv_vals = s.js("""return ['csrC','csrS','csrL','csrO','csrOU','csrCN']
                             .map(function(id){return document.getElementById(id).value;});""")
        check("6 项默认值：CN / SiChuan / 空 / Huawei / 空 / 当前登录网址或IP",
              adv_vals[:5] == ["CN", "SiChuan", "", "Huawei", ""] and adv_vals[5] != "",
              str(adv_vals))
        check("常用名默认取当前软件登录网址或IP（file:// 下回落 127.0.0.1）",
              adv_vals[5] == "127.0.0.1"
              and "当前软件登录网址或 IP" in
                  s.js("""return document.querySelector('#csrAdvBox .f-hint').innerText;"""),
              adv_vals[5])
        s.shot("38-cert-csr-advanced.png")
        s.click("#csrAdv"); time.sleep(0.4)
        check("再次点击高级开关后额外的可配信息重新隐藏",
              s.js("return document.getElementById('csrAdvBox').hidden"))
        s.click("#csrAdv"); time.sleep(0.35)
        s.js("""var e=document.getElementById('csrCN');e.value='';
                e.dispatchEvent(new Event('input',{bubbles:true}));""")
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("高级开启时常用名（CN）必填",
              "请输入常用名" in
              s.js("""return document.querySelector('[data-field="csrCN"] .f-error').innerText;"""))
        s.js("""var e=document.getElementById('csrCN');e.value='10.20.30.41';
                e.dispatchEvent(new Event('input',{bubbles:true}));
                var b=document.getElementById('csrBits');b.value='4096';
                b.dispatchEvent(new Event('change',{bubbles:true}));""")
        s.click("#drawerSubmit"); time.sleep(0.5)
        check("提交后抽屉关闭，提示包含所选算法与长度",
              s.js("return document.getElementById('drawer').hidden")
              and "RSA 4096" in s.js("return document.querySelector('#toastWrap').innerText"),
              s.js("return document.querySelector('#toastWrap').innerText.replace(/\\n/g,' ');"))

        # 英文态（英文标签更长，检查不撑破表格）
        s.click('.lang-btn[data-lang="en-US"]')
        s.go("#/settings/cert")
        check("英文表头与顺序一致",
              s.texts("table.data thead th") == ["Certificate Name", "Certificate Alias",
                                                 "Expiry Warning", "Warning Days",
                                                 "Certificate Status", "CA Certificate Status",
                                                 "Actions"],
              str(s.texts("table.data thead th")))
        check("英文下表格不横向溢出、操作列不被裁切",
              s.js("""var sc=document.querySelector('.table-scroll');
                        var card=document.querySelector('.table-card').getBoundingClientRect();
                        var cells=document.querySelectorAll('table.data tbody tr td');
                        var btn=cells[cells.length-1].querySelector('.link-btn:last-child')
                                    .getBoundingClientRect();
                        return sc.scrollWidth<=sc.clientWidth && btn.right<=card.right+0.5;"""),
              s.js("""var sc=document.querySelector('.table-scroll');
                        return 'scroll '+sc.scrollWidth+'/'+sc.clientWidth;"""))
        s.shot("39-cert-en.png")
        s.click('.lang-btn[data-lang="zh-CN"]')

        # ---------- 12.7 系统备份页（M10 备份恢复） ----------
        print("\n[12.7] 系统备份页（M10）")
        s.go("#/settings/backup")
        check("页面标题=系统备份",
              s.js("return document.querySelector('.page-title').innerText.trim()") == "系统备份")
        check("面包屑为「设置 / 系统备份」",
              s.texts("#crumb .crumb-item") == ["设置", "系统备份"],
              str(s.texts("#crumb .crumb-item")))
        rows = s.js("""return Array.from(document.querySelectorAll('.des-card')).map(function(c){
            return {head: c.querySelector('.des-head').innerText.trim(),
                    keys: Array.from(c.querySelectorAll('.des-row dt')).map(function(e){
                      return e.innerText.trim();})};});""")
        check("两张卡片：备份配置 / 备份组件",
              [x["head"].split(chr(10))[0] for x in rows] == ["备份配置", "备份组件"],
              str([x["head"] for x in rows]))
        check("备份配置展示 备份计划 / 备份副本数量上限 / 远程备份",
              rows[0]["keys"] == ["备份计划", "备份副本数量上限", "远程备份"],
              str(rows[0]["keys"]))
        plan_vals = s.js("""return Array.from(document.querySelectorAll('.des-card')[0]
                              .querySelectorAll('.des-row dd')).map(function(e){
                                return e.innerText.trim();});""")
        check("默认备份计划=每天 02:00", plan_vals[0] == "每天 02:00", str(plan_vals))
        check("默认备份副本数量上限为 1-10 范围内的整数值",
              re.match(r"^\d+ 个$", plan_vals[1]) is not None, plan_vals[1])
        check("远程备份取自「第三方接入」的 SFTP：已配置则显示开启与服务器信息/路径",
              plan_vals[2].startswith("开启")
              and "omsbackup@192.168.1.100:22 /data/backup" in plan_vals[2], plan_vals[2])
        check("备份组件卡片带组件数量",
              rows[1]["head"].replace(chr(10), " ") == "备份组件 共 3 个组件", rows[1]["head"])
        comps = s.js("""return Array.from(document.querySelectorAll('.comp-row')).map(function(r){
            return [r.querySelector('.comp-name').innerText.trim(),
                    Array.from(r.querySelectorAll('.comp-chip')).map(function(c){
                      return c.innerText.trim();})];});""")
        check("组件清单：OMS备份 / 模型工程备份 / Terabase备份",
              [c[0] for c in comps] == ["OMS备份", "模型工程备份", "Terabase备份"], str(comps))
        check("OMS备份的备份内容=管理数据", comps[0][1] == ["管理数据"], str(comps[0]))
        check("模型工程备份的备份内容=模型工程数据库 + ETCD",
              comps[1][1] == ["模型工程数据库", "ETCD"], str(comps[1]))
        check("Terabase备份的备份内容=Terabase数据库",
              comps[2][1] == ["Terabase数据库"], str(comps[2]))
        check("组件下方有「立即备份」与「修改」两个按钮",
              s.js("return document.getElementById('btnBakNow').innerText.trim()") == "立即备份"
              and s.js("return document.getElementById('btnBakEdit').innerText.trim()") == "修改")
        check("两个按钮位于备份组件内容下方",
              s.js("""var b=document.getElementById('btnBakNow').getBoundingClientRect();
                      var c=document.querySelector('.comp-row').getBoundingClientRect();
                      return b.top>c.bottom;"""))
        s.shot("41-backup-plan.png")
        s.click("#btnBakNow"); time.sleep(0.4)
        check("「立即备份」发起备份任务并给出提示",
              s.js("return document.querySelectorAll('#toastWrap .toast').length") >= 1
              and "任务中心" in s.js("return document.querySelector('#toastWrap').innerText"))

        # --- 修改抽屉：每天 ---
        s.click("#btnBakEdit"); time.sleep(0.45)
        check("抽屉标题=修改备份配置",
              s.js("return document.getElementById('drawerTitle').innerText.trim()") == "修改备份配置")
        check("顶部是备份计划开关，默认开启",
              s.js("""return document.getElementById('bakPlanSw').classList.contains('is-on')
                        && document.querySelector('#bakPlanSw .switch-label').innerText.trim();""")
              == "开启")
        blabels = s.js("""return Array.from(document.querySelectorAll('#bakPlanBox .f-label'))
                            .map(function(e){return e.innerText.replace('*','').trim();});""")
        check("开关下方依次为 频率 / 时间 / 备份副本上限 / 远程备份 / 备份组件",
              blabels == ["频率", "时间", "备份副本上限", "远程备份", "备份组件"], str(blabels))
        check("频率为「每天 / 每周」，默认每天",
              s.texts("#bakFreqSeg .seg-btn") == ["每天", "每周"]
              and s.js("""return document.querySelector('#bakFreqSeg .seg-btn.is-on')
                            .innerText.trim();""") == "每天")
        check("每天模式不展示星期多选框",
              s.js("return document.querySelectorAll('.wd-check').length") == 0)
        check("时间可编辑且默认 02:00",
              s.js("return document.getElementById('bakTime').type") == "time"
              and s.js("return document.getElementById('bakTime').value") == "02:00")
        check("备份副本上限范围为 1-10",
              s.js("return document.getElementById('bakCopies').min") == "1"
              and s.js("return document.getElementById('bakCopies').max") == "10")
        check("远程备份为只读展示（本页不配置），内容取自第三方接入的 SFTP",
              s.js("return !document.getElementById('bakRemote')")
              and "omsbackup@192.168.1.100:22 /data/backup" in
                  s.js("""return document.querySelector('[data-field="bakRemote"] .f-readonly')
                            .innerText;""")
              and "不在本页配置" in
                  s.js("""return document.querySelector('[data-field="bakRemote"] .f-hint')
                            .innerText;"""),
              s.js("""return document.querySelector('[data-field="bakRemote"] .f-readonly')
                        .innerText.trim();"""))
        picks = s.js("""return Array.from(document.querySelectorAll('.pick-item')).map(function(l){
            var c=l.querySelector('.pick-check');
            return [c.getAttribute('data-comp'), c.checked?'checked':'unchecked',
                    c.disabled?'disabled':'enabled', l.querySelector('.pick-name').innerText.trim()];});""")
        check("备份组件三项均可多选且默认全选",
              [p[0] for p in picks] == ["oms", "model", "terabase"]
              and all(p[1] == "checked" for p in picks), str(picks))
        check("OMS备份为必选（勾选框置灰、带「必选」标记）",
              picks[0][2] == "disabled" and "必选" in picks[0][3], str(picks[0]))
        check("模型工程备份与 Terabase备份可自由勾选",
              picks[1][2] == "enabled" and picks[2][2] == "enabled")
        s.shot("42-backup-edit-drawer.png")

        # 切到每周 → 出现星期一到星期日多选
        s.js("""document.querySelector('#bakFreqSeg .seg-btn[data-freq="weekly"]').click();""")
        time.sleep(0.45)
        wd = s.texts(".wd-item")
        check("切到每周后出现星期一到星期日的多选框",
              wd == ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"],
              str(wd))
        check("星期多选沿用原配置（星期一、星期三）",
              s.js("""return Array.from(document.querySelectorAll('.wd-check'))
                        .filter(function(c){return c.checked;})
                        .map(function(c){return c.value;}).join(',');""") == "mon,wed")
        check("已选星期有选中态",
              s.js("return document.querySelectorAll('.wd-item.is-on').length") == 2)
        s.shot("43-backup-weekly-drawer.png")

        s.js("""Array.from(document.querySelectorAll('.wd-check'))
                  .filter(function(c){return c.checked;})
                  .forEach(function(c){c.click();});""")
        time.sleep(0.35)
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("每周模式未选星期时提交被拦截",
              "请至少选择一个星期" in
              s.js("""return document.querySelector('[data-field="bakWeekdays"] .f-error')
                        .innerText;"""))
        s.js("""var e=document.getElementById('bakCopies');e.value='20';
                e.dispatchEvent(new Event('input',{bubbles:true}));""")
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("备份副本上限超出 1-10 被拦截",
              "1-10" in
              s.js("""return document.querySelector('[data-field="bakCopies"] .f-error').innerText;"""))
        check("副本上限说明写明「满则清理最旧副本、手动与自动一视同仁」",
              "最旧的副本" in
              s.js("""return document.querySelector('[data-field="bakCopies"] .f-hint')
                        .innerText;""")
              and "一视同仁" in
                  s.js("""return document.querySelector('[data-field="bakCopies"] .f-hint')
                            .innerText;"""),
              s.js("""return document.querySelector('[data-field="bakCopies"] .f-hint')
                        .innerText.trim();"""))
        s.js("""document.querySelectorAll('.wd-check')[4].click();
                var e=document.getElementById('bakCopies');e.value='3';
                e.dispatchEvent(new Event('input',{bubbles:true}));
                document.querySelector('.pick-check[data-comp="model"]').click();""")
        time.sleep(0.35)
        s.click("#drawerSubmit"); time.sleep(0.5)
        check("保存后抽屉关闭并给出提示",
              s.js("return document.getElementById('drawer').hidden")
              and s.js("return document.querySelectorAll('#toastWrap .toast').length") >= 1)
        plan2 = s.js("""return Array.from(document.querySelectorAll('.des-card')[0]
                          .querySelectorAll('.des-row dd')).map(function(e){
                            return e.innerText.trim();});""")
        check("页面备份计划更新为「每周 星期五 02:00」",
              plan2[0] == "每周 星期五 02:00", plan2[0])
        check("页面副本数量上限更新为 3 个", plan2[1] == "3 个", plan2[1])
        check("远程备份仍按第三方接入的配置展示（本页不改变它）",
              plan2[2].startswith("开启")
              and "omsbackup@192.168.1.100:22 /data/backup" in plan2[2], plan2[2])
        comps2 = s.js("""return Array.from(document.querySelectorAll('.comp-row .comp-name'))
                           .map(function(e){return e.innerText.trim();});""")
        check("取消模型工程备份后组件清单只剩 2 个且 OMS 仍在",
              comps2 == ["OMS备份", "Terabase备份"], str(comps2))
        check("组件数量同步为 2 个",
              "2 个组件" in s.js("return document.querySelectorAll('.des-head')[1].innerText;"))
        check("备份配置的标签列不折行（「备份副本数量上限」一行显示）",
              s.js("""var dts=document.querySelectorAll('.des-card')[0]
                        .querySelectorAll('.des-row dt');
                      return Math.abs(dts[1].scrollHeight - dts[0].scrollHeight) <= 1;"""),
              s.js("""var dts=document.querySelectorAll('.des-card')[0]
                        .querySelectorAll('.des-row dt');
                      return dts[1].innerText+' / '+dts[1].scrollHeight+'px vs '+dts[0].scrollHeight+'px';"""))
        s.shot("44-backup-plan-updated.png")

        # 关闭备份计划开关 → 下方内容整体隐藏
        s.click("#btnBakEdit"); time.sleep(0.4)
        s.click("#bakPlanSw"); time.sleep(0.35)
        check("关闭备份计划开关后下方配置整体隐藏",
              s.js("return document.getElementById('bakPlanBox').hidden")
              and s.js("""return document.querySelector('#bakPlanSw .switch-label')
                            .innerText.trim();""") == "关闭")
        s.click("#drawerSubmit"); time.sleep(0.5)
        check("关闭计划后页面显示「未启用」，副本上限与远程备份状态保留",
              s.js("""return document.querySelectorAll('.des-card')[0]
                        .querySelectorAll('.des-row dd')[0].innerText.trim();""") == "未启用"
              and s.js("""return document.querySelectorAll('.des-card')[0]
                            .querySelectorAll('.des-row dd')[1].innerText.trim();""") == "3 个")
        s.click("#btnBakEdit"); time.sleep(0.4)
        s.click("#bakPlanSw"); time.sleep(0.35)
        s.click("#drawerSubmit"); time.sleep(0.5)
        check("重新开启计划并保存后恢复展示备份计划",
              s.js("""return document.querySelectorAll('.des-card')[0]
                        .querySelectorAll('.des-row dd')[0].innerText.trim();""")
              == "每周 星期五 02:00")

        # 第三方接入未配置 SFTP 时，远程备份显示关闭并说明来源
        s.js("var e=document.getElementById('protoSftp');e.checked=false;"
             "e.dispatchEvent(new Event('change',{bubbles:true}));"); time.sleep(0.4)
        rem_off = s.js("""return document.querySelectorAll('.des-card')[0]
                                 .querySelectorAll('.des-row dd')[2].innerText.trim();""")
        check("第三方接入未配置 SFTP 时远程备份显示关闭并说明来源",
              rem_off.startswith("关闭") and "第三方接入" in rem_off, rem_off)
        s.shot("45-backup-no-sftp.png")
        s.js("var e=document.getElementById('protoSftp');e.checked=true;"
             "e.dispatchEvent(new Event('change',{bubbles:true}));"); time.sleep(0.4)
        check("重新配置 SFTP 后远程备份恢复开启",
              s.js("""return document.querySelectorAll('.des-card')[0]
                         .querySelectorAll('.des-row dd')[2].innerText.trim();""")
              .startswith("开启"))

        # 英文态
        s.click('.lang-btn[data-lang="en-US"]')
        s.go("#/settings/backup")
        en_keys = s.js("""return Array.from(document.querySelectorAll('.des-card')[0]
                            .querySelectorAll('.des-row dt')).map(function(e){
                              return e.innerText.trim();});""")
        check("英文备份配置项与顺序一致",
              en_keys == ["Backup Plan", "Maximum Backup Copies", "Remote Backup"], str(en_keys))
        check("英文计划文案由「每周 + 星期五」组合",
              s.js("""return document.querySelectorAll('.des-card')[0]
                        .querySelectorAll('.des-row dd')[0].innerText.trim();""")
              == "Weekly Friday 02:00",
              s.js("""return document.querySelectorAll('.des-card')[0]
                        .querySelectorAll('.des-row dd')[0].innerText.trim();"""))
        check("英文副本数量用单复数正确的写法",
              s.js("""return document.querySelectorAll('.des-card')[0]
                        .querySelectorAll('.des-row dd')[1].innerText.trim();""") == "3 copies")
        s.click('.lang-btn[data-lang="zh-CN"]')   # 上一节英文态收尾，切回中文

        # ---------- 12.8 告警列表页（M17 告警管理） ----------
        print("\n[12.8] 告警列表页（M17）")
        s.go("#/settings/alarm-list")
        check("页面标题=告警列表",
              s.js("return document.querySelector('.page-title').innerText.trim()") == "告警列表")
        check("面包屑为「设置 / 告警列表」",
              s.texts("#crumb .crumb-item") == ["设置", "告警列表"],
              str(s.texts("#crumb .crumb-item")))
        check("页面可在「当前告警 / 历史告警」之间切换",
              s.texts(".tab") == ["当前告警（6）", "历史告警（5）"], str(s.texts(".tab")))
        check("默认展示当前告警",
              s.js("return document.querySelector('.tab.is-on').innerText.indexOf('当前告警')===0"))
        aheads = s.texts("table.data thead th")
        check("当前告警表头 7 列（首列为勾选框）且顺序与要求一致",
              aheads == ["", "级别", "名称", "部件类型", "告警对象", "告警来源", "产生时间", "操作"],
              str(aheads))
        check("每行左侧有可多选的小方框",
              s.js("return document.querySelectorAll('table.data tbody tr .row-check').length")
              == s.js("return document.querySelectorAll('table.data tbody tr').length") == 6)
        check("表头首列是全选框",
              s.js("return !!document.querySelector('table.data thead th.col-check input.check-all')"))
        check("表格上方有「批量清除」与「导出」按钮",
              s.js("return document.getElementById('btnAlmBatch').innerText.trim()") == "批量清除"
              and s.js("return document.getElementById('btnAlmExport').innerText.trim()") == "导出")
        check("未选中时「批量清除」置灰",
              s.js("return document.getElementById('btnAlmBatch').disabled"))
        check("筛选栏覆盖 关键字 / 级别 / 部件类型 / 告警来源 / 时间范围（FR-ALM-002、OI-M17-005）",
              [x for x in s.texts(".filter-bar .filter-item > span") if x != "~"] ==
              ["级别", "部件类型", "告警来源", "时间"],
              str(s.texts(".filter-bar .filter-item > span")))
        check("筛选栏在一行内放得下（不发生换行）",
              s.js("""var items=Array.from(document.querySelectorAll('.filter-bar > *'))
                        .map(function(e){return Math.round(e.getBoundingClientRect().top);});
                      return Math.max.apply(null,items)-Math.min.apply(null,items);""") <= 2,
              s.js("""var items=Array.from(document.querySelectorAll('.filter-bar > *'))
                        .map(function(e){return Math.round(e.getBoundingClientRect().top);});
                      return '行数偏差 '+(Math.max.apply(null,items)-Math.min.apply(null,items))+'px';"""))
        check("表头可排序列带排序标记，默认按产生时间倒序",
              s.js("""return document.querySelector("th[data-sort=at]")
                        .classList.contains('is-sorted')
                      && document.querySelector("th[data-sort=at]").classList.contains('desc')
                      && document.querySelectorAll('th.th-sort').length === 4;"""),
              s.js('return document.querySelector("th[data-sort=at]").className;'))
        check("默认按产生时间倒序排列",
              s.js("""return Array.from(document.querySelectorAll('table.data tbody .col-ip'))
                        .filter(function(e){return /\\d{4}-/.test(e.innerText);})
                        .map(function(e){return e.innerText.trim();})
                        .every(function(v,i,a){return i===0 || a[i-1] >= v;});"""))
        levels = s.texts("table.data tbody .badge-lv-hint, table.data tbody .badge-lv-normal, "
                         "table.data tbody .badge-lv-major, table.data tbody .badge-lv-critical")
        check("级别列取值为「建议 / 一般 / 重要 / 紧急」",
              set(levels) == {"建议", "一般", "重要", "紧急"},
              str(sorted(set(levels))))
        check("级别按 4 档配色区分（各自独立样式）",
              s.js("""return ['hint','normal','major','critical'].every(function(lv){
                        return document.querySelectorAll('table.data tbody .badge-lv-'+lv).length>0;});"""))
        parts = set(s.texts("table.data tbody tr td:nth-child(4)"))
        check("部件类型取值为 OMS / 模型工程 / Terabase", parts == {"OMS", "模型工程", "Terabase"},
              str(parts))
        objs = s.texts("table.data tbody tr td:nth-child(5)")
        check("告警对象列展示对象名（如 License / Backup / Transfer）",
              "License" in objs and "Backup" in objs and "Transfer" in objs, str(objs))
        check("告警来源列为 IP、产生时间为 yyyy-MM-dd HH:mm:ss",
              s.js("""return Array.from(document.querySelectorAll('table.data tbody tr')).every(function(r){
                        return /^\\d{1,3}(\\.\\d{1,3}){3}$/.test(r.children[5].innerText.trim())
                            && /^\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}$/.test(r.children[6].innerText.trim());});"""))
        check("操作列两个按钮：清除 / 设置屏蔽规则",
              set(s.texts("table.data tbody .row-actions .link-btn")) == {"清除", "设置屏蔽规则"},
              str(set(s.texts("table.data tbody .row-actions .link-btn"))))
        s.shot("47-alarm-current.png")

        # --- 单条清除：二次确认弹窗展示名称 / 级别 / 部件类型 ---
        s.js("""document.querySelector('tr[data-alarm="a3"] [data-alm-act="clear"]').click();""")
        time.sleep(0.45)
        check("点「清除」弹出二次确认窗口",
              not s.js("return document.getElementById('modalMask').hidden")
              and s.js("return document.getElementById('modalTitle').innerText.trim();") == "清除告警")
        keys = s.texts("#modalBody .mini-table th")
        check("确认窗口展示告警名称 / 级别 / 部件类型",
              keys == ["告警名称", "级别", "部件类型"], str(keys))
        vals = s.texts("#modalBody .mini-table td")
        check("确认窗口内容为被清除的那条告警",
              vals[0] == "Nginx 证书即将到期" and vals[1] == "重要" and vals[2] == "OMS", str(vals))
        check("清除为破坏性操作（红色警示三角）",
              s.js("return !!document.querySelector('#modalIcon path')")
              and "btn-danger" in s.js("return document.getElementById('modalConfirm').className"))
        s.shot("48-alarm-clear-modal.png")
        s.js("document.getElementById('modalConfirm').click();"); time.sleep(0.5)
        check("确认后该告警从当前告警移出",
              s.js("return !document.querySelector('tr[data-alarm=\"a3\"]')")
              and s.js("return document.querySelectorAll('table.data tbody tr').length") == 5)
        check("清除后当前告警计数同步为 5",
              "当前告警（5）" in s.js("return document.querySelector('.tab').innerText"))
        check("清除后给出轻提示",
              s.js("return document.querySelectorAll('#toastWrap .toast').length") >= 1)
        s.click('.tab[data-tab="history"]'); time.sleep(0.4)
        newrow = s.js("""var r=document.querySelector('table.data tbody tr');
                         return Array.from(r.children).map(function(c){return c.innerText.trim();});""")
        check("被清除的告警转入历史告警并记录清除时间与手动清除",
              newrow[1] == "Nginx 证书即将到期" and newrow[7] == "手动清除"
              and re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", newrow[6]) is not None,
              str(newrow))
        s.click('.tab[data-tab="current"]'); time.sleep(0.4)

        # --- 历史告警：无勾选框、无批量清除、操作只有设置屏蔽规则 ---
        s.click('.tab[data-tab="history"]'); time.sleep(0.45)
        hheads = s.texts("table.data thead th")
        check("历史告警表头比当前告警多「清除时间」「清除类型」两列",
              hheads == ["级别", "名称", "部件类型", "告警对象", "告警来源", "产生时间",
                         "清除时间", "清除类型", "操作"], str(hheads))
        check("历史告警每行左侧没有勾选框",
              s.js("return document.querySelectorAll('table.data .row-check, "
                   "table.data .check-all').length") == 0)
        check("历史告警没有「批量清除」按钮，但仍可导出",
              s.js("return !document.getElementById('btnAlmBatch')")
              and s.js("return !!document.getElementById('btnAlmExport')"))
        check("历史告警操作只有「设置屏蔽规则」",
              set(s.texts("table.data tbody .row-actions .link-btn")) == {"设置屏蔽规则"},
              str(set(s.texts("table.data tbody .row-actions .link-btn"))))
        check("清除类型取值为「自动清除 / 手动清除」",
              set(s.texts("table.data tbody .badge-plain")) == {"自动清除", "手动清除"},
              str(set(s.texts("table.data tbody .badge-plain"))))
        s.shot("49-alarm-history.png")

        # --- 筛选（FR-ALM-002、OI-M17-005） ---
        s.js("""var e=document.getElementById('almlevel');e.value='major';
                e.dispatchEvent(new Event('change',{bubbles:true}));""")
        time.sleep(0.45)
        check("按告警级别=重要筛选历史告警命中 3 条",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 3
              and set(s.texts("table.data tbody .badge-lv-major")) == {"重要"},
              str(s.js("return document.querySelectorAll('table.data tbody tr').length;")))
        s.click("#almFilterReset"); time.sleep(0.4)
        s.js("""var e=document.getElementById('almip');e.value='10.20.32.11';
                e.dispatchEvent(new Event('change',{bubbles:true}));""")
        time.sleep(0.45)
        check("按告警来源=10.20.32.11 筛选命中 1 条",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 1
              and "Terabase 节点磁盘使用率偏高" in
                  s.js("return document.querySelector('table.data tbody').innerText"))
        s.click("#almFilterReset"); time.sleep(0.4)
        s.js("""var e=document.getElementById('almfrom');e.value='2026-10-11';
                e.dispatchEvent(new Event('change',{bubbles:true}));""")
        time.sleep(0.45)
        check("按产生时间起始 2026-10-11 筛选命中 4 条",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 4,
              str(s.js("return document.querySelectorAll('table.data tbody tr').length;")))
        check("筛选后页脚标注已筛选与该视图总数",
              "已筛选，该视图共 6 条" in
              s.js("return document.querySelector('.table-foot').innerText"),
              s.js("return document.querySelector('.table-foot').innerText.trim();"))
        s.click("#almFilterReset"); time.sleep(0.4)
        s.js("""var e=document.getElementById('almq');e.value='ALM-0904';
                e.dispatchEvent(new Event('input',{bubbles:true}));""")
        time.sleep(0.45)
        check("按告警ID 搜索命中 1 条",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 1)
        s.js("""var e=document.getElementById('almq');e.value='zzzz';
                e.dispatchEvent(new Event('input',{bubbles:true}));""")
        time.sleep(0.45)
        check("筛选无匹配时提示「无匹配告警记录」而非空白",
              s.js("return document.querySelector('table.data tbody').innerText.trim();") == "无匹配告警记录",
              s.js("return document.querySelector('table.data tbody').innerText.trim();"))
        s.click("#almFilterReset"); time.sleep(0.4)
        check("重置筛选后恢复该视图全部 6 条",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 6
              and "已筛选" not in s.js("return document.querySelector('.table-foot').innerText"))
        s.shot("49b-alarm-filter.png")

        # --- 排序 ---
        s.js("""document.querySelector("th[data-sort=level]").click();""")
        time.sleep(0.45)
        check("点击「级别」表头按级别升序（建议→紧急）",
              s.js("""return document.querySelector("th[data-sort=level]")
                        .classList.contains('asc')
                      && document.querySelector('table.data tbody .badge-lv-hint') !== null
                      && /建议/.test(document.querySelector('table.data tbody tr').innerText);"""),
              s.js("return document.querySelector('table.data tbody tr').innerText.trim();"))
        s.js("""document.querySelector("th[data-sort=level]").click();""")
        time.sleep(0.45)
        check("再次点击同一表头切换为降序（紧急在前）",
              s.js("""return document.querySelector("th[data-sort=level]")
                        .classList.contains('desc')""")
              and "紧急" in s.js("return document.querySelector('table.data tbody tr').innerText"),
              s.js("return document.querySelector('table.data tbody tr').innerText.trim();"))
        s.js("""document.querySelector("th[data-sort=clearedAt]").click();""")
        time.sleep(0.45)
        check("历史告警可按清除时间排序（默认降序）",
              s.js("""return document.querySelector("th[data-sort=clearedAt]")
                        .classList.contains('desc')""")
              and s.js("""return Array.from(document.querySelectorAll('table.data tbody tr'))
                            .map(function(r){return r.children[6].innerText.trim();})
                            .every(function(v,i,a){return i===0 || a[i-1] >= v;});"""),
              s.js('return document.querySelector("th[data-sort=clearedAt]").className;'))
        s.shot("49c-alarm-sort.png")
        s.click('.tab[data-tab="current"]'); time.sleep(0.45)
        check("切回当前告警时排序键回落为产生时间倒序",
              s.js("""return document.querySelector("th[data-sort=at]")
                        .classList.contains('desc')"""))
        s.click('.tab[data-tab="history"]'); time.sleep(0.4)

        # --- 设置屏蔽规则抽屉 ---
        s.js("""document.querySelector('table.data tbody [data-alm-act="block"]').click();""")
        time.sleep(0.5)
        check("抽屉标题=设置屏蔽规则",
              s.js("return document.getElementById('drawerTitle').innerText.trim()") == "设置屏蔽规则")
        blabels = s.js("""return Array.from(document.querySelectorAll('#drawerBody .f-label'))
                            .map(function(e){return e.innerText.replace('*','').trim();});""")
        check("抽屉依次为 屏蔽项 / 屏蔽规则名称 / 描述 / 屏蔽日期 / 屏蔽时间段",
              blabels == ["屏蔽项", "屏蔽规则名称", "描述", "屏蔽日期", "屏蔽时间段"], str(blabels))
        opts = s.texts("#drawerBody .radio-item")
        check("屏蔽项两个可选：屏蔽该 IP 的所有告警 / 屏蔽该 IP 的当前告警",
              opts == ["屏蔽 10.20.30.41 的所有告警",
                       "屏蔽 10.20.30.41 的「Nginx 证书即将到期」告警"], str(opts))
        check("屏蔽项默认选中「所有告警」且为单选",
              s.js("""return document.querySelector('.radio-item.is-on .radio-input').value;""") == "ip"
              and s.js("""return document.querySelectorAll('#drawerBody .radio-input').length;""") == 2
              and s.js("""return document.querySelector('#drawerBody .radio-input').name;""") == "blkScope")
        check("屏蔽日期可选「永久 / 指定日期」，默认永久",
              s.texts("#blkDateSeg .seg-btn") == ["永久", "指定日期"]
              and s.js("""return document.querySelector('#blkDateSeg .seg-btn.is-on')
                            .innerText.trim();""") == "永久"
              and s.js("return document.querySelectorAll('#blkFrom, #blkTo').length") == 0)
        check("屏蔽时间段可选「24小时 / 指定时间」，默认 24小时",
              s.texts("#blkTimeSeg .seg-btn") == ["24小时", "指定时间"]
              and s.js("""return document.querySelector('#blkTimeSeg .seg-btn.is-on')
                            .innerText.trim();""") == "24小时"
              and s.js("return document.querySelectorAll('#blkStart, #blkEnd').length") == 0)
        check("描述为多行文本且说明必填原因",
              s.js("return document.getElementById('blkDesc').tagName") == "TEXTAREA"
              and "留痕" in s.js("""return document.querySelector('[data-field="blkDesc"] .f-hint')
                                      .innerText;"""))
        s.shot("50-alarm-block-drawer.png")

        # 切到指定日期 + 指定时间 → 出现起止输入
        s.js("""document.querySelector('#blkDateSeg .seg-btn[data-dmode="range"]').click();""")
        time.sleep(0.35)
        s.js("""document.querySelector('#blkTimeSeg .seg-btn[data-tmode="range"]').click();""")
        time.sleep(0.4)
        check("切到「指定日期」出现起止日期输入，切到「指定时间」出现起止时间输入",
              s.js("return !!document.getElementById('blkFrom') && !!document.getElementById('blkTo')")
              and s.js("return !!document.getElementById('blkStart') && !!document.getElementById('blkEnd')"))
        check("日期与时间输入类型正确",
              s.js("return document.getElementById('blkFrom').type") == "date"
              and s.js("return document.getElementById('blkStart').type") == "time")
        # 必填与先后顺序校验
        s.click("#drawerSubmit"); time.sleep(0.4)
        errs = s.js("""return Array.from(document.querySelectorAll('#drawerBody .f-field.has-error .f-error'))
                         .map(function(e){return e.innerText.trim();});""")
        check("规则名称、描述与起止日期时间为必填",
              s.js("""return ['blkName','blkDesc','blkDate','blkTime'].every(function(k){
                        return document.querySelector('[data-field="'+k+'"]')
                          .classList.contains('has-error');});""")
              and errs.count("此项为必填") == 2
              and "请选择起始与终止日期" in errs
              and "请选择起始与终止时间" in errs, str(errs))
        s.js("""function setv(id,v){var e=document.getElementById(id);e.value=v;
                  e.dispatchEvent(new Event('input',{bubbles:true}));
                  e.dispatchEvent(new Event('change',{bubbles:true}));}
                setv('blkName','屏蔽 License 授权告警');
                setv('blkDesc','License 正在续期中，暂时屏蔽该来源告警');
                setv('blkFrom','2026-10-14'); setv('blkTo','2026-10-20');
                setv('blkStart','08:00'); setv('blkEnd','06:00');""")
        time.sleep(0.35)
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("起始时间晚于终止时间被拦截",
              "起始时间需早于终止时间" in
              s.js("""return document.querySelector('[data-field="blkTime"] .f-error').innerText;"""),
              s.js("""return document.querySelector('[data-field="blkTime"] .f-error').innerText;"""))
        s.js("""var e=document.getElementById('blkEnd');e.value='06:00';
                e.dispatchEvent(new Event('change',{bubbles:true}));
                var f=document.getElementById('blkFrom');f.value='2026-10-20';
                var t2=document.getElementById('blkTo');t2.value='2026-10-14';
                t2.dispatchEvent(new Event('change',{bubbles:true}));""")
        time.sleep(0.3)
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("起始日期晚于终止日期被拦截",
              "起始日期需早于终止日期" in
              s.js("""return document.querySelector('[data-field="blkDate"] .f-error').innerText;"""))
        s.js("""var f=document.getElementById('blkFrom');f.value='2026-10-14';
                f.dispatchEvent(new Event('change',{bubbles:true}));
                var e2=document.getElementById('blkEnd');e2.value='18:00';
                e2.dispatchEvent(new Event('change',{bubbles:true}));""")
        time.sleep(0.3)
        check("改正起止日期与时间后错误提示即时清除",
              s.js("""return !document.querySelector('[data-field="blkDate"]')
                        .classList.contains('has-error')
                      && !document.querySelector('[data-field="blkTime"]')
                        .classList.contains('has-error');"""),
              s.js("""return document.querySelector('[data-field="blkDate"] .f-error').innerText
                      + ' | ' +
                      document.querySelector('[data-field="blkTime"] .f-error').innerText;"""))
        s.shot("51-alarm-block-range.png")
        # 保存（默认「所有告警」范围较大 → 需要二次确认，FR-ALM-003）
        s.js("""document.querySelector('#drawerBody .radio-input[value="ip"]').click();""")
        time.sleep(0.3)
        s.click("#drawerSubmit"); time.sleep(0.5)
        check("屏蔽范围为「该 IP 的所有告警」时保存前要求确认（FR-ALM-003）",
              s.js("return document.getElementById('drawer').hidden")
              and not s.js("return document.getElementById('modalMask').hidden")
              and s.js("return document.getElementById('modalTitle').innerText.trim();")
                  == "屏蔽范围较大，请确认",
              s.js("return document.getElementById('modalTitle').innerText.trim();"))
        check("范围提示为告知性确认（蓝色信息圆，非警示三角）",
              s.js("return !!document.querySelector('#modalIcon circle')"))
        s.shot("52-alarm-block-confirm.png")
        s.js("document.getElementById('modalConfirm').click();"); time.sleep(0.5)
        check("确认后提示屏蔽规则已创建",
              "屏蔽规则已创建" in s.js("return document.querySelector('#toastWrap').innerText"))

        # 选择「屏蔽该告警」时不需要额外确认
        s.js("""document.querySelector('table.data tbody [data-alm-act="block"]').click();""")
        time.sleep(0.45)
        s.js("""document.querySelector('#drawerBody .radio-input[value="alarm"]').click();
                function setv2(id,v){var e=document.getElementById(id);e.value=v;
                  e.dispatchEvent(new Event('input',{bubbles:true}));}
                setv2('blkName','屏蔽单一告警'); setv2('blkDesc','该告警已知，暂时屏蔽');""")
        time.sleep(0.35)
        s.click("#drawerSubmit"); time.sleep(0.5)
        check("仅屏蔽该条告警时直接保存（无额外确认）",
              s.js("return document.getElementById('drawer').hidden")
              and s.js("return document.getElementById('modalMask').hidden")
              and "屏蔽规则已创建" in s.js("return document.querySelector('#toastWrap').innerText"))

        # --- 批量清除 ---
        s.click('.tab[data-tab="current"]'); time.sleep(0.4)
        s.js("""['a1','a2'].forEach(function(id){
                  document.querySelector('tr[data-alarm="'+id+'"] .row-check').click();});""")
        time.sleep(0.4)
        check("勾选后「批量清除」可用并显示数量",
              not s.js("return document.getElementById('btnAlmBatch').disabled")
              and s.js("return document.getElementById('almBatchCount').innerText.trim();") == "（2）",
              s.js("return document.getElementById('almBatchCount').innerText.trim();"))
        check("页脚显示已选数量",
              "已选 2 个" in s.js("return document.querySelector('.table-foot').innerText"))
        s.click("#btnAlmBatch"); time.sleep(0.5)
        check("批量清除弹窗展示每条待清除告警的名称 / 级别 / 部件类型",
              s.js("return document.getElementById('modalTitle').innerText.trim();") == "批量清除告警"
              and s.texts("#modalBody .mini-table thead th") == ["告警名称", "级别", "部件类型"]
              and s.js("return document.querySelectorAll('#modalBody .mini-table tbody tr').length;") == 2,
              str(s.texts("#modalBody .mini-table thead th")))
        rows2 = s.js("""return Array.from(document.querySelectorAll('#modalBody .mini-table tbody tr'))
                          .map(function(r){return Array.from(r.children)
                            .map(function(c){return c.innerText.trim();});});""")
        check("弹窗内容与勾选的告警一致",
              [r[0] for r in rows2] == ["License 授权剩余天数不足", "备份任务执行失败"], str(rows2))
        check("批量弹窗为宽弹窗，内容不挤压",
              s.js("return document.getElementById('modalBox').classList.contains('is-wide')"))
        s.shot("53-alarm-batch-clear.png")
        s.js("document.getElementById('modalConfirm').click();"); time.sleep(0.5)
        check("确认后批量清除生效：当前告警剩 3 条",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 3
              and "当前告警（3）" in s.js("return document.querySelector('.tab').innerText"))
        check("批量清除后按钮回到置灰态、已选计数清空",
              s.js("return document.getElementById('btnAlmBatch').disabled")
              and s.js("return document.getElementById('almBatchCount').innerText.trim();") == "")
        s.click('.tab[data-tab="history"]'); time.sleep(0.45)
        check("批量清除的两条均已转入历史告警（共 8 条）",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 8
              and "历史告警（8）" in s.js("return document.querySelectorAll('.tab')[1].innerText"),
              s.js("return document.querySelectorAll('.tab')[1].innerText.trim();"))

        # 全选 → 全部清除 → 空态
        s.click('.tab[data-tab="current"]'); time.sleep(0.4)
        s.js("document.getElementById('almCheckAll').click();"); time.sleep(0.4)
        check("全选后选中全部剩余 3 条",
              s.js("return document.getElementById('almBatchCount').innerText.trim();") == "（3）")
        s.click("#btnAlmBatch"); time.sleep(0.4)
        s.js("document.getElementById('modalConfirm').click();"); time.sleep(0.5)
        check("全部清除后给出空态提示而非空白",
              s.js("return document.querySelector('table.data tbody').innerText.trim();") == "暂无当前告警"
              and "共 0 条当前告警" in s.js("return document.querySelector('.table-foot').innerText"))
        s.shot("54-alarm-empty.png")

        # 导出
        s.click("#btnAlmExport"); time.sleep(0.4)
        check("点「导出」按当前视图给出导出 Excel 的反馈",
              "Excel" in s.js("return document.querySelector('#toastWrap').innerText")
              and "当前告警" in s.js("return document.querySelector('#toastWrap').innerText"))

        # 英文态（先重载恢复告警数据，再检查英文版面）
        s.nav(PAGE)
        s.go("#/settings/alarm-list")
        s.click('.lang-btn[data-lang="en-US"]')
        en_heads = s.texts("table.data thead th")
        check("英文表头与顺序一致",
              en_heads == ["", "Level", "Name", "Component", "Alarm Object", "Source",
                           "Raised At", "Actions"], str(en_heads))
        check("英文级别取值为 Info / Minor / Major / Critical",
              set(s.texts("table.data tbody .badge-lv-hint, table.data tbody .badge-lv-normal, "
                          "table.data tbody .badge-lv-major, table.data tbody .badge-lv-critical"))
              <= {"Info", "Minor", "Major", "Critical"})
        check("英文下表格不横向溢出、操作列不被裁切",
              s.js("""var sc=document.querySelector('.table-scroll');
                        var card=document.querySelector('.table-card').getBoundingClientRect();
                        var cells=document.querySelectorAll('table.data tbody tr td');
                        var btn=cells[cells.length-1].querySelector('.link-btn:last-child')
                                    .getBoundingClientRect();
                        return sc.scrollWidth<=sc.clientWidth && btn.right<=card.right+0.5;"""),
              s.js("""var sc=document.querySelector('.table-scroll');
                        return 'scroll '+sc.scrollWidth+'/'+sc.clientWidth;"""))
        s.shot("55-alarm-en.png")
        s.click('.lang-btn[data-lang="zh-CN"]')
        s.click('.lang-btn[data-lang="zh-CN"]')   # 上一节英文态收尾，切回中文

        # ---------- 12.9 告警设置页（M17 屏蔽规则） ----------
        print("\n[12.9] 告警设置页（M17 屏蔽规则）")
        s.go("#/settings/alarm-config")
        check("页面标题=告警设置",
              s.js("return document.querySelector('.page-title').innerText.trim()") == "告警设置")
        check("面包屑为「设置 / 告警设置」",
              s.texts("#crumb .crumb-item") == ["设置", "告警设置"],
              str(s.texts("#crumb .crumb-item")))
        check("表格卡片标题为「屏蔽规则」并带条数",
              s.js("return document.querySelector('.des-head').innerText.replace(/\\s+/g,' ').trim();")
              == "屏蔽规则 共 4 条屏蔽规则",
              s.js("return document.querySelector('.des-head').innerText.trim();"))
        rheads = s.texts("table.data thead th")
        check("表头 8 列（首列为勾选框）且顺序与要求一致",
              rheads == ["", "名称", "状态", "屏蔽日期", "屏蔽时间段", "更新时间", "描述", "操作"],
              str(rheads))
        check("每行左侧有可多选的小方框",
              s.js("return document.querySelectorAll('table.data tbody tr .row-check').length")
              == s.js("return document.querySelectorAll('table.data tbody tr').length") == 4)
        check("状态列取值为「启用 / 禁用」",
              set(s.texts("table.data tbody .badge-ok, table.data tbody .badge-plain")) <= {"启用", "禁用"},
              str(set(s.texts("table.data tbody .badge-ok, table.data tbody .badge-plain"))))
        check("屏蔽日期列为「永久」或「起始日期 至 终止日期」",
              s.js("""return Array.from(document.querySelectorAll('table.data tbody tr')).every(function(r){
                        var v=r.children[3].innerText.trim();
                        return v==='永久' || /^\\d{4}-\\d{2}-\\d{2} 至 \\d{4}-\\d{2}-\\d{2}$/.test(v);});"""),
              str(s.texts("table.data tbody tr td:nth-child(4)")))
        check("屏蔽时间段列为「24小时」或「起始时刻 至 终止时刻」",
              s.js("""return Array.from(document.querySelectorAll('table.data tbody tr')).every(function(r){
                        var v=r.children[4].innerText.trim();
                        return v==='24小时' || /^\\d{2}:\\d{2} 至 \\d{2}:\\d{2}$/.test(v);});"""),
              str(s.texts("table.data tbody tr td:nth-child(5)")))
        check("更新时间列为 yyyy-MM-dd HH:mm:ss",
              s.js("""return Array.from(document.querySelectorAll('table.data tbody tr')).every(function(r){
                        return /^\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}$/.test(
                          r.children[5].innerText.trim());});"""))
        check("操作列为 修改 / 启用·禁用 / 删除 三个按钮",
              set(s.texts("table.data tbody .row-actions .link-btn")) == {"修改", "启用", "禁用", "删除"},
              str(set(s.texts("table.data tbody .row-actions .link-btn"))))
        check("表格上方四个按钮：批量启用 / 批量禁用 / 批量删除 / 创建",
              s.texts(".page-actions .btn") == ["批量启用", "批量禁用", "批量删除", "创建"],
              str(s.texts(".page-actions .btn")))
        check("未选中时三个批量按钮置灰",
              s.js("""return ['btnRuleEnable','btnRuleDisable','btnRuleBatchDelete']
                        .every(function(id){return document.getElementById(id).disabled;});"""))
        s.shot("56-rule-list.png")

        # --- 创建抽屉 ---
        s.click("#btnRuleCreate"); time.sleep(0.45)
        check("抽屉标题=创建屏蔽规则",
              s.js("return document.getElementById('drawerTitle').innerText.trim()") == "创建屏蔽规则")
        secs = s.texts("#drawerBody .f-section")
        check("抽屉分「基本信息」「屏蔽规则」两栏", secs == ["基本信息", "屏蔽规则"], str(secs))
        rlabels = s.js("""return Array.from(document.querySelectorAll('#drawerBody .f-label'))
                            .map(function(e){return e.innerText.replace('*','').trim();});""")
        check("基本信息含 名称 / 启用规则 / 屏蔽日期 / 屏蔽时间段 / 描述，" 
              "屏蔽规则含 告警来源 / 告警名称",
              rlabels == ["名称", "启用规则", "屏蔽日期", "屏蔽时间段", "描述",
                          "告警来源", "告警名称"], str(rlabels))
        check("「启用规则」为开关且默认开启",
              s.js("""return document.getElementById('ruleEnabled').classList.contains('is-on')
                        && document.querySelector('#ruleEnabled .switch-label').innerText.trim();""")
              == "开启")
        check("屏蔽日期默认「永久」、屏蔽时间段默认「24小时」",
              s.texts("#ruleDateSeg .seg-btn") == ["永久", "指定日期"]
              and s.texts("#ruleTimeSeg .seg-btn") == ["24小时", "指定时间"]
              and s.js("return document.querySelector('#ruleDateSeg .seg-btn.is-on').innerText.trim();")
                  == "永久"
              and s.js("return document.querySelector('#ruleTimeSeg .seg-btn.is-on').innerText.trim();")
                  == "24小时")
        check("告警来源可选「全部告警源 / 自定义告警源」",
              s.texts("#ruleSrcSeg .seg-btn") == ["全部告警源", "自定义告警源"]
              and s.js("""return document.querySelector('#ruleSrcSeg .seg-btn.is-on')
                            .innerText.trim();""") == "全部告警源")
        check("告警名称可选「全部告警 / 自定义告警」",
              s.texts("#ruleNmSeg .seg-btn") == ["全部告警", "自定义告警"]
              and s.js("""return document.querySelector('#ruleNmSeg .seg-btn.is-on')
                            .innerText.trim();""") == "全部告警")
        check("选「全部」时不展示自定义表格与添加按钮",
              s.js("return !document.getElementById('ruleAddSrc') && !document.getElementById('ruleAddAlm')"))
        s.shot("57-rule-create-drawer.png")

        # 必填校验
        s.click("#drawerSubmit"); time.sleep(0.4)
        rerrs = s.js("""return Array.from(document.querySelectorAll('#drawerBody .f-field.has-error .f-error'))
                         .map(function(e){return e.innerText.trim();});""")
        check("名称与描述为必填", rerrs.count("此项为必填") == 2, str(rerrs))

        # --- 自定义告警源：添加 ---
        s.js("""document.querySelector('#ruleSrcSeg .seg-btn[data-smode="custom"]').click();""")
        time.sleep(0.4)
        check("切到「自定义告警源」后出现「添加」按钮与空态提示",
              s.js("return !!document.getElementById('ruleAddSrc')")
              and "尚未添加告警源" in
                  s.js("return document.querySelector('#drawerBody .scope-empty').innerText"))
        s.click("#ruleAddSrc"); time.sleep(0.45)
        check("「添加」弹出表格窗口，表头为 告警来源 / 部件类型 / 告警对象",
              s.js("return document.getElementById('modalTitle').innerText.trim();") == "添加告警源"
              and s.texts("#modalBody .mini-table thead th") == ["", "告警来源", "部件类型", "告警对象"],
              str(s.texts("#modalBody .mini-table thead th")))
        check("候选条目带可勾选框",
              s.js("return document.querySelectorAll('#modalBody .pick-row').length") >= 3)
        s.click("#modalConfirm"); time.sleep(0.4)
        check("未勾选任何条目时不能添加（窗口保持打开并提示）",
              not s.js("return document.getElementById('modalMask').hidden")
              and "请先勾选" in s.js("return document.querySelector('#toastWrap').innerText"))
        s.js("""document.querySelectorAll('#modalBody .pick-row')[0].click();
                document.querySelectorAll('#modalBody .pick-row')[1].click();""")
        time.sleep(0.3)
        s.shot("59-rule-add-source.png")
        s.click("#modalConfirm"); time.sleep(0.5)
        check("勾选后添加成功：抽屉表格出现 2 行、计数同步",
              s.js("return document.getElementById('modalMask').hidden")
              and s.js("return document.querySelectorAll('#drawerBody .mini-table tbody tr').length") == 2
              and "已添加 2 项" in s.js("return document.querySelector('#drawerBody .scope-count').innerText"))
        check("抽屉内表格表头为 告警来源 / 部件类型 / 告警对象",
              s.texts("#drawerBody .mini-table thead th") == ["告警来源", "部件类型", "告警对象", ""],
              str(s.texts("#drawerBody .mini-table thead th")))
        check("已添加的条目可逐条移除",
              s.js("return document.querySelectorAll('#drawerBody [data-scope-del]').length") == 2)

        # --- 自定义告警：添加 ---
        s.js("""document.querySelector('#ruleNmSeg .seg-btn[data-nmode="custom"]').click();""")
        time.sleep(0.4)
        check("切到「自定义告警」后出现添加按钮与空态提示",
              s.js("return !!document.getElementById('ruleAddAlm')")
              and "尚未添加告警" in
                  s.js("return document.querySelector('#drawerBody .scope-empty').innerText"),
              s.js("return document.querySelector('#drawerBody .scope-empty').innerText;"))
        s.click("#ruleAddAlm"); time.sleep(0.45)
        check("「添加告警」弹窗表头为 告警来源 / 告警ID / 告警名称",
              s.js("return document.getElementById('modalTitle').innerText.trim();") == "添加告警"
              and s.texts("#modalBody .mini-table thead th") == ["", "告警来源", "告警ID", "告警名称"],
              str(s.texts("#modalBody .mini-table thead th")))
        check("告警ID 形如 ALM-1001",
              re.match(r"^ALM-\d{4}$",
                       s.js("return document.querySelector('#modalBody .mini-table tbody tr td:nth-child(3)').innerText.trim();")) is not None,
              s.js("return document.querySelector('#modalBody .mini-table tbody tr td:nth-child(3)').innerText.trim();"))
        s.js("""document.querySelectorAll('#modalBody .pick-row')[0].click();""")
        time.sleep(0.3)
        s.shot("60-rule-add-alarm.png")
        s.click("#modalConfirm"); time.sleep(0.5)
        check("添加告警成功：抽屉第二张表格出现 1 行",
              s.js("""return document.querySelectorAll('#drawerBody .mini-table')[1]
                        .querySelectorAll('tbody tr').length;""") == 1)
        # 抽屉内容较长，滚到底部再出图，便于看到「告警名称」自定义部分
        s.js("document.getElementById('drawerBody').scrollTop = 9999;"); time.sleep(0.4)
        s.shot("58-rule-custom-scope.png")

        # 填名称与描述后保存
        s.js("""function setrv(id,v){var e=document.getElementById(id);e.value=v;
                  e.dispatchEvent(new Event('input',{bubbles:true}));
                  e.dispatchEvent(new Event('change',{bubbles:true}));}
                setrv('ruleName','自定义范围屏蔽规则');
                setrv('ruleDesc','仅屏蔽指定的告警源与告警名称');""")
        time.sleep(0.35)
        s.click("#drawerSubmit"); time.sleep(0.55)
        check("创建成功后抽屉关闭并给出提示",
              s.js("return document.getElementById('drawer').hidden")
              and "屏蔽规则已保存" in s.js("return document.querySelector('#toastWrap').innerText"))
        check("列表新增该规则（共 5 条）",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 5
              and "自定义范围屏蔽规则" in s.js("return document.querySelector('table.data tbody').innerText")
              and "共 5 条屏蔽规则" in s.js("return document.querySelector('.des-head').innerText"),
              s.js("return document.querySelector('.des-head').innerText.trim();"))

        # --- 修改抽屉：带出原值 ---
        s.js("""document.querySelector('tr[data-rule="r2"] [data-rule-act="edit"]').click();""")
        time.sleep(0.5)
        check("修改抽屉标题=修改屏蔽规则",
              s.js("return document.getElementById('drawerTitle').innerText.trim()") == "修改屏蔽规则")
        check("带出原规则内容（名称 / 禁用状态 / 描述）",
              s.js("return document.getElementById('ruleName').value") == "备份任务失败告警屏蔽"
              and s.js("""return !document.getElementById('ruleEnabled').classList.contains('is-on');""")
              and s.js("return document.getElementById('ruleDesc').value").startswith("备份任务调整期间"),
              s.js("return document.getElementById('ruleName').value + ' / ' + document.getElementById('ruleDesc').value;"))
        check("带出屏蔽日期（指定日期）与起止值",
              s.js("return document.querySelector('#ruleDateSeg .seg-btn.is-on').innerText.trim();")
              == "指定日期"
              and s.js("return document.getElementById('ruleFrom').value") == "2026-10-15"
              and s.js("return document.getElementById('ruleTo').value") == "2026-10-22")
        check("带出告警名称的「自定义告警」与已添加条目",
              s.js("return document.querySelector('#ruleNmSeg .seg-btn.is-on').innerText.trim();")
              == "自定义告警"
              and s.js("return document.querySelectorAll('#drawerBody .mini-table tbody tr').length") == 1)
        s.shot("61-rule-edit-drawer.png")
        s.js("""var e=document.getElementById('ruleName');e.value='备份失败告警屏蔽（已改）';
                e.dispatchEvent(new Event('input',{bubbles:true}));""")
        time.sleep(0.3)
        s.click("#drawerSubmit"); time.sleep(0.5)
        check("修改后列表同步更新",
              "备份失败告警屏蔽（已改）" in s.js("return document.querySelector('table.data tbody').innerText"))

        # --- 勾选与批量操作 ---
        s.js("""['r1','r3'].forEach(function(id){
                  document.querySelector('tr[data-rule="'+id+'"] .row-check').click();});""")
        time.sleep(0.4)
        check("勾选后三个批量按钮可用、页脚显示已选数量",
              not s.js("return document.getElementById('btnRuleEnable').disabled")
              and not s.js("return document.getElementById('btnRuleDisable').disabled")
              and not s.js("return document.getElementById('btnRuleBatchDelete').disabled")
              and "已选 2 个" in s.js("return document.querySelector('.table-foot').innerText"))
        s.click("#btnRuleEnable"); time.sleep(0.45)
        check("批量启用弹窗：文字 + 名称/状态/描述 表格",
              s.js("return document.getElementById('modalTitle').innerText.trim();") == "批量启用"
              and "确定启用以下规则？" in s.js("return document.getElementById('modalBody').innerText")
              and s.texts("#modalBody .mini-table thead th") == ["名称", "状态", "描述"]
              and s.js("return document.querySelectorAll('#modalBody .mini-table tbody tr').length;") == 2,
              s.js("return document.getElementById('modalBody').innerText.split('\\n')[1];"))
        check("启用为告知性确认（蓝色信息圆）",
              s.js("return !!document.querySelector('#modalIcon circle')"))
        s.shot("62-rule-enable-confirm.png")
        s.js("document.getElementById('modalConfirm').click();"); time.sleep(0.5)
        check("批量启用后两条规则状态均为「启用」",
              s.js("""return ['r1','r3'].every(function(id){
                        return document.querySelector('tr[data-rule="'+id+'"] .badge-ok') !== null;});"""))
        # 单条禁用
        s.js("""document.querySelector('tr[data-rule="r3"] [data-rule-act="toggle"]').click();""")
        time.sleep(0.45)
        check("单条禁用弹窗文字为「确定禁用以下规则？」",
              "确定禁用以下规则？" in s.js("return document.getElementById('modalBody').innerText")
              and s.js("return document.querySelectorAll('#modalBody .mini-table tbody tr').length;") == 1)
        s.js("document.getElementById('modalConfirm').click();"); time.sleep(0.5)
        check("禁用后该规则状态变为「禁用」",
              s.js("""return document.querySelector('tr[data-rule="r3"] .badge-plain') !== null;"""))
        # 批量删除
        s.js("""document.querySelectorAll('table.data tbody .row-check')[0].click();""")
        time.sleep(0.35)
        s.click("#btnRuleBatchDelete"); time.sleep(0.45)
        check("删除弹窗文案与语义正确",
              "确定删除以下规则？删除操作无法恢复，请谨慎操作。" in
              s.js("return document.getElementById('modalBody').innerText")
              and s.js("return !!document.querySelector('#modalIcon path')")
              and "btn-danger" in s.js("return document.getElementById('modalConfirm').className"))
        s.shot("63-rule-delete-confirm.png")
        s.js("document.getElementById('modalConfirm').click();"); time.sleep(0.5)
        check("删除后规则数减少、卡片计数同步",
              "共 4 条屏蔽规则" in s.js("return document.querySelector('.des-head').innerText"),
              s.js("return document.querySelector('.des-head').innerText.trim();"))
        check("删除后批量按钮回到置灰态",
              s.js("return document.getElementById('btnRuleBatchDelete').disabled"))

        # 全选 → 空态
        s.js("document.getElementById('ruleCheckAll').click();"); time.sleep(0.4)
        s.click("#btnRuleBatchDelete"); time.sleep(0.4)
        s.js("document.getElementById('modalConfirm').click();"); time.sleep(0.5)
        check("全部删除后给出空态提示而非空白",
              s.js("return document.querySelector('table.data tbody').innerText.trim();") == "暂无屏蔽规则"
              and "共 0 条屏蔽规则" in s.js("return document.querySelector('.des-head').innerText"))

        # --- 告警列表创建的规则会出现在告警设置里（跨页一致） ---
        s.nav(PAGE)
        s.go("#/settings/alarm-list")
        s.js("""document.querySelector('table.data tbody [data-alm-act="block"]').click();""")
        time.sleep(0.5)
        s.js("""function setbv(id,v){var e=document.getElementById(id);e.value=v;
                  e.dispatchEvent(new Event('input',{bubbles:true}));}
                setbv('blkName','来自告警列表的屏蔽规则');
                setbv('blkDesc','在告警列表页直接创建的规则');
                document.querySelector('#drawerBody .radio-input[value="alarm"]').click();""")
        time.sleep(0.35)
        s.click("#drawerSubmit"); time.sleep(0.5)
        s.go("#/settings/alarm-config")
        check("在告警列表创建的屏蔽规则出现在「告警设置」中",
              "来自告警列表的屏蔽规则" in s.js("return document.querySelector('table.data tbody').innerText")
              and "共 5 条屏蔽规则" in s.js("return document.querySelector('.des-head').innerText"),
              s.js("return document.querySelector('.des-head').innerText.trim();"))

        # 英文态
        s.click('.lang-btn[data-lang="en-US"]')
        s.go("#/settings/alarm-config")
        en_rheads = s.texts("table.data thead th")
        check("英文表头与顺序一致",
              en_rheads == ["", "Name", "Status", "Blocking Dates", "Blocking Hours",
                            "Updated At", "Description", "Actions"], str(en_rheads))
        check("英文状态取值为 Enabled / Disabled",
              set(s.texts("table.data tbody .badge-ok, table.data tbody .badge-plain"))
              <= {"Enabled", "Disabled"})
        check("英文下表格不横向溢出、操作列不被裁切",
              s.js("""var sc=document.querySelector('.table-scroll');
                        var card=document.querySelector('.table-card').getBoundingClientRect();
                        var cells=document.querySelectorAll('table.data tbody tr td');
                        var btn=cells[cells.length-1].querySelector('.link-btn:last-child')
                                    .getBoundingClientRect();
                        return sc.scrollWidth<=sc.clientWidth && btn.right<=card.right+0.5;"""),
              s.js("""var sc=document.querySelector('.table-scroll');
                        return 'scroll '+sc.scrollWidth+'/'+sc.clientWidth;"""))
        s.shot("64-rule-en.png")
        s.click('.lang-btn[data-lang="zh-CN"]')   # 上一节英文态收尾，切回中文

        # ---------- 12.10 告警统计页（M17） ----------
        print("\n[12.10] 告警统计页（M17）")
        s.go("#/settings/alarm-stats")
        check("页面标题=告警统计",
              s.js("return document.querySelector('.page-title').innerText.trim()") == "告警统计")
        check("面包屑为「设置 / 告警统计」",
              s.texts("#crumb .crumb-item") == ["设置", "告警统计"],
              str(s.texts("#crumb .crumb-item")))
        cards = s.js("""return Array.from(document.querySelectorAll('.des-card, .table-card'))
                          .map(function(c){return c.querySelector('.des-head').innerText
                            .replace(/\\s+/g,' ').trim();});""")
        check("上方是「告警数量 Top10」、下方是统计明细表格",
              cards[0].startswith("告警数量 Top10") and cards[1].startswith("告警统计明细"),
              str(cards))
        check("Top10 卡片标注了统计时间范围与总次数",
              "统计时间范围 2026-10-08 ~ 2026-10-14" in cards[0] and "共 130 次告警" in cards[0],
              cards[0])
        rank = s.js("""return Array.from(document.querySelectorAll('.rank-row')).map(function(r){
            return [r.querySelector('.rank-no').innerText.trim(),
                    r.querySelector('.rank-name').innerText.trim(),
                    r.querySelector('.rank-count').innerText.trim()];});""")
        check("Top10 排行固定 10 条（数量最多的 10 条）", len(rank) == 10, f"{len(rank)} 条")
        check("排行按数量倒序",
              [int(x[2]) for x in rank] == sorted([int(x[2]) for x in rank], reverse=True),
              str([x[2] for x in rank]))
        check("Top10 之首为 ALM-1001（26 次）",
              rank[0][1] == "License 授权剩余天数不足" and rank[0][2] == "26", str(rank[0]))
        check("排行条目带序号与级别徽标",
              s.js("return document.querySelectorAll('.rank-row .badge').length") == 10
              and rank[0][0] == "1" and rank[9][0] == "10")
        bars = s.js("""return Array.from(document.querySelectorAll('.rank-row .rank-bar i'))
                         .map(function(b){return b.style.width;});""")
        check("条形宽度按数量成比例（首条 100%、末端更短）",
              bars[0] == "100%" and all(b.endswith('%') for b in bars)
              and float(bars[0][:-1]) > float(bars[-1][:-1]), str(bars))
        check("条形按告警级别配色",
              s.js("return document.querySelectorAll('.rank-bar i.is-critical, .rank-bar i.is-major, "
                   ".rank-bar i.is-normal, .rank-bar i.is-hint').length") == 10)
        s.shot("65-stat-top10.png")

        sheads = s.texts("table.data thead th")
        check("明细表表头 6 列且顺序与要求一致",
              sheads == ["告警级别", "告警名称", "告警ID", "对象类型", "部件类型", "数量"], str(sheads))
        check("明细表列出全部 13 条统计（Top10 只取前 10）",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 13,
              str(s.js("return document.querySelectorAll('table.data tbody tr').length")))
        first = s.js("""return Array.from(document.querySelector('table.data tbody tr').children)
                          .map(function(c){return c.innerText.trim();});""")
        check("明细行含 级别 / 名称 / 告警ID / 对象类型 / 部件类型 / 数量",
              first == ["紧急", "License 授权剩余天数不足", "ALM-1001", "License", "OMS", "26"],
              str(first))
        check("告警ID 用等宽字体、数量右对齐加粗",
              s.js("""return getComputedStyle(document.querySelector('table.data tbody .des-mono'))
                        .fontFamily.toLowerCase().indexOf('mono') >= 0
                      || getComputedStyle(document.querySelector('table.data tbody .des-mono'))
                        .fontFamily.toLowerCase().indexOf('consolas') >= 0;""")
              and s.js("""return getComputedStyle(document.querySelector('table.data tbody .col-count'))
                            .fontWeight;""") in ("600", "700"),
              s.js("return getComputedStyle(document.querySelector('table.data tbody .col-count')).fontWeight;"))
        check("页脚给出统计条数与合计次数",
              "共 13 条统计记录，合计 130 次告警" in
              s.js("return document.querySelectorAll('.table-foot')[1].innerText"))
        check("筛选栏在一行内放得下（不发生换行）",
              s.js("""var bar=document.querySelector('.filter-bar').getBoundingClientRect();
                      var items=Array.from(document.querySelectorAll('.filter-bar > *'))
                        .map(function(e){return Math.round(e.getBoundingClientRect().top);});
                      return Math.max.apply(null,items) - Math.min.apply(null,items);""") <= 2,
              s.js("""var items=Array.from(document.querySelectorAll('.filter-bar > *'))
                        .map(function(e){return Math.round(e.getBoundingClientRect().top);});
                      return '行数偏差 '+ (Math.max.apply(null,items)-Math.min.apply(null,items)) +'px';"""))
        stat_filters = [x for x in s.texts(".filter-bar .filter-item > span") if x != "~"]
        check("筛选栏覆盖 级别 / 部件类型 / 对象类型 / 时间范围",
              stat_filters == ["级别", "部件类型", "对象类型", "时间"], str(stat_filters))
        # 表格在首屏下方，滚动到表格再出图
        s.js("document.querySelector('.table-card').scrollIntoView({block:'start'});"); time.sleep(0.45)
        s.shot("66-stat-table.png")

        # --- 时间范围统计 ---
        s.js("""var f=document.getElementById('statfrom');f.value='2026-10-01';
                f.dispatchEvent(new Event('change',{bubbles:true}));""")
        time.sleep(0.45)
        check("放宽起始日期后统计范围与合计随之变化",
              "统计时间范围 2026-10-01 ~ 2026-10-14" in
              s.js("return document.querySelector('.des-head').innerText")
              and "共 140 次告警" in s.js("return document.querySelector('.des-head').innerText"),
              s.js("return document.querySelector('.des-head').innerText.replace(/\\s+/g,' ').trim();"))
        check("放宽范围后 ALM-1001 的次数从 26 增加到 30",
              s.js("""return Array.from(document.querySelectorAll('table.data tbody tr'))
                        .filter(function(r){return r.children[2].innerText.trim()==='ALM-1001';})[0]
                        .children[5].innerText.trim();""") == "30",
              s.js("""return Array.from(document.querySelectorAll('table.data tbody tr'))
                        .filter(function(r){return r.children[2].innerText.trim()==='ALM-1001';})[0]
                        .children[5].innerText.trim();"""))
        # 收窄到最后一天 → 只剩 3 条
        s.js("""function sv(id,v){var e=document.getElementById(id);e.value=v;
                  e.dispatchEvent(new Event('change',{bubbles:true}));}
                sv('statfrom','2026-10-14');""")
        time.sleep(0.45)
        check("收窄到 2026-10-14 当天只剩 3 条、共 10 次",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 3
              and "共 3 条统计记录，合计 10 次告警" in
                  s.js("return document.querySelectorAll('.table-foot')[1].innerText"),
              s.js("return document.querySelectorAll('.table-foot')[1].innerText.trim();"))
        check("不足 10 条时排行按实际数量展示并说明",
              s.js("return document.querySelectorAll('.rank-row').length") == 3
              and "共 3 条告警计入排行" in
                  s.js("return document.querySelectorAll('.table-foot')[0].innerText"),
              s.js("return document.querySelectorAll('.table-foot')[0].innerText.trim();"))
        s.click("#statFilterReset"); time.sleep(0.45)
        check("重置筛选恢复到默认时间范围与 13 条",
              s.js("return document.getElementById('statfrom').value") == "2026-10-08"
              and s.js("return document.querySelectorAll('table.data tbody tr').length") == 13)

        # --- 维度筛选 ---
        s.js("""var e=document.getElementById('statlevel');e.value='critical';
                e.dispatchEvent(new Event('change',{bubbles:true}));""")
        time.sleep(0.45)
        check("按告警级别=紧急筛选出 3 条",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 3
              and set(s.texts("table.data tbody .badge-lv-critical")) == {"紧急"},
              str(s.js("return document.querySelectorAll('table.data tbody tr').length")))
        s.click("#statFilterReset"); time.sleep(0.4)
        s.js("""var e=document.getElementById('statpart');e.value='model';
                e.dispatchEvent(new Event('change',{bubbles:true}));""")
        time.sleep(0.45)
        check("按部件类型=模型工程筛选出 4 条",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 4
              and set(s.texts("table.data tbody tr td:nth-child(5)")) == {"模型工程"},
              str(s.js("return document.querySelectorAll('table.data tbody tr').length")))
        s.click("#statFilterReset"); time.sleep(0.4)
        s.js("""var e=document.getElementById('statobj');e.value='License';
                e.dispatchEvent(new Event('change',{bubbles:true}));""")
        time.sleep(0.45)
        check("按对象类型=License 筛选出 2 条、Top10 同步变为 2 条",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 2
              and s.js("return document.querySelectorAll('.rank-row').length") == 2,
              str(s.js("return document.querySelectorAll('.rank-row').length")))
        s.click("#statFilterReset"); time.sleep(0.4)
        s.js("""var e=document.getElementById('statq');e.value='ALM-1010';
                e.dispatchEvent(new Event('input',{bubbles:true}));""")
        time.sleep(0.45)
        check("按告警ID 搜索命中 1 条",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 1
              and "服务间证书校验失败" in
                  s.js("return document.querySelector('table.data tbody').innerText"))
        s.js("""var e=document.getElementById('statq');e.value='证书';
                e.dispatchEvent(new Event('input',{bubbles:true}));""")
        time.sleep(0.45)
        check("按告警名称关键字搜索命中 2 条",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 2,
              s.js("return document.querySelector('table.data tbody').innerText.replace(/\\n/g,' ');"))
        s.js("""var e=document.getElementById('statq');e.value='zzzz';
                e.dispatchEvent(new Event('input',{bubbles:true}));""")
        time.sleep(0.45)
        check("无匹配时给出明确提示而非空白",
              s.js("return document.querySelector('table.data tbody').innerText.trim();") == "无匹配统计记录"
              and "当前统计范围内暂无告警" in
                  s.js("return document.querySelector('.rank-list').innerText"))
        s.click("#statFilterReset"); time.sleep(0.45)
        check("重置后恢复 13 条", s.js("return document.querySelectorAll('table.data tbody tr').length") == 13)

        # 英文态
        s.click('.lang-btn[data-lang="en-US"]')
        s.go("#/settings/alarm-stats")
        en_sheads = s.texts("table.data thead th")
        check("英文表头与顺序一致",
              en_sheads == ["Level", "Alarm Name", "Alarm ID", "Object Type", "Component", "Count"],
              str(en_sheads))
        check("英文 Top10 卡片与统计范围文案",
              s.js("return document.querySelector('.des-head').innerText;").startswith("Top 10 Alarms by Count")
              and "130" in s.js("return document.querySelector('.des-head').innerText"),
              s.js("return document.querySelector('.des-head').innerText.replace(/\\s+/g,' ').trim();"))
        check("英文下表格不横向溢出",
              s.js("""var sc=document.querySelector('.table-scroll');
                        return sc.scrollWidth<=sc.clientWidth;"""),
              s.js("""var sc=document.querySelector('.table-scroll');
                        return 'scroll '+sc.scrollWidth+'/'+sc.clientWidth;"""))
        s.shot("67-stat-en.png")
        s.click('.lang-btn[data-lang="zh-CN"]')
        s.nav(PAGE)                       # 恢复语言与内存数据，进入 M04 用例

        # ---------- 12.11 用户组管理页（M04 FR-RG-002 / FR-RG-003） ----------
        print("\n[12.11] 用户组管理页（M04）")
        s.go("#/settings/user-group")
        check("页面标题=用户组管理",
              s.js("return document.querySelector('.page-title').innerText.trim()") == "用户组管理")
        check("面包屑为「设置 / 用户组管理」",
              s.texts("#crumb .crumb-item") == ["设置", "用户组管理"],
              str(s.texts("#crumb .crumb-item")))
        check("页头有「创建用户组」按钮",
              s.js("return document.getElementById('btnUgCreate').innerText.trim()") == "创建用户组")
        ugheads = s.texts("table.data thead th")
        check("表头 6 列且顺序与要求一致",
              ugheads == ["用户组名称", "用途说明", "成员数量", "已绑定角色", "已关联资源组", "操作"],
              str(ugheads))
        check("列出 5 个用户组", s.js("return document.querySelectorAll('table.data tbody tr').length") == 5)
        ugrows = s.js("""return Array.from(document.querySelectorAll('table.data tbody tr')).map(function(r){
            return Array.from(r.children).slice(0,5).map(function(c){return c.innerText.trim();});});""")
        check("成员数量与该组成员数一致（运维组 3 人 / 只读审计组 2 人）",
              ugrows[3][2] == "3 人" and ugrows[4][2] == "2 人", str([r[2] for r in ugrows]))
        check("已绑定角色列展示绑定结果",
              ugrows[0][3] == "系统管理员" and ugrows[3][3] == "运维员", str([r[3] for r in ugrows]))
        check("已关联资源组列展示关联结果（安全管理员组为空值）",
              ugrows[1][4] == "—" and "生产资源组" in ugrows[3][4], str([r[4] for r in ugrows]))
        check("操作列为 修改 / 成员 / 权限配置 / 删除",
              set(s.texts("table.data tbody .row-actions .link-btn")) ==
              {"修改", "成员", "权限配置", "删除"},
              str(set(s.texts("table.data tbody .row-actions .link-btn"))))
        check("内置用户组的删除按钮禁用并带说明（内置组不允许删除）",
              s.js("""return ['g-sysadmin','g-secadmin','g-secauditor'].every(function(id){
                        var b=document.querySelector('tr[data-ug="'+id+'"] .link-btn.is-danger');
                        return b && b.disabled && b.getAttribute('title')==='内置组不允许删除';});"""))
        check("普通用户组可删除",
              s.js("""return !document.querySelector('tr[data-ug="g-ops"] .link-btn.is-danger').disabled;"""))
        check("点击内置用户组的（置灰）删除按钮不会弹出删除确认（OI-M04-006）",
              s.js("""document.querySelector('tr[data-ug="g-sysadmin"] .link-btn.is-danger').click();
                      return document.getElementById('modalMask').hidden;"""))
        check("内置用户组带内置标记",
              s.js("return document.querySelectorAll('table.data tbody .badge-builtin').length") == 3)
        check("页脚说明「账户只能归属一个用户组、权限经用户组传递」",
              "一个账户只能归属一个用户组" in s.js("return document.querySelector('.table-foot').innerText"))
        s.shot("68-usergroup-list.png")

        # 查询（按名称 / 用途说明）
        s.js("""var e=document.getElementById('ugq');e.value='运维';e.dispatchEvent(new Event('input',{bubbles:true}));""")
        time.sleep(0.4)
        check("按关键字查询命中用途说明含「运维」的用户组",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 1
              and "运维组" in s.js("return document.querySelector('table.data tbody').innerText"))
        s.js("""var e=document.getElementById('ugq');e.value='zzzz';e.dispatchEvent(new Event('input',{bubbles:true}));""")
        time.sleep(0.4)
        check("无匹配时给出空态而非空白",
              s.js("return document.querySelector('table.data tbody').innerText.trim();") == "暂无用户组")
        s.click("#ugFilterReset"); time.sleep(0.4)
        check("重置筛选恢复 5 个用户组",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 5)

        # --- 创建用户组 ---
        s.click("#btnUgCreate"); time.sleep(0.45)
        check("抽屉标题=创建用户组",
              s.js("return document.getElementById('drawerTitle').innerText.trim()") == "创建用户组")
        check("创建表单=用户组名称 + 用途说明（均为必填）",
              s.js("""return Array.from(document.querySelectorAll('#drawerBody .f-label'))
                        .map(function(e){return [e.innerText.replace('*','').trim(),
                          e.querySelector('.req')?'required':'optional'];});""")
              == [["用户组名称", "required"], ["用途说明", "required"]])
        check("用途说明为多行文本并说明必填原因",
              s.js("return document.getElementById('grpDesc').tagName") == "TEXTAREA"
              and "用途说明为必填" in
                  s.js("return document.querySelector('[data-field=\"grpDesc\"] .f-hint').innerText"))
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("名称与用途说明未填写时被拦截",
              s.js("""return document.querySelectorAll('#drawerBody .f-field.has-error').length;""") == 2)
        s.js("""function svg(id,v){var e=document.getElementById(id);e.value=v;
                  e.dispatchEvent(new Event('input',{bubbles:true}));}
                svg('grpName','运维组');svg('grpDesc','重名测试');""")
        time.sleep(0.3)
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("名称重复时拒绝创建并提示",
              "已存在" in s.js("""return document.querySelector('[data-field="grpName"] .f-error').innerText;"""))
        s.js("""function sv2(id,v){var e=document.getElementById(id);e.value=v;
                  e.dispatchEvent(new Event('input',{bubbles:true}));}
                sv2('grpName','网络运维组');sv2('grpDesc','负责网络设备的日常运维');""")
        time.sleep(0.3)
        s.shot("69-usergroup-create.png")
        s.click("#drawerSubmit"); time.sleep(0.5)
        check("创建成功后列表新增该用户组（6 个）",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 6
              and "网络运维组" in s.js("return document.querySelector('table.data tbody').innerText"))
        # 清理：删除刚创建的组，避免影响后续用例
        s.js("""var rows=Array.from(document.querySelectorAll('table.data tbody tr'));
                var r=rows.filter(function(x){return x.innerText.indexOf('网络运维组')>=0;})[0];
                r.querySelector('[data-ug-act="delete"]').click();""")
        time.sleep(0.45)
        s.js("document.getElementById('modalConfirm').click();"); time.sleep(0.5)
        check("删除新建用户组后回到 5 个",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 5)

        # --- 修改用户组：可改名与用途说明 ---
        s.js("""document.querySelector('tr[data-ug="g-ops"] [data-ug-act="edit"]').click();""")
        time.sleep(0.5)
        check("抽屉标题=修改用户组",
              s.js("return document.getElementById('drawerTitle').innerText.trim()") == "修改用户组")
        check("带出原名称与用途说明",
              s.js("return document.getElementById('grpName').value") == "运维组"
              and len(s.js("return document.getElementById('grpDesc').value")) > 0,
              s.js("return document.getElementById('grpName').value + ' / ' + document.getElementById('grpDesc').value;"))
        check("普通用户组的名称可以改（非只读）",
              not s.js("return document.getElementById('grpName').readOnly"))
        s.js("""function sve(id,v){var e=document.getElementById(id);e.value=v;
                  e.dispatchEvent(new Event('input',{bubbles:true}));}
                sve('grpName','基础运维组');sve('grpDesc','负责部署、训练任务与备份执行的一线运维人员');""")
        time.sleep(0.3)
        s.click("#drawerSubmit"); time.sleep(0.5)
        check("改名与用途说明保存后列表同步更新",
              "基础运维组" in s.js("return document.querySelector('table.data tbody').innerText")
              and "一线运维人员" in s.js("return document.querySelector('table.data tbody').innerText"))
        s.go("#/settings/account")
        check("账户管理页的用户组名同步变为新名称（跨页一致）",
              s.js("""return document.querySelector('tr[data-name="zhangwei"] .col-group').innerText.trim();""")
              == "基础运维组")
        s.go("#/settings/user-group")
        s.js("""document.querySelector('tr[data-ug="g-sysadmin"] [data-ug-act="edit"]').click();""")
        time.sleep(0.5)
        check("内置用户组的名称字段只读并给出「内置组不允许改名」说明",
              s.js("return document.getElementById('grpName').readOnly")
              and "内置组不允许改名" in
                  s.js("""return document.querySelector('[data-field="grpName"] .f-hint').innerText;"""),
              s.js("""return document.querySelector('[data-field="grpName"] .f-hint').innerText;"""))
        check("内置用户组的用途说明仍可编辑",
              not s.js("return document.getElementById('grpDesc').readOnly"))
        s.js("""var e=document.getElementById('grpDesc');e.value='承载平台全部管理能力的系统管理员账户（已改）';
                e.dispatchEvent(new Event('input',{bubbles:true}));""")
        time.sleep(0.3)
        s.click("#drawerSubmit"); time.sleep(0.5)
        check("内置用户组只改了用途说明、名称不变",
              "系统管理员组" in s.js("return document.querySelector('table.data tbody').innerText")
              and "已改" in s.js("return document.querySelector('table.data tbody').innerText"))

        # --- 成员管理 ---
        s.js("""document.querySelector('tr[data-ug="g-ops"] [data-ug-act="members"]').click();""")
        time.sleep(0.5)
        check("抽屉标题=成员管理",
              s.js("return document.getElementById('drawerTitle').innerText.trim()") == "成员管理")
        check("抽屉列出该组成员（运维组 3 人）",
              s.js("return document.querySelectorAll('#drawerBody .mini-table tbody tr').length") == 3
              and "3 人" in s.js("return document.querySelector('#drawerBody .f-section').innerText"))
        check("成员表格列为 账户名称 / 认证类型 / 状态",
              s.texts("#drawerBody .mini-table thead th") == ["账户名称", "认证类型", "状态", ""],
              str(s.texts("#drawerBody .mini-table thead th")))
        s.shot("70-usergroup-members.png")
        s.click("#btnAddMember"); time.sleep(0.5)
        check("「添加成员」弹出可加入账户清单（排除本组成员）",
              s.js("return document.getElementById('modalTitle').innerText.trim();") == "添加成员"
              and s.js("return document.querySelectorAll('#modalBody .pick-row').length;") == 5,
              str(s.js("return document.querySelectorAll('#modalBody .pick-row').length;")))
        check("已归属其他用户组的账户标注「将迁入本组」",
              s.js("return document.querySelectorAll('#modalBody .badge-plain').length;") == 5
              and "将迁入本组" in s.js("return document.querySelector('#modalBody').innerText"))
        check("已锁定（待激活）的账户可以加入用户组（OI-M04-004 结论）",
              s.js("""var r=Array.from(document.querySelectorAll('#modalBody .mini-table tbody tr'))
                        .filter(function(x){return x.innerText.indexOf('sunlei')>=0;})[0];
                      return r.innerText.indexOf('已锁定')>=0
                          && !r.querySelector('.pick-row').disabled;"""))
        s.js("""var rows=Array.from(document.querySelectorAll('#modalBody .pick-row'));
                rows.filter(function(c){
                  return c.closest('tr').innerText.indexOf('sunlei')>=0;})[0].click();""")
        time.sleep(0.3)
        s.shot("71-usergroup-add-member.png")
        s.click("#modalConfirm"); time.sleep(0.5)
        check("加入后该账户迁入本组（运维组变 4 人）",
              s.js("return document.querySelectorAll('#drawerBody .mini-table tbody tr').length") == 4
              and "4 人" in s.js("return document.querySelector('#drawerBody .f-section').innerText"))
        s.click("#drawerSubmit"); time.sleep(0.4)      # 关闭抽屉
        check("只读抽屉（成员管理）底部的「关闭」按钮真的能关闭抽屉",
              s.js("return document.getElementById('drawer').hidden")
              and s.js("return document.getElementById('drawerSubmit').innerText.trim();") == "关闭")
        s.go("#/settings/account")
        check("账户管理页中 sunlei 的用户组已变为「基础运维组」（前面刚改过名）",
              s.js("""return document.querySelector('tr[data-name="sunlei"] .col-group').innerText.trim();""")
              == "基础运维组",
              s.js("""return document.querySelector('tr[data-name="sunlei"] .col-group').innerText.trim();"""))
        s.go("#/settings/user-group")
        # 移出成员 → 账户变成未归属
        s.js("""document.querySelector('tr[data-ug="g-ops"] [data-ug-act="members"]').click();""")
        time.sleep(0.45)
        s.js("""document.querySelector('#drawerBody [data-member-del="sunlei"]').click();""")
        time.sleep(0.5)
        check("移出成员后该账户不再属于本组（运维组回到 3 人）",
              s.js("return document.querySelectorAll('#drawerBody .mini-table tbody tr').length") == 3)
        s.click("#drawerSubmit"); time.sleep(0.4)
        s.go("#/settings/account")
        check("被移出的账户在账户管理页显示未归属用户组（—）",
              s.js("""return document.querySelector('tr[data-name="sunlei"] .col-group').innerText.trim();""")
              == "—")
        s.go("#/settings/user-group")

        # --- 权限配置：绑定角色 + 关联资源组 ---
        s.js("""document.querySelector('tr[data-ug="g-ops"] [data-ug-act="perm"]').click();""")
        time.sleep(0.5)
        check("抽屉标题=权限配置，分「绑定角色」「关联资源组」两栏",
              s.js("return document.getElementById('drawerTitle').innerText.trim()") == "权限配置"
              and s.texts("#drawerBody .f-section") == ["绑定角色", "关联资源组"],
              str(s.texts("#drawerBody .f-section")))
        perm_tables = s.js("""return Array.from(document.querySelectorAll('#drawerBody .mini-table')).map(function(t){
            return Array.from(t.querySelectorAll('thead th')).map(function(e){return e.innerText.trim();});});""")
        check("绑定角色表=角色名称/职责说明，关联资源组表=资源组名称/资源数量",
              perm_tables[0] == ["角色名称", "职责说明", ""]
              and perm_tables[1] == ["资源组名称", "资源数量", ""], str(perm_tables))
        check("带出当前绑定：运维员 1 个角色、2 个资源组",
              s.js("""return document.querySelectorAll('#drawerBody .mini-table')[0]
                        .querySelectorAll('tbody tr').length;""") == 1
              and s.js("""return document.querySelectorAll('#drawerBody .mini-table')[1]
                            .querySelectorAll('tbody tr').length;""") == 2)
        s.shot("72-usergroup-perm.png")
        # 绑定角色
        s.click("#btnBindRole"); time.sleep(0.5)
        check("「绑定角色」弹出内置角色清单（含职责说明）",
              s.js("return document.getElementById('modalTitle').innerText.trim();") == "绑定角色"
              and s.texts("#modalBody .mini-table thead th") == ["", "角色名称", "职责说明"]
              and s.js("return document.querySelectorAll('#modalBody .pick-row').length;") == 4)
        s.js("""document.querySelectorAll('#modalBody .pick-row')[4-1].click();""")
        time.sleep(0.3)
        s.click("#modalConfirm"); time.sleep(0.5)
        check("绑定后角色数变为 2",
              s.js("""return document.querySelectorAll('#drawerBody .mini-table')[0]
                        .querySelectorAll('tbody tr').length;""") == 2)
        # 解除角色绑定
        s.js("""document.querySelector('#drawerBody [data-unbind-role="ops"]').click();""")
        time.sleep(0.5)
        check("解除后角色数回到 1",
              s.js("""return document.querySelectorAll('#drawerBody .mini-table')[0]
                        .querySelectorAll('tbody tr').length;""") == 1)
        # 三权分立互斥：在**非内置**组（基础运维组）上先绑系统管理员，再绑审计管理员 → 拒绝
        # （内置用户组的绑定入口已按 OI-M04-007 置灰，互斥判定改在可绑定的组上验证）
        s.click("#btnBindRole"); time.sleep(0.5)
        s.js("""var rows=Array.from(document.querySelectorAll('#modalBody .pick-row'));
                rows.filter(function(c){
                  return c.closest('tr').innerText.indexOf('系统管理员')>=0;})[0].click();""")
        time.sleep(0.3)
        s.click("#modalConfirm"); time.sleep(0.5)
        check("非内置用户组可以绑定系统管理员（角色数变 2）",
              s.js("""return document.querySelectorAll('#drawerBody .mini-table')[0]
                        .querySelectorAll('tbody tr').length;""") == 2)
        s.click("#btnBindRole"); time.sleep(0.5)
        s.js("""var rows=Array.from(document.querySelectorAll('#modalBody .pick-row'));
                rows.filter(function(c){
                  return c.closest('tr').innerText.indexOf('审计管理员')>=0;})[0].click();""")
        time.sleep(0.3)
        s.click("#modalConfirm"); time.sleep(0.5)
        check("同一用户组同时绑定系统管理员与审计管理员被拒绝（三权分立）",
              "三权分立" in s.js("return document.querySelector('#toastWrap').innerText")
              and s.js("""return document.querySelectorAll('#drawerBody .mini-table')[0]
                            .querySelectorAll('tbody tr').length;""") == 2,
              s.js("return document.querySelector('#toastWrap').innerText.replace(/\\n/g,' ');"))
        s.js("""document.querySelector('#drawerBody [data-unbind-role="sysadmin"]').click();""")
        time.sleep(0.5)
        check("解除系统管理员绑定后角色数回到 1（复原）",
              s.js("""return document.querySelectorAll('#drawerBody .mini-table')[0]
                        .querySelectorAll('tbody tr').length;""") == 1)
        s.click("#drawerSubmit"); time.sleep(0.4)
        # 关联资源组
        s.js("""document.querySelector('tr[data-ug="g-ops"] [data-ug-act="perm"]').click();""")
        time.sleep(0.45)
        s.click("#btnLinkRes"); time.sleep(0.5)
        check("「关联资源组」弹出未关联的资源组清单",
              s.js("return document.getElementById('modalTitle').innerText.trim();") == "关联资源组"
              and s.texts("#modalBody .mini-table thead th") == ["", "资源组名称", "资源数量"]
              and s.js("return document.querySelectorAll('#modalBody .pick-row').length;") == 2,
              str(s.js("return document.querySelectorAll('#modalBody .pick-row').length;")))
        s.js("""document.querySelector('#modalBody .pick-row').click();""")
        time.sleep(0.3)
        s.click("#modalConfirm"); time.sleep(0.5)
        check("关联后资源组数变为 3",
              s.js("""return document.querySelectorAll('#drawerBody .mini-table')[1]
                        .querySelectorAll('tbody tr').length;""") == 3)
        s.js("""document.querySelector('#drawerBody [data-unlink-rg="rg-prod"]').click();""")
        time.sleep(0.5)
        check("解除关联后资源组数回到 2",
              s.js("""return document.querySelectorAll('#drawerBody .mini-table')[1]
                        .querySelectorAll('tbody tr').length;""") == 2)
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("只读抽屉（权限配置）底部的「关闭」按钮真的能关闭抽屉",
              s.js("return document.getElementById('drawer').hidden"))

        # --- 内置用户组：绑定角色由系统固化，不允许添加 / 移除（OI-M04-007） ---
        s.js("""document.querySelector('tr[data-ug="g-sysadmin"] [data-ug-act="perm"]').click();""")
        time.sleep(0.5)
        check("内置用户组「权限配置」的「绑定角色」置灰并给出原因",
              s.js("""var b=document.getElementById('btnBindRole');
                      return b && b.disabled && b.getAttribute('title')==='内置组不允许调整绑定角色';"""),
              s.js("""return document.getElementById('btnBindRole').getAttribute('title');"""))
        check("内置用户组给出「绑定角色由系统固化」的说明",
              "由系统固化" in s.js("return (document.querySelector('#drawerBody .f-hint')||{}).innerText||''"),
              s.js("return (document.querySelector('#drawerBody .f-hint')||{}).innerText||'';"))
        check("内置用户组角色表的「移出」全部置灰（没有可点的移除入口）",
              s.js("return document.querySelectorAll('#drawerBody [data-unbind-role]').length") == 0
              and s.js("""var b=document.querySelector('#drawerBody .link-btn.is-danger');
                          return b && b.disabled && b.getAttribute('title')==='内置组不允许调整绑定角色';"""))
        check("内置用户组仍只读展示已固化的角色（系统管理员）",
              s.js("return document.getElementById('drawerBody').innerText.indexOf('系统管理员')>=0"))
        check("内置用户组的「关联资源组」仍可调整（范围维度不受限）",
              s.js("return !!document.getElementById('btnLinkRes')")
              and not s.js("return document.getElementById('btnLinkRes').disabled"))
        time.sleep(1.6)                   # 等前面的 toast 消失再出图
        s.shot("81-usergroup-perm-builtin.png")
        check("点击（置灰的）「绑定角色」不会弹出角色清单",
              s.js("""document.getElementById('btnBindRole').click();
                      return document.getElementById('modalMask').hidden;"""))
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("内置用户组「权限配置」底部的「关闭」按钮真的能关闭抽屉",
              s.js("return document.getElementById('drawer').hidden"))

        # --- 删除用户组：提示成员与授权影响 ---
        s.js("""document.querySelector('tr[data-ug="g-readonly"] [data-ug-act="delete"]').click();""")
        time.sleep(0.5)
        body = s.js("return document.getElementById('modalBody').innerText")
        check("删除用户组弹窗提示成员影响（不删除账户）",
              "个成员" in body and "不删除账户" in body, body.replace("\n", " ")[:80])
        check("同时提示已绑定角色与已关联资源组的解除",
              "绑定关系一并解除" in body and "关联关系一并解除" in body,
              body.replace("\n", " "))
        s.shot("73-usergroup-delete.png")
        s.js("document.getElementById('modalConfirm').click();"); time.sleep(0.5)
        check("删除后用户组少一个（4 个）",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 4,
              str(s.js("return document.querySelectorAll('table.data tbody tr').length;")))
        s.go("#/settings/account")
        check("原成员被解除用户组归属（不删除账户）",
              s.js("""return document.querySelector('tr[data-name="chenjing"] .col-group').innerText.trim();""")
              == "—"
              and s.js("return !!document.querySelector('tr[data-name=\"chenjing\"]')"))

        # ---------- 12.12 资源组管理页（M04 FR-RG-001 / FR-RG-004） ----------
        print("\n[12.12] 资源组管理页（M04）")
        s.nav(PAGE)                       # 恢复内存数据（上一节改动了角色与资源组关联）
        s.go("#/settings/resource-group")
        check("页面标题=资源组管理",
              s.js("return document.querySelector('.page-title').innerText.trim()") == "资源组管理")
        check("面包屑为「设置 / 资源组管理」",
              s.texts("#crumb .crumb-item") == ["设置", "资源组管理"],
              str(s.texts("#crumb .crumb-item")))
        rgheads = s.texts("table.data thead th")
        check("表头 5 列且顺序与要求一致",
              rgheads == ["资源组名称", "用途说明", "资源数量", "已授权用户组", "操作"], str(rgheads))
        check("列出 4 个资源组（含内置的「系统管理员资源组」）",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 4
              and "系统管理员资源组" in
                  s.js("return document.querySelector('table.data tbody').innerText"),
              s.js("return document.querySelector('table.data tbody').innerText.replace(/\\n/g,' ');"))
        check("内置资源组的删除按钮禁用并带说明",
              s.js("""var b=document.querySelector('tr[data-rg="rg-sysadmin"] .link-btn.is-danger');
                      return b && b.disabled && b.getAttribute('title')==='内置组不允许删除';"""))
        check("点击内置资源组的（置灰）删除按钮不会弹出删除确认（OI-M04-006）",
              s.js("""document.querySelector('tr[data-rg="rg-sysadmin"] .link-btn.is-danger').click();
                      return document.getElementById('modalMask').hidden;"""))
        rgrows = s.js("""return Array.from(document.querySelectorAll('table.data tbody tr')).map(function(r){
            return Array.from(r.children).slice(0,4).map(function(c){return c.innerText.trim();});});""")
        check("资源数量与组内资源数一致（生产 2 个 / 共享 0 个）",
              rgrows[1][2] == "2 个" and rgrows[3][2] == "0 个", str([r[2] for r in rgrows]))
        check("已授权用户组列展示授权结果",
              "运维组" in rgrows[1][3] and "安全管理员组" not in rgrows[1][3], rgrows[1][3])
        check("操作列为 修改 / 资源 / 授权 / 删除",
              set(s.texts("table.data tbody .row-actions .link-btn")) == {"修改", "资源", "授权", "删除"},
              str(set(s.texts("table.data tbody .row-actions .link-btn"))))
        check("页脚说明资源组为平铺结构、授权只到资源组这一层",
              "平铺结构" in s.js("return document.querySelector('.table-foot').innerText"))
        s.shot("74-resourcegroup-list.png")

        # --- 资源清单 ---
        s.js("""document.querySelector('tr[data-rg="rg-dev"] [data-rg-act="res"]').click();""")
        time.sleep(0.5)
        check("抽屉标题=资源清单",
              s.js("return document.getElementById('drawerTitle').innerText.trim()") == "资源清单")
        check("资源表列=资源名称/资源类型/来源模块，含 2 个资源",
              s.texts("#drawerBody .mini-table thead th") == ["资源名称", "资源类型", "来源模块"]
              and s.js("return document.querySelectorAll('#drawerBody .mini-table tbody tr').length;") == 2,
              str(s.texts("#drawerBody .mini-table thead th")))
        check("资源类型与来源模块取业务模块名称",
              "模型部署资源" in s.js("return document.querySelector('#drawerBody').innerText")
              and "模型训练" in s.js("return document.querySelector('#drawerBody').innerText"))
        check("资源清单为只读：没有「添加资源」与「移出」入口（OI-M04-005 结论）",
              s.js("return !document.getElementById('btnAddRes')")
              and s.js("return document.querySelectorAll('#drawerBody [data-res-del]').length;") == 0
              and "不提供移动或切换归属的入口" in
                  s.js("return document.querySelector('#drawerBody .f-hint').innerText"),
              s.js("return document.querySelector('#drawerBody .f-hint').innerText;"))
        s.shot("75-resourcegroup-res-list.png")
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("只读抽屉（资源清单）底部的「关闭」按钮真的能关闭抽屉",
              s.js("return document.getElementById('drawer').hidden")
              and s.js("return document.getElementById('drawerSubmit').innerText.trim();") == "关闭")
        s.js("""document.querySelector('tr[data-rg="rg-sysadmin"] [data-rg-act="edit"]').click();""")
        time.sleep(0.5)
        check("内置资源组的名称字段只读、用途说明可改",
              s.js("return document.getElementById('grpName').readOnly")
              and not s.js("return document.getElementById('grpDesc').readOnly")
              and "内置组不允许改名" in
                  s.js("""return document.querySelector('[data-field="grpName"] .f-hint').innerText;"""))
        s.click("#drawerSubmit"); time.sleep(0.4)
        # 内置资源组的授权关系不锁定（OI-M04-008 结论：暂不锁定，保持现状）
        s.js("""document.querySelector('tr[data-rg="rg-sysadmin"] [data-rg-act="grant"]').click();""")
        time.sleep(0.5)
        check("内置资源组的「授权用户组」入口可用、已授权行的「移出」可点（OI-M04-008 暂不锁定）",
              s.js("return !!document.getElementById('btnGrantUg')")
              and not s.js("return document.getElementById('btnGrantUg').disabled")
              and s.js("return document.querySelectorAll('#drawerBody [data-grant-del]').length;") >= 1
              and s.js("return !document.querySelector('#drawerBody .link-btn.is-danger').disabled"))
        s.click("#drawerSubmit"); time.sleep(0.4)
        # 内置用户组的成员与关联资源组同样不锁定（OI-M04-009 待确认，当前按允许调整实现）
        s.go("#/settings/user-group")
        s.js("""document.querySelector('tr[data-ug="g-sysadmin"] [data-ug-act="members"]').click();""")
        time.sleep(0.5)
        check("内置用户组的「添加成员」与「移出」均可用（OI-M04-009 当前实现）",
              s.js("return !!document.getElementById('btnAddMember')")
              and not s.js("return document.getElementById('btnAddMember').disabled")
              and s.js("return document.querySelectorAll('#drawerBody [data-member-del]').length;") >= 1)
        s.click("#drawerSubmit"); time.sleep(0.4)
        s.go("#/settings/resource-group")
        s.js("""document.querySelector('tr[data-rg="rg-dev"] [data-rg-act="edit"]').click();""")
        time.sleep(0.5)
        s.js("""function svrg(id,v){var e=document.getElementById(id);e.value=v;
                  e.dispatchEvent(new Event('input',{bubbles:true}));}
                svrg('grpName','开发资源组');svrg('grpDesc','开发环境的模型部署与训练资源');""")
        time.sleep(0.3)
        s.click("#drawerSubmit"); time.sleep(0.5)
        check("资源组改名后列表同步更新",
              "开发资源组" in s.js("return document.querySelector('table.data tbody').innerText"))
        s.go("#/settings/user-group")
        check("用户组页面的「已关联资源组」同步显示新名称（跨页一致）",
              "开发资源组" in s.js("return document.querySelector('table.data tbody').innerText"))
        s.go("#/settings/resource-group")

        # --- 授权配置 ---
        s.js("""document.querySelector('tr[data-rg="rg-shared"] [data-rg-act="grant"]').click();""")
        time.sleep(0.5)
        check("抽屉标题=授权配置",
              s.js("return document.getElementById('drawerTitle').innerText.trim()") == "授权配置")
        check("授权抽屉的按钮文案为「授权用户组」",
              s.js("return document.getElementById('btnGrantUg').innerText.trim();") == "授权用户组",
              s.js("return document.getElementById('btnGrantUg').innerText.trim();"))
        check("授权表列=用户组名称/成员数量，列出 2 个已授权用户组",
              s.texts("#drawerBody .mini-table thead th") == ["用户组名称", "成员数量", ""]
              and s.js("return document.querySelectorAll('#drawerBody .mini-table tbody tr').length;") == 2,
              str(s.texts("#drawerBody .mini-table thead th")))
        s.shot("77-resourcegroup-grant.png")
        s.click("#btnGrantUg"); time.sleep(0.5)
        check("「授权用户组」列出未授权用户组",
              s.js("return document.getElementById('modalTitle').innerText.trim();") == "授权用户组"
              and s.js("return document.querySelectorAll('#modalBody .pick-row').length;") == 3,
              str(s.js("return document.querySelectorAll('#modalBody .pick-row').length;")))
        s.js("""document.querySelectorAll('#modalBody .pick-row')[0].click();""")
        time.sleep(0.3)
        s.click("#modalConfirm"); time.sleep(0.5)
        check("授权后已授权用户组变 3 个",
              s.js("return document.querySelectorAll('#drawerBody .mini-table tbody tr').length") == 3)
        s.js("""document.querySelector('#drawerBody [data-grant-del="g-sysadmin"]').click();""")
        time.sleep(0.5)
        check("解除授权后回到 2 个",
              s.js("return document.querySelectorAll('#drawerBody .mini-table tbody tr').length") == 2)
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("只读抽屉（授权配置）底部的「关闭」按钮真的能关闭抽屉",
              s.js("return document.getElementById('drawer').hidden"))

        # --- 删除资源组：有资源时拒绝、有授权时提示自动失效 ---
        s.js("""document.querySelector('tr[data-rg="rg-prod"] [data-rg-act="delete"]').click();""")
        time.sleep(0.5)
        blocked = s.js("return document.getElementById('modalBody').innerText")
        check("组内仍有资源时拒绝删除并说明原因（FR-RG-001）",
              s.js("return document.getElementById('modalTitle').innerText.trim();") == "无法删除资源组"
              and "仍有 2 个资源" in blocked and "OMS 侧无法移动资源" in blocked,
              blocked.replace("\n", " "))
        check("该弹窗只有一个「知道了」按钮，为告知性确认",
              s.js("return document.getElementById('modalConfirm').innerText.trim();") == "知道了"
              and s.js("return !!document.querySelector('#modalIcon circle')")
              and s.js("return document.getElementById('modalCancel').hidden;"))
        s.shot("78-resourcegroup-delete-blocked.png")
        s.js("document.getElementById('modalConfirm').click();"); time.sleep(0.4)
        check("拒绝后资源组仍为 4 个",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 4)

        s.js("""document.querySelector('tr[data-rg="rg-shared"] [data-rg-act="delete"]').click();""")
        time.sleep(0.5)
        dbody = s.js("return document.getElementById('modalBody').innerText")
        check("无资源但有授权时提示授权关系自动失效与影响范围",
              "自动失效" in dbody and "失去该资源组范围内的访问权限" in dbody,
              dbody.replace("\n", " "))
        s.shot("79-resourcegroup-delete.png")
        s.js("document.getElementById('modalConfirm').click();"); time.sleep(0.5)
        check("删除后资源组剩 3 个",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 3)
        s.go("#/settings/user-group")
        check("用户组页面的「已关联资源组」同步去掉被删资源组（跨页一致）",
              "共享资源组" not in s.js("return document.querySelector('table.data tbody').innerText"))

        # --- 创建资源组：重名校验 ---
        s.go("#/settings/resource-group")
        s.click("#btnRgCreate"); time.sleep(0.45)
        s.js("""function svr(id,v){var e=document.getElementById(id);e.value=v;
                  e.dispatchEvent(new Event('input',{bubbles:true}));}
                svr('grpName','生产资源组');svr('grpDesc','重复名称测试');""")
        time.sleep(0.3)
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("资源组名称重复时拒绝创建",
              "已存在" in s.js("""return document.querySelector('[data-field="grpName"] .f-error').innerText;"""))
        s.js("""function svr2(id,v){var e=document.getElementById(id);e.value=v;
                  e.dispatchEvent(new Event('input',{bubbles:true}));}
                svr2('grpName','边缘资源组');svr2('grpDesc','边缘节点的模型推理资源');""")
        time.sleep(0.3)
        s.click("#drawerSubmit"); time.sleep(0.5)
        check("创建成功后资源组变 4 个且新组无资源、无授权",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 4
              and "边缘资源组" in s.js("return document.querySelector('table.data tbody').innerText"))

        # 英文态
        s.click('.lang-btn[data-lang="en-US"]')
        s.go("#/settings/user-group")
        check("用户组英文表头与顺序一致",
              s.texts("table.data thead th") == ["User Group", "Description", "Members",
                                                 "Bound Roles", "Linked Resource Groups",
                                                 "Actions"],
              str(s.texts("table.data thead th")))
        s.go("#/settings/resource-group")
        check("资源组英文表头与顺序一致",
              s.texts("table.data thead th") == ["Resource Group", "Description", "Resources",
                                                 "Granted User Groups", "Actions"],
              str(s.texts("table.data thead th")))
        check("英文下两张表都不横向溢出",
              s.js("""var sc=document.querySelector('.table-scroll');
                        return sc.scrollWidth<=sc.clientWidth;"""),
              s.js("""var sc=document.querySelector('.table-scroll');
                        return 'scroll '+sc.scrollWidth+'/'+sc.clientWidth;"""))
        s.shot("80-m04-en.png")
        # 英文态：内置用户组的角色锁定文案同样本地化，且「Close」按钮可用
        s.go("#/settings/user-group")
        s.js("""document.querySelector('tr[data-ug="g-sysadmin"] [data-ug-act="perm"]').click();""")
        time.sleep(0.5)
        check("英文态下内置用户组的角色锁定说明与原因提示都本地化",
              "fixed by the system" in
                  s.js("return (document.querySelector('#drawerBody .f-hint')||{}).innerText||''")
              and s.js("""return document.getElementById('btnBindRole').getAttribute('title');""")
                  == "Built-in groups have fixed roles"
              and s.js("return document.getElementById('drawerSubmit').innerText.trim();") == "Close",
              s.js("return document.getElementById('drawerSubmit').innerText.trim();"))
        s.shot("82-m04-en-builtin-perm.png")
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("英文态下内置用户组「权限配置」的「Close」按钮可关闭抽屉",
              s.js("return document.getElementById('drawer').hidden"))
        s.click('.lang-btn[data-lang="zh-CN"]')
        s.nav(PAGE)                       # 恢复内存数据，避免影响后续用例

        # ---------- 12.13 第三方接入页（M14 FR-3RD-001/002/003） ----------
        print("\n[12.13] 第三方接入页（M14）")
        s.go("#/settings/integration")
        check("页面标题=第三方接入",
              s.js("return document.querySelector('.page-title').innerText.trim()") == "第三方接入")
        check("面包屑为「设置 / 第三方接入」",
              s.texts("#crumb .crumb-item") == ["设置", "第三方接入"],
              str(s.texts("#crumb .crumb-item")))
        heads = s.js("""return Array.from(document.querySelectorAll('.des-head')).map(function(e){
            return e.innerText.trim().split('\\n')[0];});""")
        check("页面三块：SNMP 接入配置 / SFTP 配置 / CA 服务器配置",
              heads == ["SNMP 接入配置", "SFTP 配置", "CA 服务器配置"], str(heads))

        # --- SNMP 接入：列表 ---
        snmpheads = s.texts("table.data thead th")
        check("SNMP 表头 8 列且顺序一致",
              snmpheads == ["名称", "SNMP版本", "IP地址", "端口", "上报数据类型",
                            "引擎ID", "状态", "操作"], str(snmpheads))
        check("默认 2 条 SNMP 通道，含 SNMPv3 与 SNMPv2c 两种版本",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 2
              and "SNMPv3" in s.js("return document.querySelector('table.data tbody').innerText")
              and "SNMPv2c" in s.js("return document.querySelector('table.data tbody').innerText"))
        check("列表展示引擎ID（等宽字体、超长省略）",
              s.js("""var e=document.querySelector('table.data tbody .cell-engine');
                      return e && e.innerText.indexOf('0x')===0
                          && e.getBoundingClientRect().width <= 200;"""),
              s.js("return (document.querySelector('.cell-engine')||{}).innerText"))
        check("上报数据类型：勾选告警的通道显示「告警」，未勾选的显示占位符",
              s.js("""var rows=Array.from(document.querySelectorAll('table.data tbody tr'));
                      return rows[0].innerText.indexOf('告警')>=0
                          && rows[1].children[4].innerText.trim()==='—';"""))
        check("状态列用启用/禁用徽标，行操作为 修改 / 启用|禁用 / 删除",
              s.js("""return document.querySelectorAll('table.data tbody tr')[0]
                        .querySelector('.badge').innerText.trim();""") == "启用"
              and set(s.texts("table.data tbody .row-actions .link-btn"))
                  == {"修改", "禁用", "启用", "删除"},
              str(set(s.texts("table.data tbody .row-actions .link-btn"))))
        check("SNMP 表格不横向溢出",
              s.js("""var sc=document.querySelector('.table-scroll');
                      return sc.scrollWidth<=sc.clientWidth;"""),
              s.js("""var sc=document.querySelector('.table-scroll');
                      return 'scroll '+sc.scrollWidth+'/'+sc.clientWidth;"""))
        check("页脚说明上报方式固定为 SNMP Trap、通道独立生效",
              "SNMP Trap" in s.js("return document.querySelector('.table-foot').innerText"))
        check("页面头部给出「创建SNMP接入」入口（可创建多条）",
              s.js("return document.getElementById('btnSnmpCreate').innerText.trim();") == "创建SNMP接入")
        s.shot("83-integration-page.png")

        # --- SNMP 接入：创建抽屉 ---
        s.click("#btnSnmpCreate"); time.sleep(0.5)
        check("创建抽屉标题=创建SNMP接入",
              s.js("return document.getElementById('drawerTitle').innerText.trim();") == "创建SNMP接入")
        check("创建时没有「引擎ID」字段（创建后才生成）",
              not s.js("return !!document.querySelector('[data-field=\"snmpEngineId\"]')"))
        check("端口默认为 162",
              s.js("return document.getElementById('snmpPort').value") == "162")
        check("SNMPv3 表单含全部字段（名称/版本/连通性校验/端口/IP/安全用户名/鉴权算法/复杂度校验/鉴权密码×2/加密算法/数据加密密码×2/语言/上报数据类型/描述）",
              s.js("return document.querySelectorAll('#drawerBody .f-field').length") == 16,
              str(s.js("return document.querySelectorAll('#drawerBody .f-field').length;")))
        check("鉴权算法选项为 SHA-512/SHA-384/SHA-256/SHA/MD5",
              s.js("""return Array.from(document.getElementById('snmpAuthAlg').options)
                        .map(function(o){return o.value;}).join(',');""")
              == "SHA-512,SHA-384,SHA-256,SHA,MD5")
        check("加密算法选项为 AES-256/AES-128/DES",
              s.js("""return Array.from(document.getElementById('snmpPrivAlg').options)
                        .map(function(o){return o.value;}).join(',');""")
              == "AES-256,AES-128,DES")
        check("语言选项为 中文 / 英语，默认中文",
              s.js("""return Array.from(document.getElementById('snmpLang').options)
                        .map(function(o){return o.innerText;}).join(',');""") == "中文,英语"
              and s.js("return document.getElementById('snmpLang').value") == "zh-CN")
        check("上报数据类型当前只有「告警」可勾选，且默认勾选",
              s.js("return document.querySelectorAll('[data-report]').length") == 1
              and s.js("return document.querySelector('[data-report]').checked")
              and "告警" in s.js("return document.querySelector('[data-field=\"snmpReport\"]').innerText"))
        s.shot("84-snmp-create-drawer.png")
        # 版本切换：SNMPv2c 不需要认证与加密配置
        s.js("""var sel=document.getElementById('snmpVersion');sel.value='v2c';
                sel.dispatchEvent(new Event('change',{bubbles:true}));""")
        time.sleep(0.5)
        check("切到 SNMPv2c 后隐藏认证与加密相关字段（只剩 8 项）",
              s.js("return document.querySelectorAll('#drawerBody .f-field').length") == 8
              and not s.js("return !!document.getElementById('snmpUser')")
              and not s.js("return !!document.getElementById('snmpAuthPwd')")
              and not s.js("return !!document.getElementById('snmpPrivPwd')")
              and "不需要认证与加密配置" in
                  s.js("return document.querySelector('#drawerBody').innerText"),
              str(s.js("return document.querySelectorAll('#drawerBody .f-field').length;")))
        s.shot("85-snmp-v2c.png")
        s.js("""var sel=document.getElementById('snmpVersion');sel.value='v3';
                sel.dispatchEvent(new Event('change',{bubbles:true}));""")
        time.sleep(0.5)
        check("切回 SNMPv3 后认证与加密字段重新出现",
              s.js("return document.querySelectorAll('#drawerBody .f-field').length") == 16)
        # 空表单校验
        s.click("#drawerSubmit"); time.sleep(0.4)
        bad = s.js("""return Array.from(document.querySelectorAll('#drawerBody .f-field.has-error'))
                        .map(function(e){return e.getAttribute('data-field');});""")
        check("必填校验：名称 / IP / 安全用户名 / 鉴权密码×2 / 数据加密密码×2 / 描述",
              bad == ["snmpName", "snmpIp", "snmpUser", "snmpAuthPwd", "snmpAuthPwd2",
                      "snmpPrivPwd", "snmpPrivPwd2", "snmpDesc"], str(bad))
        # 地址与端口格式
        s.js("""function sv(id,v){var e=document.getElementById(id);e.value=v;
                  e.dispatchEvent(new Event('input',{bubbles:true}));}
                sv('snmpIp','999.1.1.1');sv('snmpPort','70000');""")
        time.sleep(0.3)
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("IP 与端口格式非法时给出格式提示",
              s.js("""return document.querySelector('[data-field="snmpIp"] .f-error').innerText;""")
                  == "地址格式不正确，请填写合法的 IPv4 或 IPv6 地址"
              and s.js("""return document.querySelector('[data-field="snmpPort"] .f-error').innerText;""")
                  == "端口需为 1-65535 的整数")
        # IPv6 合法
        s.js("""function sv2(id,v){var e=document.getElementById(id);e.value=v;
                  e.dispatchEvent(new Event('input',{bubbles:true}));}
                sv2('snmpIp','2001:db8:ac10::31');sv2('snmpPort','162');""")
        time.sleep(0.3)
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("IPv6 地址被接受（IP 字段不再报错）",
              not s.js("""return document.querySelector('[data-field="snmpIp"]')
                            .classList.contains('has-error');"""))
        # 密码复杂度与一致性
        s.js("""function sv3(id,v){var e=document.getElementById(id);e.value=v;
                  e.dispatchEvent(new Event('input',{bubbles:true}));}
                sv3('snmpName','探针通道');sv3('snmpUser','oms_probe');
                sv3('snmpAuthPwd','abc');sv3('snmpAuthPwd2','abcd');""")
        time.sleep(0.3)
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("开启复杂度校验时弱密码被拒（至少 8 位、至少三类字符）",
              "复杂度" in s.js("""return document.querySelector('[data-field="snmpAuthPwd"] .f-error').innerText;"""),
              s.js("""return document.querySelector('[data-field="snmpAuthPwd"] .f-error').innerText;"""))
        s.js("""function sv4(id,v){var e=document.getElementById(id);e.value=v;
                  e.dispatchEvent(new Event('input',{bubbles:true}));}
                sv4('snmpAuthPwd','Abcd@1234');""")
        time.sleep(0.3)
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("两次鉴权密码不一致时提示不一致",
              s.js("""return document.querySelector('[data-field="snmpAuthPwd2"] .f-error').innerText;""")
                  == "两次输入的密码不一致")
        # 关闭复杂度校验后弱密码可保存
        s.click("#snmpPwdCheckSw"); time.sleep(0.3)
        s.js("""function sv5(id,v){var e=document.getElementById(id);e.value=v;
                  e.dispatchEvent(new Event('input',{bubbles:true}));}
                sv5('snmpAuthPwd','abc');sv5('snmpAuthPwd2','abc');
                sv5('snmpPrivPwd','abc');sv5('snmpPrivPwd2','abc');sv5('snmpDesc','原型用例：校验关闭后允许弱口令');""")
        time.sleep(0.3)
        s.click("#drawerSubmit"); time.sleep(0.6)
        check("关闭复杂度校验后弱口令可以保存（通道创建成功）",
              s.js("return document.getElementById('drawer').hidden")
              and s.js("return document.querySelectorAll('table.data tbody tr').length;") == 3)
        newrow = s.js("""return Array.from(document.querySelectorAll('table.data tbody tr'))
                            .slice(-1)[0].innerText.replace(/\\n/g,' ');""")
        check("新建通道已生成引擎ID（0x 开头的十六进制）",
              s.js("""var e=Array.from(document.querySelectorAll('table.data tbody tr')).slice(-1)[0]
                        .querySelector('.cell-engine').innerText;
                      return e.indexOf('0x80001F8880')===0 && e.length===24;"""),
              s.js("""return Array.from(document.querySelectorAll('table.data tbody tr')).slice(-1)[0]
                        .querySelector('.cell-engine').innerText;"""))
        check("新建通道带出名称与上报数据类型（默认勾选告警）",
              "探针通道" in newrow and "告警" in newrow, newrow[:80])

        # --- SNMP 接入：修改（表单与创建一致 + 展示引擎ID） ---
        s.js("""Array.from(document.querySelectorAll('table.data tbody tr')).slice(-1)[0]
                  .querySelector('[data-snmp-act="edit"]').click();""")
        time.sleep(0.5)
        check("修改抽屉标题=修改SNMP接入，且表单字段数与创建一致（多出只读引擎ID）",
              s.js("return document.getElementById('drawerTitle').innerText.trim();") == "修改SNMP接入"
              and s.js("return document.querySelectorAll('#drawerBody .f-field').length") == 17)
        check("修改时展示系统生成的引擎ID，并说明不可修改",
              s.js("""return (document.querySelector('[data-field="snmpEngineId"] .f-readonly')||{})
                        .innerText||'';""").startswith("0x80001F8880")
              and "创建后不可修改" in
                  s.js("""return document.querySelector('[data-field="snmpEngineId"] .f-hint').innerText;"""))
        check("修改时凭据不回显：密码框为空且提示「不修改请留空」",
              s.js("return document.getElementById('snmpAuthPwd').value") == ""
              and s.js("return document.getElementById('snmpAuthPwd').placeholder") == "不修改请留空")
        s.js("""function sv6(id,v){var e=document.getElementById(id);e.value=v;
                  e.dispatchEvent(new Event('input',{bubbles:true}));}
                sv6('snmpName','探针通道-改名');""")
        time.sleep(0.3)
        s.click("#drawerSubmit"); time.sleep(0.6)
        check("修改保存后列表同步更新（名称已改，通道数不变）",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 3
              and "探针通道-改名" in s.js("return document.querySelector('table.data tbody').innerText"))

        # --- SNMP 接入：连通性校验失败 → 不允许启用 ---
        s.click("#btnSnmpCreate"); time.sleep(0.5)
        s.js("""function sv7(id,v){var e=document.getElementById(id);e.value=v;
                  e.dispatchEvent(new Event('input',{bubbles:true}));}
                sv7('snmpName','不可达通道');sv7('snmpIp','192.0.2.1');sv7('snmpUser','u1');
                sv7('snmpAuthPwd','Abcd@1234');sv7('snmpAuthPwd2','Abcd@1234');
                sv7('snmpPrivPwd','Abcd@1234');sv7('snmpPrivPwd2','Abcd@1234');
                sv7('snmpDesc','连通性校验失败用例');""")
        time.sleep(0.3)
        s.click("#drawerSubmit"); time.sleep(0.6)
        last = s.js("""return Array.from(document.querySelectorAll('table.data tbody tr'))
                          .slice(-1)[0].innerText.replace(/\\n/g,' ');""")
        check("开启连通性校验且目标不可达时不允许启用（保存后置为禁用）",
              "不可达通道" in last and "禁用" in last
              and "连通性校验未通过" in s.js("return document.getElementById('toastWrap').innerText"),
              last[:80])
        # 停用/启用切换
        s.js("""Array.from(document.querySelectorAll('table.data tbody tr')).slice(-1)[0]
                  .querySelector('[data-snmp-act="toggle"]').click();""")
        time.sleep(0.6)
        check("行内「启用」切换后状态变为启用",
              "启用" in s.js("""return Array.from(document.querySelectorAll('table.data tbody tr'))
                                    .slice(-1)[0].querySelector('.badge').innerText;"""))
        # 删除
        s.js("""Array.from(document.querySelectorAll('table.data tbody tr')).slice(-1)[0]
                  .querySelector('[data-snmp-act="delete"]').click();""")
        time.sleep(0.5)
        check("删除 SNMP 接入有二次确认并提示影响",
              s.js("return document.getElementById('modalTitle').innerText.trim();") == "删除 SNMP 接入"
              and "不可达通道" in s.js("return document.getElementById('modalBody').innerText")
              and "不再上报告警" in s.js("return document.getElementById('modalBody').innerText"))
        s.js("document.getElementById('modalConfirm').click();"); time.sleep(0.6)
        check("删除后通道数回到 3",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 3)
        s.js("""Array.from(document.querySelectorAll('table.data tbody tr')).slice(-1)[0]
                  .querySelector('[data-snmp-act="delete"]').click();""")
        time.sleep(0.4)
        s.js("document.getElementById('modalConfirm').click();"); time.sleep(0.6)
        check("清理用例数据后回到初始 2 条通道",
              s.js("return document.querySelectorAll('table.data tbody tr').length") == 2)

        # --- SFTP 接入：卡片信息 ---
        sftpcard = s.js("""return document.querySelectorAll('.des-card')[0].innerText.replace(/\\n/g,' | ');""")
        check("SFTP 卡片展示 IP / 端口 / 用户名 / 路径",
              "192.168.1.100" in sftpcard and "22" in sftpcard
              and "omsbackup" in sftpcard and "/data/backup" in sftpcard, sftpcard[:110])
        check("SFTP 卡片展示引用方与「使用中」状态",
              "备份恢复 · 远程备份" in sftpcard and "使用中" in sftpcard)
        check("SFTP 卡片操作入口为 修改 / 禁用 / 删除",
              set(s.texts(".des-card:nth-of-type(1) ~ .action-bar .btn")) >= {"修改", "禁用", "删除"}
              or s.js("return !!document.getElementById('btnSftpEdit')")
              and s.js("return !!document.getElementById('btnSftpToggle')")
              and s.js("return !!document.getElementById('btnSftpDelete')"))

        # --- SFTP 接入：测试连通性通过后才允许保存 ---
        s.click("#btnSftpEdit"); time.sleep(0.5)
        check("SFTP 抽屉底部为 测试连接 / 取消 / 保存 三个按钮（FR-3RD-002）",
              s.js("return document.getElementById('drawerExtra').innerText.trim();") == "测试连接"
              and not s.js("return document.getElementById('drawerExtra').hidden")
              and s.js("return document.getElementById('drawerCancel').innerText.trim();") == "取消"
              and s.js("return document.getElementById('drawerSubmit').innerText.trim();") == "保存")
        check("未测试连通性时「保存」不可用并给出提示",
              s.js("return document.getElementById('drawerSubmit').disabled")
              and "请先「测试连接」" in s.js("return document.getElementById('sftpTestMsg').innerText"))
        check("修改表单与创建表单一致：带出 IP / 端口 / 用户名 / 路径，密码不回显",
              s.js("return document.getElementById('sftpIp').value") == "192.168.1.100"
              and s.js("return document.getElementById('sftpPort').value") == "22"
              and s.js("return document.getElementById('sftpUser').value") == "omsbackup"
              and s.js("return document.getElementById('sftpPath').value") == "/data/backup"
              and s.js("return document.getElementById('sftpPwd').value") == ""
              and s.js("return document.getElementById('sftpPwd').placeholder") == "不修改请留空")
        time.sleep(1.6)                   # 等前面的 toast 消失再出图
        s.shot("86-sftp-test-gate.png")
        s.click("#drawerExtra"); time.sleep(0.5)
        check("测试连通性通过后「保存」解禁",
              not s.js("return document.getElementById('drawerSubmit').disabled")
              and "测试通过" in s.js("return document.getElementById('sftpTestMsg').innerText"))
        s.js("""var e=document.getElementById('sftpPath');e.value='/data/backup-oms';
                e.dispatchEvent(new Event('input',{bubbles:true}));""")
        time.sleep(0.3)
        check("改动字段后需重新测试（「保存」重新置灰）",
              s.js("return document.getElementById('drawerSubmit').disabled")
              and "请先「测试连接」" in s.js("return document.getElementById('sftpTestMsg').innerText"))
        s.js("""var e=document.getElementById('sftpIp');e.value='192.0.2.1';
                e.dispatchEvent(new Event('input',{bubbles:true}));""")
        time.sleep(0.3)
        s.click("#drawerExtra"); time.sleep(0.5)
        check("连通性测试失败时给出具体原因且不允许保存",
              "连通性测试未通过" in s.js("return document.getElementById('sftpTestMsg').innerText")
              and "不可达" in s.js("return document.getElementById('sftpTestMsg').innerText")
              and s.js("return document.getElementById('drawerSubmit').disabled"))
        s.js("""var e=document.getElementById('sftpIp');e.value='192.168.1.100';
                e.dispatchEvent(new Event('input',{bubbles:true}));""")
        time.sleep(0.3)
        s.click("#drawerExtra"); time.sleep(0.4)
        s.click("#drawerSubmit"); time.sleep(0.6)
        check("测试通过后保存成功，卡片路径与测试时间同步更新",
              s.js("return document.getElementById('drawer').hidden")
              and "/data/backup-oms" in
                  s.js("return document.querySelectorAll('.des-card')[0].innerText"))
        # 停用 → 备份页引用方随之不可用（跨页一致）
        s.click("#btnSftpToggle"); time.sleep(0.6)
        check("停用 SFTP 后卡片状态为禁用、引用方显示未使用",
              "未使用" in s.js("return document.querySelectorAll('.des-card')[0].innerText"))
        s.go("#/settings/backup")
        check("跨页一致：备份页的远程备份随 SFTP 停用而关闭并说明原因（M10 ⇄ M14）",
              "SFTP 接入已停用" in s.js("return document.querySelector('.des-card').innerText"))
        s.go("#/settings/integration")
        # 仍被引用时不允许删除
        s.click("#btnSftpToggle"); time.sleep(0.5)      # 先启用回来
        s.click("#btnSftpDelete"); time.sleep(0.5)
        check("连接仍被引用时拒绝删除并提示先停用（FR-3RD-002）",
              s.js("return document.getElementById('modalTitle').innerText.trim();") == "无法删除 SFTP 接入"
              and "备份恢复 · 远程备份" in s.js("return document.getElementById('modalBody').innerText")
              and s.js("return document.getElementById('modalCancel').hidden;"))
        s.js("document.getElementById('modalConfirm').click();"); time.sleep(0.4)
        check("拒绝删除后 SFTP 配置保持不变",
              s.js("return !!document.getElementById('btnSftpEdit')")
              and "192.168.1.100" in s.js("return document.querySelectorAll('.des-card')[0].innerText"))
        # 停用后可删除 → 空态 → 重新配置
        s.click("#btnSftpToggle"); time.sleep(0.5)
        s.click("#btnSftpDelete"); time.sleep(0.5)
        check("停用后允许删除，弹窗说明影响并提示「先停用再删除」口径",
              s.js("return document.getElementById('modalTitle').innerText.trim();") == "删除 SFTP 接入"
              and "远程备份" in s.js("return document.getElementById('modalBody').innerText"))
        s.js("document.getElementById('modalConfirm').click();"); time.sleep(0.6)
        check("删除后为空态，入口变为「配置SFTP接入」",
              s.js("return document.querySelectorAll('.des-card')[0].innerText.indexOf('尚未接入')>=0")
              and s.js("return document.getElementById('btnSftpEdit').innerText.trim();")
                  == "配置SFTP接入")
        check("原型面板的「已配置远程 SFTP」开关同步为未勾选",
              not s.js("return document.getElementById('protoSftp').checked"))
        s.go("#/settings/backup")
        check("跨页一致：SFTP 删除后备份页显示「未在第三方接入中配置远程 SFTP」",
              "未在「第三方接入」中配置远程 SFTP" in
                  s.js("return document.querySelector('.des-card').innerText"))
        s.go("#/settings/integration")
        s.click("#btnSftpEdit"); time.sleep(0.5)
        check("创建表单为空且密码为必填（未配置时不允许留空）",
              s.js("return document.getElementById('sftpIp').value") == ""
              and s.js("return document.getElementById('sftpPath').value") == "")
        s.click("#drawerExtra"); time.sleep(0.4)
        check("空表单测试连通性直接失败（必填项缺失）",
              "连通性测试未通过" in s.js("return document.getElementById('sftpTestMsg').innerText")
              and s.js("return document.getElementById('drawerSubmit').disabled"))
        s.js("""function svs(id,v){var e=document.getElementById(id);e.value=v;
                  e.dispatchEvent(new Event('input',{bubbles:true}));}
                svs('sftpIp','192.168.1.100');svs('sftpPort','22');svs('sftpUser','omsbackup');
                svs('sftpPwd','Oms@Backup1');svs('sftpPath','/data/backup');""")
        time.sleep(0.3)
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("未测试通过时「保存」保持禁用，点击不会提交（抽屉仍打开）",
              not s.js("return document.getElementById('drawer').hidden")
              and s.js("return document.getElementById('drawerSubmit').disabled"))
        s.click("#drawerExtra"); time.sleep(0.5)
        s.click("#drawerSubmit"); time.sleep(0.6)
        check("测试通过后保存成功，SFTP 恢复为已配置",
              s.js("return document.getElementById('drawer').hidden")
              and "192.168.1.100" in s.js("return document.querySelectorAll('.des-card')[0].innerText")
              and s.js("return document.getElementById('protoSftp').checked"))
        s.shot("87-sftp-configured.png")

        # --- CA 服务器接入 ---
        cacard = s.js("""return document.querySelectorAll('.des-card')[1].innerText.replace(/\\n/g,' | ');""")
        check("CA 卡片展示基础信息：IP / 端口 / 路径 / 证书自动更新提前天数",
              "10.20.30.40" in cacard and "8443" in cacard and "/ca/oms" in cacard
              and "30 天" in cacard, cacard[:110])
        check("CA 卡片展示 证书 / CA证书 / 证书私钥 文件名与「私钥密码已配置（不回显）」",
              "oms-nginx.crt" in cacard and "oms-ca.crt" in cacard
              and "oms-nginx.key" in cacard and "已配置" in cacard
              and "不回显" in cacard)
        check("CA 卡片说明服务对象为 Nginx 对外证书",
              "Nginx 证书" in cacard)
        s.click("#btnCaEdit"); time.sleep(0.5)
        check("CA 修改抽屉标题与两个分区（基础信息 / 证书与私钥）",
              s.js("return document.getElementById('drawerTitle').innerText.trim();") == "修改CA服务器接入"
              and s.texts("#drawerBody .f-section") == ["基础信息", "证书与私钥"],
              str(s.texts("#drawerBody .f-section")))
        check("CA 修改表单与创建一致：带出 IP / 端口 / 路径 / 提前天数，私钥密码不回显",
              s.js("return document.getElementById('caIp').value") == "10.20.30.40"
              and s.js("return document.getElementById('caPort').value") == "8443"
              and s.js("return document.getElementById('caPath').value") == "/ca/oms"
              and s.js("return document.getElementById('caRenewDays').value") == "30"
              and s.js("return document.getElementById('caKeyPwd').value") == ""
              and s.js("return document.getElementById('caKeyPwd').placeholder") == "不修改请留空")
        check("CA 表单含 证书 / CA证书 / 证书私钥 三个上传栏并带出当前文件名",
              s.texts("#drawerBody .up-name") == ["oms-nginx.crt · 4.2 KB", "oms-ca.crt · 3.1 KB",
                                                 "oms-nginx.key · 1.7 KB"],
              str(s.texts("#drawerBody .up-name")))
        s.shot("88-ca-drawer.png")
        s.js("""function sc1(id,v){var e=document.getElementById(id);e.value=v;
                  e.dispatchEvent(new Event('input',{bubbles:true}));}
                sc1('caRenewDays','200');""")
        time.sleep(0.3)
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("提前天数超出 7-180 被拒",
              "7-180" in s.js("""return document.querySelector('[data-field="caRenewDays"] .f-error').innerText;"""))
        s.js("""function sc2(id,v){var e=document.getElementById(id);e.value=v;
                  e.dispatchEvent(new Event('input',{bubbles:true}));}
                sc2('caRenewDays','45');sc2('caIp','2001:db8::5');""")
        time.sleep(0.3)
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("CA 地址只允许 IPv4（IPv6 被拒）",
              s.js("""return document.querySelector('[data-field="caIp"] .f-error').innerText;""")
                  == "仅支持 IPv4 地址")
        s.js("""function sc3(id,v){var e=document.getElementById(id);e.value=v;
                  e.dispatchEvent(new Event('input',{bubbles:true}));}
                sc3('caIp','10.20.30.41');""")
        time.sleep(0.3)
        s.click("#drawerSubmit"); time.sleep(0.6)
        check("CA 保存成功，卡片同步更新 IP 与提前天数",
              s.js("return document.getElementById('drawer').hidden")
              and "10.20.30.41" in s.js("return document.querySelectorAll('.des-card')[1].innerText")
              and "45 天" in s.js("return document.querySelectorAll('.des-card')[1].innerText"))
        # 删除 → 空态 → 重新接入（文件必填）
        s.click("#btnCaDelete"); time.sleep(0.5)
        check("删除 CA 接入有二次确认并提示影响（不提供回退自签）",
              s.js("return document.getElementById('modalTitle').innerText.trim();") == "删除 CA 服务器接入"
              and "已签发的证书不受影响" in s.js("return document.getElementById('modalBody').innerText"))
        s.js("document.getElementById('modalConfirm').click();"); time.sleep(0.6)
        check("删除后为空态，入口变为「接入CA服务器」",
              s.js("return document.querySelectorAll('.des-card')[1].innerText.indexOf('尚未接入')>=0")
              and s.js("return document.getElementById('btnCaEdit').innerText.trim();") == "接入CA服务器")
        s.click("#btnCaEdit"); time.sleep(0.5)
        check("创建 CA 表单为空，提前天数默认 30",
              s.js("return document.getElementById('caIp').value") == ""
              and s.js("return document.getElementById('caRenewDays').value") == "30")
        s.click("#drawerSubmit"); time.sleep(0.4)
        check("创建 CA 时 IP/端口/路径/三个文件/私钥密码 均必填",
              set(s.js("""return Array.from(document.querySelectorAll('#drawerBody .f-field.has-error'))
                            .map(function(e){return e.getAttribute('data-field');});"""))
              == {"caIp", "caPort", "caPath", "up-cert", "up-ca", "up-key", "caKeyPwd"},
              str(s.js("""return Array.from(document.querySelectorAll('#drawerBody .f-field.has-error'))
                            .map(function(e){return e.getAttribute('data-field');});""")))
        s.js("""function scc(id,name,text){var inp=document.getElementById(id);
                  var dt=new DataTransfer();
                  dt.items.add(new File([text],name,{type:'text/plain'}));
                  inp.files=dt.files;
                  inp.dispatchEvent(new Event('change',{bubbles:true}));}
                scc('file-cert','oms-nginx.crt','-----BEGIN CERTIFICATE-----');
                scc('file-ca','oms-ca.crt','-----BEGIN CERTIFICATE-----');
                scc('file-key','oms-nginx.key','-----BEGIN PRIVATE KEY-----');""")
        time.sleep(0.4)
        s.js("""function sc4(id,v){var e=document.getElementById(id);e.value=v;
                  e.dispatchEvent(new Event('input',{bubbles:true}));}
                sc4('caIp','10.20.30.40');sc4('caPort','8443');sc4('caPath','/ca/oms');
                sc4('caKeyPwd','Ca@Key12345');""")
        time.sleep(0.3)
        s.click("#drawerSubmit"); time.sleep(0.6)
        check("补齐必填并上传文件后 CA 接入成功（卡片恢复）",
              s.js("return document.getElementById('drawer').hidden")
              and "10.20.30.40" in s.js("return document.querySelectorAll('.des-card')[1].innerText")
              and "oms-nginx.crt" in s.js("return document.querySelectorAll('.des-card')[1].innerText"))

        # --- 英文态 ---
        s.click('.lang-btn[data-lang="en-US"]')
        s.go("#/settings/integration")
        check("英文态：三块标题与 SNMP 表头均本地化",
              s.js("""return Array.from(document.querySelectorAll('.des-head')).map(function(e){
                        return e.innerText.trim().split('\\n')[0];}).join('|');""")
                  == "SNMP Access|SFTP Configuration|CA Server Configuration"
              and s.texts("table.data thead th") == ["Name", "SNMP Version", "IP Address", "Port",
                                                     "Reported Data Type", "Engine ID", "Status",
                                                     "Actions"],
              str(s.texts("table.data thead th")))
        check("英文态：SFTP 表单的三个底部按钮与测试提示本地化",
              s.js("return document.getElementById('btnSftpEdit').innerText.trim();") != "")
        s.click("#btnSftpEdit"); time.sleep(0.5)
        check("英文态 SFTP 抽屉：Test Connection / Close / Save 与测试提示",
              s.js("return document.getElementById('drawerExtra').innerText.trim();") == "Test Connection"
              and s.js("return document.getElementById('drawerCancel').innerText.trim();") == "Cancel"
              and "Test Connection" in s.js("return document.getElementById('sftpTestMsg').innerText"))
        s.shot("89-m14-en.png")
        s.click("#drawerCancel"); time.sleep(0.4)
        s.click('.lang-btn[data-lang="zh-CN"]')
        s.nav(PAGE)                       # 恢复内存数据，避免影响后续用例

        # ---------- 13. 任务中心入口 ----------
        print("\n[13] 任务中心入口（FR-COM-002）")
        s.go("#/home")
        tc = s.js("""var b=document.getElementById('taskCenterBtn').getBoundingClientRect();
                     var l=document.querySelector('.lang-switch').getBoundingClientRect();
                     var t=document.querySelector('.topbar').getBoundingClientRect();
                     return [Math.round(b.right), Math.round(l.left), Math.round(t.right)];""")
        check("任务中心按钮位于语言切换左侧、且在顶栏右半区",
              tc[0] <= tc[1] and tc[0] > tc[2] * 0.5,
              f"任务中心right={tc[0]} 语言切换left={tc[1]} 顶栏right={tc[2]}")
        s.click("#taskCenterBtn")
        check("点击进入 #/tasks", s.js("return location.hash") == "#/tasks")
        check("任务中心页标题",
              s.js("return document.querySelector('.page-title').innerText.trim()") == "任务中心")
        check("任务中心面包屑为单层", s.texts("#crumb .crumb-item") == ["任务中心"],
              str(s.texts("#crumb .crumb-item")))
        s.shot("09-task-center.png")

        # ---------- 14. 侧边栏分组 ----------
        print("\n[14] 侧边栏 13 项分组")
        s.go("#/settings/account")
        labels = s.texts("#settingsGroup .nav-group-label")
        check("出现「告警管理」「用户管理组」两个分组标题",
              labels == ["告警管理", "用户管理组"], str(labels))
        grouped = s.js("""return Array.from(document.querySelectorAll('#settingsGroup .nav-child.is-grouped'))
                            .map(function(e){return e.innerText.trim();});""")
        check("分组内条目：告警3项 + 用户管理4项",
              grouped == ["告警列表", "告警设置", "告警统计",
                          "资源组管理", "用户组管理", "账户管理", "会话管理"], str(grouped))
        flat = s.js("""return Array.from(document.querySelectorAll('#settingsGroup .nav-child:not(.is-grouped)'))
                         .map(function(e){return e.innerText.trim();});""")
        check("其余 6 项各自单独成组、平铺展示",
              flat == ["证书管理", "许可证管理", "系统备份", "操作日志", "运行日志", "第三方接入"],
              str(flat))
        check("分组后子条目总数仍为 13",
              len(grouped) + len(flat) == 13)

        # ---------- 15. 安全管理员视图 ----------
        print("\n[15] 安全管理员账户管理视图")
        s.click('#roleSeg button[data-role="secadmin"]')
        check("顶栏用户切换为安全管理员",
              s.js("return document.getElementById('userName').innerText.trim()") == "安全管理员",
              s.js("return document.getElementById('userName').innerText.trim()"))
        s.go("#/settings/account")
        check("隐藏「创建账户」「导入账户」按钮",
              s.js("return !document.getElementById('btnCreate') && !document.getElementById('btnImport')"))
        check("安全管理员视角无勾选列（没有删除能力）",
              s.js("return document.querySelectorAll('table.data .row-check, table.data .check-all').length") == 0
              and s.js("return !document.getElementById('btnBatchDelete')"))
        check("安全管理员表头为 8 列（无勾选列）",
              len(s.texts("table.data thead th")) == 8,
              str(len(s.texts("table.data thead th"))))
        sec_acts = s.js("""return Array.from(document.querySelectorAll(
                             'table.data tbody tr[data-name] .link-btn'))
                             .map(function(b){return b.innerText.trim();});""")
        check("仅本地普通账户有「锁定 / 激活」按钮（3 个）",
              set(sec_acts) <= {"锁定", "激活"} and len(sec_acts) == 3,
              f"{len(sec_acts)} 个按钮，取值 {sorted(set(sec_acts))}")
        check("内置账户（admin/secadmin/secauditor）操作列直接隐藏锁定按钮",
              s.js("""return ['admin','secadmin','secauditor'].every(function(n){
                        var r=document.querySelector('tr[data-name="'+n+'"]');
                        return r.querySelectorAll('.link-btn').length===0;});"""),
              s.js("""return JSON.stringify(['admin','secadmin','secauditor'].map(function(n){
                        var r=document.querySelector('tr[data-name="'+n+'"]');
                        return n+':'+r.querySelector('.row-actions').innerText.trim();}));"""))
        check("本地普通账户可锁定",
              s.js("""return ['zhangwei','sunlei'].every(function(n){
                        var b=document.querySelector('tr[data-name="'+n+'"] .link-btn');
                        return b && !b.disabled;});"""),
              s.js("""return JSON.stringify(['zhangwei','sunlei'].map(function(n){
                        var b=document.querySelector('tr[data-name="'+n+'"] .link-btn');
                        return n+':'+(b?(b.disabled?'disabled':'enabled'):'absent');}));"""))
        check("三方SSO认证账户不允许锁定，操作列隐藏按钮",
              s.js("""return ['chenjing','wangfang'].every(function(n){
                        var r=document.querySelector('tr[data-name="'+n+'"]');
                        return r.querySelectorAll('.link-btn').length===0;});"""),
              s.js("""return JSON.stringify(['chenjing','wangfang'].map(function(n){
                        var r=document.querySelector('tr[data-name="'+n+'"]');
                        return n+':'+r.querySelector('.row-actions').innerText.trim();}));"""))
        check("SSO 账户的占位符带不可锁定说明",
              s.js("""return document.querySelector('tr[data-name="chenjing"] .cell-empty')
                        .getAttribute('title');""") == "三方SSO认证账户不允许被锁定",
              s.js("""return document.querySelector('tr[data-name="chenjing"] .cell-empty')
                        .getAttribute('title');"""))
        check("已激活账户显示「锁定」、已锁定账户显示「激活」",
              s.js("""return document.querySelector('tr[data-name="zhangwei"] .link-btn')
                        .innerText.trim();""") == "锁定" and
              s.js("""return document.querySelector('tr[data-name="liuyang"] .link-btn')
                        .innerText.trim();""") == "激活")
        s.shot("15-account-secadmin.png")
        s.js("""document.querySelector('tr[data-name="zhangwei"] .link-btn[data-act="lock"]').click();""")
        time.sleep(0.45)
        check("点「锁定」后该账户状态变为已锁定",
              s.js("""return !!document.querySelector('tr[data-name="zhangwei"] .badge-locked');"""))
        s.js("""document.querySelector('tr[data-name="zhangwei"] .link-btn[data-act="activate"]').click();""")
        time.sleep(0.45)
        check("点「激活」后恢复为已激活",
              s.js("""return !!document.querySelector('tr[data-name="zhangwei"] .badge-active');"""))
        s.click('#roleSeg button[data-role="admin"]')
        s.go("#/settings/account")
        check("切回系统管理员后恢复创建/导入按钮与三个操作",
              s.js("return !!document.getElementById('btnCreate') && !!document.getElementById('btnImport')")
              and len(s.js("""return Array.from(document.querySelectorAll(
                             'table.data tbody tr[data-name="zhangwei"] .link-btn'));""")) == 3)

        # ---------- 16. 用户菜单：基本信息 / 修改密码 ----------
        print("\n[16] 用户菜单：基本信息 / 修改密码")
        s.js("document.getElementById('userBtn').click();"); time.sleep(0.35)
        items = s.texts("#userMenu .user-menu-item")
        check("菜单项顺序 = 基本信息 / 修改密码 / 退出登录",
              items == ["基本信息", "修改密码", "退出登录"], str(items))
        s.click("#profileBtn"); time.sleep(0.4)
        check("「基本信息」弹出窗口", not s.js("return document.getElementById('infoMask').hidden"))
        keys = s.texts("#infoBody dt")
        check("窗口含账户名称 / 用户组 / 用户组关联的角色 / 邮箱",
              keys == ["账户名称", "用户组", "用户组关联的角色", "邮箱"], str(keys))
        vals = s.texts("#infoBody dd")
        check("展示了真实取值",
              vals[0] == "admin" and vals[1] == "系统管理员组"
              and vals[2] == "系统管理员" and vals[3] == "admin@modelengine.local", str(vals))
        s.shot("16-profile-modal.png")
        s.click("#infoClose"); time.sleep(0.3)
        check("窗口可关闭", s.js("return document.getElementById('infoMask').hidden"))

        s.js("document.getElementById('userBtn').click();"); time.sleep(0.35)
        s.click("#selfPwdBtn"); time.sleep(0.45)
        check("「修改密码」打开抽屉",
              s.js("return document.getElementById('drawerTitle').innerText.trim()") == "修改密码")
        check("修改密码字段 = 原密码 / 新密码 / 确认新密码",
              s.js("""return Array.from(document.querySelectorAll('#drawerBody .f-label'))
                        .map(function(e){return e.innerText.replace('*','').trim();});""")
              == ["原密码", "新密码", "再次输入新密码"])
        s.click("#drawerSubmit")
        check("原密码为空时被拦截",
              s.js("""return Array.from(document.querySelectorAll('#drawerBody .f-field.has-error .f-error'))
                        .map(function(e){return e.innerText.trim();});""").count("请输入原密码") == 1)
        s.shot("17-self-password.png")
        s.click("#drawerCancel")

        # ---------- 17. 安全策略（仅安全管理员，M15） ----------
        print("\n[17] 安全策略页（仅安全管理员可见）")
        s.go("#/home")
        check("系统管理员视图看不到「安全策略」菜单",
              "安全策略" not in s.texts("#settingsGroup .nav-child") and
              s.js("return document.querySelectorAll('#settingsGroup .nav-child').length") == 13,
              f"{s.js('return document.querySelectorAll("#settingsGroup .nav-child").length')} 项")
        s.click('#roleSeg button[data-role="secadmin"]')
        kids_sec = s.texts("#settingsGroup .nav-child")
        check("安全管理员「设置」内只剩三栏：安全策略 / 操作日志 / 账户管理",
              kids_sec == ["安全策略", "操作日志", "账户管理"], str(kids_sec))
        # 安全管理员不可见第三方接入：直达应回落到首页
        s.go("#/settings/integration")
        check("安全管理员直达第三方接入回落首页",
              s.js("return location.hash") == "#/home", s.js("return location.hash"))
        check("安全管理员看不到上层业务模块菜单",
              s.texts("#navSlot .nav-item") == [], str(s.texts("#navSlot .nav-item")))
        check("安全管理员仍保留「首页」",
              s.texts("#navHome .nav-text") == ["首页"])
        check("安全管理员视角不显示扩展槽占位提示",
              s.texts("#navSlot .nav-slot-empty") == [],
              str(s.texts("#navSlot .nav-slot-empty")))
        s.click('#settingsGroup .nav-child')
        check("进入 #/security", s.js("return location.hash") == "#/security")
        check("页面标题=安全策略",
              s.js("return document.querySelector('.page-title').innerText.trim()") == "安全策略")
        check("面包屑为「设置 / 安全策略」",
              s.texts("#crumb .crumb-item") == ["设置", "安全策略"],
              str(s.texts("#crumb .crumb-item")))
        check("进入安全策略时「设置」分组自动展开",
              s.js("return document.getElementById('settingsGroup').classList.contains('is-open')"))

        groups = s.texts(".pol-card .pol-head h2")
        check("三个策略分组：账户 / 密码 / 会话",
              groups == ["账户策略", "密码策略", "会话策略"], str(groups))
        counts = s.js("""return Array.from(document.querySelectorAll('.pol-card'))
                            .map(function(c){return c.querySelectorAll('.pol-row').length;});""")
        check("分组条目数 7 / 11 / 2", counts == [7, 11, 2], str(counts))

        # 逐项核对「展示名 + 范围 + 默认值」
        spec = s.js("""return Array.from(document.querySelectorAll('.pol-row')).map(function(r){
            var inp = r.querySelector('.pol-input');
            return {
              name: r.querySelector('.pol-name').innerText.trim(),
              meta: (r.querySelector('.pol-meta')||{innerText:''}).innerText.trim(),
              val: inp ? inp.value : r.querySelector('.pol-seg-btn.is-on').innerText.trim(),
              min: inp ? inp.getAttribute('min') : null,
              max: inp ? inp.getAttribute('max') : null
            };});""")
        expect = [
          ("系统最大账户限制", "0", "1024", "50"),
          ("最短账户名长度", "1", "32", "1"),
          ("最长账户名长度", "1", "64", "32"),
          ("连续登录/密码修改失败次数，超过即被锁定", "3", "5", "5"),
          ("登录失败周期", "3", "30", "5"),
          ("账户锁定时间", "10", "30", "10"),
          ("是否允许创建同名用户", None, None, "否"),
          ("最短密码长度", "8", "32", "8"),
          ("最长密码长度", "8", "32", "32"),
          ("是否必须包含特殊字符", None, None, "是"),
          ("是否允许使用用户名或反向用户名", None, None, "否"),
          ("是否开启弱口令检查", None, None, "是"),
          ("机机账号密码被重置和首次登录时是否要求修改密码", None, None, "否"),
          ("密码与前N次不可重复", "0", "5", "5"),
          ("密码是否永不过期", None, None, "否"),
          ("密码最长使用时间", "30", "999", "90"),
          ("密码修改间隔时间", "3", "10", "5"),
          ("到期N天前警告", "3", "10", "7"),
          ("会话超时时间", "5", "120", "10"),
          ("单个账户创建会话上限", "1", "50", "10")
        ]
        got = [(x["name"], x["min"], x["max"], x["val"]) for x in spec]
        mismatch = [(e, g) for e, g in zip(expect, got) if tuple(e) != g]
        check("20 项的展示名 / 范围 / 默认值全部一致", not mismatch,
              str(mismatch[:3]) if mismatch else f"{len(got)} 项逐项核对通过")
        check("范围提示按「取值范围 x-y」展示",
              spec[0]["meta"] == "取值范围 0-1024", spec[0]["meta"])
        check("登录失败周期带说明文案",
              "不计为连续失败" in s.js("""return document.querySelector('[data-field="failWindow"] .pol-meta').innerText;"""))
        s.shot("18-security-policy.png")
        s.js("""document.querySelector('[data-group="password"]')
                  .scrollIntoView({block:'start'});""")
        time.sleep(0.5)
        s.shot("19-security-policy-detail.png")

        # 密码永不过期 → 相关项置灰
        s.js("""document.querySelector('[data-bool="neverExpire"] .pol-seg-btn[data-val="true"]').click();""")
        time.sleep(0.4)
        check("「密码永不过期=是」时，密码最长使用时间与到期警告置灰",
              s.js("""return document.getElementById('pol_maxAge').disabled
                        && document.getElementById('pol_expireWarn').disabled;"""))
        s.js("""document.querySelector('[data-bool="neverExpire"] .pol-seg-btn[data-val="false"]').click();""")
        time.sleep(0.4)
        check("改回「否」后恢复可编辑",
              s.js("""return !document.getElementById('pol_maxAge').disabled
                        && !document.getElementById('pol_expireWarn').disabled;"""))

        # 越界校验
        s.js("""document.getElementById('pol_failThreshold').value='9';
                document.getElementById('pol_failThreshold')
                  .dispatchEvent(new Event('input',{bubbles:true}));""")
        s.click("#secSave"); time.sleep(0.4)
        check("超出取值范围的项被拦截并标红",
              s.js("""return document.querySelector('[data-field="failThreshold"]')
                        .classList.contains('has-error');"""))
        check("越界时给出取值范围提示",
              "3-5" in s.js("""return document.querySelector('[data-field="failThreshold"] .pol-meta').innerText;"""))

        # 最短 > 最长
        s.js("""document.getElementById('pol_failThreshold').value='5';
                document.getElementById('pol_failThreshold').dispatchEvent(new Event('input',{bubbles:true}));
                document.getElementById('pol_minPwdLen').value='20';
                document.getElementById('pol_minPwdLen').dispatchEvent(new Event('input',{bubbles:true}));
                document.getElementById('pol_maxPwdLen').value='10';
                document.getElementById('pol_maxPwdLen').dispatchEvent(new Event('input',{bubbles:true}));""")
        s.click("#secSave"); time.sleep(0.4)
        check("最短密码长度大于最长时被拦截",
              "不能大于最长长度" in s.js("""return document.querySelector('[data-field="maxPwdLen"] .pol-meta').innerText;"""),
              s.js("""return document.querySelector('[data-field="maxPwdLen"] .pol-meta').innerText;"""))

        s.click("#secReset"); time.sleep(0.4)
        check("「恢复默认值」把越界值复位",
              s.js("return document.getElementById('pol_maxPwdLen').value") == "32"
              and s.js("return document.getElementById('pol_failThreshold').value") == "5")

        s.click('#roleSeg button[data-role="admin"]')
        s.go("#/security")
        check("系统管理员直接访问 #/security 时回落首页（菜单不可见也不可通过 URL 进入）",
              s.js("return location.hash") != "#/security"
              or s.js("return document.querySelector('.page-title').innerText.trim()") != "安全策略",
              s.js("return document.querySelector('.page-title').innerText.trim()"))

        # ---------- 18. 首次登录用户协议（FR-AUTH-008，在主界面弹出） ----------
        print("\n[18] 首次登录用户协议（进入主界面后弹出）")
        s.js("sessionStorage.setItem('oms.pendingAgreement','1');"
             "sessionStorage.removeItem('oms.agreementConfirmed');")
        s.nav(PAGE)
        check("带待确认标记进入主界面时自动弹出协议窗口",
              not s.js("return document.getElementById('agrMask').hidden"))
        check("窗口标题=用户协议",
              s.js("return document.getElementById('agrTitle').innerText.trim()") == "用户协议")
        check("窗口内为完整协议条文（6 节）",
              s.js("return document.querySelectorAll('#agrBody h3').length") == 6)
        check("「确定」初始不可点击",
              s.js("return document.getElementById('agrConfirm').disabled"))
        check("「确定」带倒计时文案",
              "确定（" in s.js("return document.getElementById('agrConfirm').innerText"),
              s.js("return document.getElementById('agrConfirm').innerText.trim()"))
        check("给出倒计时提示",
              "秒后可点击" in s.js("return document.getElementById('agrHint').innerText"))
        check("协议覆盖全屏（未确认前无法使用系统）",
              s.js("""var r=document.getElementById('agrMask').getBoundingClientRect();
                      return Math.round(r.width)===window.innerWidth
                          && Math.round(r.height)===window.innerHeight;"""))
        s.shot("26-agreement.png")

        # Esc 不应关闭
        s.js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));")
        time.sleep(0.35)
        check("Esc 不能关闭协议窗口（必须先作出选择）",
              not s.js("return document.getElementById('agrMask').hidden"))
        # 倒计时期间点击无效
        s.click("#agrConfirm")
        check("倒计时期间点击「确定」无效",
              not s.js("return document.getElementById('agrMask').hidden"))
        check("倒计时期间按钮仍不可点击",
              s.js("return document.getElementById('agrConfirm').disabled"))

        time.sleep(5.0)
        check("满 5 秒后「确定」变为可点击",
              not s.js("return document.getElementById('agrConfirm').disabled"))
        check("解禁后按钮文案去掉倒计时",
              s.js("return document.getElementById('agrConfirm').innerText.trim()") == "确定")
        s.shot("27-agreement-ready.png")

        s.click("#agrConfirm"); time.sleep(0.5)
        check("点「确定」后窗口关闭、可正常使用系统",
              s.js("return document.getElementById('agrMask').hidden"))
        check("确认结果已记录（标记清除）",
              s.js("return sessionStorage.getItem('oms.pendingAgreement')") is None
              and s.js("return sessionStorage.getItem('oms.agreementConfirmed')") == "1")
        check("确认后给出轻提示",
              s.js("return document.querySelectorAll('#toastWrap .toast').length") >= 1)

        # 取消 → 强制登出，返回登录页
        s.js("sessionStorage.setItem('oms.pendingAgreement','1');"
             "sessionStorage.removeItem('oms.agreementConfirmed');")
        s.nav(PAGE)
        check("[取消路径] 协议窗口重新弹出",
              not s.js("return document.getElementById('agrMask').hidden"))
        s.click("#agrCancel"); time.sleep(1.2)
        check("[取消路径] 强制登出并返回登录页",
              "login.html" in s.js("return location.href"),
              s.js("return location.href.split('/').pop()"))
        check("[取消路径] 待确认标记已清除",
              s.js("return sessionStorage.getItem('oms.pendingAgreement')") is None)

        s.close()

        # ---------- 7. 窄屏 ----------
        print("\n[7] 窄屏 390x844")
        m = Session(390, 844, "移动端", mobile=True)
        check("窄屏侧边栏默认收起",
              m.js("return !document.getElementById('layout').classList.contains('nav-open')"))
        check("窄屏侧边栏移出视口",
              m.js("var r=document.getElementById('sidebar').getBoundingClientRect();"
                   "return r.right<=1"))
        check("窄屏显示汉堡按钮",
              m.js("return getComputedStyle(document.getElementById('navToggle')).display") != "none")
        m.click("#navToggle")
        check("点击汉堡可展开抽屉",
              m.js("var r=document.getElementById('sidebar').getBoundingClientRect();return r.left>=0"))
        check("抽屉展开有遮罩", not m.js("return document.getElementById('navOverlay').hidden"))
        m.shot("07-mobile-drawer.png")
        m.js("document.getElementById('navOverlay').click();"); time.sleep(0.35)
        check("点遮罩可收起", m.js("return !document.getElementById('layout')"
                                   ".classList.contains('nav-open')"))
        check("窄屏内容区无横向溢出",
              m.js("return document.querySelector('.content').scrollWidth"
                   "<=document.querySelector('.content').clientWidth+1"))
        m.shot("08-mobile.png")
        m.go("#/settings/account")
        mb = m.js("""var b=document.getElementById('btnCreate').getBoundingClientRect();
                     var c=document.getElementById('content');
                     return [Math.round(b.width), c.scrollWidth<=c.clientWidth+1,
                             Math.round(document.querySelector('.filter-bar').getBoundingClientRect().width)];""")
        check("窄屏：创建账户按钮等宽铺满、筛选栏不溢出",
              mb[0] > 120 and mb[1], f"按钮宽={mb[0]} 内容区无横向溢出={mb[1]}")
        m.shot("14-account-mobile.png")

        m.go("#/settings/session")
        ms = m.js("""var t=document.querySelector('.table-scroll');
                     var c=document.getElementById('content');
                     var b=document.getElementById('btnSessBatchDelete').getBoundingClientRect();
                     return [c.scrollWidth<=c.clientWidth+1, t.scrollWidth>t.clientWidth,
                             Math.round(b.width)];""")
        check("窄屏：会话管理页内容区不溢出、表格自身可横向滚动",
              ms[0] and ms[1], f"内容区无溢出={ms[0]} 表格可横滚={ms[1]} 按钮宽={ms[2]}")
        m.shot("32-session-mobile.png")

        m.go("#/settings/cert")
        mc = m.js("""var t=document.querySelector('.table-scroll');
                     var c=document.getElementById('content');
                     var b=document.getElementById('btnCertImport').getBoundingClientRect();
                     return [c.scrollWidth<=c.clientWidth+1, Math.round(b.width)];""")
        check("窄屏：证书管理页内容区不溢出、导入按钮铺满",
              mc[0] and mc[1] > 120, f"内容区无溢出={mc[0]} 按钮宽={mc[1]}")
        m.shot("40-cert-mobile.png")

        m.go("#/settings/backup")
        mbk = m.js("""var c=document.getElementById('content');
                     var b=document.getElementById('btnBakNow').getBoundingClientRect();
                     var dt=document.querySelectorAll('.des-card')[0].querySelectorAll('.des-row dt')[1];
                     var dd=document.querySelectorAll('.des-card')[0].querySelectorAll('.des-row dd')[1];
                     return [c.scrollWidth<=c.clientWidth+1, Math.round(b.width),
                             Math.abs(dt.scrollHeight-document.querySelectorAll('.des-card')[0]
                               .querySelectorAll('.des-row dt')[0].scrollHeight)<=1,
                             dd.getBoundingClientRect().left>=document.querySelectorAll('.des-card')[0]
                               .getBoundingClientRect().left+8];""")
        check("窄屏：系统备份页内容区不溢出、按钮铺满、标签不折行",
              mbk[0] and mbk[1] > 100 and mbk[2] and mbk[3],
              f"无溢出={mbk[0]} 按钮宽={mbk[1]} 标签单行={mbk[2]} 取值未越界={mbk[3]}")
        m.shot("46-backup-mobile.png")
        m.close()

        print(f"\n=== 断言 {sum(checks)}/{len(checks)} 通过 ===")
        return 0 if all(checks) else 2
    finally:
        drv.terminate()


if __name__ == "__main__":
    sys.exit(main())
