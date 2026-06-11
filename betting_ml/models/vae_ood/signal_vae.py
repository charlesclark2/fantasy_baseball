"""betting_ml.models.vae_ood.signal_vae

Pure-numpy Variational Autoencoder for joint sub-model signal OOD detection.

Architecture: input_dim → hidden_dim → [μ_z, logvar_z] → z → hidden_dim → input_dim
  input_dim=13, hidden_dim=8, latent_dim=3

Reconstruction error at inference is deterministic (ε=0, uses encoder μ_z).
Threshold is the 95th percentile of training-era reconstruction errors; a game
above the threshold is flagged as jointly out-of-distribution.

No PyTorch/TF — pure numpy + joblib.
"""

from __future__ import annotations

import logging
from pathlib import Path

import joblib
import numpy as np

log = logging.getLogger(__name__)

# Canonical ordered list of the 13 mu columns that form the joint game-level
# signal vector.  Matches the Layer-3 matrix column contract (_SIGNAL_GROUPS
# mus after _reshape_to_game_level): env groups keep one value; per-side groups
# emit home_/away_ pairs.  Never reorder without retraining.
SIGNAL_MU_COLUMNS: list[str] = [
    # Environment (one value per game — same for both sides)
    "run_env_mu_v4",
    # Offense
    "home_pred_runs_mu_v2",
    "away_pred_runs_mu_v2",
    # Starter quality
    "home_starter_suppression_mu_v1",
    "away_starter_suppression_mu_v1",
    # Starter innings-pitched
    "home_starter_ip_mu_v1",
    "away_starter_ip_mu_v1",
    # Bullpen (NegBin μ)
    "home_bullpen_mu_v2",
    "away_bullpen_mu_v2",
    # Matchup advantage (availability-gated; imputed with training mean when absent)
    "home_matchup_advantage_mu_v1",
    "away_matchup_advantage_mu_v1",
    # Defense quality (availability-gated; imputed with training mean when absent)
    "home_defense_quality_mu_v1",
    "away_defense_quality_mu_v1",
]

_INPUT_DIM = len(SIGNAL_MU_COLUMNS)  # 13


class SignalVAE:
    """Tiny tabular VAE for joint OOD detection on sub-model signal vectors.

    Trained on 2022-2025 games.  A game whose reconstruction error exceeds
    ``threshold_`` is flagged jointly out-of-distribution.

    Manual Adam backprop — no external ML framework.
    """

    def __init__(
        self,
        input_dim: int = _INPUT_DIM,
        hidden_dim: int = 8,
        latent_dim: int = 3,
        beta: float = 0.1,
        seed: int = 42,
    ) -> None:
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.latent_dim = latent_dim
        self.beta = beta   # KL weight (β-VAE; small to avoid posterior collapse on tabular)
        self.seed = seed

        rng = np.random.default_rng(seed)
        s_in = np.sqrt(2.0 / input_dim)
        s_h  = np.sqrt(2.0 / hidden_dim)
        s_l  = np.sqrt(2.0 / latent_dim)

        # Encoder
        self.W1   = rng.normal(0, s_in, (input_dim, hidden_dim))
        self.b1   = np.zeros(hidden_dim)
        self.W_mu = rng.normal(0, s_h,  (hidden_dim, latent_dim))
        self.b_mu = np.zeros(latent_dim)
        self.W_lv = rng.normal(0, s_h,  (hidden_dim, latent_dim))
        self.b_lv = np.zeros(latent_dim)
        # Decoder
        self.W2   = rng.normal(0, s_l,  (latent_dim, hidden_dim))
        self.b2   = np.zeros(hidden_dim)
        self.W3   = rng.normal(0, s_h,  (hidden_dim, input_dim))
        self.b3   = np.zeros(input_dim)

        # Set by fit()
        self.train_mean_: np.ndarray | None = None
        self.train_std_:  np.ndarray | None = None
        self.threshold_:  float | None = None
        self.train_window_: str | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _relu(x: np.ndarray) -> np.ndarray:
        return np.maximum(0.0, x)

    @staticmethod
    def _relu_d(pre: np.ndarray) -> np.ndarray:
        """Derivative of ReLU w.r.t. pre-activation."""
        return (pre > 0.0).astype(np.float64)

    def _prepare(self, X_raw: np.ndarray) -> np.ndarray:
        """Impute NaNs with training mean, then z-score."""
        if self.train_mean_ is None:
            raise RuntimeError("VAE not fitted — call fit() first.")
        X = np.where(np.isnan(X_raw), self.train_mean_, X_raw)
        return (X - self.train_mean_) / (self.train_std_ + 1e-8)

    def _forward(
        self,
        X: np.ndarray,
        rng: np.random.Generator | None = None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Forward pass → (X_recon, mu_z, lv_z, z, h1_pre, h2_pre)."""
        h1_pre = X @ self.W1 + self.b1
        h1     = self._relu(h1_pre)
        mu_z   = h1 @ self.W_mu + self.b_mu
        lv_z   = np.clip(h1 @ self.W_lv + self.b_lv, -6.0, 4.0)
        eps    = rng.standard_normal(mu_z.shape) if rng is not None else np.zeros_like(mu_z)
        z      = mu_z + eps * np.exp(0.5 * lv_z)
        h2_pre = z @ self.W2 + self.b2
        h2     = self._relu(h2_pre)
        X_recon = h2 @ self.W3 + self.b3
        return X_recon, mu_z, lv_z, z, h1_pre, h2_pre

    def _elbo(
        self,
        X: np.ndarray,
        X_recon: np.ndarray,
        mu_z: np.ndarray,
        lv_z: np.ndarray,
    ) -> tuple[float, float, float]:
        n, d  = X.shape
        recon = float(np.sum((X - X_recon) ** 2) / (n * d))
        kl    = float(-0.5 * np.sum(1.0 + lv_z - mu_z ** 2 - np.exp(lv_z)) / n)
        return recon + self.beta * kl, recon, kl

    def _backward(
        self,
        Xb:     np.ndarray,
        X_recon: np.ndarray,
        mu_z:   np.ndarray,
        lv_z:   np.ndarray,
        z:      np.ndarray,
        h1_pre: np.ndarray,
        h2_pre: np.ndarray,
    ) -> dict[str, np.ndarray]:
        n, d = Xb.shape
        h1 = self._relu(h1_pre)
        h2 = self._relu(h2_pre)

        # Reconstruction gradient
        dXr = 2.0 * (X_recon - Xb) / (n * d)

        # Decoder output layer
        dW3 = h2.T @ dXr
        db3 = dXr.sum(0)
        dh2 = (dXr @ self.W3.T) * self._relu_d(h2_pre)

        # Decoder hidden → z
        dW2 = z.T @ dh2
        db2 = dh2.sum(0)
        dz  = dh2 @ self.W2.T

        # Reparameterisation: z = μ_z + ε·exp(0.5·lv_z)
        std   = np.exp(0.5 * lv_z)
        eps   = (z - mu_z) / (std + 1e-8)

        # KL gradient contributions
        dmu_z = dz            + self.beta * mu_z / n
        dlv_z = dz * eps * 0.5 * std + self.beta * 0.5 * (np.exp(lv_z) - 1.0) / n

        # Encoder latent heads
        dW_mu = h1.T @ dmu_z
        db_mu = dmu_z.sum(0)
        dW_lv = h1.T @ dlv_z
        db_lv = dlv_z.sum(0)

        # Encoder hidden layer
        dh1 = (dmu_z @ self.W_mu.T + dlv_z @ self.W_lv.T) * self._relu_d(h1_pre)
        dW1 = Xb.T @ dh1
        db1 = dh1.sum(0)

        return {
            "W1": dW1, "b1": db1,
            "W_mu": dW_mu, "b_mu": db_mu,
            "W_lv": dW_lv, "b_lv": db_lv,
            "W2": dW2, "b2": db2,
            "W3": dW3, "b3": db3,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit(
        self,
        X_raw: np.ndarray,
        n_epochs: int = 300,
        lr: float = 1e-3,
        batch_size: int = 64,
        train_window: str = "2022-2025",
        verbose: bool = True,
    ) -> "SignalVAE":
        """Fit on raw signal matrix (NaN-tolerant; imputed with column mean).

        Args:
            X_raw: shape (N, input_dim); NaN means signal absent.
            n_epochs: training epochs.
            lr: Adam learning rate.
            batch_size: mini-batch size.
            train_window: human-readable label stored in artifact.
            verbose: log loss every 50 epochs.
        """
        self.train_mean_  = np.nanmean(X_raw, axis=0)
        self.train_std_   = np.nanstd(X_raw, axis=0)
        self.train_window_ = train_window

        X = self._prepare(X_raw)
        N = X.shape[0]

        params = ["W1", "b1", "W_mu", "b_mu", "W_lv", "b_lv", "W2", "b2", "W3", "b3"]
        m_adam = {p: np.zeros_like(getattr(self, p)) for p in params}
        v_adam = {p: np.zeros_like(getattr(self, p)) for p in params}
        b1a, b2a, eps_a, t = 0.9, 0.999, 1e-8, 0

        rng = np.random.default_rng(self.seed)
        for epoch in range(n_epochs):
            perm = rng.permutation(N)
            epoch_loss, n_batches = 0.0, 0
            for start in range(0, N, batch_size):
                Xb = X[perm[start : start + batch_size]]
                t += 1
                X_recon, mu_z, lv_z, z, h1_pre, h2_pre = self._forward(Xb, rng=rng)
                loss, _, _ = self._elbo(Xb, X_recon, mu_z, lv_z)
                grads = self._backward(Xb, X_recon, mu_z, lv_z, z, h1_pre, h2_pre)
                for p in params:
                    g = grads[p]
                    m_adam[p] = b1a * m_adam[p] + (1 - b1a) * g
                    v_adam[p] = b2a * v_adam[p] + (1 - b2a) * g ** 2
                    m_hat = m_adam[p] / (1 - b1a ** t)
                    v_hat = v_adam[p] / (1 - b2a ** t)
                    setattr(self, p, getattr(self, p) - lr * m_hat / (np.sqrt(v_hat) + eps_a))
                epoch_loss += loss
                n_batches += 1
            if verbose and (epoch + 1) % 50 == 0:
                log.info("  [VAE] epoch %d/%d  elbo=%.5f", epoch + 1, n_epochs, epoch_loss / n_batches)

        # Threshold: 95th percentile of training-era reconstruction errors.
        # Set entirely on training data — never tuned on held-out test cohort.
        train_errs = self.reconstruction_error(X_raw)
        self.threshold_ = float(np.percentile(train_errs, 95))
        log.info(
            "[VAE] training complete  n=%d  threshold_p95=%.6f  window=%s",
            N, self.threshold_, train_window,
        )
        return self

    def reconstruction_error(self, X_raw: np.ndarray) -> np.ndarray:
        """Per-sample MSE reconstruction error (deterministic; ε=0 → encoder μ_z).

        Args:
            X_raw: shape (N, input_dim); NaN → imputed with training mean.

        Returns:
            shape (N,) float array of per-sample mean-squared reconstruction errors.
        """
        X = self._prepare(X_raw)
        X_recon, *_ = self._forward(X, rng=None)
        return np.mean((X - X_recon) ** 2, axis=1)

    def predict_ood(self, X_raw: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Compute per-sample reconstruction error and OOD flag.

        Returns:
            (recon_error shape (N,), is_ood bool shape (N,))
        """
        if self.threshold_ is None:
            raise RuntimeError("VAE not fitted — call fit() first.")
        errs = self.reconstruction_error(X_raw)
        return errs, errs > self.threshold_

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.__dict__, path)
        log.info("[VAE] artifact saved → %s", path)

    @classmethod
    def load(cls, path: str | Path) -> "SignalVAE":
        """Load a fitted SignalVAE from a joblib artifact."""
        state = joblib.load(path)
        obj = cls.__new__(cls)
        obj.__dict__.update(state)
        return obj
