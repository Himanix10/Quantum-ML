"""
feature_engineer.py
Lead Developer — AI Core
Reads train.csv and test.csv from data/processed/,
adds 11 engineered features, saves as:
  data/processed/train_engineered.csv
  data/processed/test_engineered.csv

Run AFTER data_preprocessor.py:
  python src/data_preprocessor.py
  python src/feature_engineer.py
"""

import pandas as pd
import numpy as np
import os

# ── CONFIG ───────────────────────────────────────────────────────────────────
PROCESSED_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed')
TRAIN_IN      = os.path.join(PROCESSED_DIR, 'train.csv')
TEST_IN       = os.path.join(PROCESSED_DIR, 'test.csv')
TRAIN_OUT     = os.path.join(PROCESSED_DIR, 'train_engineered.csv')
TEST_OUT      = os.path.join(PROCESSED_DIR, 'test_engineered.csv')

ROLLING_WINDOW = 30   # 30-second rolling window for stats
TREND_WINDOW   = 60   # 60-second window for EAR slope


# ── FEATURE ENGINEERING ───────────────────────────────────────────────────────
def engineer_features(df: pd.DataFrame, split_name: str) -> pd.DataFrame:
    """
    Adds 11 derived features per session without crossing session boundaries.
    All operations grouped by session_id.
    """
    print(f"\n  Engineering features for {split_name} set...")
    print(f"  Input: {len(df)} rows across {df['session_id'].nunique()} sessions")

    all_sessions = []

    for session_id, session_df in df.groupby('session_id'):
        session_df = session_df.copy().reset_index(drop=True)
        n = len(session_df)

        # ── 1. Rolling mean + std for EAR ──
        session_df['ear_roll_mean'] = (
            session_df['ear']
            .rolling(window=ROLLING_WINDOW, min_periods=1)
            .mean()
        )
        session_df['ear_roll_std'] = (
            session_df['ear']
            .rolling(window=ROLLING_WINDOW, min_periods=1)
            .std()
            .fillna(0)
        )

        # ── 2. Rolling mean + std for blink rate ──
        session_df['blink_rate_roll_mean'] = (
            session_df['blink_rate']
            .rolling(window=ROLLING_WINDOW, min_periods=1)
            .mean()
        )
        session_df['blink_rate_roll_std'] = (
            session_df['blink_rate']
            .rolling(window=ROLLING_WINDOW, min_periods=1)
            .std()
            .fillna(0)
        )

        # ── 3. Rolling mean + std for gaze deviation ──
        session_df['gaze_deviation_roll_mean'] = (
            session_df['gaze_deviation']
            .rolling(window=ROLLING_WINDOW, min_periods=1)
            .mean()
        )
        session_df['gaze_deviation_roll_std'] = (
            session_df['gaze_deviation']
            .rolling(window=ROLLING_WINDOW, min_periods=1)
            .std()
            .fillna(0)
        )

        # ── 4. Rolling mean + std for head pitch ──
        session_df['head_pitch_roll_mean'] = (
            session_df['head_pitch']
            .rolling(window=ROLLING_WINDOW, min_periods=1)
            .mean()
        )
        session_df['head_pitch_roll_std'] = (
            session_df['head_pitch']
            .rolling(window=ROLLING_WINDOW, min_periods=1)
            .std()
            .fillna(0)
        )

        # ── 5. Rolling mean + std for VFQ score ──
        session_df['vfq_score_roll_mean'] = (
            session_df['vfq_score']
            .rolling(window=ROLLING_WINDOW, min_periods=1)
            .mean()
        )
        session_df['vfq_score_roll_std'] = (
            session_df['vfq_score']
            .rolling(window=ROLLING_WINDOW, min_periods=1)
            .std()
            .fillna(0)
        )

        # ── 6. Blink irregularity ──
        # How much current blink rate deviates from session mean
        session_mean_blink = session_df['blink_rate'].mean()
        session_df['blink_irregularity'] = (
            session_df['blink_rate'] - session_mean_blink
        ).abs()

        # ── 7. Gaze instability ──
        # Rolling std of gaze deviation — how erratic gaze is
        session_df['gaze_instability'] = (
            session_df['gaze_deviation']
            .rolling(window=ROLLING_WINDOW, min_periods=1)
            .std()
            .fillna(0)
        )

        # ── 8. Fatigue progression ──
        # Position in session normalized 0 → 1
        # Encodes that strain tends to build as session goes on
        session_df['fatigue_progression'] = (
            np.arange(n) / max(n - 1, 1)
        )

        # ── 9. EAR trend ──
        # Slope of EAR over last TREND_WINDOW rows
        # Negative slope = eyes closing = fatigue building
        ear_trend = np.zeros(n)
        for i in range(n):
            start = max(0, i - TREND_WINDOW + 1)
            window_ear = session_df['ear'].iloc[start:i + 1].values
            if len(window_ear) >= 2:
                x = np.arange(len(window_ear))
                slope = np.polyfit(x, window_ear, 1)[0]
                ear_trend[i] = slope
        session_df['ear_trend'] = ear_trend

        # ── 10. Encode strain_label → integer if not already done ──
        label_map = {
            'NORMAL': 0, 'LOW': 1, 'MODERATE': 2, 'HIGH': 3, 'SEVERE': 4
        }
        if 'strain_label_enc' not in session_df.columns:
            if session_df['strain_label'].dtype == object:
                session_df['strain_label_enc'] = (
                    session_df['strain_label'].map(label_map)
                )
            else:
                session_df['strain_label_enc'] = session_df['strain_label']

        # ── 11. Encode strain_trend → integer if not already done ──
        trend_map = {'IMPROVING': 0, 'STABLE': 1, 'WORSENING': 2}
        if 'strain_trend_enc' not in session_df.columns:
            if session_df['strain_trend'].dtype == object:
                session_df['strain_trend_enc'] = (
                    session_df['strain_trend'].map(trend_map)
                )
            else:
                session_df['strain_trend_enc'] = session_df['strain_trend']

        all_sessions.append(session_df)

    result = pd.concat(all_sessions, ignore_index=True)

    # ── Drop rows where any engineered feature is NaN ──
    before = len(result)
    engineered_cols = [
        'ear_roll_mean', 'ear_roll_std',
        'blink_rate_roll_mean', 'blink_rate_roll_std',
        'gaze_deviation_roll_mean', 'gaze_deviation_roll_std',
        'head_pitch_roll_mean', 'head_pitch_roll_std',
        'vfq_score_roll_mean', 'vfq_score_roll_std',
        'blink_irregularity', 'gaze_instability',
        'fatigue_progression', 'ear_trend',
        'strain_label_enc', 'strain_trend_enc'
    ]
    result = result.dropna(subset=engineered_cols)
    after = len(result)

    if before != after:
        print(f"  Dropped {before - after} rows with NaN in engineered features")

    print(f"  Output: {after} rows")
    print(f"  Sessions: {result['session_id'].nunique()}")
    print(f"  Label distribution:")
    label_names = {0: 'NORMAL', 1: 'LOW', 2: 'MODERATE', 3: 'HIGH', 4: 'SEVERE'}
    for enc, name in label_names.items():
        count = (result['strain_label_enc'] == enc).sum()
        if count > 0:
            print(f"    {name}: {count}")

    return result


# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  feature_engineer.py — EyeStrain AI")
    print("=" * 60)

    # ── Check input files exist ──
    if not os.path.exists(TRAIN_IN):
        raise FileNotFoundError(
            f"Train file not found: {TRAIN_IN}\n"
            f"Run data_preprocessor.py first."
        )
    if not os.path.exists(TEST_IN):
        raise FileNotFoundError(
            f"Test file not found: {TEST_IN}\n"
            f"Run data_preprocessor.py first."
        )

    # ── Load ──
    print("\n[1] Loading preprocessed CSVs...")
    train_df = pd.read_csv(TRAIN_IN)
    test_df  = pd.read_csv(TEST_IN)
    print(f"  Train: {len(train_df)} rows")
    print(f"  Test:  {len(test_df)} rows")

    # ── Engineer ──
    print("\n[2] Engineering features...")
    train_eng = engineer_features(train_df, 'train')
    test_eng  = engineer_features(test_df,  'test')

    # ── Save ──
    print("\n[3] Saving engineered CSVs...")
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    train_eng.to_csv(TRAIN_OUT, index=False)
    test_eng.to_csv(TEST_OUT,   index=False)
    print(f"  Saved → {TRAIN_OUT}")
    print(f"  Saved → {TEST_OUT}")
    print(f"  Train columns: {len(train_eng.columns)}")
    print(f"  Test  columns: {len(test_eng.columns)}")

    print("\n" + "=" * 60)
    print("  feature_engineer.py complete.")
    print(f"  Train: {len(train_eng)} rows  |  Test: {len(test_eng)} rows")
    print("=" * 60)


if __name__ == '__main__':
    main()