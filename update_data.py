import os
import json
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import time

# =========================================================================
# 프로그램 명칭: KRA전국 승부예상AI_V4.0 (스피드·승급·G1F·배당률 앙상블 모델)
# =========================================================================
VERSION = "KRA전국 승부예상AI_V4.0"
API_KEY = os.environ.get("KRA_API_KEY", "")
URL = "http://apis.data.go.kr/B551015/racedetailresult/getracedetailresult"

KST = timezone(timedelta(hours=9))

MEET_CONFIG = [
    ("1", "서울"),
    ("4", "영천"),
    ("2", "제주"),
    ("3", "부산경남")
]

# 1. 기수 최근 1년 복승률 통계 DB (%)
JOCKEY_RATES = {
    "문세영": 33.2, "서승운": 31.5, "최시대": 26.8, "다나카": 25.4,
    "빅투아르": 25.1, "김용근": 24.5, "다비드": 24.2, "유현명": 23.8,
    "정도윤": 22.5, "유승완": 21.0, "김혜선": 20.8, "송재철": 19.5,
    "이혁": 19.2, "임다빈": 18.5, "김동영": 17.8, "이성재": 16.5,
    "송경윤": 15.2, "전진구": 14.8, "김어수": 14.5, "손경민": 14.0,
    "조인권": 21.4, "이동하": 16.0, "임기원": 17.5, "장추열": 18.0,
    "최범현": 15.5, "마이아": 22.0, "조상범": 13.5, "김효정": 12.0
}

# 2. 조교사 최근 1년 복승률 통계 DB (%)
TRAINER_RATES = {
    "서홍수": 24.5, "김영관": 28.0, "라이스": 25.2, "민장기": 22.1,
    "송문길": 21.5, "배휴준": 20.8, "정호익": 19.5, "최용건": 19.0,
    "구영준": 18.5, "김도현": 18.2, "안우성": 18.0, "임성실": 17.5,
    "박재우": 17.2, "이강서": 16.8, "전승규": 16.0, "강은석": 15.5,
    "서인석": 15.0, "백광열": 18.8, "심승태": 14.5, "조용배": 13.5
}

def parse_time_seconds(time_str):
    """주파기록 문자열(예: '1:14.2' 또는 '74.2')을 초 단위 float로 변환"""
    try:
        t = str(time_str).strip()
        if ":" in t:
            parts = t.split(":")
            return float(parts[0]) * 60 + float(parts[1])
        elif t and float(t) > 0:
            return float(t)
    except:
        pass
    return None

def calculate_speed_rating(time_str, dist):
    """[신규 1] 말 자체의 절대 스피드 지수 (거리별 기준 타임 비교)"""
    bonus = 0.0
    tags = []
    sec = parse_time_seconds(time_str)
    if sec and sec > 30.0:
        # 거리별 평균 기준 기록 (초)
        base_time = {
            1000: 61.5, 1200: 74.8, 1300: 82.0, 1400: 88.5,
            1600: 102.5, 1700: 111.5, 1800: 117.5, 2000: 133.0
        }.get(dist, dist * 0.063 + 0.5)

        diff = base_time - sec  # 양수면 평균보다 빠른 준족마
        if diff >= 1.5:
            bonus += 10.0
            tags.append("스피드 지수 최상 🏎️")
        elif diff >= 0.5:
            bonus += 5.0
            tags.append("기록 우수")
        elif diff <= -2.0:
            bonus -= 5.0
    return bonus, tags

def analyze_g1f(g1f_str):
    """[신규 3] 결승선 직전 200m(G1F) 스퍼트 탄력 분석"""
    bonus = 0.0
    tags = []
    try:
        g1f = float(str(g1f_str).strip())
        if 11.0 <= g1f <= 12.8:
            bonus += 7.0
            tags.append(f"직선주로 스퍼트 최강({g1f}초) 🚀")
        elif g1f <= 13.2:
            bonus += 3.0
        elif g1f >= 14.2:
            bonus -= 4.0
            tags.append("종반 탄력 둔화")
    except:
        pass
    return bonus, tags

def analyze_odds_and_value(odds_str, base_score):
    """[신규 4] 배당률 집단지성 앙상블 & 황금 복병마 탐지"""
    bonus = 0.0
    tags = []
    odds = 0.0
    try:
        odds = float(str(odds_str).strip())
    except:
        odds = 0.0

    if odds > 1.0:
        if odds <= 3.2:
            bonus += 8.0
            tags.append(f"대중 강력 지지({odds}배) 🔥")
        elif odds <= 6.5:
            bonus += 4.0
        elif odds >= 35.0:
            bonus -= 5.0  # 초비인기마 감점

        # 💡 황금 복병마 포착: AI 점수는 높은데(78점 이상) 대중 배당률이 8배~25배인 말!
        if base_score >= 75.0 and 8.0 <= odds <= 25.0:
            bonus += 4.0
            tags.append(f"초특급 꿀배당 복병({odds}배) 💰")

    return bonus, tags, odds

def fetch_meet_data(meet_code, meet_name, date_str):
    params = {
        "serviceKey": API_KEY,
        "pageNo": "1",
        "numOfRows": "150",
        "meet": meet_code,
        "rc_date": date_str
    }
    full_url = f"{URL}?{urllib.parse.urlencode(params)}"
    print(f"[{meet_name}] V4.0 풀옵션 수집 요청: {date_str}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "*/*"
    }

    try:
        req = urllib.request.Request(full_url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)
        items = root.findall(".//item")
        if not items:
            return []

        races = {}
        for it in items:
            def gv(tag_list):
                for t in tag_list:
                    n = it.find(t)
                    if n is not None and n.text and n.text.strip():
                        return n.text.strip()
                return ""

            rc_no = gv(["rcNo", "rc_no"]) or "1"
            gate = gv(["chulNo", "chul_no", "gateNo", "hrNo"]) or "0"
            name = gv(["hrName", "hr_name"]) or "경주마"
            jockey = gv(["jkName", "jk_name"]) or "기수"
            trainer = gv(["trName", "tr_name"]) or "조교사"
            weight = gv(["wgBudam", "wg_budam"]) or "55.0"
            distance = gv(["rcDist", "rc_dist", "distance"]) or "1400"
            track = gv(["track", "track_state", "trackCond"]) or "양호"
            body_diff = gv(["wgHrDiff", "diff_wg", "wg_diff"]) or "0"
            recent_date = gv(["recentRcDate", "rcDate_recent", "recent_date"]) or ""
            rc_time = gv(["rcTime", "rc_time", "recordTime", "ordTime"]) or ""
            g1f_time = gv(["g1f", "g1fTime", "g1f_time", "g1fRecord"]) or ""
            win_odds = gv(["winOdds", "win_odds", "odds"]) or "0"
            pre_ord = gv(["preOrd", "pre_ord", "recentOrd", "ord_pre"]) or ""

            # 선행마 여부 (출발 통과 순위 1~2위)
            s1f_rank = gv(["g1p", "s1f", "g1pRank", "ord1p"]) or "99"
            is_front = True if s1f_rank in ["1", "2"] else False

            ord_no = "-"
            for child in it:
                tag_low = child.tag.lower()
                if any(k in tag_low for k in ["ord", "rank", "plc", "place", "chak"]):
                    txt = child.text.strip() if child.text else ""
                    if txt.isdigit():
                        ord_no = str(int(txt))
                        break

            key = f"{meet_name}_{rc_no}"
            if key not in races:
                races[key] = {
                    "meet_code": meet_code,
                    "meet_name": meet_name,
                    "race_no": rc_no,
                    "race_date": date_str,
                    "distance": distance,
                    "track": track,
                    "version": VERSION,
                    "horses": []
                }

            races[key]["horses"].append({
                "gate": str(int(gate)) if gate.isdigit() else gate,
                "name": name,
                "jockey": jockey,
                "trainer": trainer,
                "weight": weight,
                "distance": distance,
                "track": track,
                "body_diff": body_diff,
                "recent_date": recent_date,
                "rc_time": rc_time,
                "g1f_time": g1f_time,
                "win_odds": win_odds,
                "pre_ord": pre_ord,
                "is_front": is_front,
                "actual_ord": ord_no
            })

        # ==============================================================
        # AI V4.0 종합 스코어링 (기초체급 + 컨디션 + 스피드 + 전개 + 배당률)
        # ==============================================================
        for r in races.values():
            dist = 1400
            try:
                dist = int(re.findall(r'\d+', str(r["distance"]))[0])
            except:
                pass

            front_runner_count = sum(1 for h in r["horses"] if h["is_front"])

            for h in r["horses"]:
                score = 30.0
                tags = []
                g = int(h["gate"]) if str(h["gate"]).isdigit() else 5

                # 1. 기수 & 조교사 복승률
                jk_rate = JOCKEY_RATES.get(h["jockey"], 10.0)
                score += (jk_rate * 0.8)
                if jk_rate >= 25.0:
                    tags.append("특급 기수 🏇")

                tr_rate = TRAINER_RATES.get(h["trainer"], 12.0)
                score += (tr_rate * 0.5)
                if tr_rate >= 20.0:
                    tags.append("우수 마방 🏆")

                # 2. 거리별 게이트 가중치
                if dist <= 1300:
                    score += 15.0 if g <= 3 else 7.0 if g <= 7 else -4.0
                    if g <= 3:
                        tags.append("단거리 황금게이트 ⚡")
                elif dist >= 1700:
                    score += 8.0 if g <= 4 else 5.0 if g <= 8 else 2.0
                else:
                    score += 10.0 if g <= 4 else 6.0 if g <= 8 else 1.0

                # 3. 부담중량 가중치
                try:
                    clean_w = float(re.sub(r'[^0-9.]', '', str(h["weight"])))
                    w_factor = 3.5 if dist >= 1700 else 2.5
                    score += (55.0 - clean_w) * w_factor
                    if clean_w <= 52.5:
                        tags.append(f"경량 부중({clean_w}kg) ⚡")
                except:
                    pass

                # 4. [신규 1] 스피드 지수 (주파기록)
                s_bonus, s_tags = calculate_speed_rating(h["rc_time"], dist)
                score += s_bonus
                tags.extend(s_tags)

                # 5. [신규 2] 승급전의 벽 감지 (직전 경주 1착 후 갓 승급한 말)
                if str(h["pre_ord"]).strip() == "1":
                    score -= 5.0
                    tags.append("승급 첫 도전(검증 필요) 🧱")

                # 6. [신규 3] G1F 직선주로 스퍼트 탄력
                g_bonus, g_tags = analyze_g1f(h["g1f_time"])
                score += g_bonus
                tags.extend(g_tags)

                # 7. 주로 상태 (함수율)
                track_clean = str(r["track"]).strip()
                if any(k in track_clean for k in ["포화", "불량", "다습"]):
                    if g <= 3 or h["is_front"]:
                        score += 5.0
                        tags.append("젖은 주로 선행 유리 🌧️")
                elif "건조" in track_clean:
                    tags.append("건조 주로")

                # 8. 단독 선행 찬스
                if h["is_front"] and front_runner_count == 1:
                    score += 10.0
                    tags.append("단독 선행 찬스 🚀")

                # 9. [신규 4] 배당률 앙상블 & 꿀배당 복병마 감지
                o_bonus, o_tags, parsed_odds = analyze_odds_and_value(h["win_odds"], score)
                score += o_bonus
                tags.extend(o_tags)

                h["ai_score"] = round(score, 1)
                h["ai_tags"] = tags
                h["odds_display"] = f"{parsed_odds}배" if parsed_odds > 0 else "-"

            r["horses"].sort(key=lambda x: x["ai_score"], reverse=True)

        print(f"[{meet_name}] {len(races)}개 경주 V4.0 앙상블 분석 완료")
        return list(races.values())

    except Exception as e:
        print(f"[{meet_name}] 수신 에러: {e}")
        return []

def main():
    if not API_KEY:
        print("❌ KRA_API_KEY 미설정")
        return

    today_str = datetime.now(KST).strftime("%Y%m%d")
    all_races = []

    print(f"=== [{VERSION}] {today_str} 전국 경마 V4.0 풀옵션 분석 가동 ===")
    for m_code, m_name in MEET_CONFIG:
        res = fetch_meet_data(m_code, m_name, today_str)
        all_races.extend(res)
        time.sleep(1)

    if all_races:
        meet_order = {"서울": 1, "부산경남": 2, "영천": 3, "제주": 4}
        all_races.sort(key=lambda x: (
            meet_order.get(x["meet_name"], 9),
            int(x["race_no"]) if x["race_no"].isdigit() else 99
        ))
        with open("race_data.json", "w", encoding="utf-8") as f:
            json.dump(all_races, f, ensure_ascii=False, indent=2)
        print(f"🎉 성공: 총 {len(all_races)}개 경주 [{VERSION}] 분석 저장 완료!")
    else:
        print("수신된 데이터가 없습니다.")

if __name__ == "__main__":
    main()
