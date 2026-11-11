import os
import requests
import pandas as pd
import glob
from datetime import datetime
from scipy.stats import norm

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

STD_DEV_SPREAD = 12.5
STD_DEV_TOTAL = 18.0
MARKET_TOTAL_LINE = 225.5

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

def get_actual_results(date_str):
    fmt_date = date_str.replace("-", "")
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={fmt_date}"
    results = {}
    try:
        r = requests.get(url, timeout=10)
        events = r.json().get("events", [])
        for ev in events:
            comp = ev.get("competitions", [])[0].get("competitors", [])
            if len(comp) == 2:
                home = next((c for c in comp if c["homeAway"] == "home"), None)
                away = next((c for c in comp if c["homeAway"] == "away"), None)
                if home and away and "score" in home and "score" in away:
                    h_score = int(home["score"])
                    a_score = int(away["score"])
                    h_abbr = home["team"]["abbreviation"]
                    a_abbr = away["team"]["abbreviation"]
                    results[f"{h_abbr}||{a_abbr}"] = (h_score, a_score)
    except Exception:
        pass
    return results

def get_performance_report():
    pred_files = sorted(glob.glob("nba_predictions_*.csv"))
    if not pred_files:
        return "📊 历史战绩：暂无记录 (等待第一场比赛结算)\n"

    total, win_hits, ou_hits = 0, 0, 0
    details = []

    for f in pred_files:
        date_str = f.replace("nba_predictions_", "").replace(".csv", "")
        try:
            df = pd.read_csv(f, encoding="utf-8-sig")
            actuals = get_actual_results(date_str)
            
            for _, row in df.iterrows():
                h, a = row["home"], row["away"]
                key = f"{h}||{a}"
                if key in actuals:
                    act_h, act_a = actuals[key]
                    pred_h, pred_a = row["pred_h"], row["pred_a"]
                    
                    pred_win = "H" if pred_h > pred_a else "A"
                    act_win = "H" if act_h > act_a else "A"
                    win_ok = (pred_win == act_win)
                    
                    # 简单以 225 分为基准判断大小球对错
                    pred_total = pred_h + pred_a
                    act_total = act_h + act_a
                    ou_ok = ((pred_total > 225 and act_total > 225) or (pred_total < 225 and act_total < 225))

                    total += 1
                    if win_ok: win_hits += 1
                    if ou_ok: ou_hits += 1

                    details.append({
                        "date": date_str, "match": f"{TEAM_CN.get(h, h)} vs {TEAM_CN.get(a, a)}",
                        "act": f"{act_h}-{act_a}",
                        "pred": f"{pred_h:.0f}-{pred_a:.0f}",
                        "win": win_ok, "ou": ou_ok
                    })
        except Exception:
            pass

    md = "📊 NBA 历史战绩统计\n"
    if total > 0:
        md += f"已结算 {total} 场\n"
        md += f"🎯 胜负命中率: {win_hits/total:.1%}\n"
        md += f"📈 大小分命中率: {ou_hits/total:.1%}\n\n"
        md += "近期明细 (最近3场):\n"
        for d in details[-3:]:
            md += f"🔸 {d['match']} (实际 {d['act']})\n"
            md += f"  预测 {d['pred']} | 胜负{'✅' if d['win'] else '❌'} | 大小{'✅' if d['ou'] else '❌'}\n\n"
    else:
        md += "暂无已结算的比赛 (比赛还没打或者数据源还没更新比分)\n"
    
    return md

def main():
    try:
        fixtures = pd.read_csv(FIXTURES_CSV, encoding="utf-8-sig")
    except:
        print("找不到 nba_fixtures.csv")
        return

    md = f"🏀 NBA 量化预测 ({datetime.now().strftime('%m-%d')})\n\n"
    today_str = datetime.now().strftime("%Y-%m-%d")
    results_to_save = []

    for _, row in fixtures.iterrows():
        home_abbr = str(row['home']).strip().upper()
        away_abbr = str(row['away']).strip().upper()
        
        home = get_team_stat(home_abbr)
        away = get_team_stat(away_abbr)

        if not home or not away: continue

        home_expected = (home['ppg'] + away['opp_ppg']) / 2 + 2.5
        away_expected = (away['ppg'] + home['opp_ppg']) / 2 - 2.5

        spread = home_expected - away_expected
        total = home_expected + away_expected

        home_win_prob = 1 - norm.cdf(0, loc=spread, scale=STD_DEV_SPREAD)
        away_win_prob = 1 - home_win_prob
        over_prob = 1 - norm.cdf(MARKET_TOTAL_LINE, loc=total, scale=STD_DEV_TOTAL)
        
        win_team = home['name'] if spread > 0 else away['name']

        md += f"【{home['name']}(主) vs {away['name']}(客)】\n"
        md += f"📊 预期比分：{home['name']} {home_expected:.1f} - {away['name']} {away_expected:.1f}\n"
        
        if spread > 0:
            md += f"⚖️ 理论让分：{win_team} -{spread:.1f}\n"
        else:
            md += f"⚖️ 理论让分：{win_team} -{abs(spread):.1f}\n"
            
        md += f"📈 理论大小：{total:.1f} 分\n"
        md += f"🎯 胜负概率：主胜 {home_win_prob:.1%} | 客胜 {away_win_prob:.1%}\n"
        md += f"📈 大小概率：大分 {over_prob:.1%} | 小分 {1-over_prob:.1%}\n\n"

        results_to_save.append({
            "home": home_abbr, "away": away_abbr,
            "pred_h": home_expected, "pred_a": away_expected
        })

    # 1. 保存预测记录，供以后复盘
    if results_to_save:
        pd.DataFrame(results_to_save).to_csv(f"nba_predictions_{today_str}.csv", index=False, encoding="utf-8-sig")

    # 2. 追加复盘报告
    md += "-------------------\n"
    md += get_performance_report()

    # 3. 推送
    push_to_wechat(md)

if __name__ == "__main__":
    main()
