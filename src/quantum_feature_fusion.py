import numpy as np

try:
    from qiskit import QuantumCircuit
    try:
        from qiskit_aer import AerSimulator
    except ImportError:
        try:
            from qiskit.providers.aer import AerSimulator
        except ImportError:
            AerSimulator = None
except ImportError:
    QuantumCircuit = None
    transpile = None
    AerSimulator = None


class QuantumFeatureFusion:
    """Quantum feature fusion for eye-strain features using Qiskit."""

    FEATURE_BOUNDS = {
        'EAR':            (0.1, 0.5),
        'blink_rate':     (0.0, 30.0),
        'gaze_deviation': (0.0, 2 * np.pi),
        'head_pose':      (-30.0, 30.0),
    }

    def __init__(self, shots=256, n_layers=1):
        self.shots = shots
        self.n_qubits = 4
        self.n_layers = n_layers
        self.backend = AerSimulator() if AerSimulator is not None else None
        self.params = np.zeros(self.n_layers * 2 * self.n_qubits)

    def _normalize_angle(self, value: float | None, low: float, high: float) -> float:
        """Clamp value to bounds and map to [0, 2π]; treat None as low."""
        if value is None:
            value = low
        if high == low:
            return 0.0
        clipped = float(np.clip(value, low, high))
        return 2 * np.pi * (clipped - low) / (high - low)

        if high == low:
            return 0.0
        clipped = float(np.clip(value, low, high))
        return 2 * np.pi * (clipped - low) / (high - low)

    def _build_circuit(self, angles: list[float]) -> 'QuantumCircuit':
        qc = QuantumCircuit(self.n_qubits, self.n_qubits)

        # Encode each feature as a rotation on a dedicated qubit.
        for q_idx, angle in enumerate(angles):
            qc.ry(angle, q_idx)

        qc.barrier()

        # Minimal entangling ansatz.
        for layer in range(self.n_layers):
            for q_idx in range(self.n_qubits - 1):
                qc.cx(q_idx, q_idx + 1)
            qc.cx(self.n_qubits - 1, 0)

            for q_idx in range(self.n_qubits):
                param_index = layer * 2 * self.n_qubits + q_idx * 2
                qc.ry(self.params[param_index], q_idx)
                qc.rz(self.params[param_index + 1], q_idx)

            qc.barrier()

        qc.measure(range(self.n_qubits), range(self.n_qubits))
        return qc

    def encode(self, features: dict) -> dict:
        if QuantumCircuit is None or self.backend is None:
            return {
                f'quantum_feature_{i}': 0.0
                for i in range(self.n_qubits)
            }

        angles = [
            self._normalize_angle(
                features.get(key, 0.0), low, high
            )
            for key, (low, high) in self.FEATURE_BOUNDS.items()
        ]

        qc = self._build_circuit(angles)
        job = self.backend.run(qc, shots=self.shots)
        result = job.result()
        counts = result.get_counts()

        probabilities = {
            state: counts.get(state, 0) / self.shots
            for state in [format(i, f'0{self.n_qubits}b')
                          for i in range(2 ** self.n_qubits)]
        }

        classical_features = {}
        for q_idx in range(self.n_qubits):
            prob_zero = sum(
                prob for state, prob in probabilities.items()
                if state[self.n_qubits - 1 - q_idx] == '0'
            )
            prob_one = 1.0 - prob_zero
            classical_features[f'quantum_feature_{q_idx}'] = float(prob_zero - prob_one)

        return classical_features

    def set_parameters(self, params: np.ndarray) -> None:
        if params.shape != self.params.shape:
            raise ValueError(
                f'Expected params shape {self.params.shape}, got {params.shape}'
            )
        self.params = params


if __name__ == '__main__':
    qff = QuantumFeatureFusion()
    sample_features = {
        'EAR': 0.32,
        'blink_rate': 15.0,
        'gaze_deviation': 1.0,
        'head_pose': 5.0,
    }
    print(qff.encode(sample_features))
