import os
import requests
import pandas as pd
from datetime import datetime

FIXTURES_CSV = "nba_fixtures.csv"

# 包含全部 30 支球队的 ESPN ID
TEAM_IDS = {
    "ATL": 1, "BOS": 2, "NOP": 3, "CHI": 4, "CLE": 5, "DAL": 6, "DEN": 7, "DET": 8, 
    "GSW": 9, "HOU": 10, "IND": 11, "LAC": 12, "LAL": 13, "MIA": 14, "MIL": 15, "MIN": 16, 
    "BKN": 17, "NYK": 18, "ORL": 19, "PHI": 20, "PHX": 21, "POR": 22, "SAC": 23, "SAS": 24, 
    "OKC": 25, "UTA": 26, "WAS": 27, "TOR": 28, "MEM": 29, "CHA": 30
}

# 中文队名对照
TEAM_CN = {
    "ATL": "老鹰", "BOS": "凯尔特人", "NOP": "鹈鹕", "CHI": "公牛", "CLE": "骑士", "DAL": "独行侠", 
    "DEN": "掘金", "DET": "活塞", "GSW": "勇士", "HOU": "火箭", "IND": "步行者", "LAC": "快船", 
    "LAL": "湖人", "MIA": "热火", "MIL": "雄鹿", "MIN": "森林狼", "BKN": "篮网", "NYK": "尼克斯", 
    "ORL": "魔术", "PHI": "76人", "PHX": "太阳", "POR": "开拓者", "SAC": "国王", "SAS": "马刺", 
    "OKC": "雷霆", "UTA": "爵士", "WAS": "奇才", "TOR": "猛龙", "MEM": "灰熊", "CHA": "黄蜂"
}

def push_to_wechat(md_text):
    key = os.environ.get("SERVERCHAN_KEY")
    if not key: return
    try:
        r = requests.post(f"https://sctapi.ftqq.com/{key}.send", data={"title": f"🏀 NBA量化预测 {datetime.now().strftime('%m月%d日')}", "desp": md_text}, timeout=10)
        print(f"推送状态: {r.status_code}")
    except Exception as e:
        print(f"微信异常: {e}")

def get_team_stat(team_abbr):
    team_id = TEAM_IDS.get(team_abbr.upper())
    if not team_id: return None
    
    # 使用极其稳定的球队信息接口
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}"
    try:
        r = requests.get(url, timeout=15)
        data = r.json()
        
        # 深度解析取场均得分和场均失分
        stats = data.get("team", {}).get("record", {}).get("items", [])[0].get("stats", [])
        ppg = 110.0
        opp_ppg = 110.0
        for stat in stats:
            if stat.get("name") == "avgPoints":
                ppg = float(stat.get("value"))
            elif stat.get("name") == "avgPointsAgainst":
                opp_ppg = float(stat.get("value"))
                
        return {"name": TEAM_CN.get(team_abbr.upper(), team_abbr), "ppg": ppg, "opp_ppg": opp_ppg}
    except Exception as e:
        print(f"拉取 {team_abbr} 数据失败: {e}")
        return None

def main():
    try:
        fixtures = pd.read_csv(FIXTURES_CSV, encoding="utf-8-sig")
    except:
        print("找不到 nba_fixtures.csv")
        return

    md = f"🏀 NBA 量化预测 ({datetime.now().strftime('%m-%d')})\n\n"

    for _, row in fixtures.iterrows():
        home_abbr = str(row['home']).strip().upper()
        away_abbr = str(row['away']).strip().upper()
        
        home = get_team_stat(home_abbr)
        away = get_team_stat(away_abbr)

        if not home or not away:
            md += f"⚠️ 获取 {home_abbr} 或 {away_abbr} 数据失败\n\n"
            continue

        # 篮球最经典的预测公式：两队预期得分 = (己方场均得分 + 对方场均失分) / 2 ± 主场优势
        home_expected = (home['ppg'] + away['opp_ppg']) / 2 + 2.5
        away_expected = (away['ppg'] + home['opp_ppg']) / 2 - 2.5

        spread = home_expected - away_expected
        total = home_expected + away_expected
        spread_team = home['name'] if spread > 0 else away['name']

        md += f"【{home['name']}(主) vs {away['name']}(客)】\n"
        md += f"📊 预期比分：{home['name']} {home_expected:.1f} - {away['name']} {away_expected:.1f}\n"
        md += f"⚖️ 理论让分：{spread_team} 让 {abs(spread):.1f} 分\n"
        md += f"📈 理论大小：{total:.1f} 分\n\n"

    push_to_wechat(md)

if __name__ == "__main__":
    main()
