import os
import requests
import pandas as pd
import glob
from datetime import datetime, timedelta
from scipy.stats import norm

FIXTURES_CSV = "nba_fixtures.csv"
ODDS_API_KEY = os.environ.get("ODDS_API_KEY")

# 球队 ID 与 全称映射 (用于从 ESPN 抓数据和匹配 Odds API)
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

# The Odds API 的英文全称映射
ABBR_TO_FULL = {
    "ATL": "Atlanta Hawks", "BOS": "Boston Celtics", "NOP": "New Orleans Pelicans", "CHI": "Chicago Bulls",
    "CLE": "Cleveland Cavaliers", "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets", "DET": "Detroit Pistons",
    "GSW": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers", "LAC": "LA Clippers",
    "LAL": "Los Angeles Lakers", "MIA": "Miami Heat", "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves",
    "BKN": "Brooklyn Nets", "NYK": "New York Knicks", "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers",
    "PHX": "Phoenix Suns", "POR": "Portland Trail Blazers", "SAC": "Sacramento Kings", "SAS": "San Antonio Spurs",
    "OKC": "Oklahoma City Thunder", "UTA": "Utah Jazz", "WAS": "Washington Wizards", "TOR": "Toronto Raptors",
    "MEM": "Memphis Grizzlies", "CHA": "Charlotte Hornets"
}

STD_DEV_SPREAD = 12.5
STD_DEV_TOTAL = 18.0
MARKET_TOTAL_LINE = 225.5 # 用作对比的基准线

def push_to_wechat(md_text):
    key = os.environ.get("SERVERCHAN_KEY")
    if not key: return
    try:
        requests.post(f"https://sctapi.ftqq.com/{key}.send", data={"title": f"🏀 NBA量化与战绩 {datetime.now().strftime('%m月%d日')}", "desp": md_text}, timeout=10)
    except Exception as e:
        print(f"微信异常: {e}")

def fetch_nba_odds():
    """从 The Odds API 抓取 NBA 赛程与赔率"""
    if not ODDS_API_KEY:
        print("⚠️ 未配置 ODDS_API_KEY")
        return []
    
    print("正在从 The Odds API 获取 NBA 赔率...")
    url = f"https://api.the-odds-api.com/v4/sports/basketball_nba/odds/"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us", # 美国盘口
        "markets": "h2h,spreads,totals", # 胜负、让分、大小分
        "oddsFormat": "decimal"
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200: return []
        return r.json()
    except:
        return []

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

def get_actual_results(date_str):
    fmt_date = date_str.replace("-", "")
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={fmt_date}"
    results = {}
    try:
        r = requests.get(url, timeout=10)
        events = r.json().get("events", [])
        for ev in events:
            comp = ev.get("competitions", [])[0]
            status = comp.get("status", {})
            if not status.get("type", {}).get("completed", False): continue
            competitors = comp.get("competitors", [])
            if len(competitors) == 2:
                home = next((c for c in competitors if c["homeAway"] == "home"), None)
                away = next((c for c in competitors if c["homeAway"] == "away"), None)
                if home and away and "score" in home and "score" in away:
                    h_score, a_score = int(home["score"]), int(away["score"])
                    results[f"{home['team']['abbreviation']}||{away['team']['abbreviation']}"] = (h_score, a_score)
    except: pass
    return results

def get_performance_report():
    pred_files = sorted(glob.glob("nba_predictions_*.csv"))
    if not pred_files: return "📊 历史战绩：暂无记录\n"

    total, win_hits, ou_hits = 0, 0, 0
    details = []
    seen_matches = set()

    for f in pred_files:
        date_str = f.replace("nba_predictions_", "").replace(".csv", "")
        try:
            pred_date = datetime.strptime(date_str, "%Y-%m-%d")
            df = pd.read_csv(f, encoding="utf-8-sig")
            actuals = {}
            for i in range(3): # 跨3天查赛果
                check_date = (pred_date + timedelta(days=i)).strftime("%Y-%m-%d")
                actuals.update(get_actual_results(check_date))
            
            for _, row in df.iterrows():
                h, a = row["home"], row["away"]
                key = f"{h}||{a}"
                if key in seen_matches: continue
                if key in actuals:
                    act_h, act_a = actuals[key]
                    pred_h, pred_a = row["pred_h"], row["pred_a"]
                    pred_win = "H" if pred_h > pred_a else "A"
                    act_win = "H" if act_h > act_a else "A"
                    win_ok = (pred_win == act_win)
                    ou_ok = ((pred_h + pred_a > 225 and act_h + act_a > 225) or (pred_h + pred_a < 225 and act_h + act_a < 225))

                    total += 1
                    if win_ok: win_hits += 1
                    if ou_ok: ou_hits += 1
                    seen_matches.add(key)
                    details.append({"match": f"{TEAM_CN.get(h, h)} vs {TEAM_CN.get(a, a)}", "act": f"{act_h}-{act_a}", "win": win_ok, "ou": ou_ok})
        except: pass

    md = "📊 NBA 历史战绩统计\n"
    if total > 0:
        md += f"已结算 {total} 场 | 🎯 胜负: {win_hits/total:.1%} | 📈 大小: {ou_hits/total:.1%}\n\n"
        for d in details[-3:]:
            md += f"🔸 {d['match']} (实际 {d['act']}) | 胜负{'✅' if d['win'] else '❌'} | 大小{'✅' if d['ou'] else '❌'}\n"
    else:
        md += "暂无已结算的比赛。\n"
    return md

def main():
    # 1. 获取比赛和赔率
    odds_data = fetch_nba_odds()
    
    # 如果你在本地测试，可以没 API，就用本地 fixtures.csv
    if not odds_data:
        print("未获取到 API 赔率，回退到本地 fixtures.csv...")
        try:
            fixtures = pd.read_csv(FIXTURES_CSV, encoding="utf-8-sig")
        except:
            print("找不到 nba_fixtures.csv")
            return
        matches_to_run = []
        for _, row in fixtures.iterrows():
            matches_to_run.append({
                "home_abbr": str(row['home']).strip().upper(),
                "away_abbr": str(row['away']).strip().upper(),
                "odds_h": None, "odds_a": None, "total_line": None
            })
    else:
        print(f"成功获取 {len(odds_data)} 场带赔率的 NBA 比赛！")
        matches_to_run = []
        for m in odds_data:
            h_full, a_full = m["home_team"], m["away_team"]
            h_abbr = next((k for k, v in ABBR_TO_FULL.items() if v == h_full), None)
            a_abbr = next((k for k, v in ABBR_TO_FULL.items() if v == a_full), None)
            
            if not h_abbr or not a_abbr: continue
            
            oh, oa, total_line = None, None, None
            # 提取 Pinnacle 或首选庄家的赔率
            for b in m.get("bookmakers", []):
                if b["key"] == "pinnacle":
                    for market in b.get("markets", []):
                        if market["key"] == "h2h":
                            for out in market["outcomes"]:
                                if out["name"] == h_full: oh = out["price"]
                                if out["name"] == a_full: oa = out["price"]
                        if market["key"] == "totals":
                            total_line = market["outcomes"][0].get("point") # 大小分基准线
                    if oh: break # 抓到一个庄家就够
            
            matches_to_run.append({
                "home_abbr": h_abbr, "away_abbr": a_abbr,
                "odds_h": oh, "odds_a": oa, "total_line": total_line
            })

    md = f"🏀 NBA 量化预测 ({datetime.now().strftime('%m-%d')})\n\n"
    results_to_save = []

    for match in matches_to_run:
        h_abbr, a_abbr = match["home_abbr"], match["away_abbr"]
        home, away = get_team_stat(h_abbr), get_team_stat(a_abbr)
        if not home or not away: continue

        # 计算预期得分
        home_expected = (home['ppg'] + away['opp_ppg']) / 2 + 2.5
        away_expected = (away['ppg'] + home['opp_ppg']) / 2 - 2.5

        spread = home_expected - away_expected
        total = home_expected + away_expected

        # 核心概率计算
        home_win_prob = 1 - norm.cdf(0, loc=spread, scale=STD_DEV_SPREAD)
        away_win_prob = 1 - home_win_prob
        
        # 大小分概率计算 (根据真实盘口 line 或 默认 225.5)
        cur_total_line = match["total_line"] if match["total_line"] else MARKET_TOTAL_LINE
        over_prob = 1 - norm.cdf(cur_total_line, loc=total, scale=STD_DEV_TOTAL)
                # 计算分差区间
        abs_spread = abs(spread)
        prob_1_5 = norm.cdf(5, loc=abs_spread, scale=STD_DEV_SPREAD) - norm.cdf(0, loc=abs_spread, scale=STD_DEV_SPREAD)
        prob_6_10 = norm.cdf(10, loc=abs_spread, scale=STD_DEV_SPREAD) - norm.cdf(5, loc=abs_spread, scale=STD_DEV_SPREAD)
        prob_11_15 = norm.cdf(15, loc=abs_spread, scale=STD_DEV_SPREAD) - norm.cdf(10, loc=abs_spread, scale=STD_DEV_SPREAD)
        win_team = home['name'] if spread > 0 else away['name']

        md += f"【{home['name']}(主) vs {away['name']}(客)】\n"
        md += f"📊 预期比分：{home_expected:.1f} - {away_expected:.1f} | 理论让分：{win_team} -{abs(spread):.1f}\n"
        md += f"📈 理论总分：{total:.1f} 分 (体彩盘口: {cur_total_line})\n"
        md += f"🔮 分差区间：{win_team}赢 1-5分({prob_1_5:.1%}) | 6-10分({prob_6_10:.1%}) | 11-15分({prob_11_15:.1%})\n"
        # 👇 核心：如果有 API 赔率，计算 EV 和 凯利
        oh, oa = match["odds_h"], match["odds_a"]
        if oh and oa:
            ev_h = (home_win_prob * oh) - 1
            ev_a = (away_win_prob * oa) - 1
            kelly_h = max(0, ((home_win_prob * oh - 1) / (oh - 1)) * 0.5)
            kelly_a = max(0, ((away_win_prob * oa - 1) / (oa - 1)) * 0.5)

            if ev_h > 0.05: md += f"🔥 **主胜EV +{ev_h:.1%} (建议凯利仓位 {kelly_h:.1%})**\n"
            if ev_a > 0.05: md += f"🔥 **客胜EV +{ev_a:.1%} (建议凯利仓位 {kelly_a:.1%})**\n"
            
            md += f"🎯 胜负概率：主胜 {home_win_prob:.1%} | 客胜 {away_win_prob:.1%}\n"
        else:
            md += f"💡 纯数据：主胜 {home_win_prob:.1%} | 客胜 {away_win_prob:.1%}\n"
            
        md += f"🥅 大小概率：大 {over_prob:.1%} | 小 {1-over_prob:.1%}\n\n"

        results_to_save.append({"home": h_abbr, "away": a_abbr, "pred_h": home_expected, "pred_a": away_expected})

    if results_to_save:
        pd.DataFrame(results_to_save).to_csv(f"nba_predictions_{datetime.now().strftime('%Y-%m-%d')}.csv", index=False, encoding="utf-8-sig")

    md += "-------------------\n"
    md += get_performance_report()
    push_to_wechat(md)

if __name__ == "__main__":
    main()
