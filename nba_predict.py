import os
import requests
import pandas as pd
import glob
from datetime import datetime
from scipy.stats import norm  # 👈 新增：用于计算正态分布概率

FIXTURES_CSV = "nba_fixtures.csv"

TEAM_IDS = {
    "ATL": 1, "BOS": 2, "NOP": 3, "CHI": 4, "CLE": 5, "DAL": 6, "DEN": 7, "DET": 8, 
    "GSW": 9, "HOU": 10, "IND": 11, "LAC": 12, "LAL": 13, "MIA": 14, "MIL": 15, "MIN": 16, 
    "BKN": 17, "NYK": 18, "ORL": 19, "PHI": 20, "PHX": 21, "POR": 22, "SAC": 23, "SAS": 24, 
    "OKC": 25, "UTA": 26, "WAS": 27, "TOR": 28, "MEM": 29, "CHA": 30
}

TEAM_CN = {
    "ATL": "老鹰", "BOS": "凯尔特人", "NOP": "鹈鹕", "CHI": "公牛", "CLE": "骑士", "DAL": "独行侠", 
    "DEN": "掘金", "DET": "活塞", "GSW": "勇士", "HOU": "火箭", "IND": "步行者", "LAC": "快船", 
    "LAL": "湖人", "MIA": "热火", "MIL": "雄鹿", "MIN": "森林狼", "BKN": "篮网", "NYK": "尼克斯", 
    "ORL": "魔术", "PHI": "76人", "PHX": "太阳", "POR": "开拓者", "SAC": "国王", "SAS": "马刺", 
    "OKC": "雷霆", "UTA": "爵士", "WAS": "奇才", "TOR": "猛龙", "MEM": "灰熊", "CHA": "黄蜂"
}

# 统计学常数（NBA 历史大数据统计得出）
STD_DEV_SPREAD = 12.5  # 分差的标准差
STD_DEV_TOTAL = 18.0   # 总分的标准差
MARKET_TOTAL_LINE = 225.5 # 假设一个平均大小分盘口，用于对比

def push_to_wechat(md_text):
    key = os.environ.get("SERVERCHAN_KEY")
    if not key: return
    try:
        requests.post(f"https://sctapi.ftqq.com/{key}.send", data={"title": f"🏀 NBA预测与战绩 {datetime.now().strftime('%m月%d日')}", "desp": md_text}, timeout=10)
    except Exception as e:
        print(f"微信异常: {e}")

def get_team_stat(team_abbr):
    team_id = TEAM_IDS.get(team_abbr.upper())
    if not team_id: return None
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        stats = data.get("team", {}).get("record", {}).get("items", [])[0].get("stats", [])
        ppg, opp_ppg = 110.0, 110.0
        for stat in stats:
            if stat.get("name") == "avgPoints": ppg = float(stat.get("value"))
            elif stat.get("name") == "avgPointsAgainst": opp_ppg = float(stat.get("value"))
        return {"name": TEAM_CN.get(team_abbr.upper(), team_abbr), "ppg": ppg, "opp_ppg": opp_ppg}
    except Exception:
        return None

def get_performance_report():
    # (保留之前的复盘逻辑，为了节省篇幅这里略去，直接复制你上一条的即可)
    pass # 请把上一条代码里的 get_performance_report 和 get_actual_results 完整复制到这里

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

        if not home or not away: continue

        # 1. 计算预期得分
        home_expected = (home['ppg'] + away['opp_ppg']) / 2 + 2.5
        away_expected = (away['ppg'] + home['opp_ppg']) / 2 - 2.5

        spread = home_expected - away_expected
        total = home_expected + away_expected

        # 2. 用正态分布计算概率
        # 主胜概率：分差大于 0 的概率
        home_win_prob = 1 - norm.cdf(0, loc=spread, scale=STD_DEV_SPREAD)
        away_win_prob = 1 - home_win_prob

        # 大分概率：总分大于基准线(比如225.5)的概率
        over_prob = 1 - norm.cdf(MARKET_TOTAL_LINE, loc=total, scale=STD_DEV_TOTAL)
        under_prob = 1 - over_prob

        # 分差区间概率 (假设区间为 1-5, 6-10, 11-15)
        prob_1_5 = norm.cdf(5, loc=abs(spread), scale=STD_DEV_SPREAD) - norm.cdf(0, loc=abs(spread), scale=STD_DEV_SPREAD)
        prob_6_10 = norm.cdf(10, loc=abs(spread), scale=STD_DEV_SPREAD) - norm.cdf(5, loc=abs(spread), scale=STD_DEV_SPREAD)
        prob_11_15 = norm.cdf(15, loc=abs(spread), scale=STD_DEV_SPREAD) - norm.cdf(10, loc=abs(spread), scale=STD_DEV_SPREAD)

        win_team = home['name'] if spread > 0 else away['name']

        # 3. 生成好看的报告
        md += f"【{home['name']}(主) vs {away['name']}(客)】\n"
        md += f"📊 预期比分：{home['name']} {home_expected:.1f} - {away['name']} {away_expected:.1f}\n"
        
        if spread > 0:
            md += f"⚖️ 理论让分：{win_team} -{spread:.1f}\n"
        else:
            md += f"⚖️ 理论让分：{win_team} -{abs(spread):.1f}\n"
            
        md += f"📈 理论大小：{total:.1f} 分 (基准盘口 {MARKET_TOTAL_LINE})\n"
        
        # 概率输出
        md += f"🎯 胜负概率：主胜 {home_win_prob:.1%} | 客胜 {away_win_prob:.1%}\n"
        md += f"📈 大小概率：大分 {over_prob:.1%} | 小分 {under_prob:.1%}\n"
        md += f"🔮 分差区间：{win_team}赢 1-5分({prob_1_5:.1%}) | 6-10分({prob_6_10:.1%}) | 11-15分({prob_11_15:.1%})\n\n"

    # 你需要在真实代码里加上复盘部分，为了演示概率，这里直接推送
    push_to_wechat(md)

if __name__ == "__main__":
    main()
