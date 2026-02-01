import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

# Fix for docker environments running as non-root user without a username set
# Torch (used by imagededup) requires a username to determine the cache directory
if "USER" not in os.environ:
    os.environ["USER"] = "kwc"

# Torch attempts to write to /root/.cache if HOME is not writable or set to /root
# We redirect it to a temporary directory that is definitely writable
os.environ["TORCH_HOME"] = "/tmp/torch-cache"
# Some other tools might use XDG_CACHE_HOME
os.environ["XDG_CACHE_HOME"] = "/tmp/xdg-cache"

from imagededup.methods import CNN

from kwc.utils.files import safe_remove, safe_rename

from .extractor import CancellationToken, CancelledException
from .utils import render_pattern

if TYPE_CHECKING:
    from .models import ExtractionJob

logger = logging.getLogger(__name__)


def process_deduplication(
    job: "ExtractionJob",
    cancel_token: CancellationToken | None = None,
    files_to_check: list[Path] | None = None,
) -> None:
    """
    Run deduplication on the job's output directory.
    Uses ImageDedup (CNN) to find duplicates and removes them, keeping the highest quality one (largest file size).
    Then renumbers the remaining files.
    """
    output_dir = Path(job.output_dir)
    if not output_dir.exists():
        logger.warning(f"Output directory {output_dir} does not exist, skipping deduplication")
        return

    logger.info(f"Starting deduplication for job {job.id} in {output_dir}")

    # Check for cancellation before expensive operations
    if cancel_token and cancel_token.is_cancelled():
        raise CancelledException()

    # Initialize CNN method
    try:
        cnn = CNN()
    except Exception as e:
        logger.error(f"Failed to initialize CNN: {e}")
        return

    if cancel_token and cancel_token.is_cancelled():
        raise CancelledException()

    # Find duplicates
    # This generates encodings and finds duplicates.
    # Note: imagededup can be slow on CPU for many images.
    try:
        # returns {filename: [duplicate_filenames], ...}
        # default score_threshold is 0.9 for CNN, which is reasonable for "obvious duplicates"
        
        # If files_to_check is provided, we only encode and check those files.
        # This prevents running deduplication against old files in the directory.
        if files_to_check is not None:
            encodings = {}
            # Filter files that actually exist (might have been deleted manually?)
            valid_files = [f for f in files_to_check if f.exists()]
            
            logger.info(f"Encoding {len(valid_files)} new images for deduplication...")
            
            for _i, f in enumerate(valid_files):
                if cancel_token and cancel_token.is_cancelled():
                    raise CancelledException()
                
                # Check absolute vs relative: imagededup returns simple filenames as keys usually
                # if we pass image_dir. But here we use encode_image(path).
                # We'll use filename as key to match find_duplicates output structure expectation?
                # find_duplicates returns keys matching the input dictionary keys.
                # Since the files are all in output_dir, we can just use the filename as key.
                try:
                    encodings[f.name] = cnn.encode_image(image_file=str(f))
                except Exception as e:
                    logger.warning(f"Failed to encode {f.name}: {e}")
        else:
            # Fallback for full directory scan
            logger.info(f"Encoding all images in {output_dir} for deduplication...")
            encodings = cnn.encode_images(image_dir=str(output_dir))
        
        if cancel_token and cancel_token.is_cancelled():
            raise CancelledException()
            
        duplicates = cnn.find_duplicates(encoding_map=encodings, scores=False)
    except Exception as e:
        logger.error(f"Deduplication failed during processing: {e}")
        return

    if cancel_token and cancel_token.is_cancelled():
        raise CancelledException()

    files_to_delete = set()
    
    # Process duplicates logic
    # The output is a dict where key is a filename and value is a list of duplicate filenames.
    # Example: {'A': ['B'], 'B': ['A']}
    
    processed_files: set[str] = set()
    
    # Determine which files to keep and which to delete
    for filename, dup_list in duplicates.items():
        if filename in processed_files:
            continue
            
        if not dup_list:
            continue
            
        # Form the cluster of all identical images
        cluster = {filename} | set(dup_list)
        
        # Mark all as processed so we don't re-evaluate duplicates in the same cluster
        processed_files.update(cluster)
        
        # Select best image from cluster using heuristic (file size)
        best_file = _get_best_image(output_dir, cluster)
        
        # Mark others for deletion
        for f in cluster:
            if f != best_file:
                files_to_delete.add(f)

    logger.info(f"Found {len(files_to_delete)} duplicates to delete out of {len(encodings)} images")

    # Delete files
    for fname in files_to_delete:
        if cancel_token and cancel_token.is_cancelled():
            raise CancelledException()
        safe_remove(output_dir / fname)

    # Renumber images to fill gaps if we deleted anything
    if files_to_delete:
         _renumber_images(job, cancel_token)


def _get_best_image(base_dir: Path, filenames: set[str]) -> str:
    """
    Select the best image from a set of filenames.
    Heuristic: Largest file size is considered higher quality/complexity for JPEGs.
    """
    best_file: str | None = None
    max_size = -1
    
    # Convert to list to have a stable fallback (though sets are unordered, 
    # we just need *a* file if sizes are equal)
    filename_list = list(filenames)
    
    for fname in filename_list:
        path = base_dir / fname
        if not path.exists():
            continue
            
        try:
            size = path.stat().st_size
            if size > max_size:
                max_size = size
                best_file = fname
        except OSError:
            continue
            
    return best_file or filename_list[0]


def _renumber_images(job: "ExtractionJob", cancel_token: CancellationToken | None = None) -> None:
    """
    Renumber images in the output directory to be sequential.
    """
    output_dir = Path(job.output_dir)
    params = job.params
    pattern = params.get("image_pattern") or "output_{{ counter|pad:4 }}.jpg"
    
    # Re-construct context for rendering
    context: dict[str, Any] = {
        "title": params.get("title", ""),
        "year": params.get("year", ""),
        "season": params.get("season", ""),
        "episode": params.get("episode", ""),
    }
    
    # List all image files (ignoring hidden files like .cover.jpg)
    files = sorted([f for f in output_dir.iterdir() if f.is_file() and not f.name.startswith('.')])
    
    if not files:
        return

    logger.info(f"Renumbering {len(files)} remaining images")

    # Use a staging renaming strategy to avoid collisions
    temp_files = []
    
    for i, file_path in enumerate(files):
        if cancel_token and cancel_token.is_cancelled():
            raise CancelledException()

        # Temporary rename
        temp_name = f".renumber_tmp_{i}_{file_path.name}"
        temp_path = output_dir / temp_name
        try:
            safe_rename(file_path, temp_path)
            temp_files.append(temp_path)
        except Exception as e:
            logger.error(f"Failed to rename to temp file {file_path} -> {temp_path}: {e}")
            # If we fail here, we might leave things in a messy state, but aborting is safer than continuing
            raise e
        
    # Now rename for real
    for i, temp_path in enumerate(temp_files):
        if cancel_token and cancel_token.is_cancelled():
            raise CancelledException()

        counter = i + 1
        new_name = render_pattern(pattern, {**context, "counter": counter})
        new_path = output_dir / new_name
        
        try:
            safe_rename(temp_path, new_path)
        except Exception as e:
             logger.error(f"Failed to rename from temp file {temp_path} -> {new_path}: {e}")

