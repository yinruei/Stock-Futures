"""
台指期(TX)日/夜盤 OHLC 資料擷取器（FinMind 免費 API）
每個交易日輸出兩根棒：日盤(position) + 夜盤(after_market)

用法：
  python fetch_ohlc.py                              抓 2020-01-01 至今
  python fetch_ohlc.py 2024-01-01                   指定起始
  python fetch_ohlc.py 2024-01-01 2026-07-04        指定區間
輸出：futures_ohlc.json
"""

import os, sys, json, time, requests
from datetime import date, timedelta
from collections import defaultdict

FINMIND_BASE = 'https://api.finmindtrade.com/api/v4/data'
SYMBOL   = 'TX'
OUT_FILE = 'futures_ohlc.json'


def fetch_tx_daily(from_date: date, to_date: date) -> list:
    r = requests.get(FINMIND_BASE, params={
        'dataset':    'TaiwanFuturesDaily',
        'data_id':    SYMBOL,
        'start_date': str(from_date),
        'end_date':   str(to_date),
    }, timeout=30)
    r.raise_for_status()
    return r.json().get('data', [])


def build_bars(all_rows: list) -> list:
    """
    近月合約 (成交量最大單月) 的日盤 + 夜盤。
    日盤代表時間 11:00，夜盤代表時間 20:00。
    """
    # 按日期 → 合約 → session 分組
    by_date = defaultdict(lambda: defaultdict(dict))
    for r in all_rows:
        contract = str(r['contract_date'])
        if '/' in contract:
            continue  # 排除跨月價差合約
        date_str = r['date'].replace('-', '')  # YYYYMMDD
        by_date[date_str][contract][r['trading_session']] = r

    result = []
    for date_str in sorted(by_date):
        contracts = by_date[date_str]
        # 近月 = 成交量合計最大的單月合約
        near_key, near_sessions = max(
            contracts.items(),
            key=lambda kv: sum(s.get('volume', 0) for s in kv[1].values())
        )

        # 日盤 (position): 08:45–13:30 → 代表時間 11:00
        if 'position' in near_sessions:
            s = near_sessions['position']
            result.append({
                'dt':      date_str + '1100',  # YYYYMMDDHHMM
                'session': 'day',
                'o': s['open'],  'h': s['max'],
                'l': s['min'],   'c': s['close'],
                'v': s['volume'],
            })

        # 夜盤 (after_market): 15:00–次日 05:00 → 代表時間 20:00
        if 'after_market' in near_sessions:
            s = near_sessions['after_market']
            result.append({
                'dt':      date_str + '2000',  # YYYYMMDDHHMM
                'session': 'night',
                'o': s['open'],  'h': s['max'],
                'l': s['min'],   'c': s['close'],
                'v': s['volume'],
            })

    return sorted(result, key=lambda x: x['dt'])


def run(begin_date: date = None, end_date: date = None):
    if end_date is None:
        end_date = date.today()
    if begin_date is None:
        begin_date = date(2020, 1, 1)

    print(f'抓取台指期(TX) 日/夜盤 OHLC：{begin_date} ～ {end_date}')
    all_rows = []
    current = begin_date
    while current <= end_date:
        chunk_end = min(current + timedelta(days=89), end_date)
        print(f'  {current} ～ {chunk_end} ...', end=' ', flush=True)
        rows = fetch_tx_daily(current, chunk_end)
        print(f'{len(rows)} rows')
        all_rows.extend(rows)
        current = chunk_end + timedelta(days=1)
        if current <= end_date:
            time.sleep(0.4)

    bars = build_bars(all_rows)

    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(bars, f, ensure_ascii=False)

    kb = os.path.getsize(OUT_FILE) // 1024
    day_bars   = sum(1 for b in bars if b['session'] == 'day')
    night_bars = sum(1 for b in bars if b['session'] == 'night')
    print(f'→ {OUT_FILE} 已產生（日盤 {day_bars} + 夜盤 {night_bars} = {len(bars)} 根，{kb} KB）')
    return bars


if __name__ == '__main__':
    today = date.today()
    end   = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else today
    begin = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date(2020, 1, 1)
    run(begin, end)
