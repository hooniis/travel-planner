# travel-planner

여행 일정, 항공권, 숙소 확정서, 이심 QR을 **오프라인에서도 열리는 HTML 파일 하나**로 만들어요.
동행자와는 **비밀번호로 암호화한 GitHub Pages 링크**로 공유해요.

- 날짜별 타임라인 (오늘 강조, D-day, 경고·완료 표시)
- 일정마다 구글 지도 링크, 하루 동선 지도 (번호 핀 + 구글 길찾기)
- PDF는 이미지로 넣어서 누르면 바로 펼쳐져요. 원본도 받을 수 있어요
- 날씨: AccuWeather를 기본으로, ECMWF·GFS·JMA·ICON·MET Norway·wttr.in과 비교해요 (빌드할 때마다 갱신)
- 라이트·다크 모드, 모바일 화면

## 구조

```
travel-planner/          ← 이 저장소 (코드 + 암호화된 페이지만)
  build.py               trip.json → <제목>_여행.html
  weather.py             여러 날씨 소스를 모아 비교
  publish.py             암호화해서 docs/<slug>/ 에 올림
  example/trip.json      필드 예시 (가짜 데이터)
  docs/<slug>/index.html 암호화된 여행 페이지 (GitHub Pages)

~/Documents/<여행 폴더>/  ← 여행 데이터 (올리지 않음)
  trip.json, *.pdf, *.png
  .accuweather_key, .share_password, weather_cache.json
  <제목>_여행.html        오프라인용 결과물
```

## 새 여행 시작하기

```bash
mkdir ~/Documents/2701\ 다낭
cp example/trip.json ~/Documents/2701\ 다낭/      # 고쳐서 쓰기
# PDF, QR 이미지를 같은 폴더에 넣고 documents[].file 에 파일 이름 적기

python3 build.py ~/Documents/2701\ 다낭           # 오프라인 HTML 생성
python3 publish.py ~/Documents/2701\ 다낭         # 암호화해서 공유 링크로 배포
```

`publish.py`는 처음 실행할 때 비밀번호를 만들어 여행 폴더의 `.share_password`에 저장해요.
링크와 비밀번호는 따로 전달하세요. 출발 직전에는 `<제목>_여행.html` 파일도 직접 보내서 오프라인용으로 저장해 두게 하세요.

## 준비물

- Python 3.9+
- `pdftoppm` (`brew install poppler`) — PDF를 이미지로 바꿀 때
- Node.js (`npx staticrypt`) — 암호화할 때
- `gh` CLI 로그인 — 배포할 때
- AccuWeather API 키 (선택): [developer.accuweather.com](https://developer.accuweather.com)에서 발급해
  `~/.config/travel-planner/accuweather_key`나 여행 폴더의 `.accuweather_key`에 저장하세요.
  없으면 다른 소스만으로 날씨를 보여 줘요.

## trip.json 필드

| 필드 | 설명 |
|---|---|
| `title`, `subtitle`, `start`, `end` | 제목(파일 이름에도 쓰여요), 부제, 여행 기간 |
| `slug` | 공유 URL 경로 (영문·숫자·하이픈) |
| `weather` | `lat`, `lon`, `from`, `to`, `timezone` |
| `flights[]` | 항공편, 예약번호, 항공권 번호 |
| `hotels[]` | 숙소, 체크인·아웃, 조식, 식당(`dining`), 셔틀(`shuttle`) |
| `days[].items[]` | `time`, `text`, `note`, `tag`(`flight`/`hotel`), `links[]`, `warn`(경고), `done`(완료), `todo` |
| `days[].route[]` | 동선. `ll`(좌표)이 있으면 지도에 핀, 없으면 목록에만 나와요 |
| `documents[]` | `file`(PDF·이미지), `url`, `info`(표), `todo`(아직 없음) 중 하나 |
| `contacts[]`, `checklist[]` | 연락처, 체크리스트 (`{"text", "done": true}`로 완료 표시) |

## 보안

- 저장소에는 **암호화된 페이지만** 올라가요. `.gitignore`가 여행 데이터 파일을 막아 둬요.
- 페이지는 StatiCrypt(AES-256)로 암호화돼 있어서 비밀번호 없이는 내용을 볼 수 없어요.
- 예약번호 + 이름이면 항공 예약 변경까지 가능하니 비밀번호는 링크와 따로 전달하세요.
