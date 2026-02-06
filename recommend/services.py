import logging
import pickle
from pathlib import Path
from typing import Any

import numpy as np
from django.conf import settings
from django.db import transaction
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

from .models import ImageFeature, LearnerModel
from .utils import (
    calculate_brightness,
    calculate_image_hash,
    calculate_sharpness,
    get_image_metadata,
)

logger = logging.getLogger(__name__)


class FeatureService:
    @staticmethod
    def extract_and_save_features(
        file_path: str | Path, vector_data: np.ndarray | None = None
    ) -> ImageFeature:
        """
        Extract features from an image and save to the database.
        If features already exist for this file content (hash), return existing record.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        file_hash = calculate_image_hash(path)

        # Check for existing features by hash
        # Mypy doesn't know about generated objects manager
        existing = ImageFeature.objects.filter(file_hash=file_hash).first()  # type: ignore
        if existing:
            # Update path if it changed (optional, but good for tracking)
            if existing.file_path != str(path):
                existing.file_path = str(path)
                existing.save(update_fields=["file_path"])
            return existing

        # Extract stats
        sharpness = calculate_sharpness(path)
        brightness = calculate_brightness(path)
        file_size, width, height = get_image_metadata(path)

        # Handle vector data
        # If not provided, we store an empty bytes object or a placeholder.
        # For now, we assume it's OK to have empty/null if the caller didn't provide feature vector
        # (e.g. from the CNN deduplication step).
        # In a real scenario, we might want to run the CNN here if vector_data is None.
        # But per requirements: "If vector_data is missing, we might skip it or compute it
        # (for now assume it's passed or can be None)."
        encoded_vector = b""
        if vector_data is not None:
            encoded_vector = pickle.dumps(vector_data)

        # Create record
        feature = ImageFeature(
            file_hash=file_hash,
            file_path=str(path),
            feature_vector=encoded_vector,
            sharpness_score=sharpness,
            brightness_score=brightness,
            file_size_bytes=file_size,
            resolution_width=width,
            resolution_height=height,
        )
        feature.save()
        
        logger.info(f"Saved features for {path.name} (sharpness={sharpness:.1f})")
        return feature


class TrainingService:
    @staticmethod
    def find_training_pairs() -> list[str]:
        """
        Identify folders that exist in both Wallpapers (Keeps) and Discards.
        These are the only folders we can reliably use for training assuming
        the user has finished curating them.
        """
        wallpapers_dir = Path(settings.WALLPAPERS_FOLDER)
        discards_dir = Path(settings.KWC_DISCARDS_FOLDER)

        if not wallpapers_dir.exists() or not discards_dir.exists():
            return []

        # Get top-level folders in both locations
        wallpapers_folders = {p.name for p in wallpapers_dir.iterdir() if p.is_dir()}
        discards_folders = {p.name for p in discards_dir.iterdir() if p.is_dir()}

        # Intersection
        common_folders = sorted(list(wallpapers_folders.intersection(discards_folders)))
        return common_folders

    @classmethod
    def train_new_model(cls) -> LearnerModel | None:
        """
        Train a new classifier based on current file system state.
        Returns the created model if successful, None if not enough data.
        """
        common_folders = cls.find_training_pairs()
        if not common_folders:
            logger.warning("No common folders found for training.")
            return None

        # Prepare dataset
        X: list[list[float]] = []
        y: list[int] = []

        wallpapers_dir = Path(settings.WALLPAPERS_FOLDER)
        discards_dir = Path(settings.KWC_DISCARDS_FOLDER)

        # Helper to gather samples
        def collect_samples_from_dir(directory: Path, label: int) -> None:
            # We recursively find images in the folder
            for folder in common_folders:
                target_path = directory / folder
                if not target_path.exists():
                    continue

                for file_path in target_path.rglob("*"):
                    if not file_path.is_file() or file_path.name.startswith("."):
                        continue

                    # Try to find feature in DB
                    file_hash = calculate_image_hash(file_path)
                    feature = ImageFeature.objects.filter(file_hash=file_hash).first() # type: ignore

                    if not feature:
                        # If missing, compute on the fly (slow but necessary)
                        try:
                            feature = FeatureService.extract_and_save_features(file_path)
                        except Exception:
                            continue

                    # Construct input vector
                    # Note: We prioritize CNN vector if available, but concatenate or use simple stats?
                    # For a robust MVP, let's use [sharpness, brightness, + CNN vector if compatible]
                    # To keep dimensions consistent, we need to decide on a strategy.
                    # Strategy: Use only scalar stats for now + maybe simple vector reduction if we wanted.
                    # BUT prompt requirement says "Prepare X (vectors + stats)".
                    # CNN vectors are usually large (e.g. 1024 dim).
                    # If we have mixed data (some with vectors, some without), training will fail.
                    # We will assume ONLY scalar stats for this iteration unless we are sure about vectors.
                    # Wait, Prompt 4 says "Prepare X (vectors + stats)".
                    # Let's inspect the pickled vector. If it's valid, we unpack it.
                    # If any sample is missing a vector, we might have to skip it or impute.
                    # To be safe: We try to unpickle. If successful and correct shape, use it.
                    # If we find inconsistency, we might fallback to just stats.
                    # Let's stick to a safe approach:
                    # 1. Unpickle vector. If fail/empty, skip this sample?
                    # Or better: We assume the deduplication process ran and vectors exist.
                    # If vector is missing, we skip adding it to the training set to avoid dimension mismatch.

                    vector_np: np.ndarray | None = None
                    if feature.feature_vector:
                        try:
                            vector_np = pickle.loads(feature.feature_vector)
                        except Exception:
                            pass

                    if vector_np is None:
                        # Skip samples without vectors for now to ensure quality
                        # Alternatively, we could train purely on metadata if vectors are scarce.
                        # For now, let's include if vector exists.
                        continue
                    
                    # Flatten vector
                    flat_vector = vector_np.flatten().tolist()
                    
                    # Combine features: [sharpness, brightness, file_size, ...vector]
                    # Normalizing scalar inputs might be good, but RF handles unscaled well enough.
                    row = [
                        feature.sharpness_score,
                        feature.brightness_score,
                        float(feature.file_size_bytes),
                    ] + flat_vector

                    X.append(row)
                    y.append(label)

        # 1 = One (Keep), 0 = Zero (Discard)
        collect_samples_from_dir(wallpapers_dir, 1)
        collect_samples_from_dir(discards_dir, 0)

        # Check data sufficiency
        if len(X) < 10 or len(set(y)) < 2:
            logger.warning(
                f"Insufficient data for training. Samples: {len(X)}, Classes: {len(set(y))}"
            )
            return None

        # Verify dimension consistency
        # All rows must have same length
        x_lengths = {len(row) for row in X}
        if len(x_lengths) > 1:
            logger.error(f"Inconsistent feature vector lengths: {x_lengths}")
            # Filter out inconsistent ones?
            # Let's take the most common length
            from collections import Counter
            most_common_len = Counter([len(r) for r in X]).most_common(1)[0][0]
            
            # Filter X and y
            new_X = []
            new_y = []
            for i, row in enumerate(X):
                if len(row) == most_common_len:
                    new_X.append(row)
                    new_y.append(y[i])
            X = new_X
            y = new_y
            
            if len(X) < 10:
                return None

        X_np = np.array(X)
        y_np = np.array(y)

        # Split for validation
        X_train, X_test, y_train, y_test = train_test_split(
            X_np, y_np, test_size=0.2, random_state=42
        )

        # Train Random Forest
        clf = RandomForestClassifier(
            n_estimators=100, class_weight="balanced", random_state=42, n_jobs=-1
        )
        clf.fit(X_train, y_train)

        # Validate
        y_pred = clf.predict(X_test)
        acc_score = accuracy_score(y_test, y_pred)
        
        logger.info(f"Model trained. Accuracy: {acc_score:.2f} Samples: {len(X)}")

        # Save Model
        # We re-fit on full data for the final model? 
        # Usually better to deploy the one we validated or retrain on all.
        # Let's retrain on all for production usage to maximize data utility.
        clf.fit(X_np, y_np)

        serialized_model = pickle.dumps(clf)

        # Deactivate old models
        with transaction.atomic():
            LearnerModel.objects.update(is_active=False) # type: ignore
            
            new_model = LearnerModel.objects.create( # type: ignore
                classifier_data=serialized_model,
                training_sample_count=len(X),
                accuracy_score=acc_score,
                is_active=True,
            )
            
        return new_model


class InferenceService:
    _model_cache: RandomForestClassifier | None = None
    _model_version: int = 0

    @classmethod
    def load_latest_model(cls) -> RandomForestClassifier | None:
        """
        Load the latest active model from DB, caching it in memory.
        """
        # efficient query
        latest = LearnerModel.objects.filter(is_active=True).order_by("-created_at").first() # type: ignore
        
        if not latest:
            cls._model_cache = None
            return None

        # Check if cache is stale
        if cls._model_cache and cls._model_version == latest.version:
            return cls._model_cache

        try:
            logger.info(f"Loading AI model v{latest.version}...")
            model = pickle.loads(latest.classifier_data)
            cls._model_cache = model
            cls._model_version = latest.version
            return model
        except Exception as e:
            logger.error(f"Failed to load model v{latest.version}: {e}")
            return None

    @classmethod
    def get_suggestions(cls, file_paths: list[str | Path]) -> dict[str, dict[str, Any]]:
        """
        Get suggestions for a list of file paths.
        Returns: { 'filename.jpg': { 'decision': 'keep'|'discard', 'confidence': 0.95 } }
        """
        if not getattr(settings, "KWC_AI_ENABLED", False):
            return {}

        model = cls.load_latest_model()
        if not model:
            return {}

        suggestions = {}
        X = []
        valid_paths = []

        for fp in file_paths:
            path = Path(fp)
            if not path.exists():
                continue

            # Check DB feature
            file_hash = calculate_image_hash(path)
            feature = ImageFeature.objects.filter(file_hash=file_hash).first() # type: ignore

            # If missing feature, we skip strict inference for now to avoid latency
            # Or we could compute simplified features (no CNN) if we had a fallback
            if not feature:
                continue
                
            # Reconstruct vector same as training
            vector_np: np.ndarray | None = None
            if feature.feature_vector:
                try:
                    vector_np = pickle.loads(feature.feature_vector)
                except Exception:
                    pass

            if vector_np is None:
                # We skip missing vectors to match training logic
                continue

            flat_vector = vector_np.flatten().tolist()
            
            row = [
                feature.sharpness_score,
                feature.brightness_score,
                float(feature.file_size_bytes),
            ] + flat_vector

            # Check dimension consistency with model
            # RandomForest stores n_features_in_
            if len(row) != model.n_features_in_:
                continue

            X.append(row)
            valid_paths.append(path.name)

        if not X:
            return {}

        try:
            # Predict probabilities
            # classes_ are usually [0, 1] (0=Discard, 1=Keep) but we must verify
            probs = model.predict_proba(X)
            
            # Map classes
            class_map = {c: i for i, c in enumerate(model.classes_)}
            idx_keep = class_map.get(1)
            idx_discard = class_map.get(0)

            if idx_keep is None or idx_discard is None:
                return {}

            for i, filename in enumerate(valid_paths):
                prob_keep = probs[i][idx_keep]
                prob_discard = probs[i][idx_discard]
                
                confidence = max(prob_keep, prob_discard)
                decision = "keep" if prob_keep > prob_discard else "discard"
                
                suggestions[filename] = {
                    "decision": decision,
                    "confidence": float(confidence),
                }

        except Exception as e:
            logger.error(f"Inference error: {e}")
            return {}

        return suggestions
