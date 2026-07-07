import numpy as np
import torch
from tcn_model import load_model, load_tensors, compute_metrics

def evaluate_test_set():
    # Load tensors
    X_train, y_train, X_test, y_test = load_tensors()
    # Load model and device
    model, device = load_model()
    model.eval()
    # Create DataLoader for test set
    test_dataset = torch.utils.data.TensorDataset(X_test, y_test)
    test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=32, shuffle=False)
    criterion = torch.nn.CrossEntropyLoss()
    total_loss = 0.0
    all_preds = []
    all_labels = []
    with torch.no_grad():
        for X_batch, y_batch in test_loader:
            X_batch = X_batch.to(device)
            y_batch = y_batch.to(device)
            outputs = model(X_batch)
            loss = criterion(outputs, y_batch)
            total_loss += loss.item() * len(y_batch)
            preds = outputs.argmax(dim=1)
            all_preds.extend(preds.cpu().numpy())
            all_labels.extend(y_batch.cpu().numpy())
    avg_loss = total_loss / len(all_labels)
    accuracy = (np.array(all_preds) == np.array(all_labels)).mean()
    metrics = compute_metrics(np.array(all_labels), np.array(all_preds))
    # Confusion matrix
    num_classes = max(max(all_labels), max(all_preds)) + 1
    confusion = np.zeros((num_classes, num_classes), dtype=int)
    for t, p in zip(all_labels, all_preds):
        confusion[t, p] += 1
    # Print results
    print("Test set evaluation:")
    print(f"  Loss: {avg_loss:.4f}")
    print(f"  Accuracy: {accuracy:.4f}")
    print("  Per-class metrics (Precision, Recall, F1, Support):")
    for cls, vals in metrics.items():
        if cls == 'macro_f1':
            continue
        print(f"    {cls}: precision={vals['precision']:.4f}, recall={vals['recall']:.4f}, f1={vals['f1']:.4f}, support={vals['support']}")
    print(f"  Macro F1: {metrics['macro_f1']:.4f}")
    print("  Confusion Matrix (rows=true, cols=pred):")
    for i, row in enumerate(confusion):
        print(f"    {i}: " + " ".join(str(v) for v in row))

if __name__ == '__main__':
    evaluate_test_set()
