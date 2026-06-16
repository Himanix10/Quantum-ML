import os
import json
import numpy as np
import pandas as pd
from datetime import datetime


class BaselineProfiler:
    def __init__(self, user_id="user_001", data_dir=None,
                 profile_dir=None):
        self.user_id     = user_id

        # Resolve absolute paths
        _base            = os.path.dirname(os.path.abspath(__file__))
        self.data_dir    = data_dir or os.path.join(
            _base, '..', 'data', 'users', user_id, 'sessions')
        self.profile_dir = profile_dir or os.path.join(
            _base, '..', 'data', 'users', user_id)
        self.profile_path = os.path.join(
            self.profile_dir, 'profile.json')

        os.makedirs(self.profile_dir, exist_ok=True)

    def load_all_sessions(self):
        """Load and combine all CSV session files for this user."""
        if not os.path.exists(self.data_dir):
            print(f"Sessions directory not found: {self.data_dir}")
            return None

        all_files = [
            f for f in os.listdir(self.data_dir)
            if f.startswith(self.user_id) and f.endswith(".csv")
        ]

        if not all_files:
            print("No session files found.")
            return None

        dfs = []
        for fname in all_files:
            path = os.path.join(self.data_dir, fname)
            try:
                df = pd.read_csv(path)
                dfs.append(df)
                print(f"Loaded: {fname} ({len(df)} rows)")
            except Exception as e:
                print(f"Skipped {fname}: {e}")

        if not dfs:
            return None

        combined = pd.concat(dfs, ignore_index=True)
        print(f"\nTotal rows combined: {len(combined)}")
        return combined

    def compute_baseline(self, df):
        """Compute personal baseline statistics from combined session data."""
        baseline = {}

        # ── EAR baseline ──────────────────────────────────────────────────────
        ear_data = df["ear"].dropna()
        ear_open = ear_data[ear_data > 0.20]
        if len(ear_open) > 10:
            baseline["ear_mean"]   = round(float(ear_open.mean()), 4)
            baseline["ear_std"]    = round(float(ear_open.std()),  4)
            baseline["ear_lower"]  = round(float(
                ear_open.mean() - 2 * ear_open.std()), 4)
            print(f"EAR baseline: mean={baseline['ear_mean']} "
                  f"std={baseline['ear_std']} "
                  f"lower={baseline['ear_lower']}")

        # ── Blink rate baseline ───────────────────────────────────────────────
        blink_data = df["blink_rate"].dropna()
        blink_data = blink_data[blink_data > 0]
        if len(blink_data) > 10:
            baseline["blink_mean"] = round(float(blink_data.mean()), 2)
            baseline["blink_std"]  = round(float(blink_data.std()),  2)
            baseline["blink_lower"]= round(float(
                max(blink_data.mean() - 2 * blink_data.std(), 0)), 2)
            print(f"Blink baseline: mean={baseline['blink_mean']} "
                  f"std={baseline['blink_std']} "
                  f"lower={baseline['blink_lower']}")

        # ── Gaze deviation baseline ───────────────────────────────────────────
        gaze_data = df["gaze_deviation"].dropna()
        if len(gaze_data) > 10:
            baseline["gaze_mean"]  = round(float(gaze_data.mean()), 4)
            baseline["gaze_std"]   = round(float(gaze_data.std()),  4)
            baseline["gaze_upper"] = round(float(
                gaze_data.mean() + 2 * gaze_data.std()), 4)
            print(f"Gaze baseline: mean={baseline['gaze_mean']} "
                  f"std={baseline['gaze_std']} "
                  f"upper={baseline['gaze_upper']}")

        # ── Head pitch baseline ───────────────────────────────────────────────
        pitch_data = df["head_pitch"].dropna()
        if len(pitch_data) > 10:
            baseline["pitch_mean"] = round(float(pitch_data.mean()), 4)
            baseline["pitch_std"]  = round(float(pitch_data.std()),  4)
            baseline["pitch_upper"]= round(float(
                pitch_data.mean() + 2 * pitch_data.std()), 4)
            print(f"Pitch baseline: mean={baseline['pitch_mean']} "
                  f"std={baseline['pitch_std']} "
                  f"upper={baseline['pitch_upper']}")

        # ── Luminance baseline ────────────────────────────────────────────────
        lum_data = df["luminance"].dropna()
        if len(lum_data) > 10:
            baseline["lum_mean"]   = round(float(lum_data.mean()), 2)
            baseline["lum_std"]    = round(float(lum_data.std()),  2)
            print(f"Luminance baseline: mean={baseline['lum_mean']} "
                  f"std={baseline['lum_std']}")

        # ── Keystroke baseline ────────────────────────────────────────────────
        keys_data = df["keystrokes_per_min"].dropna()
        keys_data = keys_data[keys_data > 0]
        if len(keys_data) > 10:
            baseline["keys_mean"]  = round(float(keys_data.mean()), 2)
            baseline["keys_std"]   = round(float(keys_data.std()),  2)
            print(f"Keystroke baseline: mean={baseline['keys_mean']} "
                  f"std={baseline['keys_std']}")

        # ── VFQ baseline — KEY NEW ADDITION ──────────────────────────────────
        # Use the 25th percentile of historical VFQ as the personal resting
        # state. This is more representative than the mean because the mean
        # is pulled up by strained periods. The 25th percentile captures
        # the user's typical relaxed working VFQ.
        #
        # Personal threshold = baseline_vfq_p25 + 20
        # This means: trigger a break when VFQ is 20 points above their
        # typical relaxed state — regardless of where that state falls.
        #
        # Clinical rationale: fixed deviation above personal resting state
        # is consistent with personalised health monitoring literature
        # (Gjoreski et al. 2017).
        if "vfq_score" in df.columns:
            vfq_data = pd.to_numeric(
                df["vfq_score"], errors='coerce').dropna()
            # Filter out zeros (frames where face was not detected)
            vfq_data = vfq_data[vfq_data > 0]

            if len(vfq_data) > 30:
                vfq_p25  = round(float(np.percentile(vfq_data, 25)), 1)
                vfq_p50  = round(float(np.percentile(vfq_data, 50)), 1)
                vfq_mean = round(float(vfq_data.mean()), 1)
                vfq_std  = round(float(vfq_data.std()),  1)

                # Personal break threshold: median VFQ + 15 points
                # Using p50 (median) as the baseline reference gives a more
                # realistic "normal working VFQ" than p25 (which captures
                # only the most relaxed moments). Adding 15 triggers at
                # genuine strain elevation above typical working level.
                # Clamped between 30 (clinical minimum) and 50 (clinical max).
                # Example: if median VFQ = 23, threshold = 38
                personal_threshold = round(
                    float(np.clip(vfq_p50 + 15, 30, 50)), 1)

                baseline["vfq_p25"]             = vfq_p25
                baseline["vfq_p50"]             = vfq_p50
                baseline["vfq_mean"]            = vfq_mean
                baseline["vfq_std"]             = vfq_std
                baseline["personal_vfq_threshold"] = personal_threshold

                print(f"\nVFQ baseline (personal threshold):")
                print(f"  25th pct (resting VFQ): {vfq_p25}")
                print(f"  50th pct (median VFQ):  {vfq_p50}")
                print(f"  Mean VFQ:               {vfq_mean}")
                print(f"  Personal threshold:     {personal_threshold}  "
                      f"(resting + 20, clamped 30-50)")
            else:
                print("Not enough VFQ data for personal threshold — "
                      "using default 40")

        baseline["computed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        baseline["rows_used"]   = len(df)
        return baseline

    def save_baseline(self, baseline):
        """
        Save baseline into user profile JSON.
        Also runs a one-time clinical comparison.
        """
        if not os.path.exists(self.profile_path):
            profile = {
                "user_id":        self.user_id,
                "created_at":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_sessions": 0,
                "total_duration": 0,
                "last_session":   None,
                "sessions":       []
            }
        else:
            with open(self.profile_path, "r") as f:
                profile = json.load(f)

        profile["baseline_ear"]   = baseline.get("ear_mean")
        profile["baseline_blink"] = baseline.get("blink_mean")
        profile["baseline"]       = baseline

        # ── Clinical baseline check ───────────────────────────────────────────
        try:
            from personalization import get_clinical_warnings
            clinical_warnings = get_clinical_warnings(baseline)
            profile["baseline_clinical_warnings"] = clinical_warnings
            profile["baseline_warning_shown"]     = len(clinical_warnings) == 0

            if clinical_warnings:
                print(f"\n[Baseline] Clinical warnings ({len(clinical_warnings)}):")
                for w in clinical_warnings:
                    print(f"  ⚠  {w[:80]}...")
            else:
                print("\n[Baseline] All values within clinical norms.")
        except Exception as e:
            print(f"[Baseline] Clinical check skipped: {e}")
            profile["baseline_clinical_warnings"] = []
            profile["baseline_warning_shown"]     = True

        with open(self.profile_path, "w") as f:
            json.dump(profile, f, indent=2)

        print(f"\nBaseline saved to: {self.profile_path}")

    def run(self):
        """Full pipeline: load data, compute baseline, save."""
        print(f"Computing baseline for user: {self.user_id}")
        print("=" * 50)

        df = self.load_all_sessions()
        if df is None:
            print("Not enough data to compute baseline.")
            return None

        print("\nComputing baseline statistics...")
        print("-" * 50)
        baseline = self.compute_baseline(df)
        self.save_baseline(baseline)
        return baseline


# ── Test run ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    profiler = BaselineProfiler(user_id="user_001")
    baseline = profiler.run()

    if baseline:
        print("\n" + "=" * 50)
        print("YOUR PERSONAL BASELINE:")
        print("=" * 50)
        for key, val in baseline.items():
            if key not in ["computed_at", "rows_used"]:
                print(f"  {key:30s}: {val}")
                