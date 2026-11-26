import os
import requests
import pandas as pd
import glob
from datetime import datetime, timedelta
from scipy.stats import norm

FIXTURES_CSV = "nba_fixtures.csv"
ODDS_API_KEY = os.environ.get("ODDS_API_KEY")

# 球队 ID 与 全称映射
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

def push_to_wechat(md_text):
    key = os.environ.get("SERVERCHAN_KEY")
    if not key: return
    try:
        requests.post(f"https://sctapi.ftqq.com/{key}.send", data={"title": f"🏀 NBA量化与战绩 {datetime.now().strftime('%m月%d日')}", "desp": md_text}, timeout=10)
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

def get_api_odds_for_fixture(h_abbr, a_abbr):
    """从 The Odds API 获取指定场次的真实赔率与大小分盘口"""
    if not ODDS_API_KEY: return None
    
    h_full = ABBR_TO_FULL.get(h_abbr.upper(), h_abbr)
    a_full = ABBR_TO_FULL.get(a_abbr.upper(), a_abbr)

    params = {"apiKey": ODDS_API_KEY, "regions": "us", "markets": "h2h,totals", "oddsFormat": "decimal"}
    try:
        r = requests.get(f"https://api.the-odds-api.com/v4/sports/basketball_nba/odds/", params=params, timeout=10)
        if r.status_code != 200: return None
        matches = r.json()
        for m in matches:
            if (h_full.lower() in m["home_team"].lower() or m["home_team"].lower() in h_full.lower()) and \
               (a_full.lower() in m["away_team"].lower() or m["away_team"].lower() in a_full.lower()):
                
                res = {"h2h": {}, "totals": {}}
                for b in m.get("bookmakers", []):
                    if b["key"] in ["pinnacle", "draftkings", "fanduel"]:
                        for market in b.get("markets", []):
                            if market["key"] == "h2h":
                                for out in market["outcomes"]:
                                    if out["name"] == m["home_team"]: res["h2h"]["h"] = out["price"]
                                    elif out["name"] == m["away_team"]: res["h2h"]["a"] = out["price"]
                            elif market["key"] == "totals":
                                res["totals"]["line"] = market["outcomes"][0].get("point")
                        if res["h2h"]: return res
    except Exception: pass
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
    except Exception: pass
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
            for i in range(3):
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
        except Exception: pass

    md = "📊 NBA 历史战绩统计\n"
    if total > 0:
        md += f"已结算 {total} 场 | 🎯 胜负: {win_hits/total:.1%} | 📈 大小: {ou_hits/total:.1%}\n\n"
        for d in details[-3:]:
            md += f"🔸 {d['match']} (实际 {d['act']}) | 胜负{'✅' if d['win'] else '❌'} | 大小{'✅' if d['ou'] else '❌'}\n"
    else:
        md += "暂无已结算的比赛。\n"
    return md

def main():
    try:
        fixtures = pd.read_csv(FIXTURES_CSV, encoding="utf-8-sig")
    except:
        print("找不到 nba_fixtures.csv")
        return

    md = f"🏀 NBA 量化预测 ({datetime.now().strftime('%m-%d')})\n\n"
    results_to_save = []

    for _, row in fixtures.iterrows():
        h_abbr = str(row['home']).strip().upper()
        a_abbr = str(row['away']).strip().upper()
        
        home = get_team_stat(h_abbr)
        away = get_team_stat(a_abbr)
        if not home or not away: continue

        # 获取真实 API 赔率
        api_data = get_api_odds_for_fixture(h_abbr, a_abbr)
        if api_data and "h" in api_data["h2h"]:
            oh = api_data["h2h"]["h"]
            oa = api_data["h2h"]["a"]
            total_line = api_data.get("totals", {}).get("line", 225.5)
        else:
            oh, oa, total_line = None, None, 225.5

        # 计算预期得分
        home_expected = (home['ppg'] + away['opp_ppg']) / 2 + 2.5
        away_expected = (away['ppg'] + home['opp_ppg']) / 2 - 2.5

        spread = home_expected - away_expected
        total = home_expected + away_expected

        # 核心概率
        home_win_prob = 1 - norm.cdf(0, loc=spread, scale=STD_DEV_SPREAD)
        away_win_prob = 1 - home_win_prob
        over_prob = 1 - norm.cdf(total_line, loc=total, scale=STD_DEV_TOTAL)
        
        abs_spread = abs(spread)
        prob_1_5 = norm.cdf(5, loc=abs_spread, scale=STD_DEV_SPREAD) - norm.cdf(0, loc=abs_spread, scale=STD_DEV_SPREAD)
        prob_6_10 = norm.cdf(10, loc=abs_spread, scale=STD_DEV_SPREAD) - norm.cdf(5, loc=abs_spread, scale=STD_DEV_SPREAD)
        prob_11_15 = norm.cdf(15, loc=abs_spread, scale=STD_DEV_SPREAD) - norm.cdf(10, loc=abs_spread, scale=STD_DEV_SPREAD)

        win_team = home['name'] if spread > 0 else away['name']

        md += f"【{home['name']}(主) vs {away['name']}(客)】\n"
        md += f"📊 预期比分：{home_expected:.1f} - {away_expected:.1f} | 理论让分：{win_team} -{abs(spread):.1f}\n"
        md += f"📈 理论总分：{total:.1f} 分 (盘口: {total_line})\n"

        # 如果有 API 赔率，计算 EV 和 凯利
        if oh and oa:
            ev_h = (home_win_prob * oh) - 1
            ev_a = (away_win_prob * oa) - 1
            kelly_h = max(0, ((home_win_prob * oh - 1) / (oh - 1)) * 0.5) if oh > 1 else 0
            kelly_a = max(0, ((away_win_prob * oa - 1) / (oa - 1)) * 0.5) if oa > 1 else 0

            if ev_h > 0.05: md += f"🔥 **主胜EV +{ev_h:.1%} (凯利 {kelly_h:.1%})**\n"
            if ev_a > 0.05: md += f"🔥 **客胜EV +{ev_a:.1%} (凯利 {kelly_a:.1%})**\n"
            
            md += f"🎯 胜负概率：主胜 {home_win_prob:.1%} | 客胜 {away_win_prob:.1%}\n"
        else:
            md += f"💡 纯数据：主胜 {home_win_prob:.1%} | 客胜 {away_win_prob:.1%}\n"
            
        md += f"🔮 分差区间：{win_team}赢 1-5分({prob_1_5:.1%}) | 6-10分({prob_6_10:.1%}) | 11-15分({prob_11_15:.1%})\n"
        md += f"🥅 大小概率：大 {over_prob:.1%} | 小 {1-over_prob:.1%}\n\n"

        results_to_save.append({"home": h_abbr, "away": a_abbr, "pred_h": home_expected, "pred_a": away_expected})

    if results_to_save:
        pd.DataFrame(results_to_save).to_csv(f"nba_predictions_{datetime.now().strftime('%Y-%m-%d')}.csv", index=False, encoding="utf-8-sig")

    md += "-------------------\n"
    md += get_performance_report()
    push_to_wechat(md)

if __name__ == "__main__":
    main()
