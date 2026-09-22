import os
import json
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import time

# =========================================================================
# 프로그램 명칭: KRA전국 승부예상AI_V4.0 (만능 거리 자동 탐색기 탑재본)
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

JOCKEY_RATES = {
    "문세영": 33.2, "서승운": 31.5, "최시대": 26.8, "다나카": 25.4,
    "빅투아르": 25.1, "김용근": 24.5, "다비드": 24.2, "유현명": 23.8,
    "정도윤": 22.5, "유승완": 21.0, "김혜선": 20.8, "송재철": 19.5,
    "이혁": 19.2, "임다빈": 18.5, "김동영": 17.8, "이성재": 16.5,
    "송경윤": 15.2, "전진구": 14.8, "김어수": 14.5, "손경민": 14.0,
    "조인권": 21.4, "이동하": 16.0, "임기원": 17.5, "장추열": 18.0,
    "최범현": 15.5, "마이아": 22.0, "조상범": 13.5, "김효정": 12.0
}

TRAINER_RATES = {
    "서홍수": 24.5, "김영관": 28.0, "라이스": 25.2, "민장기": 22.1,
    "송문길": 21.5, "배휴준": 20.8, "정호익": 19.5, "최용건": 19.0,
    "구영준": 18.5, "김도현": 18.2, "안우성": 18.0, "임성실": 17.5,
    "박재우": 17.2, "이강서": 16.8, "전승규": 16.0, "강은석": 15.5,
    "서인석": 15.0, "백광열": 18.8, "심승태": 14.5, "조용배": 13.5
}

def parse_time_seconds(time_str):
    try:
        t = str(time_str).strip().replace("'", "").replace('"', '')
        if not t:
            return None
        if ":" in t:
            parts = t.split(":")
            return float(parts[0]) * 60 + float(parts[1])
        if t.count(".") == 2:
            parts = t.split(".")
            return float(parts[0]) * 60 + float(f"{parts[1]}.{parts[2]}")
        val = float(t)
        if val > 30.0:
            return val
    except:
        pass
    return None

def calculate_speed_rating(time_str, dist):
    bonus = 0.0
    tags = []
    sec = parse_time_seconds(time_str)
    if sec and sec > 30.0:
        base_time = {
            1000: 61.5, 1200: 74.8, 1300: 82.0, 1400: 88.5,
            1600: 102.5, 1700: 111.5, 1800: 117.5, 2000: 133.0
        }.get(dist, dist * 0.063 + 0.5)

        diff = base_time - sec
        if diff >= 1.0:
            bonus += 10.0
            tags.append(f"스피드 지수 최상({round(sec,1)}초) 🏎️")
        elif diff >= 0.0:
            bonus += 5.0
            tags.append("기록 우수")
        elif diff <= -2.0:
            bonus -= 5.0
    return bonus, tags

def analyze_g1f(g1f_str):
    bonus = 0.0
    tags = []
    try:
        m = re.search(r'(\d+\.?\d*)', str(g1f_str))
        if m:
            g1f = float(m.group(1))
            if 11.0 <= g1f <= 12.8:
                bonus += 7.0
                tags.append(f"직선주로 스퍼트 최강({g1f}초) 🚀")
            elif 12.9 <= g1f <= 13.2:
                bonus += 3.0
            elif g1f >= 14.0:
                bonus -= 4.0
    except:
        pass
    return bonus, tags

def analyze_odds_and_value(odds_str, base_score):
    bonus = 0.0
    tags = []
    odds = 0.0
    try:
        m = re.search(r'(\d+\.?\d*)', str(odds_str))
        if m:
            odds = float(m.group(1))
    except:
        odds = 0.0

    if odds > 1.0:
        if odds <= 3.2:
            bonus += 8.0
            tags.append(f"대중 강력 지지({odds}배) 🔥")
        elif odds <= 6.5:
            bonus += 4.0
        elif odds >= 35.0:
            bonus -= 5.0

        if base_score >= 70.0 and 7.0 <= odds <= 25.0:
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
    print(f"[{meet_name}] V4.0 데이터 수신 요청: {date_str}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "*/*"
    }

    try:
        req = urllib.request.Request(full_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)
        items = root.findall(".//item")
        if not items:
            return []

        # 로그 확인용: 첫 번째 아이템의 모든 태그 출력
        sample_tags = [f"{c.tag}={c.text}" for c in items[0] if c.text]
        print(f"[{meet_name}] 원본 태그 확인: {sample_tags[:6]}")

        races = {}
        for it in items:
            def gv(tag_list):
                for t in tag_list:
                    n = it.find(t)
                    if n is not None and n.text and n.text.strip():
                        return n.text.strip()
                    for child in it:
                        if child.tag.lower() == t.lower():
                            if child.text and child.text.strip():
                                return child.text.strip()
                return ""

            rc_no = gv(["rcNo", "rc_no"]) or "1"
            gate = gv(["chulNo", "chul_no", "gateNo", "hrNo"]) or "0"
            name = gv(["hrName", "hr_name"]) or "경주마"
            jockey = gv(["jkName", "jk_name"]) or "기수"
            trainer = gv(["trName", "tr_name"]) or "조교사"
            weight = gv(["wgBudam", "wg_budam"]) or "55.0"
            track = gv(["track", "track_state", "trackCond", "weather"]) or "양호"

            # 🎯 [만능 경주 거리 자동 탐색기]
            distance = ""
            # 1단계: 태그명에 dist, ds, meter, len 등이 포함된 태그 탐색
            for child in it:
                tag_low = child.tag.lower()
                if any(k in tag_low for k in ["dist", "ds", "meter", "len", "kori"]):
                    txt = child.text.strip() if child.text else ""
                    nums = re.findall(r'\d+', txt)
                    if nums and 800 <= int(nums[0]) <= 3000:
                        distance = nums[0]
                        break

            # 2단계: 한국 경마 공식 표준 거리 숫자 자동 감지
            if not distance:
                standard_dists = [800, 900, 1000, 1110, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000, 2200, 2300]
                for child in it:
                    txt = child.text.strip() if child.text else ""
                    nums = re.findall(r'\d+', txt)
                    if nums and int(nums[0]) in standard_dists:
                        distance = nums[0]
                        break

            if not distance:
                distance = "1400"
            
            rc_time = gv(["rcTime", "rc_time", "record", "rcRecord", "ordTime"]) or ""
            g1f_time = gv(["g1f", "g1f_time", "g1fTime", "g1fRecord", "g_1f"]) or ""
            win_odds = gv(["winOdds", "win_odds", "win_rate", "odds", "singleOdds"]) or "0"
            pre_ord = gv(["preOrd", "pre_ord", "recentOrd", "preRcOrd", "rcResult1"]) or ""

            s1f_rank = gv(["g1p", "s1f", "g1pRank", "ord1p", "s1fRank"]) or "99"
            is_front = True if s1f_rank in ["1", "2", "01", "02"] else False

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
                "rc_time": rc_time,
                "g1f_time": g1f_time,
                "win_odds": win_odds,
                "pre_ord": pre_ord,
                "is_front": is_front,
                "actual_ord": ord_no
            })

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

                # 1. 기수 & 조교사
                jk_rate = JOCKEY_RATES.get(h["jockey"], 10.0)
                score += (jk_rate * 0.8)
                if jk_rate >= 25.0:
                    tags.append("특급 기수 🏇")
                elif jk_rate >= 20.0:
                    tags.append("상위 기수")

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

                # 4. 스피드 지수
                s_bonus, s_tags = calculate_speed_rating(h["rc_time"], dist)
                score += s_bonus
                tags.extend(s_tags)

                # 5. 승급전
                if str(h["pre_ord"]).strip() in ["1", "01"]:
                    score -= 5.0
                    tags.append("승급 첫 도전(검증 필요) 🧱")

                # 6. G1F 직선주로 스퍼트
                g_bonus, g_tags = analyze_g1f(h["g1f_time"])
                score += g_bonus
                tags.extend(g_tags)

                # 7. 단독 선행
                if h["is_front"] and front_runner_count == 1:
                    score += 10.0
                    tags.append("단독 선행 찬스 🚀")

                # 8. 배당률 앙상블
                o_bonus, o_tags, parsed_odds = analyze_odds_and_value(h["win_odds"], score)
                score += o_bonus
                tags.extend(o_tags)

                h["ai_score"] = round(score, 1)
                h["ai_tags"] = tags
                h["odds_display"] = f"{parsed_odds}배" if parsed_odds > 0 else "-"

            r["horses"].sort(key=lambda x: x["ai_score"], reverse=True)

        return list(races.values())

    except Exception as e:
        print(f"[{meet_name}] 수신 에러: {e}")
        return []

def get_target_race_date():
    now = datetime.now(KST)
    weekday = now.weekday()
    if weekday in [4, 5, 6]:
        return now.strftime("%Y%m%d")
    days_back = weekday + 1
    last_sunday = now - timedelta(days=days_back)
    return last_sunday.strftime("%Y%m%d")

def main():
    if not API_KEY:
        print("❌ KRA_API_KEY 미설정")
        return

    target_date = get_target_race_date()
    print(f"=== [{VERSION}] 타겟 경마일 {target_date} 거리 정밀 분석 시작 ===")

    all_races = []
    for m_code, m_name in MEET_CONFIG:
        res = fetch_meet_data(m_code, m_name, target_date)
        all_races.extend(res)

    if all_races:
        meet_order = {"서울": 1, "부산경남": 2, "영천": 3, "제주": 4}
        all_races.sort(key=lambda x: (
            meet_order.get(x["meet_name"], 9),
            int(x["race_no"]) if x["race_no"].isdigit() else 99
        ))
        with open("race_data.json", "w", encoding="utf-8") as f:
            json.dump(all_races, f, ensure_ascii=False, indent=2)
        print(f"🎉 성공: [{VERSION}] {target_date} 전 경주 실제 거리 반영 완료!")
    else:
        print("데이터를 가져오지 못했습니다.")

if __name__ == "__main__":
    main()
