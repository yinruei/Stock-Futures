"""
IBFF 策略批次爬蟲
用法：
  python batch_scrape.py                              快速更新（2025-07-01 至今）
  python batch_scrape.py --full                       完整歷史（2020-01-01 至今），供前端切片
  python batch_scrape.py --begin 2025-01-02           指定起始至今
  python batch_scrape.py --begin 2025-01-02 --end 2026-07-02  指定區間（結果與官網篩選一致）
  python batch_scrape.py 2025-01-02 2026-07-02        舊格式（位置式參數，向下相容）
"""

import os
import sys
import json
import time
from datetime import date
from strategy_scraper import fetch_strategy, parse_info, calc_stats, calc_monthly, save_json

# ── 策略清單（手動維護，來源：IBFF 網站）──────────────────────────────────────
STRATEGIES = [
    # 組合策略
    {"code": "IBF_A1pf_tm",  "name": "事事如意組合 一般", "subscribe_pts": 28000, "category": "組合"},
    {"code": "IBF_A2pf_tm",  "name": "事事如意組合 專",   "subscribe_pts": 70000, "category": "組合"},
    {"code": "IBF_B1pf_tm",  "name": "四方進財組合 一般", "subscribe_pts": 28000, "category": "組合"},
    {"code": "IBF_B2pf_tm",  "name": "四方進財組合 專",   "subscribe_pts": 70000, "category": "組合"},
    {"code": "IBF_C1pf_tm",  "name": "事事長紅組合 一般", "subscribe_pts": 28000, "category": "組合"},
    {"code": "IBF_C2pf_tm",  "name": "事事長紅組合 專",   "subscribe_pts": 70000, "category": "組合"},
    {"code": "IBF_3fpf_tm",  "name": "三陽開泰組合 一般", "subscribe_pts":     0, "category": "組合"},
    {"code": "IBF_4fpf_tm",  "name": "好事連連組合 一般", "subscribe_pts": 28000, "category": "組合"},
    {"code": "IBF_4fpfs_tm", "name": "好事連連組合 專",   "subscribe_pts": 70000, "category": "組合"},
    {"code": "IBF_5fpf_tm",  "name": "五福臨門組合 一般", "subscribe_pts": 32400, "category": "組合"},
    {"code": "IBF_55fpf_tm", "name": "五福臨門組合 專",   "subscribe_pts": 81000, "category": "組合"},
    # 波段策略（名稱由 API 自動取得）
    {"code": "KW149_tm",       "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "W2262_tm",       "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "W2261_tm",       "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "moneycat13_tm",  "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "W1232_tm",       "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "OW02_tm",        "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "IBF_R440_tm",    "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "OW05_tm",        "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "KW150_tm",       "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "IBF_R9y_tm",     "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "KW112_tm",       "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "KW140_tm",       "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "W3063_tm",       "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "IBF_R2y_tm",     "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "IBF_PNK60_tm",   "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "PBOV260_SJ_tm",  "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "W3061_tm",       "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "moneycat15_tm",  "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "DP2_tm",         "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "IBF_PKC450_tm",  "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "IBF_CC15_tm",    "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "IBF_PDT450_tm",  "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "OW01_tm",        "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "IBF_NKC_tm",     "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "Sam_1208_tm",    "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "OW03_tm",        "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "Sam_1219_tm",    "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "OW06_tm",        "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "KW073_tm",       "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "IBF_LT42_tm",    "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "PBO_SJ_tm",      "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "W3062_tm",       "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "KW146_tm",       "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "KW116_tm",       "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "CQRF10_tm",      "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "CQRF9_tm",       "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "IBF_KAL_tm",     "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "CQRF5_tm",       "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "KW134_tm",       "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "W2254_tm",       "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "OW04_tm",        "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "W2252_tm",       "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "CQRF2_tm",       "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "KW136_tm",       "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "IBF_PJM900_tm",  "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "CQRF7_tm",       "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "W2052_tm",       "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "W2253_tm",       "name": None, "subscribe_pts": 0, "category": "波段"},
    {"code": "PBOV290_SJ_tm",  "name": None, "subscribe_pts": 0, "category": "波段"},
]

# 建議資金（TAIFEX_TMF 微型台指，來源：IBFF 網站登入後）
SUGGESTED_CAPITAL = 265850
TICK_VALUE = 10


def scrape_all(begin_date: date, end_date: date):
    results = []
    all_outputs = []
    total = len(STRATEGIES)

    for idx, s in enumerate(STRATEGIES, 1):
        code = s["code"]
        print(f"\n[{idx}/{total}] 抓取 {code}（{s['name']}）...")
        try:
            raw     = fetch_strategy(code, begin_date, end_date)
            info    = parse_info(raw[0])
            stats   = calc_stats(info, raw[1])
            monthly = calc_monthly(stats["daily_pnl"])

            output = {
                "strategy_code": code,
                "strategy_name": s["name"] or info.get("name", code),
                "strategy_category": s.get("category", ""),
                "subscribe_pts": s["subscribe_pts"],
                "begin_date": str(begin_date),
                "end_date":   str(end_date),
                "info":       info,
                "stats": {k: v for k, v in stats.items() if k not in ("daily_pnl", "trade_records")},
                "monthly":    monthly,
                "daily_pnl":  stats["daily_pnl"],
                "trades":     stats["trade_records"],
            }
            save_json(output, f"{code}_data.json")
            all_outputs.append(output)

            net_pnl = stats["net_closed_pnl"] + stats["floating_pnl"]
            net_rate = net_pnl * TICK_VALUE / SUGGESTED_CAPITAL * 100
            results.append({
                "code":    code,
                "name":    s["name"],
                "net_rate": round(net_rate, 2),
                "net_pnl":  round(net_pnl, 0),
                "drawdown": stats["max_drawdown_points"],
                "win_rate": stats["win_rate_pct"],
                "pf":       stats["profit_factor"],
                "trades":   stats["total_trades"],
                "ok": True,
            })
        except Exception as e:
            print(f"  ✗ 失敗：{e}")
            results.append({"code": code, "name": s["name"], "ok": False, "error": str(e)})

        if idx < total:
            time.sleep(1.5)

    print_comparison(results)
    if all_outputs:
        save_compare_js(all_outputs)

    # 台指期 OHLC（免費，FinMind）
    print('\n[OHLC] 抓取台指期日/夜盤資料...')
    try:
        import fetch_ohlc
        fetch_ohlc.run(begin_date, end_date)
    except Exception as e:
        print(f'  ✗ 台指期 OHLC 抓取失敗（跳過）：{e}')

    return results


def save_compare_js(all_outputs: list):
    """產生 compare_data.json，供 strategy_compare.html 靜態載入"""
    with open("compare_data.json", "w", encoding="utf-8") as f:
        json.dump(all_outputs, f, ensure_ascii=False)
    size_kb = os.path.getsize("compare_data.json") // 1024
    print(f"  → compare_data.json 已產生（{len(all_outputs)} 筆策略，{size_kb} KB）")


def print_comparison(results):
    sep = "─" * 85
    print(f"\n{sep}")
    print(f"{'代碼':<18} {'策略名稱':<14} {'淨報酬率':>8} {'淨報酬(點)':>10} {'最大回撤':>8} {'勝率':>6} {'獲利因子':>8} {'筆數':>5}")
    print(sep)
    for r in results:
        if not r["ok"]:
            print(f"  {r['code']:<16}  ✗ {r.get('error','')}")
            continue
        print(
            f"  {r['code']:<16}  {(r['name'] or r['code']):<12}"
            f"  {r['net_rate']:>7.2f}%"
            f"  {int(r['net_pnl']):>9,}"
            f"  {r['drawdown']:>7.0f}"
            f"  {r['win_rate']:>5.1f}%"
            f"  {r['pf']:>7.4f}"
            f"  {r['trades']:>4}"
        )
    print(sep)


if __name__ == "__main__":
    def _get_flag(flag):
        try:
            i = sys.argv.index(flag)
            return sys.argv[i + 1]
        except (ValueError, IndexError):
            return None

    full_mode  = "--full" in sys.argv
    begin_arg  = _get_flag("--begin")
    end_arg    = _get_flag("--end")
    pos_args   = [a for a in sys.argv[1:] if not a.startswith("-")]

    end_date   = date.fromisoformat(end_arg   or (pos_args[1] if len(pos_args) > 1 else str(date.today())))
    begin_date = date.fromisoformat(begin_arg or (pos_args[0] if len(pos_args) > 0 else
                     str(date(2020, 1, 1))))

    print(f"批次爬取：{begin_date} ～ {end_date}，共 {len(STRATEGIES)} 個策略")
    if begin_arg or end_arg:
        print("（指定區間模式：結果與官網同日期篩選一致）")
    elif full_mode:
        print("（完整歷史模式：前端可自由切片，但波段策略篩選結果與官網重算有差異）")
    scrape_all(begin_date, end_date)
