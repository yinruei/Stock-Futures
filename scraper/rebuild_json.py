"""從現有的 *_data.json 重建 compare_data.json（不需重爬）"""
import json, glob, os
from pathlib import Path

files = sorted(glob.glob('*_data.json'))
print(f'找到 {len(files)} 個 JSON 檔案')
all_outputs = []
for f in files:
    try:
        data = json.loads(Path(f).read_text(encoding='utf-8'))
        all_outputs.append(data)
    except Exception as e:
        print(f'  ✗ {f}: {e}')

with open('compare_data.json', 'w', encoding='utf-8') as f:
    json.dump(all_outputs, f, ensure_ascii=False)

size_kb = os.path.getsize('compare_data.json') // 1024
print(f'compare_data.json 已產生（{len(all_outputs)} 筆策略，{size_kb} KB）')
