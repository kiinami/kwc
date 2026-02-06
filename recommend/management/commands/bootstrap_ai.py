import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand
from imagededup.methods import CNN

from recommend.services import FeatureService, TrainingService
from recommend.utils import calculate_image_hash
from recommend.models import ImageFeature

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Backfill image features and train the initial AI model."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--scan-only",
            action="store_true",
            help="Scan for features but do not train model.",
        )

    def _initialize_cnn_environment(self) -> None:
        """Initialize environment variables for imagededup/torch."""
        # Ensure USER is set for caching
        if "USER" not in os.environ:
            os.environ["USER"] = "kwc"
            
        # Redirect Torch cache to temp dir
        temp_dir = tempfile.gettempdir()
        os.environ["TORCH_HOME"] = os.path.join(temp_dir, "torch-cache")
        os.environ["XDG_CACHE_HOME"] = os.path.join(temp_dir, "xdg-cache")

    def handle(self, *args: Any, **options: Any) -> None:
        scan_only = options["scan_only"]
        
        self.stdout.write("Initializing AI bootstrap...")
        
        # Setup CNN
        self._initialize_cnn_environment()
        try:
            self.stdout.write("Loading CNN model (this may take a moment)...")
            cnn = CNN()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to initialize CNN: {e}"))
            return

        # Directories to scan
        directories = [
            Path(settings.WALLPAPERS_FOLDER),
            Path(settings.KWC_DISCARDS_FOLDER),
        ]
        
        total_processed = 0
        total_skipped = 0
        total_errors = 0
        
        for root_dir in directories:
            if not root_dir.exists():
                self.stdout.write(self.style.WARNING(f"Directory not found: {root_dir}"))
                continue
                
            self.stdout.write(f"Scanning {root_dir}...")
            
            # Find all images recursively
            all_files = [
                f for f in root_dir.rglob("*") 
                if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in {".jpg", ".jpeg", ".png"}
            ]
            
            self.stdout.write(f"Found {len(all_files)} images in {root_dir.name}")
            
            # Batch process? No, simple iteration is safer for now to avoid OOM
            # But we need vectors. calling cnn.encode_image for single file is slow.
            # However, batch encoding requires a directory structure compatible with imagededup
            # or manual loop. cnn.encode_image() works on single file path.
            
            for file_path in all_files:
                try:
                    # Check if feature exists
                    file_hash = calculate_image_hash(file_path)
                    exists = ImageFeature.objects.filter(file_hash=file_hash).exists()
                    
                    if exists:
                        total_skipped += 1
                        continue
                        
                    # Calculate vector
                    # CNN.encode_image returns a numpy array if input is single image path?
                    # Actually check source code or docs: encode_image(image_file=...) -> ndarray
                    # cnn.encode_images(image_dir=...) -> dict
                    vector = cnn.encode_image(image_file=str(file_path))
                    
                    if vector is not None:
                        # flatten if needed, but FeatureService expects ndarray to pickle
                        if len(vector.shape) > 1:
                            vector = vector.flatten()
                            
                        FeatureService.extract_and_save_features(file_path, vector_data=vector)
                        total_processed += 1
                        
                        if total_processed % 10 == 0:
                            self.stdout.write(".", ending="")
                            self.stdout.flush()
                            
                except Exception as e:
                    total_errors += 1
                    logger.error(f"Failed to process {file_path}: {e}")
            
            self.stdout.write("") # Newline after dots

        self.stdout.write(
            self.style.SUCCESS(
                f"Scan complete. Processed: {total_processed}, Skipped: {total_skipped}, Errors: {total_errors}"
            )
        )
        
        if not scan_only:
            self.stdout.write("Starting model training...")
            model = TrainingService.train_new_model()
            
            if model:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Model v{model.version} trained successfully! Accuracy: {model.accuracy_score:.2f}, Samples: {model.training_sample_count}"
                    )
                )
            else:
                self.stdout.write(self.style.WARNING("Training failed or insufficient data."))
