"""
tcn_model.py
Lead Developer — AI Core
Temporal Convolutional Network + Multi-Head Self-Attention
for real-time eye strain prediction.

Architecture:
  Input  → TCN Encoder (dilated causal conv) → Self-Attention → Classifier
  Input shape:  (batch, 60, 23)
  Output shape: (batch, 5)  — 5 strain classes

Training:
  python src/tcn_model.py

Inference (from session_manager.py):
  from src.tcn_model import load_model, predict
"""

import numpy as np
import json
import os
import time
from collections import Counter

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader, TensorDataset
except Exception as e:
    import warnings
    warnings.warn(f"Torch could not be imported: {e}")
    torch = None
    nn = None
    optim = None
    DataLoader = None
    TensorDataset = None
from config import USE_QUANTUM

# ── CONFIG ───────────────────────────────────────────────────────────────────
PROCESSED_DIR  = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed')
MODEL_DIR      = os.path.join(os.path.dirname(__file__), '..', 'models')
MODEL_PATH     = os.path.join(MODEL_DIR, 'tcn_model.pt')
LOG_FILE       = os.path.join(PROCESSED_DIR, 'training_log.json')
WEIGHTS_FILE   = os.path.join(PROCESSED_DIR, 'class_weights.json')

# Model hyperparameters — reduced to prevent overfitting on small dataset
# Input size depends on quantum flag
INPUT_SIZE = 27 if USE_QUANTUM else 23
SEQ_LEN        = 60
NUM_CLASSES    = 5
NUM_CHANNELS   = [32, 32, 64, 64, 128]   # reduced from [64, 64, 128, 128, 256]
KERNEL_SIZE    = 3
DROPOUT        = 0.4                      # increased from 0.2
ATTN_HEADS     = 4
ATTN_DIM       = 128                      # reduced from 256

# Training hyperparameters
EPOCHS         = 60                       # increased from 50
BATCH_SIZE     = 32                       # reduced from 64
LEARNING_RATE  = 5e-4                     # reduced from 1e-3
PATIENCE       = 15                       # increased from 10

LABEL_MAP = {0: 'NORMAL', 1: 'LOW', 2: 'MODERATE', 3: 'HIGH', 4: 'SEVERE'}

os.makedirs(MODEL_DIR, exist_ok=True)


# ── TCN BUILDING BLOCKS ──────────────────────────────────────────────────────

class CausalConv1d(nn.Module):
    """
    Causal convolution — only looks at past, never future.
    Pads left side so output length = input length.
    """
    def __init__(self, in_channels, out_channels, kernel_size, dilation):
        super().__init__()
        self.padding = (kernel_size - 1) * dilation
        self.conv = nn.Conv1d(
            in_channels, out_channels,
            kernel_size=kernel_size,
            dilation=dilation,
            padding=self.padding
        )

    def forward(self, x):
        x = self.conv(x)
        return x[:, :, :-self.padding] if self.padding > 0 else x


class TCNBlock(nn.Module):
    """
    One TCN residual block:
      CausalConv → LayerNorm → ReLU → Dropout →
      CausalConv → LayerNorm → ReLU → Dropout →
      + residual connection
    """
    def __init__(self, in_channels, out_channels, kernel_size, dilation, dropout):
        super().__init__()

        self.conv1 = CausalConv1d(in_channels, out_channels, kernel_size, dilation)
        self.norm1 = nn.LayerNorm(out_channels)
        self.relu1 = nn.ReLU()
        self.drop1 = nn.Dropout(dropout)

        self.conv2 = CausalConv1d(out_channels, out_channels, kernel_size, dilation)
        self.norm2 = nn.LayerNorm(out_channels)
        self.relu2 = nn.ReLU()
        self.drop2 = nn.Dropout(dropout)

        self.residual = (
            nn.Conv1d(in_channels, out_channels, kernel_size=1)
            if in_channels != out_channels else None
        )

    def forward(self, x):
        residual = x

        out = self.conv1(x)
        out = self.norm1(out.transpose(1, 2)).transpose(1, 2)
        out = self.relu1(out)
        out = self.drop1(out)

        out = self.conv2(out)
        out = self.norm2(out.transpose(1, 2)).transpose(1, 2)
        out = self.relu2(out)
        out = self.drop2(out)

        if self.residual is not None:
            residual = self.residual(residual)

        return self.relu2(out + residual)


class TCNEncoder(nn.Module):
    """
    Stack of TCN blocks with exponentially increasing dilation rates.
    Dilation rates: 1, 2, 4, 8, 16 — receptive field covers ~60 seconds.
    """
    def __init__(self, input_size, num_channels, kernel_size, dropout):
        super().__init__()

        layers         = []
        dilation_rates = [2 ** i for i in range(len(num_channels))]

        in_ch = input_size
        for i, out_ch in enumerate(num_channels):
            layers.append(TCNBlock(
                in_channels=in_ch,
                out_channels=out_ch,
                kernel_size=kernel_size,
                dilation=dilation_rates[i],
                dropout=dropout
            ))
            in_ch = out_ch

        self.network = nn.Sequential(*layers)

    def forward(self, x):
        x = x.transpose(1, 2)
        x = self.network(x)
        x = x.transpose(1, 2)
        return x


class SelfAttention(nn.Module):
    """
    Multi-Head Self-Attention over the temporal dimension.
    Captures long-range dependencies — strain that built up
    10 minutes ago affecting current prediction.
    """
    def __init__(self, embed_dim, num_heads, dropout):
        super().__init__()
        self.attn = nn.MultiheadAttention(
            embed_dim=embed_dim,
            num_heads=num_heads,
            dropout=dropout,
            batch_first=True
        )
        self.norm = nn.LayerNorm(embed_dim)
        self.drop = nn.Dropout(dropout)

    def forward(self, x):
        attn_out, _ = self.attn(x, x, x)
        return self.norm(x + self.drop(attn_out))


class EyeStrainTCN(nn.Module):
    """
    Full model:
      TCN Encoder → Self-Attention → Global Average Pool → Classifier
    """
    def __init__(
        self,
        input_size=INPUT_SIZE,
        num_channels=NUM_CHANNELS,
        kernel_size=KERNEL_SIZE,
        dropout=DROPOUT,
        attn_heads=ATTN_HEADS,
        attn_dim=ATTN_DIM,
        num_classes=NUM_CLASSES
    ):
        super().__init__()

        self.tcn        = TCNEncoder(input_size, num_channels, kernel_size, dropout)
        self.attn       = SelfAttention(attn_dim, attn_heads, dropout)
        self.classifier = nn.Sequential(
            nn.Linear(attn_dim, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, num_classes)
        )

    def forward(self, x):
        x = self.tcn(x)        # (batch, 60, 128)
        x = self.attn(x)       # (batch, 60, 128)
        x = x.mean(dim=1)      # (batch, 128)
        x = self.classifier(x) # (batch, 5)
        return x


# ── TRAINING UTILITIES ───────────────────────────────────────────────────────

def load_tensors():
    print("  Loading tensors...")
    X_train = np.load(os.path.join(PROCESSED_DIR, 'X_train.npy'))
    y_train = np.load(os.path.join(PROCESSED_DIR, 'y_train.npy'))
    X_test  = np.load(os.path.join(PROCESSED_DIR, 'X_test.npy'))
    y_test  = np.load(os.path.join(PROCESSED_DIR, 'y_test.npy'))

    print(f"  X_train: {X_train.shape}  y_train: {y_train.shape}")
    print(f"  X_test:  {X_test.shape}   y_test:  {y_test.shape}")

    return (
        torch.FloatTensor(X_train),
        torch.LongTensor(y_train),
        torch.FloatTensor(X_test),
        torch.LongTensor(y_test)
    )


def load_class_weights(device):
    with open(WEIGHTS_FILE, 'r') as f:
        data = json.load(f)
    weights = [data['class_weights_by_index'][str(i)] for i in range(NUM_CLASSES)]
    print(f"  Class weights: {[round(w, 3) for w in weights]}")
    return torch.FloatTensor(weights).to(device)


def compute_metrics(y_true, y_pred):
    metrics = {}
    all_f1  = []

    for cls in range(NUM_CLASSES):
        tp = ((y_pred == cls) & (y_true == cls)).sum()
        fp = ((y_pred == cls) & (y_true != cls)).sum()
        fn = ((y_pred != cls) & (y_true == cls)).sum()

        precision = tp / (tp + fp + 1e-8)
        recall    = tp / (tp + fn + 1e-8)
        f1        = 2 * precision * recall / (precision + recall + 1e-8)

        metrics[LABEL_MAP[cls]] = {
            'precision': round(float(precision), 4),
            'recall':    round(float(recall),    4),
            'f1':        round(float(f1),        4),
            'support':   int((y_true == cls).sum())
        }
        all_f1.append(float(f1))

    metrics['macro_f1'] = round(float(np.mean(all_f1)), 4)
    return metrics


def print_metrics(metrics):
    print(f"\n  {'Class':<12} {'Precision':>10} {'Recall':>10} {'F1':>8} {'Support':>9}")
    print("  " + "-" * 52)
    for cls_name, m in metrics.items():
        if cls_name == 'macro_f1':
            continue
        print(f"  {cls_name:<12} {m['precision']:>10.4f} {m['recall']:>10.4f} "
              f"{m['f1']:>8.4f} {m['support']:>9}")
    print("  " + "-" * 52)
    print(f"  {'Macro F1':<12} {metrics['macro_f1']:>10.4f}")


def update_training_log(entry):
    log = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            try:
                log = json.load(f)
            except json.JSONDecodeError:
                log = []
    log.append(entry)
    with open(LOG_FILE, 'w') as f:
        json.dump(log, f, indent=2)


# ── TRAINING LOOP ─────────────────────────────────────────────────────────────

def train(model, loader, optimizer, criterion, device):
    model.train()
    total_loss = 0
    correct    = 0
    total      = 0

    for X_batch, y_batch in loader:
        X_batch = X_batch.to(device)
        y_batch = y_batch.to(device)

        optimizer.zero_grad()
        outputs = model(X_batch)
        loss    = criterion(outputs, y_batch)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()

        total_loss += loss.item() * len(y_batch)
        preds       = outputs.argmax(dim=1)
        correct    += (preds == y_batch).sum().item()
        total      += len(y_batch)

    return total_loss / total, correct / total


def evaluate(model, loader, criterion, device):
    model.eval()
    total_loss = 0
    all_preds  = []
    all_labels = []

    with torch.no_grad():
        for X_batch, y_batch in loader:
            X_batch = X_batch.to(device)
            y_batch = y_batch.to(device)

            outputs    = model(X_batch)
            loss       = criterion(outputs, y_batch)
            total_loss += loss.item() * len(y_batch)

            preds = outputs.argmax(dim=1)
            all_preds.extend(preds.cpu().numpy())
            all_labels.extend(y_batch.cpu().numpy())

    avg_loss = total_loss / len(all_labels)
    accuracy = (np.array(all_preds) == np.array(all_labels)).mean()
    metrics  = compute_metrics(np.array(all_labels), np.array(all_preds))

    return avg_loss, accuracy, metrics


# ── INFERENCE API ─────────────────────────────────────────────────────────────

# Load model implementation follows below


# Torch import fallback – using dummy implementation
if torch is None:
    # Minimal dummy nn module
    class _DummyModule:
        def __init__(self, *args, **kwargs):
            pass
        def __call__(self, *args, **kwargs):
            return self
    class _DummyNN:
        Module = _DummyModule
        Sequential = _DummyModule
        ReLU = _DummyModule
        Dropout = _DummyModule
        Linear = _DummyModule
        LayerNorm = _DummyModule
        CrossEntropyLoss = _DummyModule
    nn = _DummyNN()
    optim = None
    DataLoader = None
    TensorDataset = None

def load_model():
    """Load the TCN model, with fallback if torch is unavailable.
    Returns a tuple (model, device). The dummy model implements the minimal
    interface required by the pipeline: a callable that returns a tensor-like
    object with a .tcn attribute and supports .eval()."""
    if torch is None:
        class DummyModel:
            def __call__(self, *args, **kwargs):
                # Return dummy logits for 5 classes
                class DummyTensor:
                    def cpu(self):
                        return self
                    def numpy(self):
                        return np.array([0.2, 0.2, 0.2, 0.2, 0.2], dtype=np.float32)
                    def flatten(self):
                        return self.numpy()
                return DummyTensor()
            def eval(self):
                pass
            @property
            def tcn(self):
                # Return self for compatibility
                return self
        model = DummyModel()
        device = 'cpu'
        return model, device
    # Normal torch path
    model = EyeStrainTCN()
    model_path = os.path.join(MODEL_DIR, 'tcn_model.pt')
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.to(device)
    model.eval()
    return model, device

def extract_embedding(model, window, device):
    """Extract embedding vector from the model. Fallback returns zeros."""
    if torch is None:
        return np.zeros(128, dtype=np.float32)
    with torch.no_grad():
        window_tensor = torch.tensor(window, dtype=torch.float32).unsqueeze(0).to(device)
        embedding = model.tcn(window_tensor).mean(dim=1)
        return embedding.cpu().numpy().flatten()

def predict_proba(model, window, device):
    """Predict class probabilities. Fallback returns uniform probabilities."""
    if torch is None:
        probs = [0.2] * 5
        pred = np.argmax(probs)
        label = LABEL_MAP.get(pred, 'UNKNOWN')
        return pred, label, probs
    with torch.no_grad():
        window_tensor = torch.tensor(window, dtype=torch.float32).unsqueeze(0).to(device)
        logits = model(window_tensor)
        probs = torch.softmax(logits, dim=1).cpu().numpy().flatten()
        pred = np.argmax(probs)
        label = LABEL_MAP.get(pred, 'UNKNOWN')
        return pred, label, probs.tolist()

def predict(model, window, device):
    """
    Predicts strain level for a single 60-second window.

    Args:
        model:  trained EyeStrainTCN
        window: numpy array of shape (60, 23)
        device: torch device

    Returns:
        predicted_class (int): 0–4
        label (str):           NORMAL / LOW / MODERATE / HIGH / SEVERE
        probabilities (list):  softmax probabilities for all 5 classes
    """
    model.eval()
    with torch.no_grad():
        x      = torch.FloatTensor(window).unsqueeze(0).to(device)
        logits = model(x)
        probs  = torch.softmax(logits, dim=1).squeeze().cpu().numpy()
        pred   = int(np.argmax(probs))
        return pred, LABEL_MAP[pred], probs.tolist()

def extract_embedding(model, window, device):
    """Extract 128‑dim embedding from a raw window after TCN and attention.

    Args:
        model: Trained EyeStrainTCN model.
        window (np.ndarray): Input array of shape (60, 23) or (60, INPUT_SIZE).
        device: torch device (cpu or cuda).
    Returns:
        np.ndarray: 128‑dim embedding vector.
    """
    if torch is None:
        return np.zeros(128, dtype=np.float32)
    model.eval()
    with torch.no_grad():
        x = torch.FloatTensor(window).unsqueeze(0).to(device)
        # Pass through encoder and attention layers
        x = model.tcn(x)          # (1, 60, 128)
        x = model.attn(x)         # (1, 60, 128)
        embedding = x.mean(dim=1) # (1, 128)
    return embedding.squeeze(0).cpu().numpy()

def predict_proba(model, window, device):
    """Return softmax probabilities for all classes.

    Args:
        model: Trained EyeStrainTCN model.
        window (np.ndarray): Input array of shape (60, 23).
        device: torch device.
    Returns:
        list: Probabilities for each class.
    """
    if torch is None:
        # Return dummy prediction, label, and uniform probabilities
        dummy_pred = 0
        return dummy_pred, LABEL_MAP[dummy_pred], [0.2] * 5
    model.eval()
    with torch.no_grad():
        x = torch.FloatTensor(window).unsqueeze(0).to(device)
        logits = model(x)
        probs = torch.softmax(logits, dim=1).squeeze().cpu().numpy()
        pred = int(np.argmax(probs))
        return pred, LABEL_MAP[pred], probs.tolist()


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  tcn_model.py — EyeStrain AI")
    print("=" * 60)

    # ── Device (Guarded) ──
    if torch is None:
        print("\n  Torch not available. Skipping TCN training and inference.")
        return
    else:
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        print(f"\n  Device: {device}")
        if device.type == 'cuda':
            print(f"  GPU: {torch.cuda.get_device_name(0)}")

    # ── Load data ──
    print("\n[1] Loading tensors...")
    X_train, y_train, X_test, y_test = load_tensors()

    train_loader = DataLoader(
        TensorDataset(X_train, y_train),
        batch_size=BATCH_SIZE, shuffle=True, num_workers=0
    )
    test_loader = DataLoader(
        TensorDataset(X_test, y_test),
        batch_size=BATCH_SIZE, shuffle=False, num_workers=0
    )

    # ── Model ──
    print("\n[2] Building model...")
    model        = EyeStrainTCN().to(device)
    total_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"  Trainable parameters: {total_params:,}")
    print(f"  Architecture: TCN {NUM_CHANNELS} → Attention ({ATTN_HEADS} heads) → FC(64) → {NUM_CLASSES} classes")

    # ── Loss + optimizer ──
    print("\n[3] Setting up training...")
    class_weights = load_class_weights(device)
    print(f"  Loaded class weights: {class_weights.tolist()}")
    criterion     = nn.CrossEntropyLoss(weight=class_weights)
    optimizer     = optim.Adam(model.parameters(), lr=LEARNING_RATE, weight_decay=1e-4)
    scheduler     = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', patience=5, factor=0.5
    )

    # ── Training ──
    print(f"\n[4] Training for up to {EPOCHS} epochs (early stop patience={PATIENCE})...")
    print(f"  Batch size: {BATCH_SIZE}  |  LR: {LEARNING_RATE}  |  Dropout: {DROPOUT}")
    print()

    best_val_loss  = float('inf')
    best_macro_f1  = 0.0
    best_epoch     = 0
    patience_count = 0
    history        = []

    for epoch in range(1, EPOCHS + 1):
        start = time.time()

        train_loss, train_acc          = train(model, train_loader, optimizer, criterion, device)
        val_loss, val_acc, metrics     = evaluate(model, test_loader, criterion, device)

        scheduler.step(val_loss)

        macro_f1 = metrics['macro_f1']
        elapsed  = time.time() - start

        print(f"  Epoch {epoch:02d}/{EPOCHS} | "
              f"Train Loss: {train_loss:.4f}  Acc: {train_acc:.4f} | "
              f"Val Loss: {val_loss:.4f}  Acc: {val_acc:.4f} | "
              f"Macro F1: {macro_f1:.4f} | "
              f"{elapsed:.1f}s")

        history.append({
            'epoch':      epoch,
            'train_loss': round(train_loss, 4),
            'train_acc':  round(train_acc,  4),
            'val_loss':   round(val_loss,   4),
            'val_acc':    round(val_acc,    4),
            'macro_f1':   macro_f1
        })

        # Save on best val loss — more stable than macro F1
        if val_loss < best_val_loss:
            best_val_loss  = val_loss
            best_macro_f1  = macro_f1
            best_epoch     = epoch
            patience_count = 0
            torch.save(model.state_dict(), MODEL_PATH)
            print(f"    ✓ Best model saved (Val Loss: {best_val_loss:.4f}  Macro F1: {macro_f1:.4f})")
        else:
            patience_count += 1
            if patience_count >= PATIENCE:
                print(f"\n  Early stopping at epoch {epoch} "
                      f"(no improvement for {PATIENCE} epochs)")
                break

    # ── Final evaluation ──
    print(f"\n[5] Final evaluation — loading best model from epoch {best_epoch}...")
    model.load_state_dict(torch.load(MODEL_PATH, map_location=device))
    _, final_acc, final_metrics = evaluate(model, test_loader, criterion, device)

    print(f"\n  Test Accuracy: {final_acc:.4f}")
    print_metrics(final_metrics)

    # ── Save training log ──
    print("\n[6] Saving training log...")
    update_training_log({
        "run_type":          "tcn_training",
        "run_date":          __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "device":            str(device),
        "epochs_run":        len(history),
        "best_epoch":        best_epoch,
        "best_val_loss":     round(best_val_loss, 4),
        "best_macro_f1":     best_macro_f1,
        "final_accuracy":    round(final_acc, 4),
        "per_class_metrics": final_metrics,
        "hyperparameters": {
            "epochs":        EPOCHS,
            "batch_size":    BATCH_SIZE,
            "learning_rate": LEARNING_RATE,
            "dropout":       DROPOUT,
            "kernel_size":   KERNEL_SIZE,
            "num_channels":  NUM_CHANNELS,
            "attn_heads":    ATTN_HEADS,
            "attn_dim":      ATTN_DIM,
            "patience":      PATIENCE,
            "weight_decay":  1e-4
        },
        "history": history
    })

    print("\n" + "=" * 60)
    print(f"  Training complete.")
    print(f"  Best Val Loss:  {best_val_loss:.4f}  (epoch {best_epoch})")
    print(f"  Best Macro F1:  {best_macro_f1:.4f}")
    print(f"  Final Accuracy: {final_acc:.4f}")
    print(f"  Model saved  →  {MODEL_PATH}")
    print("=" * 60)


if __name__ == '__main__':
    main()