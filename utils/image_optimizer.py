"""
Image Optimization Utilities for OCR Performance

Provides intelligent image compression and optimization before OCR processing
to reduce memory usage and improve performance for large screenshots.

Key Features:
- Smart compression preserving OCR accuracy
- Configurable quality and dimension limits
- Automatic format optimization (PNG compression)
- Size calculation and reporting
- Support for both file paths and numpy arrays

Author: OverlayTranslate Team
Created: 2025-11-17 (Item 34)
"""

import os
import logging
from typing import Optional, Tuple, Dict, Any
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


# Default optimization settings
DEFAULT_MAX_DIMENSION = 1920  # Max width or height before scaling
DEFAULT_JPEG_QUALITY = 92     # JPEG quality (85-95 recommended for OCR)
DEFAULT_PNG_COMPRESSION = 6   # PNG compression level (0-9, 6 is good balance)
DEFAULT_SCALE_FACTOR = 0.75   # Scale to 75% if over max dimension


class ImageOptimizationStats:
    """Statistics for image optimization operations."""
    
    def __init__(self):
        self.original_size_bytes: int = 0
        self.optimized_size_bytes: int = 0
        self.original_dimensions: Tuple[int, int] = (0, 0)
        self.optimized_dimensions: Tuple[int, int] = (0, 0)
        self.compression_ratio: float = 0.0
        self.size_reduction_percent: float = 0.0
        self.was_resized: bool = False
        self.was_compressed: bool = False
    
    def calculate_metrics(self):
        """Calculate derived metrics from size data."""
        if self.original_size_bytes > 0:
            self.compression_ratio = self.original_size_bytes / max(self.optimized_size_bytes, 1)
            self.size_reduction_percent = (
                (self.original_size_bytes - self.optimized_size_bytes) / 
                self.original_size_bytes * 100
            )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert stats to dictionary for logging."""
        return {
            'original_size_kb': round(self.original_size_bytes / 1024, 2),
            'optimized_size_kb': round(self.optimized_size_bytes / 1024, 2),
            'original_dimensions': self.original_dimensions,
            'optimized_dimensions': self.optimized_dimensions,
            'compression_ratio': round(self.compression_ratio, 2),
            'size_reduction_percent': round(self.size_reduction_percent, 1),
            'was_resized': self.was_resized,
            'was_compressed': self.was_compressed
        }
    
    def __str__(self) -> str:
        """Human-readable stats summary."""
        return (
            f"ImageOptimization: "
            f"{self.original_dimensions[0]}x{self.original_dimensions[1]} → "
            f"{self.optimized_dimensions[0]}x{self.optimized_dimensions[1]}, "
            f"{self.original_size_bytes/1024:.1f}KB → {self.optimized_size_bytes/1024:.1f}KB "
            f"({self.size_reduction_percent:.1f}% reduction)"
        )


class ImageOptimizer:
    """
    Intelligent image optimizer for OCR preprocessing.
    
    Reduces image size while preserving OCR accuracy through:
    - Dimension scaling for oversized images
    - PNG compression optimization
    - Memory-efficient processing
    
    Usage:
        optimizer = ImageOptimizer(max_dimension=1920, png_compression=6)
        optimized_path, stats = optimizer.optimize_file('/path/to/image.png')
        
        # Or optimize in-place
        img_array = cv2.imread('/path/to/image.png')
        optimized_array, stats = optimizer.optimize_array(img_array)
    """
    
    def __init__(
        self,
        max_dimension: int = DEFAULT_MAX_DIMENSION,
        png_compression: int = DEFAULT_PNG_COMPRESSION,
        scale_factor: float = DEFAULT_SCALE_FACTOR,
        enabled: bool = True
    ):
        """
        Initialize image optimizer.
        
        Args:
            max_dimension: Maximum width or height (larger images are scaled down)
            png_compression: PNG compression level 0-9 (higher = smaller but slower)
            scale_factor: Scaling factor when resizing (0.5-1.0)
            enabled: Whether optimization is enabled
        """
        # Convert to int/float in case config values are loaded as strings
        self.max_dimension = int(max_dimension)
        self.png_compression = max(0, min(9, int(png_compression)))
        self.scale_factor = max(0.1, min(1.0, float(scale_factor)))
        self.enabled = bool(enabled)
        
        logger.debug(
            f"ImageOptimizer initialized: max_dim={max_dimension}, "
            f"png_compression={self.png_compression}, scale={self.scale_factor}, "
            f"enabled={enabled}"
        )
    
    def should_resize(self, width: int, height: int) -> bool:
        """
        Check if image dimensions exceed the maximum threshold.
        
        Args:
            width: Image width in pixels
            height: Image height in pixels
            
        Returns:
            True if image should be resized
        """
        return width > self.max_dimension or height > self.max_dimension
    
    def calculate_new_dimensions(
        self, 
        width: int, 
        height: int
    ) -> Tuple[int, int]:
        """
        Calculate new dimensions while maintaining aspect ratio.
        
        Args:
            width: Original width
            height: Original height
            
        Returns:
            Tuple of (new_width, new_height)
        """
        if not self.should_resize(width, height):
            return (width, height)
        
        # Calculate aspect ratio
        aspect_ratio = width / height
        
        # Determine which dimension is limiting
        if width > height:
            new_width = int(self.max_dimension * self.scale_factor)
            new_height = int(new_width / aspect_ratio)
        else:
            new_height = int(self.max_dimension * self.scale_factor)
            new_width = int(new_height * aspect_ratio)
        
        # Ensure dimensions are at least 100px
        new_width = max(100, new_width)
        new_height = max(100, new_height)
        
        return (new_width, new_height)
    
    def optimize_array(
        self,
        img: np.ndarray,
        return_stats: bool = True
    ) -> Tuple[np.ndarray, Optional[ImageOptimizationStats]]:
        """
        Optimize a numpy array image in-place.
        
        Args:
            img: Image as numpy array (OpenCV BGR format)
            return_stats: Whether to calculate and return statistics
            
        Returns:
            Tuple of (optimized_image_array, stats or None)
        """
        if not self.enabled:
            return img, None
        
        stats = ImageOptimizationStats() if return_stats else None
        
        try:
            height, width = img.shape[:2]
            
            if stats:
                stats.original_dimensions = (width, height)
                # Estimate original memory size
                stats.original_size_bytes = img.nbytes
            
            # Check if resizing is needed
            if self.should_resize(width, height):
                new_width, new_height = self.calculate_new_dimensions(width, height)
                
                # Use INTER_AREA for downscaling (best quality for OCR)
                img = cv2.resize(
                    img, 
                    (new_width, new_height), 
                    interpolation=cv2.INTER_AREA
                )
                
                if stats:
                    stats.was_resized = True
                    stats.optimized_dimensions = (new_width, new_height)
                    stats.optimized_size_bytes = img.nbytes
                
                logger.debug(
                    f"Resized image: {width}x{height} → {new_width}x{new_height}"
                )
            else:
                if stats:
                    stats.optimized_dimensions = (width, height)
                    stats.optimized_size_bytes = img.nbytes
            
            if stats:
                stats.calculate_metrics()
            
            return img, stats
            
        except Exception as e:
            logger.error(f"Error optimizing image array: {e}", exc_info=True)
            return img, None
    
    def optimize_file(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        in_place: bool = False
    ) -> Tuple[str, Optional[ImageOptimizationStats]]:
        """
        Optimize an image file with compression and optional resizing.
        
        Args:
            input_path: Path to input image
            output_path: Path for optimized image (if None, creates temp file)
            in_place: If True, overwrites input_path (ignores output_path)
            
        Returns:
            Tuple of (output_file_path, optimization_stats)
        """
        if not self.enabled:
            return input_path, None
        
        stats = ImageOptimizationStats()
        
        try:
            # Get original file size
            if os.path.exists(input_path):
                stats.original_size_bytes = os.path.getsize(input_path)
            
            # Load image with PIL for better compression control
            img = Image.open(input_path)
            
            # Convert RGBA to RGB if needed (for JPEG compatibility)
            if img.mode == 'RGBA':
                # Create white background
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])  # Use alpha as mask
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            original_width, original_height = img.size
            stats.original_dimensions = (original_width, original_height)
            
            # Resize if needed
            if self.should_resize(original_width, original_height):
                new_width, new_height = self.calculate_new_dimensions(
                    original_width, 
                    original_height
                )
                
                # Use LANCZOS for high-quality downsampling
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                stats.was_resized = True
                stats.optimized_dimensions = (new_width, new_height)
                
                logger.debug(
                    f"Resized image file: {original_width}x{original_height} → "
                    f"{new_width}x{new_height}"
                )
            else:
                stats.optimized_dimensions = (original_width, original_height)
            
            # Determine output path
            if in_place:
                final_output_path = input_path
            elif output_path:
                final_output_path = output_path
            else:
                # Create temp file with optimization suffix
                input_file = Path(input_path)
                final_output_path = str(
                    input_file.parent / f"{input_file.stem}_opt{input_file.suffix}"
                )
            
            # Save with PNG compression
            img.save(
                final_output_path,
                format='PNG',
                optimize=True,
                compress_level=self.png_compression
            )
            
            stats.was_compressed = True
            
            # Get optimized file size
            if os.path.exists(final_output_path):
                stats.optimized_size_bytes = os.path.getsize(final_output_path)
            
            stats.calculate_metrics()
            
            logger.info(f"Image optimization complete: {stats}")
            
            return final_output_path, stats
            
        except Exception as e:
            logger.error(f"Error optimizing image file {input_path}: {e}", exc_info=True)
            # Return original path on error
            return input_path, None
    
    def get_image_info(self, path: str) -> Dict[str, Any]:
        """
        Get information about an image file.
        
        Args:
            path: Path to image file
            
        Returns:
            Dictionary with image information
        """
        try:
            img = Image.open(path)
            file_size = os.path.getsize(path) if os.path.exists(path) else 0
            
            return {
                'path': path,
                'format': img.format,
                'mode': img.mode,
                'width': img.width,
                'height': img.height,
                'size_bytes': file_size,
                'size_kb': round(file_size / 1024, 2),
                'needs_optimization': self.should_resize(img.width, img.height)
            }
        except Exception as e:
            logger.error(f"Error getting image info for {path}: {e}")
            return {'error': str(e)}


# Convenience function for quick optimization
def optimize_image_for_ocr(
    image_path: str,
    max_dimension: int = DEFAULT_MAX_DIMENSION,
    in_place: bool = False,
    enabled: bool = True
) -> Tuple[str, Optional[ImageOptimizationStats]]:
    """
    Quick helper to optimize an image for OCR processing.
    
    Args:
        image_path: Path to image file
        max_dimension: Maximum width/height (default 1920)
        in_place: Whether to overwrite original file
        enabled: Whether optimization is enabled
        
    Returns:
        Tuple of (optimized_image_path, stats)
        
    Example:
        optimized_path, stats = optimize_image_for_ocr(
            '/path/to/screenshot.png',
            max_dimension=1920,
            in_place=True
        )
        if stats:
            print(f"Reduced size by {stats.size_reduction_percent:.1f}%")
    """
    optimizer = ImageOptimizer(
        max_dimension=max_dimension,
        png_compression=DEFAULT_PNG_COMPRESSION,
        enabled=enabled
    )
    
    return optimizer.optimize_file(image_path, in_place=in_place)


if __name__ == '__main__':
    # Test/demo code
    import sys
    
    logging.basicConfig(level=logging.DEBUG)
    
    print("Image Optimizer Test")
    print("=" * 50)
    
    if len(sys.argv) > 1:
        test_image = sys.argv[1]
        
        if os.path.exists(test_image):
            optimizer = ImageOptimizer(max_dimension=1920, png_compression=6)
            
            print(f"\nOriginal image info:")
            info = optimizer.get_image_info(test_image)
            for key, value in info.items():
                print(f"  {key}: {value}")
            
            print(f"\nOptimizing...")
            output_path, stats = optimizer.optimize_file(test_image)
            
            if stats:
                print(f"\nOptimization results:")
                for key, value in stats.to_dict().items():
                    print(f"  {key}: {value}")
                print(f"\n{stats}")
            else:
                print("Optimization skipped or failed")
        else:
            print(f"Error: File not found: {test_image}")
    else:
        print("Usage: python image_optimizer.py <image_path>")
        print("Example: python image_optimizer.py screenshot.png")
