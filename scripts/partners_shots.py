# -*- coding: utf-8 -*-
"""쿠팡 파트너스 '활동 페이지' 등록용 스크린샷을 페이지마다 1장씩 만든다.

가이드 요건(공식 PDF 2026-09-17판): [내 정보]에 '링크가 있는 모든 페이지'를 등록하고
페이지별로 '링크/위젯 + 대가성 문구가 함께 보이는' 활동 스크린샷을 올린다.
그래서 한 장 안에 ①본문 맨 위 고지 문구와 ②쿠팡 링크 블록이 둘 다 들어와야 한다.

픽담 호스트의 NinjaFirewall 이 헤드리스 브라우저에 403을 주므로
실제 데스크톱 UA · navigator.webdriver 가림 · 요청 간격을 둔다(2026-10-01 실측).
"""
import json, os, re, sys, time
from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
OUT = "partners/shots"
NOTICE = "쿠팡 파트너스 활동의 일환"
PAD = 24

def slug_of(url):
    s = url.rstrip("/").rsplit("/", 1)[-1] or "home"
    return re.sub(r"[^a-z0-9_-]", "", s.lower())[:40] or "home"

def main():
    rows = json.load(open("partners/posts.json", encoding="utf-8"))
    targets = [r for r in rows if r["coupang"]]
    os.makedirs(OUT, exist_ok=True)
    report = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium",
                               args=["--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(user_agent=UA, viewport={"width": 1280, "height": 1600},
                            locale="ko-KR", device_scale_factor=1)
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        pg = ctx.new_page()
        for i, r in enumerate(targets, 1):
            name = f"{i:02d}_{slug_of(r['link'])}.png"
            path = os.path.join(OUT, name)
            try:
                resp = pg.goto(r["link"], wait_until="domcontentloaded", timeout=60000)
                code = resp.status if resp else 0
                if code != 200:
                    report.append({**r, "file": "", "ok": False, "why": f"HTTP {code}"})
                    print(f"  ✗ #{r['id']} HTTP {code}")
                    time.sleep(4); continue
                # 지연 로딩 이미지 때문에 레이아웃이 밀리면 클립이 어긋난다 — 먼저 끝까지 훑는다
                pg.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                pg.wait_for_timeout(1200)
                pg.evaluate("window.scrollTo(0, 0)")
                pg.wait_for_timeout(1200)
                box = pg.evaluate("""() => {
                  const NOTICE = '쿠팡 파트너스 활동의 일환';
                  const all = [...document.querySelectorAll('p,div,span')];
                  const n = all.find(e => (e.textContent||'').includes(NOTICE) && e.children.length === 0)
                         || all.find(e => (e.textContent||'').includes(NOTICE));
                  const a = document.querySelector('a[href*="link.coupang.com"]');
                  if (!n || !a) return null;
                  const nb = n.getBoundingClientRect(), ab = a.getBoundingClientRect();
                  const sy = window.scrollY, sx = window.scrollX;
                  // 링크 '버튼 자체'가 반드시 들어오게 — 앵커 아래로 넉넉히 더 잡는다
                  const top = Math.min(nb.top, ab.top) + sy;
                  const bottom = Math.max(nb.bottom, ab.bottom + 140) + sy;
                  const left = Math.min(nb.left, ab.left) + sx - 8;
                  const right = Math.max(nb.right, ab.right) + sx + 8;
                  return {x:left, y:top, w:right-left, h:bottom-top,
                          noticeText:(n.textContent||'').trim().slice(0,60),
                          href:a.getAttribute('href')};
                }""")
                if not box:
                    report.append({**r, "file": "", "ok": False, "why": "고지문 또는 쿠팡 링크를 못 찾음"})
                    print(f"  ✗ #{r['id']} 요소 없음"); time.sleep(4); continue
                clip = {"x": max(0, box["x"] - PAD), "y": max(0, box["y"] - PAD),
                        "width": box["w"] + PAD * 2, "height": box["h"] + PAD * 2}
                pg.screenshot(path=path, clip=clip, full_page=True)
                kb = os.path.getsize(path) // 1024
                report.append({**r, "file": name, "ok": True,
                               "height": int(clip["height"]), "kb": kb,
                               "subid_in_href": "subId" in (box["href"] or "") or "subid" in (box["href"] or "")})
                print(f"  ✓ {name}  {int(clip['height'])}px {kb}KB")
            except Exception as e:
                report.append({**r, "file": "", "ok": False, "why": str(e)[:70]})
                print(f"  ✗ #{r['id']} {str(e)[:60]}")
            time.sleep(4)
        b.close()
    json.dump(report, open("partners/shots_report.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    ok = [r for r in report if r["ok"]]
    print(f"\n성공 {len(ok)} / {len(report)}")
    return 0 if len(ok) == len(report) else 1

if __name__ == "__main__":
    sys.exit(main())
