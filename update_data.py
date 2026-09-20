import os
import json
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import time

# =========================================================================
# 프로그램 명칭: KRA전국 승부예상AI_V3.0 (프로페셔널: 주로/체중/주기/전개 통합)
# =========================================================================
VERSION = "KRA전국 승부예상AI_V3.0"
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

def analyze_track_bonus(track_str, gate, is_front_runner):
    """[무기 1] 주로 상태(함수율/비)에 따른 유불리 분석"""
    bonus = 0.0
    tags = []
    track_clean = str(track_str).strip()
    
    # 포화(15~19%) or 불량(20% 이상) -> 젖은 주로 (선행/안쪽 코스 절대 유리)
    if any(k in track_clean for k in ["포화", "불량", "다습"]):
        if 1 <= gate <= 3 or is_front_runner:
            bonus += 6.0
            tags.append("젖은 주로 선행 유리 🌧️")
        elif gate >= 9:
            bonus -= 3.0
    # 건조(1~5%) -> 뻑뻑한 깊은 모래 (선행마 체력소모 심함, 추입마 유리)
    elif "건조" in track_clean:
        if gate <= 3:
            bonus += 2.0
        tags.append("건조 주로")
    return bonus, tags

def analyze_body_weight(weight_diff_str):
    """[무기 2] 당일 마체중 급변(±10kg) 컨디션 감지"""
    bonus = 0.0
    tags = []
    try:
        # 형식 예: "+12", "-14", "480(-8)" 등에서 괄호 안 숫자 추출
        match = re.search(r'([+-]?\d+)', str(weight_diff_str))
        if match:
            diff = int(match.group(1))
            if diff >= 12:
                bonus -= 5.0
                tags.append(f"체중 급증({diff}kg) 비만 주의 ⚠️")
            elif diff <= -12:
                bonus -= 7.0
                tags.append(f"체중 급감({diff}kg) 체력 저하 ⚠️")
            elif -3 <= diff <= 3:
                bonus += 3.0
                tags.append("체중 유지 최상 ✨")
    except:
        pass
    return bonus, tags

def analyze_rest_period(recent_date_str, today_str):
    """[무기 3] 실전 출전 주기 (공백기 페널티)"""
    bonus = 0.0
    tags = []
    try:
        if recent_date_str and len(recent_date_str) >= 8 and len(today_str) >= 8:
            d_recent = datetime.strptime(recent_date_str[:8], "%Y%m%d")
            d_today = datetime.strptime(today_str[:8], "%Y%m%d")
            days = (d_today - d_recent).days

            if days >= 90:
                bonus -= 8.0
                tags.append(f"장기 휴양마({days}일 공백) ⚠️")
            elif 21 <= days <= 45:
                bonus += 4.0
                tags.append("이상적 출전 주기 👍")
    except:
        pass
    return bonus, tags

def fetch_meet_data(meet_code, meet_name, date_str):
    params = {
        "serviceKey": API_KEY,
        "pageNo": "1",
        "numOfRows": "150",
        "meet": meet_code,
        "rc_date": date_str
    }
    full_url = f"{URL}?{urllib.parse.urlencode(params)}"
    print(f"[{meet_name}] V3.0 정밀 수집 요청: {date_str}")

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
            
            # 주행 습성(선행마 여부 파악: 출발 후 선두권 기록)
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
                "is_front": is_front,
                "actual_ord": ord_no
            })

        # 경주별 AI V3.0 점수 종합 연산
        for r in races.values():
            dist = 1400
            try:
                dist = int(re.findall(r'\d+', str(r["distance"]))[0])
            except:
                pass

            # [무기 4] 단독 선행마 자동 판별
            front_runner_count = sum(1 for h in r["horses"] if h["is_front"])

            for h in r["horses"]:
                score = 35.0
                tags = []
                g = int(h["gate"]) if str(h["gate"]).isdigit() else 5

                # 1. 기수 & 조교사 복승률
                jk_rate = JOCKEY_RATES.get(h["jockey"], 10.0)
                score += (jk_rate * 0.9)
                if jk_rate >= 25.0:
                    tags.append("특급 기수 🏇")
                elif jk_rate >= 20.0:
                    tags.append("상위 기수")

                tr_rate = TRAINER_RATES.get(h["trainer"], 12.0)
                score += (tr_rate * 0.6)
                if tr_rate >= 20.0:
                    tags.append("우수 마방 🏆")

                # 2. 거리별 게이트 가중치
                if dist <= 1300:
                    score += 15.0 if g <= 3 else 8.0 if g <= 7 else -4.0
                    if g <= 3:
                        tags.append("단거리 황금게이트 ⚡")
                elif dist >= 1700:
                    score += 9.0 if g <= 4 else 6.0 if g <= 8 else 3.0
                else:
                    score += 12.0 if g <= 4 else 7.0 if g <= 8 else 2.0

                # 3. 부담중량 가중치
                try:
                    clean_w = float(re.sub(r'[^0-9.]', '', str(h["weight"])))
                    w_factor = 3.5 if dist >= 1700 else 2.5
                    score += (55.0 - clean_w) * w_factor
                    if clean_w <= 52.5:
                        tags.append(f"경량 부중({clean_w}kg) ⚡")
                except:
                    pass

                # 4. [무기 1] 주로 상태(함수율)
                t_score, t_tags = analyze_track_bonus(r["track"], g, h["is_front"])
                score += t_score
                tags.extend(t_tags)

                # 5. [무기 2] 당일 마체중 급변 감지
                b_score, b_tags = analyze_body_weight(h["body_diff"])
                score += b_score
                tags.extend(b_tags)

                # 6. [무기 3] 출전 주기 분석
                r_score, r_tags = analyze_rest_period(h["recent_date"], date_str)
                score += r_score
                tags.extend(r_tags)

                # 7. [무기 4] 단독 선행 찬스
                if h["is_front"] and front_runner_count == 1:
                    score += 12.0
                    tags.append("단독 선행 찬스 🚀")

                h["ai_score"] = round(score, 1)
                h["ai_tags"] = tags

            r["horses"].sort(key=lambda x: x["ai_score"], reverse=True)

        print(f"[{meet_name}] {len(races)}개 경주 V3.0 프로페셔널 분석 완료")
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

    print(f"=== [{VERSION}] {today_str} 전국 경마 풀옵션 AI 분석 가동 ===")
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
