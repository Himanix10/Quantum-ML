# src/data_preprocessor.py
"""
Data Preprocessor — Day 18 (updated Day 22)
Reads all session CSVs, cleans and merges into one
training-ready dataset.

Test session fixed to f4cf6fec — highest HIGH strain rows (74 HIGH, 297 MOD)
This prevents the auto-split from picking a low-strain session as test set.
"""

import os
import pandas as pd
import numpy as np
from glob import glob


class DataPreprocessor:
    """
    Cleans and merges all session CSVs into one
    training-ready dataset.

    Usage:
        preprocessor = DataPreprocessor()
        df = preprocessor.run()
    """

    # ── Fixed test session — do not change unless you have a better strained session
    TEST_SESSION_ID = 'f4cf6fec'

    def __init__(self, data_dir="../data", output_dir="../data/processed"):
        self.data_dir   = os.path.join(os.path.dirname(__file__), '..', 'data')
        self.output_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed')
        os.makedirs(self.output_dir, exist_ok=True)

        self.feature_columns = [
            "ear", "blink_rate", "gaze_deviation",
            "head_pitch", "head_yaw", "head_roll",
            "luminance", "light_variance",
            "keystrokes_per_min", "backspace_per_min",
            "mouse_dist_per_min", "clicks_per_min",
            "vfq_score", "strain_label", "strain_trend"
        ]

    def load_all_csvs(self) -> pd.DataFrame:
        """Load and merge all session CSVs."""
        pattern = os.path.join(self.data_dir, "user_001_session_*.csv")
        files   = glob(pattern)

        if not files:
            raise FileNotFoundError(f"No CSVs found in {self.data_dir}")

        print(f"Found {len(files)} session files")

        dfs = []
        for f in files:
            df = pd.read_csv(f)
            df["source_file"] = os.path.basename(f)
            dfs.append(df)
            print(f"  Loaded {len(df):5d} rows — {os.path.basename(f)}")

        merged = pd.concat(dfs, ignore_index=True)
        print(f"\nTotal rows after merge: {len(merged)}")
        return merged

    def clean(self, df: pd.DataFrame) -> pd.DataFrame:
        """Full cleaning pipeline."""
        print("\n--- Cleaning ---")
        original_len = len(df)

        # 1. Fill missing strain_trend
        if "strain_trend" in df.columns:
            df["strain_trend"] = df["strain_trend"].fillna("STABLE")
        else:
            df["strain_trend"] = "STABLE"
        print(f"✅ strain_trend filled")

        # 2. Drop rows where face not detected
        if "face_detected" in df.columns:
            before = len(df)
            df = df[df["face_detected"] == True].copy()
            print(f"✅ Dropped {before - len(df)} rows — face not detected")

        # 3. Remove inf and NaN from numeric columns
        numeric_cols = [
            "ear", "blink_rate", "gaze_deviation",
            "head_pitch", "head_yaw", "head_roll",
            "luminance", "light_variance",
            "keystrokes_per_min", "backspace_per_min",
            "mouse_dist_per_min", "clicks_per_min",
            "vfq_score"
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
                df[col] = df[col].replace([np.inf, -np.inf], np.nan)

        before = len(df)
        df = df.dropna(subset=["ear", "vfq_score", "blink_rate"])
        print(f"✅ Dropped {before - len(df)} rows — NaN in key columns")

        # 4. Remove EAR outliers
        before = len(df)
        df = df[(df["ear"] >= 0.1) & (df["ear"] <= 0.5)]
        print(f"✅ Dropped {before - len(df)} rows — EAR outliers")

        # 5. Remove VFQ outliers
        before = len(df)
        df = df[(df["vfq_score"] >= 0) & (df["vfq_score"] <= 100)]
        print(f"✅ Dropped {before - len(df)} rows — VFQ outliers")

        # 6. Remove blink rate outliers
        before = len(df)
        df = df[(df["blink_rate"] >= 0) & (df["blink_rate"] <= 60)]
        print(f"✅ Dropped {before - len(df)} rows — blink rate outliers")

        print(f"\nRows before cleaning: {original_len}")
        print(f"Rows after cleaning:  {len(df)}")
        print(f"Rows removed:         {original_len - len(df)}")

        return df

    def encode_labels(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert strain_label and strain_trend text to numeric."""
        label_map = {
            "NORMAL":   0,
            "LOW":      1,
            "MODERATE": 2,
            "HIGH":     3,
            "SEVERE":   4
        }
        trend_map = {
            "IMPROVING": -1,
            "STABLE":     0,
            "WORSENING":  1
        }
        df["strain_label_enc"] = df["strain_label"].map(label_map)
        df["strain_trend_enc"] = df["strain_trend"].map(trend_map)

        print(f"\n✅ Labels encoded")
        print(f"Label distribution:\n{df['strain_label'].value_counts()}")
        return df

    def normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Min-max normalize all numeric feature columns."""
        cols_to_normalize = [
            "ear", "blink_rate", "gaze_deviation",
            "head_pitch", "head_yaw", "head_roll",
            "luminance", "light_variance",
            "keystrokes_per_min", "backspace_per_min",
            "mouse_dist_per_min", "clicks_per_min"
        ]
        for col in cols_to_normalize:
            if col in df.columns:
                col_min = df[col].min()
                col_max = df[col].max()
                if col_max - col_min > 0:
                    df[f"{col}_norm"] = (df[col] - col_min) / (col_max - col_min)
                else:
                    df[f"{col}_norm"] = 0.0

        print(f"\n✅ Normalization complete")
        return df

    def train_test_split(self, df: pd.DataFrame):
        """
        Split by SESSION not by row — prevents data leakage.
        Test session is FIXED to TEST_SESSION_ID — the session with
        the most HIGH strain rows, ensuring meaningful model evaluation.
        All other sessions go to train.
        """
        all_sessions = df["session_id"].unique().tolist()

        # Verify test session exists in data
        if self.TEST_SESSION_ID not in all_sessions:
            print(f"\n⚠️  WARNING: Test session {self.TEST_SESSION_ID} not found.")
            print(f"  Available sessions: {all_sessions}")
            print(f"  Falling back to last 20% split.")
            n_test         = max(1, int(len(all_sessions) * 0.2))
            test_sessions  = all_sessions[-n_test:]
            train_sessions = all_sessions[:-n_test]
        else:
            test_sessions  = [self.TEST_SESSION_ID]
            train_sessions = [s for s in all_sessions if s not in test_sessions]

        train_df = df[df["session_id"].isin(train_sessions)].copy()
        test_df  = df[df["session_id"].isin(test_sessions)].copy()

        print(f"\n✅ Train/test split by session (FIXED test session)")
        print(f"  Test session:   {test_sessions}")
        print(f"  Train sessions: {len(train_sessions)} sessions — {len(train_df)} rows")
        print(f"  Test sessions:  {len(test_sessions)} session  — {len(test_df)} rows")

        print(f"\n  Train label distribution:")
        print(f"  {train_df['strain_label'].value_counts().to_dict()}")
        print(f"\n  Test label distribution:")
        print(f"  {test_df['strain_label'].value_counts().to_dict()}")

        return train_df, test_df

    def save(self, train_df, test_df) -> None:
        """Save cleaned datasets."""
        train_path = os.path.join(self.output_dir, "train.csv")
        test_path  = os.path.join(self.output_dir, "test.csv")

        train_df.to_csv(train_path, index=False)
        test_df.to_csv(test_path,   index=False)

        print(f"\n✅ Saved train.csv — {len(train_df)} rows → {train_path}")
        print(f"✅ Saved test.csv  — {len(test_df)} rows → {test_path}")

    def run(self) -> pd.DataFrame:
        """Full pipeline — load, clean, encode, normalize, split, save."""
        df = self.load_all_csvs()
        df = self.clean(df)
        df = self.encode_labels(df)
        df = self.normalize(df)
        train_df, test_df = self.train_test_split(df)
        self.save(train_df, test_df)
        print("\n🎉 Preprocessing complete!")
        return df


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    preprocessor = DataPreprocessor()
    df = preprocessor.run()