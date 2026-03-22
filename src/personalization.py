"""
personalization.py
Lead Developer — AI Core

K-Means clustering on session history to identify personal strain patterns.
Adapts alert thresholds based on:
  - Time of day patterns
  - Session length patterns  
  - Task intensity patterns (keystroke/mouse activity)
  - Personal strain trajectory patterns

Usage:
    from personalization import PersonalizationEngine
    engine = PersonalizationEngine(user_id='user_001')
    engine.fit()
    adapted = engine.get_adapted_thresholds()
"""

import os
import json
import numpy as np
import pandas as pd
from datetime import datetime
from glob import glob
from collections import defaultdict


# ── CONFIG ────────────────────────────────────────────────────────────────────
DATA_DIR     = os.path.join(os.path.dirname(__file__), '..', 'data')
PROFILE_DIR  = os.path.join(DATA_DIR, 'profiles')
N_CLUSTERS   = 3   # LOW strain sessions / MEDIUM / HIGH strain sessions
MIN_SESSIONS = 3   # minimum sessions needed before adaptation kicks in


class PersonalizationEngine:
    """
    Clusters user's session history into strain pattern groups.
    Each cluster represents a different usage context:
      Cluster 0 — relaxed sessions (low VFQ, high blink, morning)
      Cluster 1 — moderate sessions (average strain)
      Cluster 2 — intense sessions (high VFQ, low blink, late night)

    Adapted thresholds are computed per cluster so the break reminder
    fires earlier during intense sessions and later during relaxed ones.
    """

    def __init__(self, user_id='user_001'):
        self.user_id          = user_id
        self.n_clusters       = N_CLUSTERS
        self.is_fitted        = False
        self.clusters_        = None
        self.centroids_       = None
        self.session_features = None
        self.session_labels_  = None
        self.adapted_thresholds = self._default_thresholds()
        self._output_path     = os.path.join(
            PROFILE_DIR, f'{user_id}_personalization.json'
        )
        # Load existing model if available
        self._load()

    # ── Default thresholds ────────────────────────────────────────────────────

    def _default_thresholds(self):
        return {
            'break_trigger_vfq':      40,
            'break_trigger_duration': 300,
            'reminder_cooldown':      600,
            'verify_window':          300,
            'min_vfq_drop':           20,
            'context':                'default'
        }

    # ── Feature extraction ────────────────────────────────────────────────────

    def _extract_session_features(self, df, filename):
        """
        Extract 8 features per session that describe its strain character.
        These become the input vectors for K-Means clustering.
        """
        features = {}

        # 1. Average VFQ — overall strain level
        if 'vfq_score' in df.columns:
            vfqs = pd.to_numeric(
                df['vfq_score'], errors='coerce').dropna()
            features['avg_vfq']     = float(vfqs.mean()) if len(vfqs) else 0
            features['max_vfq']     = float(vfqs.max())  if len(vfqs) else 0
            features['high_pct']    = float(
                (vfqs >= 60).sum() / len(vfqs) * 100) if len(vfqs) else 0
            features['vfq_slope']   = self._compute_slope(vfqs.tolist())
        else:
            features.update({'avg_vfq': 0, 'max_vfq': 0,
                              'high_pct': 0, 'vfq_slope': 0})

        # 2. Average blink rate — low = intense focus
        if 'blink_rate' in df.columns:
            blinks = pd.to_numeric(
                df['blink_rate'], errors='coerce').dropna()
            features['avg_blink'] = float(blinks.mean()) if len(blinks) else 0
        else:
            features['avg_blink'] = 0

        # 3. Session duration — longer = more strain risk
        features['duration_min'] = len(df) / 60.0

        # 4. Hour of day — late night sessions tend to be more strained
        try:
            ts = pd.to_datetime(df['timestamp'].iloc[0], errors='coerce')
            features['hour_of_day'] = float(ts.hour) if ts else 12.0
        except Exception:
            # Try to get from filename
            try:
                hour = int(filename[-10:-8])
                features['hour_of_day'] = float(hour)
            except Exception:
                features['hour_of_day'] = 12.0

        # 5. Keystroke intensity — high = cognitive load
        if 'keystrokes_per_min' in df.columns:
            keys = pd.to_numeric(
                df['keystrokes_per_min'], errors='coerce').dropna()
            features['avg_keystrokes'] = float(
                keys.mean()) if len(keys) else 0
        else:
            features['avg_keystrokes'] = 0

        return features

    def _compute_slope(self, values):
        """Linear regression slope — positive = strain building over time."""
        if len(values) < 2:
            return 0.0
        x = np.arange(len(values))
        try:
            slope = np.polyfit(x, values, 1)[0]
            return float(slope)
        except Exception:
            return 0.0

    # ── K-Means ───────────────────────────────────────────────────────────────

    def _kmeans_fit(self, X, n_clusters, n_init=10, max_iter=300):
        """
        Pure NumPy K-Means — no sklearn dependency.
        Returns centroids and labels.
        """
        n_samples = len(X)
        if n_samples < n_clusters:
            # Not enough sessions — assign all to one cluster
            return np.array([X.mean(axis=0)]), np.zeros(n_samples, dtype=int)

        best_labels    = None
        best_centroids = None
        best_inertia   = float('inf')

        for _ in range(n_init):
            # Random initialization
            idx       = np.random.choice(n_samples, n_clusters, replace=False)
            centroids = X[idx].copy()

            for _ in range(max_iter):
                # Assign clusters
                dists  = np.linalg.norm(
                    X[:, np.newaxis] - centroids[np.newaxis, :], axis=2)
                labels = np.argmin(dists, axis=1)

                # Update centroids
                new_centroids = np.array([
                    X[labels == k].mean(axis=0)
                    if (labels == k).sum() > 0
                    else centroids[k]
                    for k in range(n_clusters)
                ])

                if np.allclose(centroids, new_centroids, atol=1e-6):
                    break
                centroids = new_centroids

            # Compute inertia
            inertia = sum(
                np.linalg.norm(X[i] - centroids[labels[i]]) ** 2
                for i in range(n_samples)
            )

            if inertia < best_inertia:
                best_inertia   = inertia
                best_labels    = labels.copy()
                best_centroids = centroids.copy()

        return best_centroids, best_labels

    # ── Fit ───────────────────────────────────────────────────────────────────

    def fit(self):
        """
        Load all session CSVs, extract features, cluster, adapt thresholds.
        Call this after every new session is added.
        """
        print(f"\n[Personalization] Fitting K-Means for {self.user_id}...")

        # Load all sessions
        pattern = os.path.join(
            DATA_DIR, f'user_001_session_*.csv')
        files   = sorted(glob(pattern))

        if len(files) < MIN_SESSIONS:
            print(f"  Only {len(files)} sessions — need {MIN_SESSIONS} minimum.")
            print(f"  Using default thresholds.")
            return False

        session_features = []
        session_files    = []

        for f in files:
            try:
                df = pd.read_csv(f)
                if len(df) < 60:  # skip sessions under 1 minute
                    continue
                feats = self._extract_session_features(df, f)
                session_features.append(feats)
                session_files.append(f)
            except Exception as e:
                print(f"  Skipped {os.path.basename(f)}: {e}")

        if len(session_features) < MIN_SESSIONS:
            print(f"  Not enough valid sessions after filtering.")
            return False

        print(f"  Sessions loaded: {len(session_features)}")

        # Build feature matrix
        feature_keys = [
            'avg_vfq', 'max_vfq', 'high_pct', 'vfq_slope',
            'avg_blink', 'duration_min', 'hour_of_day', 'avg_keystrokes'
        ]
        X_raw = np.array([
            [f.get(k, 0) for k in feature_keys]
            for f in session_features
        ], dtype=np.float32)

        # Normalize each feature to 0-1
        X_min  = X_raw.min(axis=0)
        X_max  = X_raw.max(axis=0)
        X_range = X_max - X_min
        X_range[X_range == 0] = 1  # avoid division by zero
        X_norm = (X_raw - X_min) / X_range

        # Fit K-Means
        n_clusters     = min(self.n_clusters, len(session_features))
        centroids, labels = self._kmeans_fit(X_norm, n_clusters)

        self.centroids_       = centroids
        self.clusters_        = labels
        self.session_features = session_features
        self.session_labels_  = labels
        self._X_min           = X_min
        self._X_max           = X_max
        self._feature_keys    = feature_keys
        self.is_fitted        = True

        # Analyze clusters
        cluster_analysis = self._analyze_clusters(
            session_features, labels, n_clusters)

        print(f"\n  Cluster analysis:")
        for cid, info in cluster_analysis.items():
            print(f"    Cluster {cid} — {info['label']}: "
                  f"{info['count']} sessions, "
                  f"avg VFQ {info['avg_vfq']:.1f}, "
                  f"avg blink {info['avg_blink']:.1f}/min")

        self._cluster_analysis = cluster_analysis
        self._save()

        print(f"\n  Personalization fitted successfully.")
        return True

    def _analyze_clusters(self, features, labels, n_clusters):
        """Characterize each cluster by its dominant patterns."""
        analysis = {}

        for cid in range(n_clusters):
            mask    = labels == cid
            indices = [i for i, m in enumerate(mask) if m]

            if not indices:
                continue

            cluster_feats = [features[i] for i in indices]

            avg_vfq   = np.mean([f['avg_vfq']   for f in cluster_feats])
            avg_blink = np.mean([f['avg_blink']  for f in cluster_feats])
            avg_hour  = np.mean([f['hour_of_day'] for f in cluster_feats])
            avg_dur   = np.mean([f['duration_min'] for f in cluster_feats])
            avg_high  = np.mean([f['high_pct']   for f in cluster_feats])

            # Label the cluster by its character
            if avg_vfq < 30:
                label = 'Relaxed'
            elif avg_vfq < 50:
                label = 'Moderate'
            else:
                label = 'Intense'

            analysis[cid] = {
                'label':      label,
                'count':      len(indices),
                'avg_vfq':    round(avg_vfq,   1),
                'avg_blink':  round(avg_blink, 1),
                'avg_hour':   round(avg_hour,  1),
                'avg_dur':    round(avg_dur,   1),
                'avg_high_pct': round(avg_high, 1),
            }

        return analysis

    # ── Predict current context ───────────────────────────────────────────────

    def predict_context(self, current_features: dict) -> dict:
        """
        Given current session features, predict which cluster
        this session belongs to and return adapted thresholds.

        Call this at session start or every 5 minutes during a session.
        """
        if not self.is_fitted:
            return self.adapted_thresholds

        try:
            feature_keys = self._feature_keys
            x_raw = np.array(
                [current_features.get(k, 0) for k in feature_keys],
                dtype=np.float32
            )

            # Normalize
            x_range = self._X_max - self._X_min
            x_range[x_range == 0] = 1
            x_norm = (x_raw - self._X_min) / x_range
            x_norm = x_norm.reshape(1, -1)

            # Find nearest centroid
            dists   = np.linalg.norm(
                self.centroids_ - x_norm, axis=1)
            cluster = int(np.argmin(dists))

            # Get cluster info
            info    = self._cluster_analysis.get(cluster, {})
            label   = info.get('label', 'Moderate')

            # Adapt thresholds based on cluster
            thresholds = self._adapt_thresholds(cluster, label, info)
            self.adapted_thresholds = thresholds

            print(f"[Personalization] Context: {label} "
                  f"(cluster {cluster}) — "
                  f"break trigger at VFQ {thresholds['break_trigger_vfq']}")

            return thresholds

        except Exception as e:
            print(f"[Personalization] predict_context error: {e}")
            return self._default_thresholds()

    def _adapt_thresholds(self, cluster_id, label, info):
        """
        Adapt break trigger threshold based on session context.

        Relaxed sessions:  higher threshold (user naturally low VFQ)
        Moderate sessions: default threshold
        Intense sessions:  lower threshold (user strains faster)
        """
        base_vfq      = 40
        base_duration = 300   # 5 minutes

        if label == 'Relaxed':
            # User is naturally relaxed — raise threshold slightly
            adapted_vfq      = min(55, base_vfq + 10)
            adapted_duration = int(base_duration * 1.2)
            context_note     = "Relaxed session — thresholds raised"

        elif label == 'Intense':
            # User strains fast — lower threshold, fire earlier
            adapted_vfq      = max(30, base_vfq - 10)
            adapted_duration = int(base_duration * 0.8)
            context_note     = "Intense session — thresholds lowered"

        else:
            adapted_vfq      = base_vfq
            adapted_duration = base_duration
            context_note     = "Moderate session — default thresholds"

        return {
            'break_trigger_vfq':      adapted_vfq,
            'break_trigger_duration': adapted_duration,
            'reminder_cooldown':      600,
            'verify_window':          300,
            'min_vfq_drop':           20,
            'context':                label,
            'context_note':           context_note,
            'cluster_id':             cluster_id,
        }

    def get_adapted_thresholds(self):
        """Returns current adapted thresholds."""
        return self.adapted_thresholds

    def get_cluster_summary(self):
        """Returns cluster analysis for dashboard display."""
        if not self.is_fitted:
            return {'fitted': False, 'message': 'Need more sessions'}
        return {
            'fitted':   True,
            'clusters': self._cluster_analysis,
            'n_sessions': len(self.session_features)
        }

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save(self):
        """Save fitted model to JSON."""
        try:
            os.makedirs(PROFILE_DIR, exist_ok=True)
            data = {
                'user_id':          self.user_id,
                'fitted_at':        datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"),
                'n_sessions':       len(self.session_features),
                'n_clusters':       self.n_clusters,
                'centroids':        self.centroids_.tolist(),
                'X_min':            self._X_min.tolist(),
                'X_max':            self._X_max.tolist(),
                'feature_keys':     self._feature_keys,
                'cluster_analysis': self._cluster_analysis,
                'adapted_thresholds': self.adapted_thresholds,
            }
            with open(self._output_path, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"  Saved → {self._output_path}")
        except Exception as e:
            print(f"[Personalization] Save error: {e}")

    def _load(self):
        """Load previously fitted model from JSON."""
        try:
            if not os.path.exists(self._output_path):
                return
            with open(self._output_path, 'r') as f:
                data = json.load(f)
            self.centroids_         = np.array(data['centroids'])
            self._X_min             = np.array(data['X_min'])
            self._X_max             = np.array(data['X_max'])
            self._feature_keys      = data['feature_keys']
            self._cluster_analysis  = {
                int(k): v for k, v in data['cluster_analysis'].items()
            }
            self.adapted_thresholds = data.get(
                'adapted_thresholds', self._default_thresholds())
            self.is_fitted          = True
            print(f"[Personalization] Loaded model — "
                  f"{data['n_sessions']} sessions, "
                  f"{data['n_clusters']} clusters")
        except Exception as e:
            print(f"[Personalization] Load error: {e}")


# ── Wire into session_manager ─────────────────────────────────────────────────

def run_standalone():
    """Test personalization engine standalone."""
    print("=" * 50)
    print("  Personalization Engine — EyeStrain AI")
    print("=" * 50)

    engine = PersonalizationEngine(user_id='user_001')
    success = engine.fit()

    if not success:
        print("\nNot enough sessions to cluster.")
        return

    summary = engine.get_cluster_summary()
    print(f"\nClusters found: {len(summary['clusters'])}")
    for cid, info in summary['clusters'].items():
        print(f"\n  Cluster {cid} — {info['label']}")
        print(f"    Sessions:      {info['count']}")
        print(f"    Avg VFQ:       {info['avg_vfq']}")
        print(f"    Avg Blink:     {info['avg_blink']}/min")
        print(f"    Avg Hour:      {info['avg_hour']}:00")
        print(f"    Avg Duration:  {info['avg_dur']:.0f} min")
        print(f"    High Strain %: {info['avg_high_pct']}%")

    # Simulate predicting context for a current session
    print("\n\nSimulating context prediction for current session...")
    mock_current = {
        'avg_vfq':       45.0,
        'max_vfq':       72.0,
        'high_pct':      18.0,
        'vfq_slope':     0.05,
        'avg_blink':     6.2,
        'duration_min':  25.0,
        'hour_of_day':   23.0,
        'avg_keystrokes': 45.0,
    }
    thresholds = engine.predict_context(mock_current)
    print(f"\nAdapted thresholds for this session:")
    for k, v in thresholds.items():
        print(f"  {k}: {v}")


if __name__ == '__main__':
    run_standalone()