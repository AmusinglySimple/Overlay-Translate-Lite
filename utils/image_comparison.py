"""
Image comparison utilities for detecting changes in live translation captures.

Provides efficient image comparison methods to detect content changes
without performing full OCR, optimizing live translation performance.
"""

import hashlib
import numpy as np
from typing import Optional, Tuple
import cv2
import logging

logger = logging.getLogger(__name__)


class ImageComparator:
    """
    Efficient image comparison for change detection in live translation.
    
    Supports multiple comparison methods:
    - Perceptual hash (fast, robust to minor changes)
    - Pixel difference (precise, sensitive to all changes)
    - Histogram comparison (color-based)
    """
    
    def __init__(self):
        """Initialize the image comparator."""
        self.last_hash: Optional[str] = None
        self.last_image: Optional[np.ndarray] = None
    
    def compute_perceptual_hash(self, image: np.ndarray, hash_size: int = 8) -> str:
        """
        Compute perceptual hash of an image using average hash algorithm.
        
        Args:
            image (np.ndarray): Input image (BGR or grayscale)
            hash_size (int): Hash size (default 8x8 = 64 bits)
            
        Returns:
            str: Hexadecimal hash string
        """
        try:
            # Convert to grayscale if needed
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image
            
            # Resize to hash_size x hash_size
            resized = cv2.resize(gray, (hash_size, hash_size), interpolation=cv2.INTER_AREA)
            
            # Compute average
            avg = resized.mean()
            
            # Create binary hash
            diff = resized > avg
            
            # Convert to hex string
            hash_str = hashlib.md5(diff.tobytes()).hexdigest()
            return hash_str
            
        except Exception as e:
            logger.error(f"Error computing perceptual hash: {e}")
            return ""
    
    def compute_pixel_difference(self, image1: np.ndarray, image2: np.ndarray) -> float:
        """
        Compute normalized pixel difference between two images.
        
        Args:
            image1 (np.ndarray): First image
            image2 (np.ndarray): Second image
            
        Returns:
            float: Difference ratio (0.0 = identical, 1.0 = completely different)
        """
        try:
            # Ensure images are the same size
            if image1.shape != image2.shape:
                logger.warning("Images have different shapes, resizing for comparison")
                h, w = image1.shape[:2]
                image2 = cv2.resize(image2, (w, h))
            
            # Convert to grayscale if needed
            if len(image1.shape) == 3:
                gray1 = cv2.cvtColor(image1, cv2.COLOR_BGR2GRAY)
            else:
                gray1 = image1
                
            if len(image2.shape) == 3:
                gray2 = cv2.cvtColor(image2, cv2.COLOR_BGR2GRAY)
            else:
                gray2 = image2
            
            # Compute absolute difference
            diff = cv2.absdiff(gray1, gray2)
            
            # Count pixels with significant difference (threshold at 30/255)
            threshold = 30
            significant_diff = np.sum(diff > threshold)
            total_pixels = diff.size
            
            # Return ratio of changed pixels
            return significant_diff / total_pixels if total_pixels > 0 else 0.0
            
        except Exception as e:
            logger.error(f"Error computing pixel difference: {e}")
            return 1.0  # Assume changed on error
    
    def compute_histogram_similarity(self, image1: np.ndarray, image2: np.ndarray) -> float:
        """
        Compute histogram similarity between two images.
        
        Args:
            image1 (np.ndarray): First image
            image2 (np.ndarray): Second image
            
        Returns:
            float: Similarity score (1.0 = identical, 0.0 = completely different)
        """
        try:
            # Convert to grayscale if needed
            if len(image1.shape) == 3:
                gray1 = cv2.cvtColor(image1, cv2.COLOR_BGR2GRAY)
            else:
                gray1 = image1
                
            if len(image2.shape) == 3:
                gray2 = cv2.cvtColor(image2, cv2.COLOR_BGR2GRAY)
            else:
                gray2 = image2
            
            # Compute histograms
            hist1 = cv2.calcHist([gray1], [0], None, [256], [0, 256])
            hist2 = cv2.calcHist([gray2], [0], None, [256], [0, 256])
            
            # Normalize histograms
            cv2.normalize(hist1, hist1, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
            cv2.normalize(hist2, hist2, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
            
            # Compare using correlation method
            similarity = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
            
            return max(0.0, similarity)  # Ensure non-negative
            
        except Exception as e:
            logger.error(f"Error computing histogram similarity: {e}")
            return 0.0  # Assume different on error
    
    def has_changed(
        self, 
        current_image: np.ndarray, 
        threshold: float = 0.05,
        method: str = 'pixel'
    ) -> Tuple[bool, float]:
        """
        Check if current image has changed compared to last image.
        
        Args:
            current_image (np.ndarray): Current image to check
            threshold (float): Change threshold (0.0-1.0)
            method (str): Comparison method ('hash', 'pixel', or 'histogram')
            
        Returns:
            Tuple[bool, float]: (has_changed, change_amount)
        """
        # First call - no previous image
        if self.last_image is None:
            self.last_image = current_image.copy()
            if method == 'hash':
                self.last_hash = self.compute_perceptual_hash(current_image)
            return True, 1.0
        
        changed = False
        change_amount = 0.0
        
        try:
            if method == 'hash':
                current_hash = self.compute_perceptual_hash(current_image)
                changed = current_hash != self.last_hash
                change_amount = 1.0 if changed else 0.0
                if changed:
                    self.last_hash = current_hash
                    
            elif method == 'pixel':
                change_amount = self.compute_pixel_difference(self.last_image, current_image)
                changed = change_amount >= threshold
                
            elif method == 'histogram':
                similarity = self.compute_histogram_similarity(self.last_image, current_image)
                change_amount = 1.0 - similarity
                changed = change_amount >= threshold
                
            else:
                logger.warning(f"Unknown comparison method '{method}', defaulting to pixel")
                change_amount = self.compute_pixel_difference(self.last_image, current_image)
                changed = change_amount >= threshold
            
            # Update last image if changed
            if changed:
                self.last_image = current_image.copy()
            
            return changed, change_amount
            
        except Exception as e:
            logger.error(f"Error in has_changed: {e}")
            # On error, assume changed to be safe
            self.last_image = current_image.copy()
            return True, 1.0
    
    def reset(self):
        """Reset comparator state, clearing cached images and hashes."""
        self.last_hash = None
        self.last_image = None
        logger.debug("ImageComparator state reset")


def load_image_for_comparison(image_path: str) -> Optional[np.ndarray]:
    """
    Load an image file for comparison.
    
    Args:
        image_path (str): Path to image file
        
    Returns:
        Optional[np.ndarray]: Loaded image or None on error
    """
    try:
        image = cv2.imread(image_path)
        if image is None:
            logger.error(f"Failed to load image: {image_path}")
            return None
        return image
    except Exception as e:
        logger.error(f"Error loading image {image_path}: {e}")
        return None
