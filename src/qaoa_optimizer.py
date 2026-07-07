import numpy as np
from typing import Tuple

# Optional Qiskit imports – fall back if not installed
try:
    # pyrefly: ignore [missing-import]
    from qiskit_optimization import QuadraticProgram
    # pyrefly: ignore [missing-import]
    from qiskit_optimization.minimum_eigensolvers import QAOA
    # pyrefly: ignore [missing-import]
    from qiskit_optimization.utils import algorithm_globals
    # pyrefly: ignore [missing-import]
    from qiskit_aer import AerSimulator
    # pyrefly: ignore [missing-import]
    from qiskit.algorithms.optimizers import COBYLA
    # pyrefly: ignore [missing-import]
    from qiskit_aer.primitives import SamplerV2
    
    _HAS_QISKIT = True
except ImportError:
    _HAS_QISKIT = False
    # Define minimal placeholder classes/functions for type compatibility
    class QuadraticProgram:
        def __init__(self):
            self.vars = []
        def binary_var(self, name):
            self.vars.append(name)
        def minimize(self, linear):
            self.linear = linear
        def linear_constraint(self, linear, sense, rhs, name):
            self.constraint = (linear, sense, rhs, name)
        def to_ising(self):
            # Return dummy operator compatible with Sampler
            return None
    # Placeholder classes remain for environments without Qiskit; they are not used when Qiskit is available.
    class Sampler:
        def __init__(self):
            pass
        def sample(self, *args, **kwargs):
            return None
    class Aer:
        @staticmethod
        def get_backend(name):
            return None

    class AerSimulator:
        """Placeholder AerSimulator for environments without qiskit_aer."""
        def __init__(self, *args, **kwargs):
            pass
        @staticmethod
        def get_backend(name):
            return None

    class QAOA:
        def __init__(self, *args, **kwargs):
            pass
        def compute_minimum_eigenvalue(self, qubo):
            # Return dummy result with a single sample
            class Sample:
                def __init__(self):
                    self.binary = '000'
                    self.probability = 1.0
                    self.energy = 0.0
            class Result:
                def __init__(self):
                    self.samples = [Sample()]
            return Result()
    # algorithm_globals placeholder
    class algorithm_globals:
        random_seed = 42


def build_qubo(state: dict) -> QuadraticProgram:
    """Construct a 3‑variable QUBO (continue, reminder, break).
    ``state`` must contain:
        - ``probs``: np.ndarray of shape (5,) – class probabilities
        - ``workload``: float (normalised 0‑1)
    Returns a ``QuadraticProgram`` ready for QAOA.
    """
    probs = state["probs"]
    workload = state["workload"]

    # Linear costs – higher predicted strain penalises "continue"
    continue_cost = 10.0 * np.max(probs)
    reminder_cost = 3.0 * np.mean(probs)
    break_cost    = 1.0 * (1.0 - workload)

    qp = QuadraticProgram()
    qp.binary_var(name="continue")
    qp.binary_var(name="reminder")
    qp.binary_var(name="break")
    qp.minimize(linear=[continue_cost, reminder_cost, break_cost])

    # Exactly‑one‑action constraint

    return qp

def run_qaoa(qp: QuadraticProgram, p_layers: int = 2) -> Tuple[np.ndarray, float]:
    """Execute a 2‑layer QAOA on the Aer state‑vector simulator.
    Returns a tuple ``(bits, energy)`` where ``bits`` is a NumPy array of shape (3,)
    containing the binary solution and ``energy`` is the objective value.
    """
    # Translate the QuadraticProgram to an Ising (QUBO) operator
    qubo = qp.to_ising()

    # Use the new AerSimulator and SamplerV2 from qiskit-aer
    try:
        sampler = SamplerV2()
    except Exception:
        # Fallback to older Sampler class if SamplerV2 unavailable
        from qiskit_aer.primitives import Sampler
        sampler = Sampler()
    try:
        backend = AerSimulator()
    except Exception:
        # Fallback dummy backend if AerSimulator unavailable
        class DummyBackend:
            pass
        backend = DummyBackend()
    algorithm_globals.random_seed = 42

    # Initialize QAOA with the sampler and the desired number of layers
    # Instantiate optimizer with fallback if COBYLA unavailable
    try:
        optimizer = COBYLA()
    except NameError:
        # Define a minimal dummy optimizer that does nothing
        class DummyOptimizer:
            def __init__(self, *args, **kwargs):
                pass
        optimizer = DummyOptimizer()
    qaoa = QAOA(sampler=sampler, optimizer=optimizer, reps=p_layers)
    # Attach the backend to the QAOA algorithm (depends on Qiskit version)
    qaoa.quantum_instance = backend
    result = qaoa.compute_minimum_eigenvalue(qubo)

    # Choose the most likely bitstring
    best_sample = max(result.samples, key=lambda s: s.probability)
    bits = np.array([int(b) for b in best_sample.binary])
    energy = best_sample.energy
    return bits, energy

def decode_bits(bits: np.ndarray) -> str:
    """Map a 3‑bit solution to an action identifier.
    Index 0 → "continue", 1 → "reminder", 2 → "break".
    """
    mapping = {0: "continue", 1: "reminder", 2: "break"}
    return mapping[int(np.argmax(bits))]


def optimize_action(state: dict, q_values: np.ndarray) -> str:
    """Convert Q‑values into a QUBO, solve with QAOA if possible, else fallback.

    The function builds a QUBO using the provided ``state`` (currently only the
    probability and workload fields are used) and attempts to solve it with a
    shallow QAOA circuit when the ``qiskit`` stack is available. If any step
    fails – for example because Qiskit is not installed – the function falls
    back to a deterministic ``np.argmax`` selection, guaranteeing the pipeline
    never crashes.
    """
    # Prefer QAOA when available.
    if _HAS_QISKIT:
        try:
            qp = build_qubo(state)
            bits, _ = run_qaoa(qp)
            # Decode the binary solution to an action name.
            return decode_bits(bits)
        except Exception:
            # Any error (e.g., unexpected Qiskit behavior) falls back.
            pass
    # Fallback: choose action with highest Q‑value.
    idx = int(np.argmax(q_values))
    actions = ["continue", "reminder", "break"]
    return actions[idx]
