import os
import json
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import time

# =========================================================================
# 프로그램 명칭: KRA전국 승부예상AI_V5.0 (프로 마방·조교·콤비 특수 엔진)
# =========================================================================
VERSION = "KRA전국 승부예상AI_V5.0"
API_KEY = os.environ.get("KRA_API_KEY", "")
URL = "http://apis.data.go.kr/B551015/racedetailresult/getracedetailresult"

KST = timezone(timedelta(hours=9))

MEET_CONFIG = [
    ("1", "서울"),
    ("4", "영천"),
    ("2", "제주"),
    ("3", "부산경남")
]

BACKUP_DISTANCES = {
    ("서울", "1"): "1200", ("서울", "2"): "1400", ("서울", "3"): "1300",
    ("서울", "4"): "1700", ("서울", "5"): "1800", ("서울", "6"): "1200",
    ("서울", "7"): "1300", ("서울", "8"): "1400", ("서울", "9"): "1800",
    ("서울", "10"): "2000", ("서울", "11"): "1200",
    ("영천", "1"): "1400", ("영천", "2"): "1600", ("영천", "3"): "1200",
    ("영천", "4"): "1400", ("영천", "5"): "1200", ("영천", "6"): "1200",
    ("제주", "1"): "900", ("제주", "2"): "900", ("제주", "3"): "900",
    ("제주", "4"): "1000", ("제주", "5"): "1000", ("제주", "6"): "1110",
    ("제주", "7"): "1110", ("제주", "8"): "1200"
}

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

def fetch_live_chulma_distances():
    dist_map = {}
    meets = [("1", "서울"), ("3", "부산경남"), ("2", "제주")]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*"
    }

    print("🌐 마사회 공식 출마표 전산망에서 실시간 경주거리 수집 중...")
    for m_code, m_name in meets:
        try:
            url = f"https://race.kra.co.kr/chulmainfo/ChulmaDetailInfoList.do?Act=02&Sub=1&meet={m_code}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as res:
                html = res.read().decode('euc-kr', errors='ignore')

            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
            for row in rows:
                dist_match = re.search(r'(\d{3,4})\s*M', row, re.IGNORECASE)
                if dist_match:
                    dist_val = dist_match.group(1)
                    target_meet = m_name
                    if "영천" in row:
                        target_meet = "영천"
                    elif "부경" in row or "부산" in row:
                        target_meet = "부산경남"
                    elif "제주" in row:
                        target_meet = "제주"
                    elif "서울" in row:
                        target_meet = "서울"

                    tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
                    for td in tds:
                        clean_td = re.sub(r'<.*?>', '', td).strip()
                        if clean_td.isdigit() and 1 <= int(clean_td) <= 16:
                            rc_no = str(int(clean_td))
                            dist_map[(target_meet, rc_no)] = dist_val
                            break
        except Exception:
            continue

    if dist_map:
        print(f"✅ 마사회 실시간 출마표 연동 성공! 총 {len(dist_map)}개 경주거리 자동 확보")
    return dist_map

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

def calculate_speed_rating_dual(current_time_str, past_time_str, rating_str, dist, is_post_race=False):
    bonus = 0.0
    tags = []
    base_time = {
        900: 55.0, 1000: 61.5, 1110: 69.0, 1200: 74.8, 1300: 82.0, 1400: 88.5,
        1600: 102.5, 1700: 111.5, 1800: 117.5, 2000: 133.0
    }.get(dist, dist * 0.063 + 0.5)

    if is_post_race:
        sec = parse_time_seconds(current_time_str)
        if sec and sec > 30.0:
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

    past_sec = parse_time_seconds(past_time_str)
    if past_sec and past_sec > 30.0:
        diff = base_time - past_sec
        if diff >= 1.0:
            bonus += 10.0
            tags.append(f"과거 스피드 최상({round(past_sec,1)}초) 🏎️")
        elif diff >= 0.0:
            bonus += 5.0
            tags.append("과거 기록 우수")
        elif diff <= -2.0:
            bonus -= 4.0
    else:
        try:
            r = int(re.sub(r'[^0-9]', '', str(rating_str)))
            if r >= 65:
                bonus += 8.0
                tags.append(f"능력평점 최상(R{r}) 🏎️")
            elif r >= 45:
                bonus += 4.0
                tags.append(f"능력평점 우수(R{r})")
        except:
            pass

    return bonus, tags

# =========================================================================
# 🎯 [V5.0 신규] 마구(장구), 새벽조교, 단짝 콤비 정밀 분석 함수군
# =========================================================================
def analyze_gear(gear_str):
    """[V5.0 무기 1] 마구(장구) 변경 분석: 눈가면 첫 착용 등"""
    bonus = 0.0
    tags = []
    g_str = str(gear_str).strip()
    if any(k in g_str for k in ["눈가면(신규)", "블링커(신규)", "신규눈가면", "눈가면신규", "블링커신규"]):
        bonus += 6.0
        tags.append("눈가면 첫 착용 🤿")
    elif any(k in g_str for k in ["눈가면", "블링커", "Blinker"]):
        bonus += 2.0
        tags.append("눈가면 착용 🤿")
    elif any(k in g_str for k in ["혀묶음끈", "승인장구", "특수재갈"]):
        bonus += 2.0
        tags.append("특수 장구 보완 🤿")
    return bonus, tags

def analyze_training(training_str, jockey_name):
    """[V5.0 무기 2] 새벽 조교(훈련) 강도 & 주전 기수 전담 조교 분석"""
    bonus = 0.0
    tags = []
    t_str = str(training_str).strip()
    # 1. 전력질주 습보 훈련 감지
    if any(k in t_str for k in ["습보", "강훈련", "강구보", "습보2회", "습보3회"]):
        bonus += 7.0
        tags.append("새벽 습보 강훈련 🏋️")
    # 2. 기수 직접 조교 감지 (마방 승부 신호)
    if jockey_name and (jockey_name in t_str or "기수조교" in t_str or "기수직접" in t_str):
        bonus += 5.0
        tags.append("기수 직접 전담조교 🚴")
    return bonus, tags

def analyze_combo(combo_str):
    """[V5.0 무기 3] 기수-경주마 단짝 콤비 전적 분석"""
    bonus = 0.0
    tags = []
    c_str = str(combo_str).strip()
    if any(k in c_str for k in ["1승", "2승", "3승", "우승", "동반1위", "입상2회", "입상 2회"]):
        bonus += 6.0
        tags.append("찰떡 콤비(우승 경험) 🤝")
    elif any(k in c_str for k in ["2착", "입상1회", "입상 1회", "동반입상", "동반 2착"]):
        bonus += 3.0
        tags.append("동반 입상 이력 🤝")
    return bonus, tags

def analyze_g1f(g1f_str, is_post_race=False):
    bonus = 0.0
    tags = []
    if not is_post_race:
        return bonus, tags
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

def fetch_meet_data(meet_code, meet_name, date_str, live_distances):
    params = {
        "serviceKey": API_KEY,
        "pageNo": "1",
        "numOfRows": "150",
        "meet": meet_code,
        "rc_date": date_str
    }
    full_url = f"{URL}?{urllib.parse.urlencode(params)}"
    print(f"[{meet_name}] 마사회 데이터 수신 요청: {date_str}")

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

            raw_rc_no = gv(["rcNo", "rc_no"]) or "1"
            rc_no = str(int(raw_rc_no)) if raw_rc_no.isdigit() else raw_rc_no

            gate = gv(["chulNo", "chul_no", "gateNo", "hrNo"]) or "0"
            name = gv(["hrName", "hr_name"]) or "경주마"
            jockey = gv(["jkName", "jk_name"]) or "기수"
            trainer = gv(["trName", "tr_name"]) or "조교사"
            weight = gv(["wgBudam", "wg_budam"]) or "55.0"
            track = gv(["track", "track_state", "trackCond", "weather"]) or "양호"

            rc_time = gv(["rcTime", "rc_time", "record", "rcRecord", "raceRcd", "ordTime"]) or ""
            past_time = gv(["bestRecord", "bestRcTime", "recentRecord", "recentRcTime", "preRcTime", "bestTime", "fastTime"]) or ""
            rating = gv(["rating", "rat", "hr_rating"]) or ""
            g1f_time = gv(["g1f", "g1f_time", "g1fTime", "g1fRecord", "goffPassRcd", "g_1f"]) or ""
            win_odds = gv(["winOdds", "win_odds", "win_rate", "odds", "singleOdds"]) or "0"
            pre_ord = gv(["preOrd", "pre_ord", "recentOrd", "preRcOrd", "rcResult1"]) or ""

            # [V5.0 신규 데이터 태그]
            gear_info = gv(["gear", "janggu", "hrequip", "equip", "blinker", "equipName", "chulmaGear"]) or ""
            training_info = gv(["training", "jogyo", "trackwork", "trainType", "trainRider", "chulmaTraining"]) or ""
            combo_info = gv(["combo", "dongban", "jkHrRecord", "jockeyCombo", "chulmaCombo"]) or ""

            s1f_rank = gv(["g1p", "s1f", "g1pRank", "ord1p", "s1fRank", "ffurPassRcd"]) or "99"
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
                    "distance": "1400",
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
                "track": track,
                "rc_time": rc_time,
                "past_time": past_time,
                "rating": rating,
                "g1f_time": g1f_time,
                "win_odds": win_odds,
                "pre_ord": pre_ord,
                "gear_info": gear_info,
                "training_info": training_info,
                "combo_info": combo_info,
                "is_front": is_front,
                "actual_ord": ord_no
            })

        # ==============================================================
        # 🎯 V5.0 풀옵션 AI 채점 (거리 + 듀얼스피드 + 장구 + 조교 + 콤비)
        # ==============================================================
        for r in races.values():
            meet = r["meet_name"]
            r_no = str(int(r["race_no"])) if str(r["race_no"]).isdigit() else str(r["race_no"])

            if (meet, r_no) in live_distances:
                actual_dist = live_distances[(meet, r_no)]
            elif (meet, r_no) in BACKUP_DISTANCES:
                actual_dist = BACKUP_DISTANCES[(meet, r_no)]
            else:
                actual_dist = "1400"

            r["distance"] = actual_dist
            dist = int(actual_dist)

            has_finished = any(h["actual_ord"].isdigit() for h in r["horses"])
            front_runner_count = sum(1 for h in r["horses"] if h["is_front"])

            for h in r["horses"]:
                h["distance"] = str(dist)
                score = 30.0
                tags = []
                g = int(h["gate"]) if str(h["gate"]).isdigit() else 5

                # 1. 기수 & 조교사 복승률
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

                # 4. 듀얼 모드 스피드 지수
                s_bonus, s_tags = calculate_speed_rating_dual(
                    h["rc_time"], h["past_time"], h["rating"], dist, is_post_race=has_finished
                )
                score += s_bonus
                tags.extend(s_tags)

                # 5. [V5.0 신규 1] 마구(장구) 변경 분석
                gear_bonus, gear_tags = analyze_gear(h["gear_info"])
                score += gear_bonus
                tags.extend(gear_tags)

                # 6. [V5.0 신규 2] 새벽 조교 강도 & 기수 전담 조교
                train_bonus, train_tags = analyze_training(h["training_info"], h["jockey"])
                score += train_bonus
                tags.extend(train_tags)

                # 7. [V5.0 신규 3] 기수-말 찰떡 콤비 분석
                combo_bonus, combo_tags = analyze_combo(h["combo_info"])
                score += combo_bonus
                tags.extend(combo_tags)

                # 8. 승급전 감지
                if str(h["pre_ord"]).strip() in ["1", "01"]:
                    score -= 5.0
                    tags.append("승급 첫 도전(검증 필요) 🧱")

                # 9. G1F 직선주로 스퍼트 (경기 후)
                g_bonus, g_tags = analyze_g1f(h["g1f_time"], is_post_race=has_finished)
                score += g_bonus
                tags.extend(g_tags)

                # 10. 단독 선행
                if h["is_front"] and front_runner_count == 1:
                    score += 10.0
                    tags.append("단독 선행 찬스 🚀")

                # 11. 배당률 앙상블 & 꿀배당 감지
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

    live_distances = fetch_live_chulma_distances()
    target_date = get_target_race_date()
    print(f"=== [{VERSION}] {target_date} 프로 특수엔진 가동 ===")

    all_races = []
    for m_code, m_name in MEET_CONFIG:
        res = fetch_meet_data(m_code, m_name, target_date, live_distances)
        all_races.extend(res)

    if all_races:
        meet_order = {"서울": 1, "부산경남": 2, "영천": 3, "제주": 4}
        all_races.sort(key=lambda x: (
            meet_order.get(x["meet_name"], 9),
            int(x["race_no"]) if x["race_no"].isdigit() else 99
        ))
        with open("race_data.json", "w", encoding="utf-8") as f:
            json.dump(all_races, f, ensure_ascii=False, indent=2)
        print(f"🎉 성공: [{VERSION}] {target_date} 프로 특수엔진 갱신 완료!")
    else:
        print("데이터를 가져오지 못했습니다.")

if __name__ == "__main__":
    main()
