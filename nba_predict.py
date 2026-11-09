import os
import requests
import pandas as pd
from datetime import datetime

FIXTURES_CSV = "nba_fixtures.csv"

# 转换球队简称为 ESPN 的 ID
TEAM_IDS = {
    "ATL": 1, "BOS": 2, "NOP": 3, "CHI": 4, "CLE": 5, "DAL": 6, "DEN": 7, "DET": 8, 
    "GSW": 9, "HOU": 10, "IND": 11, "LAC": 12, "LAL": 13, "MIA": 14, "MIL": 15, "MIN": 16, 
    "BKN": 17, "NYK": 18, "ORL": 19, "PHI": 20, "PHX": 21, "POR": 22, "SAC": 23, "SAS": 24, 
    "OKC": 25, "UTA": 26, "WAS": 27, "TOR": 28, "MEM": 29
}

def push_to_wechat(md_text):
    key = os.environ.get("SERVERCHAN_KEY")
    if not key:
        print("⚠️ 未配置 SERVERCHAN_KEY")
        return
    print("正在推送到微信...")
    try:
        r = requests.post(f"https://sctapi.ftqq.com/{key}.send", data={"title": f"🏀 NBA量化预测 {datetime.now().strftime('%m月%d日')}", "desp": md_text}, timeout=10)
        print(f"推送状态码: {r.status_code}")
    except Exception as e:
        print(f"❌ 微信推送异常: {e}")

def get_team_stat(team_abbr):
    """从 ESPN 免费接口获取球队的场均得分、场均失分、节奏"""
    team_id = TEAM_IDS.get(team_abbr.upper())
    if not team_id: return None
    
    # 获取球队基础数据
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/statistics"
    try:
        r = requests.get(url, timeout=15)
        data = r.json()
        
        # ESPN 的数据藏在很深的字典里，我们提取“场均得分”、“场均失分”作为替代指标
        stats = data.get("results", {}).get("stats", {}).get("splits", {}).get("categories", [])
        
        ppg = 110.0 # 默认联盟平均分
        opp_ppg = 110.0
        pace = 100.0
        
        for category in stats:
            if category.get("name") == "offensive":
                for stat in category.get("stats", []):
                    if stat.get("name") == "avgPoints": ppg = float(stat.get("value"))
                    if stat.get("name") == "avgPossessions": pace = float(stat.get("value"))
            if category.get("name") == "defensive":
                for stat in category.get("stats", []):
                    if stat.get("name") == "avgPoints": opp_ppg = float(stat.get("value"))
                    
        return {"name": data.get("team", {}).get("displayName"), "ppg": ppg, "opp_ppg": opp_ppg, "pace": pace}
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
    
    # 联盟平均进攻水平（可以粗略用 114.5 代替，或者动态算）
    league_avg_ppg = 114.5

    for _, row in fixtures.iterrows():
        home_abbr = str(row['home']).strip().upper()
        away_abbr = str(row['away']).strip().upper()
        
        home_stats = get_team_stat(home_abbr)
        away_stats = get_team_stat(away_abbr)

        if not home_stats or not away_stats:
            md += f"⚠️ 获取 {home_abbr} 或 {away_abbr} 数据失败\n\n"
            continue

        # 计算预期得分 (结合了进攻、防守和节奏)
        pace_avg = (home_stats['pace'] + away_stats['pace']) / 2
        
        home_expected = (home_stats['ppg'] * (away_stats['opp_ppg'] / league_avg_ppg)) * (pace_avg / 100) + 2.5
        away_expected = (away_stats['ppg'] * (home_stats['opp_ppg'] / league_avg_ppg)) * (pace_avg / 100) - 2.5

        spread = home_expected - away_expected
        total = home_expected + away_expected
        spread_team = home_abbr if spread > 0 else away_abbr

        md += f"【{home_abbr}(主) vs {away_abbr}(客)】\n"
        md += f"📊 预期比分：{home_abbr} {home_expected:.1f} - {away_abbr} {away_expected:.1f}\n"
        md += f"⚖️ 理论让分：{spread_team} 让 {abs(spread):.1f} 分\n"
        md += f"📈 理论大小：{total:.1f} 分\n\n"

    push_to_wechat(md)

if __name__ == "__main__":
    main()
