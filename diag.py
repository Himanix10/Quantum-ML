import glob
import pandas as pd

files = sorted(glob.glob('data/user_001_session_*.csv'))
print(f'Total files found: {len(files)}')
print()

for f in files[-5:]:
    try:
        df = pd.read_csv(f)
        print(f'File: {f[-35:]}')
        print(f'  Rows: {len(df)}')
        print(f'  Columns: {list(df.columns)}')
        if 'timestamp' in df.columns:
            print(f'  First ts: {df.timestamp.iloc[0]}')
        if 'vfq_score' in df.columns:
            print(f'  VFQ: {df.vfq_score.dropna().head(3).tolist()}')
        if 'blink_rate' in df.columns:
            print(f'  Blink: {df.blink_rate.dropna().head(3).tolist()}')
        print()
    except Exception as e:
        print(f'  ERROR: {e}')