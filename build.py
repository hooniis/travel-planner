#!/usr/bin/env python3
"""여행 폴더의 trip.json + PDF/이미지 → 오프라인용 단일 HTML (<제목>_여행.html).

PDF는 페이지를 JPEG로 렌더링해 <img>로 넣고, 원본도 data URI로 함께 넣어요.
JS 없이도 전부 보이도록 만들고, JS는 D-day·오늘 강조에만 써요.

사용법: python3 build.py <여행 폴더>   (pdftoppm 필요: brew install poppler)
"""
import base64
import datetime as dt
import html
import json
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

import weather as wx

ROOT = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else Path.cwd()  # 여행 폴더
WEEK = "월화수목금토일"


def esc(s):
    return html.escape(str(s or ""))


def fmt_date(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.month}/{d.day} ({WEEK[d.weekday()]})"


def b64(path):
    return base64.b64encode(path.read_bytes()).decode()


def render_pdf(pdf):
    """PDF 각 페이지를 JPEG data URI 목록으로."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["pdftoppm", "-jpeg", "-jpegopt", "quality=80", "-r", "110", str(pdf), f"{tmp}/p"],
            check=True,
        )
        return [f"data:image/jpeg;base64,{b64(p)}" for p in sorted(Path(tmp).glob("p*.jpg"))]


def tel(phone):
    return f'<a href="tel:{esc(phone)}">{esc(phone)}</a>'


def kv(rows):
    return "<dl class='kv'>" + "".join(
        f"<dt>{esc(k)}</dt><dd>{v}</dd>" for k, v in rows if v
    ) + "</dl>"


def route_block(route):
    """동선: 번호 핀 지도(Leaflet, 온라인 전용) + 방문 순서 + 구글 지도 길찾기 링크."""
    # 좌표가 있으면 좌표로 넘겨야 구글이 엉뚱한 곳으로 잡지 않아요
    path = "/".join(
        f"{st['ll'][0]},{st['ll'][1]}" if st.get("ll") else urllib.parse.quote(st["query"], safe="")
        for st in route if st.get("ll") or st.get("query"))
    dir_url = f"https://www.google.com/maps/dir/{path}"
    pins = json.dumps([{"n": i, "label": st["label"], "ll": st["ll"]}
                       for i, st in enumerate(route, 1) if st.get("ll")], ensure_ascii=False)
    stops = "".join(
        f"<li>{esc(st['label'])}{'' if st.get('ll') else ' <span class=muted>(지도 위치 미확인)</span>'}</li>"
        for st in route)
    return (f"<div class='route-map'><div class='leaflet-box' data-pins='{esc(pins)}'></div>"
            f"<ol class='stops'>{stops}</ol>"
            f"<a class='btn' href='{esc(dir_url)}'>구글 지도에서 동선 열기 ↗</a>"
            f"<div class='muted small'>지도는 인터넷 연결 시에만 보여요 · 직선 연결이라 실제 도로와 달라요</div></div>")


def section_days(trip, weather):
    out = []
    for day in trip["days"]:
        items = []
        for it in day["items"]:
            cls = "item" + (" warn" if it.get("warn") else "") + (" todo" if it.get("todo") else "") + (f" t-{it['tag']}" if it.get("tag") else "")
            note = f"<div class='note'>{esc(it['note'])}</div>" if it.get("note") else ""
            warn = f"<div class='warnmsg'>⚠ {esc(it['warn'])}</div>" if it.get("warn") else ""
            done = f"<div class='donemsg'>✓ {esc(it['done'])}</div>" if it.get("done") else ""
            links = " · ".join(f"<a href='{esc(l['url'])}'>{esc(l['label'])} ↗</a>" for l in it.get("links", []))
            links = f"<div class='links'>{links}</div>" if links else ""
            items.append(
                f"<li class='{cls}'><span class='time'>{esc(it.get('time'))}</span>"
                f"<div><div class='what'>{esc(it['text'])}</div>{note}{links}{warn}{done}</div></li>"
            )
        out.append(
            f"<article class='day' data-date='{day['date']}'>"
            f"<header><span class='date'>{fmt_date(day['date'])}</span>"
            f"<span class='dtitle'>{esc(day['title'])}</span><span class='today'>오늘</span></header>"
            f"{wx.block(day['date'], weather, esc)}"
            f"<ol>{''.join(items)}</ol>{route_block(day['route']) if day.get('route') else ''}</article>"
        )
    return "".join(out)


def section_flights(trip):
    out = []
    for f in trip["flights"]:
        a, b = f["from"], f["to"]
        tickets = ", ".join(f"{esc(t['name'])} {esc(t['number'])}" for t in f["tickets"])
        out.append(f"""
<article class="card">
  <div class="card-top"><span class="pill">{esc(f['label'])}</span><span class="muted">{esc(f['airline'])} {esc(f['no'])}</span></div>
  <div class="route">
    <div><div class="code">{esc(a['code'])}</div><div class="muted">{esc(a['city'])} {esc(a['terminal'])}</div>
      <div class="when">{fmt_date(a['date'])} <b>{esc(a['time'])}</b></div></div>
    <div class="arrow">✈<div class="muted small">{esc(f['duration'])}</div></div>
    <div class="r"><div class="code">{esc(b['code'])}</div><div class="muted">{esc(b['city'])} {esc(b['terminal'])}</div>
      <div class="when">{fmt_date(b['date'])} <b>{esc(b['time'])}</b></div></div>
  </div>
  {kv([("항공사 예약번호", f"<b class='mono big'>{esc(f['pnr'])}</b>"),
       ("여행사 예약번호", esc(f['agencyRef'])),
       ("좌석 등급", esc(f['cabin'])),
       ("수하물", esc(f['baggage'])),
       ("항공권 번호", tickets)])}
  <p class="hint">{esc(f.get('seatNote'))}</p>
</article>""")
    return "".join(out)


def section_hotels(trip):
    out = []
    for h in trip["hotels"]:
        nights = (dt.date.fromisoformat(h["checkout"]) - dt.date.fromisoformat(h["checkin"])).days
        out.append(f"""
<article class="card">
  <div class="card-top"><span class="pill">{nights}박</span><span class="muted">{esc(h['via'])}</span></div>
  <h3>{esc(h['nameKo'])}<div class="muted small">{esc(h['name'])}</div></h3>
  <div class="stay"><div><div class="muted small">체크인</div><b>{fmt_date(h['checkin'])} {esc(h.get('checkinTime'))}</b></div>
    <div class="arrow">→</div><div class="r"><div class="muted small">체크아웃</div><b>{fmt_date(h['checkout'])} {esc(h.get('checkoutTime'))}</b></div></div>
  {kv([("예약 번호", f"<b class='mono big'>{esc(h['bookingId'])}</b>"),
       ("객실", esc(h['room'])),
       ("대표 투숙객", esc(h['guest'])),
       ("연락처", tel(h['phone'])),
       ("주소", f"{esc(h['address'])}<br><a href='{esc(h['map'])}'>구글 지도 열기 ↗</a>"),
       ("포함", esc(h['includes'])),
       ("조식", esc(h.get('breakfast'))),
       ("식당", "<br>".join(esc(x) for x in h.get('dining', []))),
       ("시내 셔틀", esc(h.get('shuttle'))),
       ("요청사항", esc(h['remarks'])),
       ("취소 규정", esc(h['policy']))])}
  <p class="hint">{esc(h.get('note'))}</p>
</article>""")
    return "".join(out)


def section_docs(trip):
    out, group = [], None
    for d in trip["documents"]:
        if d["group"] != group:
            group = d["group"]
            out.append(f"<h3 class='group'>{esc(group)}</h3>")
        if d.get("info"):
            out.append(f"<div class='card info'>{kv((k, esc(v)) for k, v in d['info'])}</div>")
            continue
        if d.get("todo"):
            out.append(f"<div class='doc todo'><span>{esc(d['title'])}</span><span class='muted small'>{esc(d['todo'])}</span></div>")
            continue
        if d.get("url") and not d.get("file"):
            out.append(f"<a class='doc' href='{esc(d['url'])}'><span>{esc(d['title'])}</span><span class='muted small'>링크 ↗</span></a>")
            continue
        src = ROOT / d["file"]
        if src.suffix.lower() == ".pdf":
            pages = render_pdf(src)
            raw = f"data:application/pdf;base64,{b64(src)}"
        else:  # 이미지(QR 등)
            pages = [f"data:image/{src.suffix[1:].lower().replace('jpg', 'jpeg')};base64,{b64(src)}"]
            raw = pages[0]
        imgs = "".join(f"<img loading='lazy' src='{p}' alt='{esc(d['title'])}'>" for p in pages)
        out.append(
            f"<details class='doc'><summary><span>{esc(d['title'])}</span><span class='muted small'>보기</span></summary>"
            f"<div class='pages'>{imgs}</div>"
            f"<a class='raw' download='{esc(src.name)}' href='{raw}'>원본 파일 받기</a>"
            + (f" · <a class='raw' href='{esc(d['url'])}'>온라인 링크 ↗</a>" if d.get("url") else "")
            + "</details>"
        )
    return "".join(out)


def section_budget(budget):
    """확정(결제 완료) 금액과 예상 범위를 원화로 합산. vnd 값은 rate로 환산해요."""
    rate = budget.get("krwPerVnd", 0)

    def krw_range(it):
        if "krw" in it:
            v = it["krw"]
        elif "vnd" in it:
            v = [x * rate for x in it["vnd"]] if isinstance(it["vnd"], list) else it["vnd"] * rate
        else:
            return None
        return (v, v) if not isinstance(v, list) else tuple(v)

    def won(lo, hi, exact=False):  # 예상치만 천 원 단위로 반올림
        f = (lambda x: f"{x:,.0f}") if exact else (lambda x: f"{round(x, -3):,.0f}")
        return f"{f(lo)}원" if f(lo) == f(hi) else f"{f(lo)}~{f(hi)}원"

    rows, paid, est = [], 0, [0, 0]
    for it in budget["items"]:
        r = krw_range(it)
        vnd = it.get("vnd")
        sub = (f"{vnd[0]:,}~{vnd[1]:,}동" if isinstance(vnd, list) else f"{vnd:,}동") if vnd else ""
        note = " · ".join(x for x in (sub, it.get("note", "")) if x)
        if r is None:
            amount, cls = "금액 미입력", "muted"
        elif it.get("status") == "paid":
            paid += r[0]
            amount, cls = won(*r, exact=True), "paid"
        else:
            est[0] += r[0]
            est[1] += r[1]
            amount, cls = won(*r), "est"
        tag = "<span class='pill'>결제 완료</span>" if it.get("status") == "paid" else ""
        rows.append(f"<li class='b-{cls}'><div><div>{esc(it['name'])} {tag}</div>"
                    f"{f'<div class=note>{esc(note)}</div>' if note else ''}</div><b>{amount}</b></li>")
    return f"""
<article class="card budget">
  <div class="totals">
    <div><div class="muted small">결제 완료</div><b>{won(paid, paid, exact=True)}</b></div>
    <div><div class="muted small">현지 예상</div><b>{won(*est)}</b></div>
    <div><div class="muted small">합계 (2인)</div><b>{won(paid + est[0], paid + est[1])}</b></div>
  </div>
  <ul class="budget-list">{''.join(rows)}</ul>
  <p class="hint">{esc(budget.get('note'))}</p>
</article>"""


def section_info(trip):
    contacts = "".join(f"<li><span>{esc(c['name'])}</span>{tel(c['phone'])}</li>" for c in trip["contacts"])
    checks = "".join(
        f"<li><label><input type='checkbox'{' checked' if isinstance(c, dict) and c.get('done') else ''}> "
        f"{esc(c['text'] if isinstance(c, dict) else c)}</label></li>"
        for c in trip["checklist"])
    people = " · ".join(esc(p) for p in trip["travelers"])
    return f"""
<article class="card"><h3>연락처</h3><ul class="contacts">{contacts}</ul></article>
<article class="card"><h3>출발 전 체크</h3><ul class="checks">{checks}</ul></article>
<p class="muted small center">여행자 {people}</p>"""


CSS = """
:root{--bg:#f6f4ef;--card:#fff;--ink:#1d1d1f;--muted:#6e6e73;--line:#e6e2d8;--accent:#0a7d74;--accent-soft:#e1f2ef;--warn:#b45309;--warn-soft:#fff4e0}
@media (prefers-color-scheme:dark){:root{--bg:#121413;--card:#1c1f1e;--ink:#ececec;--muted:#9a9a9f;--line:#2c302e;--accent:#4fc3b6;--accent-soft:#1d3532;--warn:#f0a952;--warn-soft:#3a2a14}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Pretendard",sans-serif;-webkit-text-size-adjust:100%}
a{color:var(--accent)}
.wrap{max-width:640px;margin:0 auto;padding:0 16px 48px}
.hero{padding:28px 0 16px}
.hero h1{margin:0;font-size:32px;letter-spacing:-.02em}
.hero p{margin:4px 0 0;color:var(--muted)}
.dday{display:inline-block;margin-top:10px;padding:2px 10px;border-radius:99px;background:var(--accent);color:#fff;font-weight:700;font-size:14px}
.dday:empty{display:none}
nav{position:sticky;top:0;z-index:1000;background:var(--bg);border-bottom:1px solid var(--line);margin:0 -16px;padding:8px 16px;display:flex;gap:6px;overflow-x:auto}
nav a{flex:none;padding:6px 12px;border-radius:99px;background:var(--card);border:1px solid var(--line);color:var(--ink);text-decoration:none;font-size:14px}
section{scroll-margin-top:56px;padding-top:24px}
h2{font-size:20px;margin:0 0 12px}
h3{margin:4px 0 12px;font-size:18px}
.card,.day{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px;margin-bottom:12px}
.card-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.pill{background:var(--accent-soft);color:var(--accent);font-weight:700;font-size:13px;padding:2px 10px;border-radius:99px}
.muted{color:var(--muted)}.small{font-size:13px}.center{text-align:center}.r{text-align:right}
.mono{font-family:ui-monospace,Menlo,monospace}.big{font-size:18px;letter-spacing:.04em}
.route,.stay{display:flex;justify-content:space-between;align-items:center;gap:8px;margin:4px 0 12px}
.code{font-size:28px;font-weight:800;letter-spacing:.02em}
.when{font-size:14px}
.arrow{text-align:center;color:var(--muted);font-size:20px}
.kv{display:grid;grid-template-columns:auto 1fr;gap:6px 12px;margin:0;padding-top:12px;border-top:1px dashed var(--line);font-size:14px}
.kv dt{color:var(--muted)}.kv dd{margin:0;word-break:break-word}
.hint{margin:10px 0 0;font-size:13px;color:var(--muted)}
.day header{display:flex;align-items:baseline;gap:8px;margin-bottom:8px}
.day .date{font-weight:800}
.day .dtitle{color:var(--muted);font-size:14px}
.day .today{display:none;margin-left:auto;font-size:12px;font-weight:700;color:#fff;background:var(--accent);padding:1px 8px;border-radius:99px}
.day.is-today{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent-soft)}
.day.is-today .today{display:inline-block}
.day.is-past{opacity:.55}
.weather{font-size:14px;margin:-4px 0 8px;padding:6px 10px;border-radius:8px;background:var(--accent-soft)}
.weather summary{cursor:pointer;list-style:none}
.weather summary::-webkit-details-marker{display:none}
.wx-wrap{overflow-x:auto}
.wx{width:100%;margin-top:6px;border-collapse:collapse;font-size:12px}
.wx th,.wx td{text-align:left;padding:3px 6px 3px 0;border-top:1px solid var(--line);white-space:nowrap}
.day ol{list-style:none;margin:0;padding:0}
.item{display:grid;grid-template-columns:52px 1fr;gap:8px;padding:8px 0;border-top:1px solid var(--line)}
.item:first-child{border-top:0}
.time{font-variant-numeric:tabular-nums;color:var(--muted);font-size:14px;padding-top:1px}
.t-flight .what::before{content:"✈ ";color:var(--accent)}
.t-hotel .what::before{content:"⌂ ";color:var(--accent)}
.note{font-size:13px;color:var(--muted)}
.links{font-size:13px;margin-top:2px}
.item.todo .what{color:var(--muted);font-style:italic}
.warn .what{color:var(--warn);font-weight:700}
.warnmsg{margin-top:4px;font-size:13px;background:var(--warn-soft);color:var(--warn);padding:6px 8px;border-radius:8px}
.donemsg{margin-top:4px;font-size:13px;background:var(--accent-soft);color:var(--accent);padding:6px 8px;border-radius:8px}
.group{font-size:14px;color:var(--muted);margin:16px 0 8px}
.doc{display:flex;justify-content:space-between;gap:8px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin-bottom:8px;color:var(--ink);text-decoration:none}
details.doc{display:block}
details.doc summary{display:flex;justify-content:space-between;gap:8px;cursor:pointer;list-style:none}
details.doc summary::-webkit-details-marker{display:none}
details.doc[open] summary .muted{visibility:hidden}
.info .kv{border-top:0;padding-top:0}
.doc.todo{border-style:dashed;color:var(--muted)}
.pages img{display:block;width:100%;margin-top:12px;border-radius:8px;border:1px solid var(--line);background:#fff}
.raw{display:inline-block;margin-top:10px;font-size:14px}
.route-map{margin-top:12px;padding-top:12px;border-top:1px dashed var(--line)}
.leaflet-box{height:280px;border-radius:12px;background:var(--accent-soft);z-index:0}
.pin{background:var(--accent);color:#fff;border:2px solid #fff;border-radius:50%;width:26px;height:26px;line-height:22px;text-align:center;font:700 13px/22px sans-serif;box-shadow:0 1px 4px rgba(0,0,0,.4)}
.day ol.stops{list-style:decimal;margin:8px 0;padding-left:22px;font-size:14px}
.btn{display:block;text-align:center;padding:10px;border-radius:10px;background:var(--accent);color:#fff;text-decoration:none;font-weight:700;margin-bottom:6px}
.totals{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:8px}
.totals b{font-size:16px;font-variant-numeric:tabular-nums}
.budget-list{list-style:none;margin:0;padding:0}
.budget-list li{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-top:1px solid var(--line)}
.budget-list b{white-space:nowrap;font-variant-numeric:tabular-nums}
.b-est b{color:var(--muted)}
.b-muted b{color:var(--warn);font-weight:400;font-size:13px}
.contacts,.checks{list-style:none;margin:0;padding:0}
.contacts li{display:flex;justify-content:space-between;padding:8px 0;border-top:1px solid var(--line)}
.contacts li:first-child{border-top:0}
.checks li{padding:6px 0}
.checks input{width:18px;height:18px;vertical-align:-3px;accent-color:var(--accent)}
"""

LEAFLET_JS = """
(function(){
  var boxes=document.querySelectorAll('.leaflet-box'); if(!boxes.length) return;
  var css=document.createElement('link'); css.rel='stylesheet';
  css.href='https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css'; document.head.appendChild(css);
  var js=document.createElement('script');
  js.src='https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js';
  js.onload=function(){ boxes.forEach(function(box){
    var pins=JSON.parse(box.dataset.pins), map=L.map(box,{scrollWheelZoom:false});
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap'}).addTo(map);
    var lls=pins.map(function(p){return p.ll;});
    L.polyline(lls,{color:'#0a7d74',weight:3,dashArray:'6 6'}).addTo(map);
    var groups={};  // 같은 좌표는 핀 하나로 합치기 (예: 1·6)
    pins.forEach(function(p){var k=p.ll.join(',');(groups[k]=groups[k]||{ll:p.ll,ps:[]}).ps.push(p);});
    Object.keys(groups).forEach(function(k){
      var g=groups[k], nums=g.ps.map(function(p){return p.n;}).join('·'), w=Math.max(26,nums.length*9+12);
      L.marker(g.ll,{icon:L.divIcon({className:'',html:'<div class="pin" style="width:'+w+'px;border-radius:13px">'+nums+'</div>',iconSize:[w,26],iconAnchor:[w/2,13]})})
       .addTo(map).bindPopup(g.ps.map(function(p){return p.n+'. '+p.label;}).join('<br>'));
    });
    map.fitBounds(lls,{padding:[24,24]});
  });};
  js.onerror=function(){ boxes.forEach(function(b){b.textContent='오프라인이라 지도를 불러오지 못했어요';b.style.cssText+='display:flex;align-items:center;justify-content:center;font-size:13px;color:var(--muted)';}); };
  document.head.appendChild(js);
})();
"""

JS = """
(function(){
  var p=function(s){var a=s.split('-');return new Date(+a[0],a[1]-1,+a[2]);};
  var now=new Date(),t=new Date(now.getFullYear(),now.getMonth(),now.getDate());
  var s=p(document.body.dataset.start),e=p(document.body.dataset.end),el=document.getElementById('dday');
  var diff=Math.round((s-t)/864e5);
  el.textContent=diff>0?'D-'+diff:(t<=e?'여행 중':'');
  document.querySelectorAll('.day').forEach(function(d){
    var dd=p(d.dataset.date);
    if(+dd===+t){d.classList.add('is-today');setTimeout(function(){d.scrollIntoView({block:'start'});},0);}
    else if(dd<t)d.classList.add('is-past');
  });
})();
"""


def build():
    trip = json.loads((ROOT / "trip.json").read_text())
    weather = wx.fetch(trip["weather"], ROOT) if trip.get("weather") else {}
    page = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<title>{esc(trip['title'])} 여행</title>
<style>{CSS}</style></head>
<body data-start="{trip['start']}" data-end="{trip['end']}"><div class="wrap">
<div class="hero"><h1>{esc(trip['title'])}</h1><p>{esc(trip['subtitle'])}</p><span class="dday" id="dday"></span></div>
<nav><a href="#plan">일정</a><a href="#flight">항공</a><a href="#hotel">숙소</a><a href="#docs">문서</a>{'<a href="#budget">비용</a>' if trip.get('budget') else ''}<a href="#info">연락처·체크</a></nav>
<section id="plan"><h2>일정</h2>{section_days(trip, weather)}</section>
<section id="flight"><h2>항공</h2>{section_flights(trip)}</section>
<section id="hotel"><h2>숙소</h2>{section_hotels(trip)}</section>
<section id="docs"><h2>문서</h2>{section_docs(trip)}</section>
{f'<section id="budget"><h2>비용</h2>{section_budget(trip["budget"])}</section>' if trip.get('budget') else ''}
<section id="info"><h2>연락처 · 체크리스트</h2>{section_info(trip)}</section>
<p class="muted small center">생성 {dt.datetime.now():%Y-%m-%d %H:%M}</p>
</div><script>{JS}{LEAFLET_JS}</script></body></html>"""
    out = ROOT / f"{trip['title']}_여행.html"
    out.write_text(page)
    print(f"{out}  {out.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    build()
