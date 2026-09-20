import os
import json
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import time

# ==============================================================
# 프로그램 명칭: KRA전국 승부예상AI_V2.5 (고급 통계 & 거리적성 모델)
# ==============================================================
VERSION = "KRA전국 승부예상AI_V2.5"
API_KEY = os.environ.get("KRA_API_KEY", "")
URL = "http://apis.data.go.kr/B551015/racedetailresult/getracedetailresult"

KST = timezone(timedelta(hours=9))

MEET_CONFIG = [
    ("1", "서울"),
    ("4", "영천"),
    ("2", "제주"),
    ("3", "부산경남")
]

# 1. 최근 1년 기수 복승률(1~2착 확률) 통계 DB (단위: %)
JOCKEY_RATES = {
    "문세영": 33.2, "서승운": 31.5, "최시대": 26.8, "다나카": 25.4,
    "빅투아르": 25.1, "김용근": 24.5, "다비드": 24.2, "유현명": 23.8,
    "정도윤": 22.5, "유승완": 21.0, "김혜선": 20.8, "송재철": 19.5,
    "이혁": 19.2, "임다빈": 18.5, "김동영": 17.8, "이성재": 16.5,
    "송경윤": 15.2, "전진구": 14.8, "김어수": 14.5, "손경민": 14.0,
    "조인권": 21.4, "이동하": 16.0, "임기원": 17.5, "장추열": 18.0,
    "최범현": 15.5, "마이아": 22.0, "조상범": 13.5, "김효정": 12.0
}

# 2. 최근 1년 조교사 복승률 통계 DB (단위: %)
TRAINER_RATES = {
    "서홍수": 24.5, "김영관": 28.0, "라이스": 25.2, "민장기": 22.1,
    "송문길": 21.5, "배휴준": 20.8, "정호익": 19.5, "최용건": 19.0,
    "구영준": 18.5, "김도현": 18.2, "안우성": 18.0, "임성실": 17.5,
    "박재우": 17.2, "이강서": 16.8, "전승규": 16.0, "강은석": 15.5,
    "서인석": 15.0, "백광열": 18.8, "심승태": 14.5, "조용배": 13.5
}

def calculate_ai_score_v25(gate, weight, jockey, trainer, distance_str):
    """
    [V2.5 엔진]
    - 기수 & 조교사 1년 복승률 수치 기반 정밀 환산
    - 경주 거리(단거리 vs 장거리)에 따른 게이트 / 부중 동적 가중치
    - AI 분석 태그 자동 추출
    """
    score = 40.0
    tags = []

    # 1. 기수 복승률 반영 (최대 35점)
    jk_rate = JOCKEY_RATES.get(jockey, 10.0)
    score += (jk_rate * 0.9)
    if jk_rate >= 25.0:
        tags.append("특급 기수 🏇")
    elif jk_rate >= 20.0:
        tags.append("상위 기수")

    # 2. 조교사 복승률 반영 (최대 20점)
    tr_rate = TRAINER_RATES.get(trainer, 12.0)
    score += (tr_rate * 0.6)
    if tr_rate >= 20.0:
        tags.append("우수 마방 🏆")

    # 3. 거리 파싱 (단거리: 1300m 이하 / 장거리: 1700m 이상)
    dist = 1400
    try:
        dist_nums = re.findall(r'\d+', str(distance_str))
        if dist_nums:
            dist = int(dist_nums[0])
    except:
        dist = 1400

    # 4. 거리별 게이트 가중치
    try:
        g = int(gate)
        if dist <= 1300:  # 단거리는 안쪽 코너 선점이 절대적
            if 1 <= g <= 3:
                score += 15.0
                tags.append("단거리 안쪽 황금게이트 ⚡")
            elif 4 <= g <= 7:
                score += 8.0
            else:
                score -= 4.0  # 단거리 외곽 불리 감점
        elif dist >= 1700:  # 장거리는 코너링 여유가 있어 게이트 영향 완만
            if 1 <= g <= 4:
                score += 9.0
            elif 5 <= g <= 8:
                score += 6.0
            else:
                score += 3.0
        else:  # 중거리 (1400~1600m)
            if 1 <= g <= 4:
                score += 12.0
            elif 5 <= g <= 8:
                score += 7.0
            else:
                score += 2.0
    except:
        score += 5.0

    # 5. 거리별 부담중량 가중치 (*52.5 등 기호 정제)
    try:
        clean_w = re.sub(r'[^0-9.]', '', str(weight))
        w = float(clean_w)
        # 장거리일수록 부담중량 1kg의 피로도가 기하급수적으로 증가
        weight_factor = 3.5 if dist >= 1700 else 2.5
        weight_bonus = (55.0 - w) * weight_factor
        score += weight_bonus
        if w <= 52.5:
            tags.append(f"경량 부중 유리({w}kg) 🪶")
    except:
        pass

    return round(score, 1), tags

def fetch_meet_data(meet_code, meet_name, date_str):
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
            distance = gv(["rcDist", "rc_dist", "distance", "dist"]) or "1400"

            # 착순 자동 감지
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
                    "version": VERSION,
                    "horses": []
                }

            score, tags = calculate_ai_score_v25(gate, weight, jockey, trainer, distance)

            races[key]["horses"].append({
                "gate": str(int(gate)) if gate.isdigit() else gate,
                "name": name,
                "jockey": jockey,
                "trainer": trainer,
                "weight": weight,
                "distance": distance,
                "actual_ord": ord_no,
                "ai_score": score,
                "ai_tags": tags
            })

        for r in races.values():
            r["horses"].sort(key=lambda x: x["ai_score"], reverse=True)

        print(f"[{meet_name}] {len(races)}개 경주 V2.5 고급 분석 완료")
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

    print(f"=== [{VERSION}] {today_str} 전국 경마 통계/거리적성 정밀 분석 시작 ===")
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
