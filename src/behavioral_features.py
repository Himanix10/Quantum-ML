import time
from collections import deque
from pynput import keyboard, mouse


class BehavioralFeatureExtractor:
    def __init__(self, window_seconds=15):
        # ── Reduced from 60s to 15s ───────────────────────────────────────────
        # 60s window meant keystrokes from a minute ago still showed up in
        # the rate — causing false "still typing" gates during neck stretch
        # and 20-20-20 verification even after the user had stopped completely.
        # 15s window reflects actual current behaviour much more accurately.
        self.window_seconds  = window_seconds

        # Keyboard tracking
        self.key_times       = deque()
        self.backspace_times = deque()

        # Mouse tracking
        self.mouse_positions    = deque(maxlen=2)
        self.mouse_dist_buffer  = deque()
        self.click_times        = deque()

        # Start listeners
        self.kb_listener = keyboard.Listener(on_press=self._on_key_press)
        self.ms_listener = mouse.Listener(
            on_move=self._on_mouse_move,
            on_click=self._on_mouse_click
        )
        self.kb_listener.start()
        self.ms_listener.start()

    def _on_key_press(self, key):
        now = time.time()
        self.key_times.append(now)
        if key == keyboard.Key.backspace:
            self.backspace_times.append(now)

    def _on_mouse_move(self, x, y):
        now = time.time()
        if self.mouse_positions:
            last_x, last_y, _ = self.mouse_positions[-1]
            dist = ((x - last_x)**2 + (y - last_y)**2) ** 0.5
            self.mouse_dist_buffer.append((dist, now))
        self.mouse_positions.append((x, y, now))

    def _on_mouse_click(self, x, y, button, pressed):
        if pressed:
            self.click_times.append(time.time())

    def _clean_window(self, dq):
        now = time.time()
        while dq and now - dq[0] > self.window_seconds:
            dq.popleft()

    def reset_keyboard(self):
        """
        Clear all keyboard history immediately.
        Called by reward_system when verification starts so stale
        keystrokes from before the break reminder do not block gates.
        """
        self.key_times.clear()
        self.backspace_times.clear()

    def reset_mouse(self):
        """
        Clear mouse distance buffer immediately.
        Called by reward_system when verification starts so accumulated
        mouse movement from before the break reminder does not block the
        20-20-20 gate (mouse threshold 5000 px/min).
        """
        self.mouse_dist_buffer.clear()
        self.click_times.clear()

    def get_features(self):
        now = time.time()

        # Clean old events outside window
        self._clean_window(self.key_times)
        self._clean_window(self.backspace_times)
        self._clean_window(self.click_times)

        # Clean mouse dist buffer
        while self.mouse_dist_buffer and \
              now - self.mouse_dist_buffer[0][1] > self.window_seconds:
            self.mouse_dist_buffer.popleft()

        # Keystrokes per minute — normalised to 1 minute
        keystrokes_per_min = len(self.key_times) / \
                             (self.window_seconds / 60)

        # Backspace rate (error proxy)
        backspace_per_min  = len(self.backspace_times) / \
                             (self.window_seconds / 60)

        # Mouse distance per minute
        mouse_dist         = sum(d for d, _ in self.mouse_dist_buffer)
        mouse_dist_per_min = mouse_dist / (self.window_seconds / 60)

        # Click rate
        clicks_per_min     = len(self.click_times) / \
                             (self.window_seconds / 60)

        return {
            "keystrokes_per_min":  round(keystrokes_per_min, 2),
            "backspace_per_min":   round(backspace_per_min,  2),
            "mouse_dist_per_min":  round(mouse_dist_per_min, 2),
            "clicks_per_min":      round(clicks_per_min,     2)
        }

    def stop(self):
        self.kb_listener.stop()
        self.ms_listener.stop()


# ── Test run ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Behavioral Feature Extractor running.")
    print("Type something, move your mouse, click around...")
    print("Press Ctrl+C to stop.\n")

    extractor = BehavioralFeatureExtractor()

    try:
        while True:
            features = extractor.get_features()
            print(f"Keys/min: {features['keystrokes_per_min']:6.1f} | "
                  f"Backspace/min: {features['backspace_per_min']:5.1f} | "
                  f"Mouse dist/min: {features['mouse_dist_per_min']:8.1f} | "
                  f"Clicks/min: {features['clicks_per_min']:5.1f}")
            time.sleep(2)
    except KeyboardInterrupt:
        extractor.stop()
        print("\nStopped.")