import os
import json
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import time

# ==========================================
# 프로그램 명칭: KRA전국 승부예상AI_V2.0
# ==========================================
VERSION = "KRA전국 승부예상AI_V2.0"
API_KEY = os.environ.get("KRA_API_KEY", "")
URL = "http://apis.data.go.kr/B551015/racedetailresult/getracedetailresult"

# 한국 표준시(KST) 설정
KST = timezone(timedelta(hours=9))

# 전국 4대 경마장 설정 (1: 서울, 4: 영천, 2: 제주, 3: 부산경남)
MEET_CONFIG = [
    ("1", "서울"),
    ("4", "영천"),
    ("2", "제주"),
    ("3", "부산경남")
]

# 상위 기수 가중치
TOP_JOCKEYS = {
    "문세영": 25.0, "김용근": 20.0, "유승완": 18.0, "송재철": 17.0,
    "이혁": 16.0, "임다빈": 15.0, "빅투아르": 22.0, "다나카": 22.0,
    "서승운": 24.0, "유현명": 21.0, "최시대": 21.0, "다비드": 21.0,
    "정도윤": 20.0, "김동영": 17.0, "김혜선": 18.0, "이성재": 16.0,
    "송경윤": 15.0, "김어수": 15.0, "손경민": 14.0, "전진구": 15.0
}

def calculate_ai_score(gate, weight, jockey):
    score = 50.0
    score += TOP_JOCKEYS.get(jockey, 10.0)

    try:
        g = int(gate)
        if 1 <= g <= 4:
            score += 12.0
        elif 5 <= g <= 8:
            score += 8.0
        else:
            score += 4.0
    except:
        score += 5.0

    try:
        clean_w = re.sub(r'[^0-9.]', '', str(weight))
        w = float(clean_w)
        score += (55.0 - w) * 2.5
    except:
        pass

    return round(score, 1)

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
                    "version": VERSION,
                    "horses": []
                }

            score = calculate_ai_score(gate, weight, jockey)

            races[key]["horses"].append({
                "gate": str(int(gate)) if gate.isdigit() else gate,
                "name": name,
                "jockey": jockey,
                "trainer": trainer,
                "weight": weight,
                "actual_ord": ord_no,
                "ai_score": score
            })

        for r in races.values():
            r["horses"].sort(key=lambda x: x["ai_score"], reverse=True)

        print(f"[{meet_name}] {len(races)}개 경주 수신 및 착순 추출 완료")
        return list(races.values())

    except Exception as e:
        print(f"[{meet_name}] 수신 에러: {e}")
        return []

def main():
    if not API_KEY:
        print("❌ KRA_API_KEY 환경변수가 설정되지 않았습니다.")
        return

    today_str = datetime.now(KST).strftime("%Y%m%d")
    all_races = []

    print(f"=== [{VERSION}] {today_str} 전국 경마 분석 시작 ===")
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
