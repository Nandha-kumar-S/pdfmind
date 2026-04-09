"""
PDFMind Processor Modules

This package contains specialized processors for different aspects of PDF parsing:
- TOCProcessor: Handles Table of Contents extraction and processing (with Python fallback)
- TableProcessor: Handles table extraction and conversion
- ImageProcessor: Handles image extraction and processing (placeholder for future implementation)
"""

from .toc_processor import TOCProcessor
from .table_processor import TableProcessor
from .image_processor import ImageProcessor

__all__ = ['TOCProcessor', 'TableProcessor', 'ImageProcessor']
