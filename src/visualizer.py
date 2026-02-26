import cv2
import time
import collections
import numpy as np
from pipeline import UnifiedPipeline

# How many seconds of history to show in chart
HISTORY_SECONDS = 60
CHART_WIDTH     = 640
CHART_HEIGHT    = 400


def draw_chart(history, labels, colors, title):
    chart = np.zeros((CHART_HEIGHT, CHART_WIDTH, 3), dtype=np.uint8)
    chart[:] = (30, 30, 30)  # Dark background

    # Title
    cv2.putText(chart, title, (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

    # Draw grid lines
    for i in range(1, 5):
        y = int(CHART_HEIGHT * i / 5)
        cv2.line(chart, (0, y), (CHART_WIDTH, y), (60, 60, 60), 1)

    # Draw each feature line
    for key, color in zip(labels, colors):
        values = list(history[key])
        if len(values) < 2:
            continue

        # Normalize to 0-1 range for display
        min_val = min(values)
        max_val = max(values)
        if max_val == min_val:
            continue

        normalized = [(v - min_val) / (max_val - min_val) for v in values]

        # Draw line
        for i in range(1, len(normalized)):
            x1 = int((i - 1) / len(normalized) * CHART_WIDTH)
            x2 = int(i       / len(normalized) * CHART_WIDTH)
            y1 = int((1 - normalized[i - 1]) * (CHART_HEIGHT - 60) + 30)
            y2 = int((1 - normalized[i])     * (CHART_HEIGHT - 60) + 30)
            cv2.line(chart, (x1, y1), (x2, y2), color, 2)

        # Label with current value
        current = values[-1]
        idx     = labels.index(key)
        cv2.putText(chart, f"{key}: {current:.2f}",
                    (10, CHART_HEIGHT - 10 - idx * 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

    return chart


if __name__ == "__main__":
    pipeline = UnifiedPipeline()
    cap      = cv2.VideoCapture(0)

    # Feature history buffers
    history = {
        "ear":            collections.deque(maxlen=HISTORY_SECONDS),
        "blink_rate":     collections.deque(maxlen=HISTORY_SECONDS),
        "gaze_deviation": collections.deque(maxlen=HISTORY_SECONDS),
        "head_pitch":     collections.deque(maxlen=HISTORY_SECONDS),
        "luminance":      collections.deque(maxlen=HISTORY_SECONDS),
        "keystrokes_per_min": collections.deque(maxlen=HISTORY_SECONDS),
    }

    last_sample_time = time.time()
    print("Visualizer running. Press Q to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame, features = pipeline.process_frame(frame)

        # Sample features once per second
        now = time.time()
        if now - last_sample_time >= 1.0:
            for key in history:
                val = features.get(key)
                if val is not None:
                    history[key].append(float(val))
            last_sample_time = now

        # Draw chart
        chart = draw_chart(
            history,
            labels=["ear", "blink_rate", "gaze_deviation",
                    "head_pitch", "luminance", "keystrokes_per_min"],
            colors=[
                (0,   255, 255),   # EAR - yellow
                (0,   255, 0),     # blink rate - green
                (255, 0,   255),   # gaze - magenta
                (255, 165, 0),     # head pitch - orange
                (255, 255, 255),   # luminance - white
                (0,   128, 255),   # keystrokes - blue
            ],
            title="Live Feature Chart (last 60 seconds)"
        )

        cv2.imshow("Unified Pipeline", frame)
        cv2.imshow("Live Features",    chart)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    pipeline.stop()
    cap.release()
    cv2.destroyAllWindows()