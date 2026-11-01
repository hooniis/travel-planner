"""여러 소스의 일별 예보를 모아 비교해요. 소스별로 실패하면 그 소스만 캐시 값을 써요.

주 소스:
- AccuWeather (API 키 필요 · 15일 예보) → 환경변수 ACCUWEATHER_API_KEY,
  여행 폴더의 .accuweather_key, ~/.config/travel-planner/accuweather_key 순서로 찾아요
참고 소스 (키 불필요):
- Open-Meteo를 통한 ECMWF(유럽) / GFS(미국) / JMA(일본) / ICON(독일) 모델
- MET Norway (yr.no)
- wttr.in (3일치만 줘서 여행 직전에만 잡혀요)
"""
import datetime as dt
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

UA = {"User-Agent": "nhatrang-trip-planner/1.0"}  # MET Norway는 UA 없으면 거절해요

WMO = {0: ("☀️", "맑음"), 1: ("🌤", "대체로 맑음"), 2: ("⛅", "구름 조금"), 3: ("☁️", "흐림"),
       45: ("🌫", "안개"), 48: ("🌫", "안개"), 51: ("🌦", "약한 이슬비"), 53: ("🌦", "이슬비"), 55: ("🌧", "강한 이슬비"),
       61: ("🌧", "약한 비"), 63: ("🌧", "비"), 65: ("🌧", "강한 비"), 80: ("🌦", "약한 소나기"),
       81: ("🌧", "소나기"), 82: ("⛈", "강한 소나기"), 95: ("⛈", "뇌우"), 96: ("⛈", "뇌우"), 99: ("⛈", "뇌우")}
OM_MODELS = {"ecmwf_ifs025": "ECMWF (유럽)", "gfs_seamless": "GFS (미국)",
             "jma_seamless": "JMA (일본)", "icon_seamless": "ICON (독일)"}
MET_SYMBOL = [("thunder", 95), ("heavyrain", 65), ("rain", 61), ("sleet", 61), ("fog", 45),
              ("partlycloudy", 2), ("cloudy", 3), ("fair", 1), ("clearsky", 0)]


def _get(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers={**UA, **(headers or {})}), timeout=20) as r:
        return json.load(r)


def open_meteo(cfg):
    qs = urllib.parse.urlencode({
        "latitude": cfg["lat"], "longitude": cfg["lon"], "timezone": cfg["timezone"],
        "start_date": cfg["from"], "end_date": cfg["to"], "models": ",".join(OM_MODELS),
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum"})
    d = _get(f"https://api.open-meteo.com/v1/forecast?{qs}")["daily"]
    out = {}
    for m, name in OM_MODELS.items():
        for i, t in enumerate(d["time"]):
            if d[f"temperature_2m_max_{m}"][i] is None:  # 이 모델의 예보 범위 밖
                continue
            out.setdefault(name, {})[t] = {
                "code": d[f"weather_code_{m}"][i], "max": d[f"temperature_2m_max_{m}"][i],
                "min": d[f"temperature_2m_min_{m}"][i], "pop": d[f"precipitation_probability_max_{m}"][i],
                "rain": d[f"precipitation_sum_{m}"][i]}
    return out


def met_norway(cfg):
    ts = _get(f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={cfg['lat']}&lon={cfg['lon']}")
    days = {}
    for row in ts["properties"]["timeseries"]:
        t = dt.datetime.fromisoformat(row["time"].replace("Z", "+00:00")).astimezone(ZoneInfo(cfg["timezone"])).date().isoformat()
        data = row["data"]
        step = 1 if "next_1_hours" in data else 6
        nxt = data.get("next_1_hours") or data.get("next_6_hours")
        if not (cfg["from"] <= t <= cfg["to"]) or not nxt:
            continue
        d = days.setdefault(t, {"temps": [], "rain": 0.0, "codes": [], "covered": 0})
        if d["covered"] >= 24:  # 6시간 구간이 겹쳐 강수량이 중복되지 않게
            continue
        d["temps"].append(data["instant"]["details"]["air_temperature"])
        d["rain"] += nxt["details"].get("precipitation_amount", 0)
        d["codes"].append(next((c for k, c in MET_SYMBOL if k in nxt["summary"]["symbol_code"]), 3))
        d["covered"] += step
    return {"MET Norway (yr.no)": {
        t: {"code": max(d["codes"]), "max": max(d["temps"]), "min": min(d["temps"]), "pop": None,
            "rain": round(d["rain"], 1)}
        for t, d in days.items()}}


PRIMARY = "AccuWeather"


def _accu_key(trip_dir):
    if os.environ.get("ACCUWEATHER_API_KEY"):
        return os.environ["ACCUWEATHER_API_KEY"]
    for f in (trip_dir / ".accuweather_key", Path.home() / ".config/travel-planner/accuweather_key"):
        if f.exists():
            return f.read_text().strip()
    return ""


def accuweather(cfg):
    key = _accu_key(cfg["_dir"])
    if not key:
        raise RuntimeError("API 키 없음 (.accuweather_key)")
    base = "https://dataservice.accuweather.com"
    auth = {"Authorization": f"Bearer {key}"}  # URL에 키를 넣지 않아 오류 로그에 안 남아요
    loc = _get(f"{base}/locations/v1/cities/geoposition/search?q={cfg['lat']},{cfg['lon']}", auth)["Key"]
    fc = _get(f"{base}/forecasts/v1/daily/15day/{loc}?language=ko-kr&details=true&metric=true", auth)
    out = {}
    for d in fc["DailyForecasts"]:
        t = d["Date"][:10]
        if not cfg["from"] <= t <= cfg["to"]:
            continue
        day, night = d["Day"], d["Night"]
        pop = max(day.get("PrecipitationProbability", 0), night.get("PrecipitationProbability", 0))
        rain = (day.get("TotalLiquid", {}).get("Value") or 0) + (night.get("TotalLiquid", {}).get("Value") or 0)
        out[t] = {"link": d.get("MobileLink") or d.get("Link"),
                  "code": 61 if day.get("HasPrecipitation") or night.get("HasPrecipitation") else 2,
                  "text": day.get("IconPhrase"), "max": d["Temperature"]["Maximum"]["Value"],
                  "min": d["Temperature"]["Minimum"]["Value"], "pop": pop, "rain": round(rain, 1)}
    return {PRIMARY: out}


def wttr(cfg):
    out = {}
    for w in _get(f"https://wttr.in/{cfg['lat']},{cfg['lon']}?format=j1")["weather"]:
        if not cfg["from"] <= w["date"] <= cfg["to"]:
            continue
        pop = max(int(h["chanceofrain"]) for h in w["hourly"])
        out[w["date"]] = {"code": 61 if pop >= 60 else 2, "max": float(w["maxtempC"]), "min": float(w["mintempC"]),
                          "pop": pop, "rain": round(sum(float(h["precipMM"]) for h in w["hourly"]) * 3, 1)}  # 3시간 간격
    return {"wttr.in": out}


def fetch(cfg, trip_dir):
    """{소스명: {"fetched": "MM/DD HH:MM", "days": {날짜: 예보}}} · 캐시는 여행 폴더에 저장"""
    cfg = {"timezone": "Asia/Seoul", **cfg, "_dir": trip_dir}
    cache_file = trip_dir / "weather_cache.json"
    cached = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    sources = cached.get("sources", {})
    now = dt.datetime.now().strftime("%m/%d %H:%M")
    for fn in (accuweather, open_meteo, met_norway, wttr):
        try:
            for name, days in fn(cfg).items():
                if days:
                    sources[name] = {"fetched": now, "days": days}
        except Exception as e:
            print(f"날씨 소스 실패 ({fn.__name__}) → 캐시 사용: {e}")
    cache_file.write_text(json.dumps({"sources": sources}, ensure_ascii=False, indent=2))
    print("날씨:", ", ".join(f"{n} {len(v['days'])}일" for n, v in sources.items()))
    return sources


def _rainy(w):
    return (w.get("rain") or 0) >= 1 or w["code"] >= 51


def block(date, sources, esc):
    """일정 카드에 넣을 날씨 요약 + 소스별 표."""
    rows = sorted(((n, v["fetched"], v["days"][date]) for n, v in sources.items() if date in v["days"]),
                  key=lambda r: r[0] != PRIMARY)
    if not rows:
        return ""
    ws = [w for _, _, w in rows]
    rainy = sum(_rainy(w) for w in ws)
    if rows[0][0] == PRIMARY:  # 주 소스가 있으면 그 값을 앞세우고, 나머지는 참고로
        p = rows[0][2]
        icon = "🌧" if _rainy(p) else "☀️"
        head = (f"{icon} {esc(p.get('text') or '')} · {p['min']:.0f}–{p['max']:.0f}°C · 강수 {p['pop']}%"
                f" <span class='muted small'>AccuWeather · 다른 소스 비 예보 {rainy - _rainy(p)}/{len(ws) - 1}곳 ▾</span>")
    else:
        icon, label = (("🌧", "비 올 가능성 높음") if rainy * 2 > len(ws) else
                       ("🌦", "소나기 가능") if rainy else ("☀️", "대체로 맑음"))
        tmin, tmax = min(w["min"] for w in ws), max(w["max"] for w in ws)
        head = (f"{icon} {label} · {tmin:.0f}–{tmax:.0f}°C · 비 예보 {rainy}/{len(ws)}곳"
                f" <span class='muted small'>소스별 ▾</span>")
    trs = "".join(
        f"<tr><td>{'<b>' + esc(n) + '</b>' if n == PRIMARY else esc(n)}</td>"
        f"<td>{esc(w['text']) if w.get('text') else ' '.join(WMO.get(w['code'], ('🌡', '-')))}</td>"
        f"<td>{w['min']:.0f}–{w['max']:.0f}°</td>"
        f"<td>{'-' if w.get('pop') is None else str(w['pop']) + '%'}</td>"
        f"<td>{(w.get('rain') or 0):g}mm</td><td class='muted'>{esc(f)}</td></tr>"
        for n, f, w in rows)
    return (f"<details class='weather'><summary>{head}</summary>"
            f"<div class='wx-wrap'><table class='wx'><tr><th>소스</th><th>날씨</th><th>기온</th><th>강수확률</th>"
            f"<th>강수량</th><th>받은 시각</th></tr>{trs}</table></div>"
            + (f"<a class='small' href='{esc(rows[0][2]['link'])}'>AccuWeather에서 시간대별 보기 ↗</a>"
               if rows[0][2].get("link") else "")
            + "</details>")
