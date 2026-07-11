"""
IBFF 策略評估分析爬蟲
用途：爬取 ibff.com.tw 單一策略的完整績效資料
用法：python strategy_scraper.py IBF_A1pf_tm [開始日期 YYYY-MM-DD] [結束日期 YYYY-MM-DD]
"""

import re
import sys
import json
import csv
import requests
from datetime import date, timedelta
from html import unescape
from collections import defaultdict

BASE_URL = "https://www.ibff.com.tw/APP/EManager/Strategy"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": f"{BASE_URL}/analysis.aspx",
}


# ── API ──────────────────────────────────────────────────────────────────────

def fetch_strategy(code: str, begin: date, end: date) -> dict:
    """呼叫 analysisData.aspx 並回傳解析後的資料"""
    payload = {"strategyitems": f"{code},{begin},{end}"}
    resp = requests.post(
        f"{BASE_URL}/analysisData.aspx",
        headers=HEADERS,
        data=payload,
        timeout=90,
    )
    resp.raise_for_status()

    if "Status=999" in resp.text:
        raise RuntimeError("API 回傳 Status=999，請確認策略代碼是否正確")

    raw = json.loads(unescape(resp.text))
    return raw


# ── 解析策略基本資訊 ─────────────────────────────────────────────────────────

def parse_info(info_arr: list) -> dict:
    """解析 responseArray[0]"""
    description_raw = info_arr[4] if len(info_arr) > 4 else ""
    # 移除 @@@ 結尾的分隔符
    description_parts = [p for p in description_raw.split("@") if p.strip()]

    products = []
    # 每個商品佔 4 個欄位，從 index 5 開始
    for i in range(3):
        base = i * 4 + 5
        if len(info_arr) > base and info_arr[base] != 0:
            products.append({
                "code":        info_arr[base],
                "tick_value":  info_arr[base + 1] if len(info_arr) > base + 1 else None,
                "name":        info_arr[base + 2] if len(info_arr) > base + 2 else None,
                "price":       info_arr[base + 3] if len(info_arr) > base + 3 else None,
            })

    # ── 從描述文字解析最大留倉口數，估算建議資金 ────────────────────────────────
    full_desc = " ".join(description_parts)

    # 找描述中所有「數字+口」或「最大執行倍數：N倍」，取最大值即為最大同時留倉口數
    lot_matches = re.findall(r'(\d+)\s*口', full_desc)
    bei_matches = re.findall(r'最大執行倍數[：:]\s*(\d+)\s*倍', full_desc)
    max_lots = max((int(x) for x in lot_matches + bei_matches), default=1)

    # 保證金 = products[0].price（API 回傳的當下保證金）
    margin = next((p["price"] for p in products if p.get("tick_value") and p.get("price")), 31800)
    # 建議資金 ≈ 最大口數 × 保證金 × 2.33（依已知資料反推之乘數）
    suggested_capital = round(max_lots * margin * 2.33)

    return {
        "name":               info_arr[0],
        "trade_style":        info_arr[1],
        "tick_diff":          info_arr[2],
        "cost_ticks":         info_arr[3],
        "cost_points":        info_arr[2] * info_arr[3],
        "description":        description_parts,
        "products":           products,
        "max_lots":           max_lots,
        "margin":             margin,
        "suggested_capital":  suggested_capital,
    }


# ── 計算統計數字（對應 analysis.js 的演算法）──────────────────────────────────

def calc_stats(info: dict, daily_data: list) -> dict:
    """
    依照 analysis.js 的計算邏輯重現所有統計指標。
    每筆成交：[date, datetime, product, qty_signed, price, 'O'/'C']
      qty 正 = 多單  負 = 空單
      'O' = 開倉  'C' = 平倉
    P&L = (平倉價 - 開倉價) * 方向 * -1 - 成本
    """
    cost = info["cost_points"]
    in_queue = []          # 未平倉部位 FIFO: (direction, open_price, open_date)

    gross_win  = 0.0
    gross_loss = 0.0
    win_times  = 0
    loss_times = 0

    sum_profit   = 0.0     # 累積淨損益（已扣成本）
    sum_gross    = 0.0     # 累積毛利（未扣成本，對應網站「總報酬」）
    max_profit   = 0.0     # 資金曲線最高點
    max_drawdown = 0.0

    daily_pnl = []
    trade_records = []

    last_index = 0         # 最後一天的台指期收盤（API day_entry[1]，用於計算浮動損益）

    for day_entry in daily_data:
        date_str  = day_entry[0]
        index_val = day_entry[1]
        trades    = day_entry[2] if len(day_entry) > 2 else []
        last_index = index_val

        day_profit = 0.0
        day_gross  = 0.0

        for t in trades:
            if not isinstance(t, list):   # [0] 為無交易佔位符
                continue
            qty_signed = t[3]
            price      = t[4]
            oc         = t[5]
            direction  = 1 if qty_signed > 0 else -1
            abs_qty    = abs(qty_signed)

            if oc == "O":
                for _ in range(abs_qty):
                    in_queue.append((direction, price, date_str))
            elif oc == "C" and in_queue:
                for _ in range(abs_qty):
                    if not in_queue:
                        break
                    open_dir, open_price, open_date = in_queue.pop(0)
                    raw_pnl  = (price - open_price) * open_dir   # 毛利
                    net_pnl  = round((raw_pnl - cost) * 1e7) / 1e7
                    day_profit += net_pnl
                    day_gross  += raw_pnl

                    if raw_pnl > 0:
                        gross_win  += raw_pnl
                        win_times  += 1
                    elif raw_pnl < 0:
                        gross_loss += abs(raw_pnl)
                        loss_times += 1

                    trade_records.append({
                        "open_date":   open_date,
                        "date":        date_str,
                        "open_price":  open_price,
                        "close_price": price,
                        "direction":   "多" if open_dir > 0 else "空",
                        "raw_pnl":     raw_pnl,
                        "net_pnl":     net_pnl,
                    })

        sum_profit += day_profit
        sum_gross  += day_gross
        if sum_profit > max_profit:
            max_profit = sum_profit
        drawdown = max_profit - sum_profit
        if drawdown > max_drawdown:
            max_drawdown = drawdown

        # 每日收盤時的未平倉浮動損益（用於前端精確區間計算）
        daily_float = sum(
            round((index_val - op) * od * 1e7) / 1e7
            for od, op, _ in in_queue
        )
        daily_pnl.append({
            "date":        date_str,
            "index":       index_val,
            "day_profit":  round(day_profit, 4),
            "cum_profit":  round(sum_profit, 4),
            "daily_float": round(daily_float, 4),
        })

    # 未平倉浮動損益（對應 JS holdProfit）
    hold_profit = sum(
        round((last_index - op) * od * 1e7) / 1e7
        for od, op, _ in in_queue
    )
    open_positions = [
        {"direction": "多" if od > 0 else "空", "open_price": op}
        for od, op, _ in in_queue
    ]

    total_trades  = win_times + loss_times
    total_cost    = total_trades * cost
    # 對應網站「總報酬」= 毛利 + 浮動（與 JS 完全一致）
    website_total = round(sum_gross + hold_profit, 2)
    win_rate      = win_times / total_trades * 100 if total_trades > 0 else 0
    profit_factor = gross_win / gross_loss if gross_loss > 0 else float("inf")
    avg_win       = gross_win  / win_times  if win_times  > 0 else 0
    avg_loss      = gross_loss / loss_times if loss_times > 0 else 0
    pnl_ratio     = avg_win / avg_loss if avg_loss > 0 else float("inf")

    return {
        "website_total_pnl":   website_total,          # 對應網站「總報酬」(毛利+浮動)
        "net_closed_pnl":      round(sum_profit, 2),   # 平倉淨損益（扣成本）
        "peak_profit":         round(max_profit, 2),   # 淨損益歷史高峰（用於回撤 %）
        "floating_pnl":        round(hold_profit, 2),  # 未平倉浮動損益
        "total_cost":          round(total_cost, 2),   # 已付成本
        "max_drawdown_points": round(max_drawdown, 2),
        "total_trades":        total_trades,
        "win_times":           win_times,
        "loss_times":          loss_times,
        "open_positions":      open_positions,
        "win_rate_pct":        round(win_rate, 2),
        "profit_factor":       round(profit_factor, 4),
        "pnl_ratio":           round(pnl_ratio, 4),
        "avg_win_points":      round(avg_win, 2),
        "avg_loss_points":     round(avg_loss, 2),
        "gross_win":           round(gross_win, 2),
        "gross_loss":          round(gross_loss, 2),
        "daily_pnl":           daily_pnl,
        "trade_records":       trade_records,
    }


# ── 月度統計 ─────────────────────────────────────────────────────────────────

def calc_monthly(daily_pnl: list) -> list:
    monthly = defaultdict(float)
    for d in daily_pnl:
        month = d["date"][:6]   # YYYYMM
        monthly[month] += d["day_profit"]
    return [
        {"month": k, "pnl": round(v, 2)}
        for k, v in sorted(monthly.items())
    ]


# ── 輸出 ─────────────────────────────────────────────────────────────────────

def save_json(data: dict, filename: str):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  → JSON 已儲存：{filename}")


def save_csv(rows: list, filename: str, fieldnames: list):
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  → CSV 已儲存：{filename}")


def print_summary(info: dict, stats: dict, monthly: list):
    sep = "─" * 55
    print(f"\n{sep}")
    print(f"  策略名稱  ：{info['name']}")
    print(f"  交易模式  ：{info['trade_style']}")
    print(f"  交易成本  ：{info['cost_points']} 點/口")
    if info["products"]:
        p = info["products"][0]
        print(f"  商品      ：{p['name']}  現價 {p['price']}")
    print(sep)
    print(f"  【網站總報酬】：{stats['website_total_pnl']:+.2f} 點  ← 對應網站「總報酬」")
    print(f"  平倉淨損益   ：{stats['net_closed_pnl']:+.2f} 點  （已扣成本）")
    print(f"  未平倉浮動   ：{stats['floating_pnl']:+.2f} 點  （{len(stats['open_positions'])} 口未平倉）")
    print(f"  已付成本     ：{stats['total_cost']:.2f} 點")
    print(sep)
    print(f"  最大回撤  ：{stats['max_drawdown_points']:.2f} 點")
    print(f"  交易次數  ：{stats['total_trades']} 筆（勝 {stats['win_times']} / 敗 {stats['loss_times']}）")
    print(f"  勝率      ：{stats['win_rate_pct']:.2f}%")
    print(f"  獲利因子  ：{stats['profit_factor']:.4f}")
    print(f"  盈虧比    ：{stats['pnl_ratio']:.4f}  (均獲 {stats['avg_win_points']:.1f} / 均虧 {stats['avg_loss_points']:.1f} 點)")
    print(sep)
    print("  月度損益（近 6 個月）：")
    for m in monthly[-6:]:
        bar = "+" * int(m["pnl"] / 10) if m["pnl"] > 0 else "-" * int(abs(m["pnl"]) / 10)
        sign = "+" if m["pnl"] >= 0 else ""
        print(f"    {m['month']}  {sign}{m['pnl']:>8.1f} 點  {bar[:30]}")
    print(sep)


# ── 主程式 ───────────────────────────────────────────────────────────────────

def main():
    code = sys.argv[1] if len(sys.argv) > 1 else "IBF_A1pf_tm"
    end_date   = date.fromisoformat(sys.argv[3]) if len(sys.argv) > 3 else date.today()
    begin_date = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date(2024, 1, 1)

    print(f"\n抓取策略：{code}  ({begin_date} ～ {end_date})")
    print("呼叫 API...")

    raw = fetch_strategy(code, begin_date, end_date)
    info   = parse_info(raw[0])
    stats  = calc_stats(info, raw[1])
    monthly = calc_monthly(stats["daily_pnl"])

    print_summary(info, stats, monthly)

    # 儲存完整 JSON
    output = {
        "strategy_code": code,
        "begin_date": str(begin_date),
        "end_date":   str(end_date),
        "info":       info,
        "stats": {k: v for k, v in stats.items() if k not in ("daily_pnl", "trade_records")},
        "monthly":    monthly,
        "daily_pnl":  stats["daily_pnl"],
        "trades":     stats["trade_records"],
    }
    save_json(output, f"{code}_data.json")

    # 儲存每日損益 CSV
    save_csv(
        stats["daily_pnl"],
        f"{code}_daily.csv",
        ["date", "index", "day_profit", "cum_profit"],
    )

    # 儲存交易紀錄 CSV
    save_csv(
        stats["trade_records"],
        f"{code}_trades.csv",
        ["date", "direction", "open_price", "close_price", "raw_pnl", "net_pnl"],
    )


if __name__ == "__main__":
    main()
