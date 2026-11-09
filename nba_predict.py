import os
import requests
import pandas as pd
from datetime import datetime
from nba_api.stats.endpoints import leaguedashteamstats
from nba_api.stats.static import teams

FIXTURES_CSV = "nba_fixtures.csv"

def push_to_wechat(md_text):
    key = os.environ.get("SERVERCHAN_KEY")
    if not key:
        print("⚠️ 未配置 SERVERCHAN_KEY，跳过微信推送")
        return
    print("正在推送到微信...")
    try:
        r = requests.post(f"https://sctapi.ftqq.com/{key}.send", data={"title": f"🏀 NBA量化预测 {datetime.now().strftime('%m月%d日')}", "desp": md_text}, timeout=10)
        print(f"推送状态码: {r.status_code}")
    except Exception as e:
        print(f"❌ 微信推送异常: {e}")

def main():
    print("正在从 NBA 官方拉取本赛季数据...")
    try:
        stats = leaguedashteamstats.LeagueDashTeamStats(
            season='2025-26', 
            measure_type_detailed_defense='Advanced',
            league_id_nullable='00', 
            team_id_nullable='0'
        )
        df = stats.get_data_frames()[0][['TEAM_NAME', 'OFF_RATING', 'DEF_RATING', 'PACE']]
        
        all_teams = teams.get_teams()
        abbr_to_name = {t['abbreviation']: t['full_name'] for t in all_teams}
    except Exception as e:
        print(f"❌ 拉取 NBA 数据失败: {e}")
        return

    # 读取赛程表
    try:
        fixtures = pd.read_csv(FIXTURES_CSV, encoding="utf-8-sig")
    except FileNotFoundError:
        print(f"❌ 找不到 {FIXTURES_CSV}，请检查文件是否存在。")
        return

    md = f"🏀 NBA 量化预测 ({datetime.now().strftime('%m-%d')})\n\n"
    league_avg_ortg = df['OFF_RATING'].mean()
    league_avg_pace = df['PACE'].mean()

    for _, row in fixtures.iterrows():
        home_abbr = str(row['home']).strip()
        away_abbr = str(row['away']).strip()
        
        home_name = abbr_to_name.get(home_abbr)
        away_name = abbr_to_name.get(away_abbr)

        if not home_name or not away_name:
            md += f"⚠️ 找不到球队缩写: {home_abbr} 或 {away_abbr}\n\n"
            continue

        try:
            home_stats = df[df['TEAM_NAME'] == home_name].iloc[0]
            away_stats = df[df['TEAM_NAME'] == away_name].iloc[0]
        except IndexError:
            md += f"⚠️ 数据库中暂无 {home_abbr} 或 {away_abbr} 的赛季数据\n\n"
            continue

        # 核心算法：预期得分
        pace_avg = (home_stats['PACE'] + away_stats['PACE']) / 2
        home_expected = (home_stats['OFF_RATING'] * away_stats['DEF_RATING'] / league_avg_ortg) * (pace_avg / league_avg_pace) + 2.5
        away_expected = (away_stats['OFF_RATING'] * home_stats['DEF_RATING'] / league_avg_ortg) * (pace_avg / league_avg_pace) - 2.5

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
