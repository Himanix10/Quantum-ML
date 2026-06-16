"""
migrate_user_data.py
EyeStrain AI — One-Time Data Migration Script

Run this ONCE to move existing user_001 data from the old flat structure
into the new multi-user folder structure.

Old structure:
  data/
    user_001_session_*.csv
    profiles/
      user_001_profile.json
      rewards.json
      user_001_personalization.json

New structure:
  data/
    users/
      user_001/
        sessions/
          session_*.csv     (renamed from user_001_session_*.csv)
        profile.json
        rewards.json
        personalization.json
    app/
      users.json            (new — registry entry for user_001)
      system_pin.json       (new — created on first launch)

Usage:
  cd C:\\EyeStrain
  venv\\Scripts\\activate
  python src/migrate_user_data.py

Safe to run multiple times — skips already-migrated files.
"""

import os
import sys
import json
import shutil
import hashlib
from datetime import datetime
from pathlib import Path
from glob import glob

ROOT_DIR  = Path(__file__).parent.parent
DATA_DIR  = ROOT_DIR / 'data'
APP_DIR   = DATA_DIR / 'app'
USERS_DIR = DATA_DIR / 'users'

APP_DIR.mkdir(parents=True, exist_ok=True)
USERS_DIR.mkdir(parents=True, exist_ok=True)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def migrate_user(user_id: str = 'user_001'):
    print(f"\n{'='*55}")
    print(f"  EyeStrain AI — Data Migration")
    print(f"  Migrating: {user_id}")
    print(f"{'='*55}\n")

    user_dir      = USERS_DIR / user_id
    sessions_dir  = user_dir / 'sessions'
    user_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir.mkdir(parents=True, exist_ok=True)

    moved_csv = 0
    skipped   = 0

    # ── 1. Move session CSVs ──────────────────────────────────────────────────
    csv_files = sorted(glob(str(DATA_DIR / f'{user_id}_session_*.csv')))
    print(f"Found {len(csv_files)} session CSV(s) to migrate...")

    for src_path in csv_files:
        src      = Path(src_path)
        # Rename: user_001_session_20260407_121329.csv → session_20260407_121329.csv
        new_name = src.name.replace(f'{user_id}_session_', 'session_')
        dest     = sessions_dir / new_name

        if dest.exists():
            print(f"  Already migrated: {new_name}")
            skipped += 1
            continue

        shutil.copy2(src, dest)
        print(f"  Copied: {src.name} → users/{user_id}/sessions/{new_name}")
        moved_csv += 1

    # ── 2. Copy profile.json ──────────────────────────────────────────────────
    old_profile = DATA_DIR / 'profiles' / f'{user_id}_profile.json'
    new_profile = user_dir / 'profile.json'

    if old_profile.exists() and not new_profile.exists():
        shutil.copy2(old_profile, new_profile)
        print(f"\n  Copied: profiles/{user_id}_profile.json → users/{user_id}/profile.json")
    elif new_profile.exists():
        print(f"\n  profile.json already exists — skipped")
    else:
        print(f"\n  No profile.json found — will be created on first session")

    # ── 3. Copy rewards.json ──────────────────────────────────────────────────
    old_rewards = DATA_DIR / 'profiles' / 'rewards.json'
    new_rewards = user_dir / 'rewards.json'

    if old_rewards.exists() and not new_rewards.exists():
        shutil.copy2(old_rewards, new_rewards)
        print(f"  Copied: profiles/rewards.json → users/{user_id}/rewards.json")
    elif new_rewards.exists():
        print(f"  rewards.json already exists — skipped")

    # ── 4. Copy personalization.json ─────────────────────────────────────────
    old_pers = DATA_DIR / 'profiles' / f'{user_id}_personalization.json'
    new_pers = user_dir / 'personalization.json'

    if old_pers.exists() and not new_pers.exists():
        shutil.copy2(old_pers, new_pers)
        print(f"  Copied: profiles/{user_id}_personalization.json "
              f"→ users/{user_id}/personalization.json")
    elif new_pers.exists():
        print(f"  personalization.json already exists — skipped")

    # ── 5. Create users.json entry ────────────────────────────────────────────
    users_json = APP_DIR / 'users.json'
    if users_json.exists():
        with open(users_json) as f:
            users = json.load(f)
    else:
        users = {}

    if user_id not in users:
        # Read display name from profile if available
        full_name = user_id
        try:
            if new_profile.exists():
                with open(new_profile) as f:
                    profile_data = json.load(f)
                full_name = profile_data.get('full_name', user_id)
        except Exception:
            pass

        print(f"\n  Creating users.json entry for {user_id}...")
        print(f"  NOTE: Password will be set to 'eyestrain123' — CHANGE THIS after login.")

        users[user_id] = {
            "username":      user_id,
            "full_name":     full_name,
            "password_hash": sha256("eyestrain123"),
            "email":         "",
            "occupation":    "IT Professional",
            "avatar_path":   "",
            "created_at":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_login":    None,
            "migrated":      True,
        }
        with open(users_json, 'w') as f:
            json.dump(users, f, indent=2)
        print(f"  users.json created at data/app/users.json")
    else:
        print(f"\n  users.json entry for {user_id} already exists — skipped")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*55}")
    print(f"  Migration complete for {user_id}")
    print(f"  CSVs copied:   {moved_csv}")
    print(f"  CSVs skipped:  {skipped} (already migrated)")
    print(f"\n  IMPORTANT:")
    print(f"  Temporary password is: eyestrain123")
    print(f"  Change it by logging in and updating your profile.")
    print(f"\n  Original files in data/ and data/profiles/ are preserved.")
    print(f"  Delete them manually once you confirm migration worked.")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    user = sys.argv[1] if len(sys.argv) > 1 else 'user_001'
    migrate_user(user)