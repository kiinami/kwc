from pathlib import Path

import pyanime4k


def upscale(directory: Path, scale: float = 2.0, model: str = "acnet-gan", processor: str = "opencl", suffix: str = "U"):
    """
    Upscale images in a directory using a specified model.

    Args:
        directory (Path): Directory containing images to upscale.
        scale (float): Scale factor for upscaling images.
        model (str): Model to use for upscaling.
        processor (str): Processor to use for upscaling (e.g., "opencl", "cpu").
        suffix (str): Suffix to append to the upscaled image filenames if not overwriting.

    Returns:
        None
    """
    pyanime4k.upscale_images(
        [str(directory / file) for file in directory.glob("*.jpg")],
        output_suffix=suffix,
        factor=scale,
        processor_name=str(processor),
        model_name=str(model),
    )