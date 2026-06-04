import pandas as pd

spreadsheet_id = '1x32OesDGzqU6QmHt_wrozLF4cIIUoaBuVCo2bypCeco'

gid_map = {
    'Teams': 0,
    'Matches_GP': 929864427,
    'Matches_FP': 1793296069,
    'Stages': 542487095
}

for key, gid in gid_map.items():
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={gid}"
    print('='*80)
    print(f"Leyendo {key} desde {url}")
    try:
        df = pd.read_csv(url)
        print(f"OK: {key} shape={df.shape}")
        print(df.head(3).to_string(index=False))
    except Exception as e:
        print(f"ERROR leyendo {key}: {e}")
