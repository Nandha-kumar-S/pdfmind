"""
PDFMind - PDF Document Processing Library

A modular Python library for extracting structured information from PDF documents,
including Table of Contents, tables, and future image processing capabilities.
"""

# Core imports - no LLM dependencies
from .processor import TOCProcessor, TableProcessor, ImageProcessor

# Optional imports with LLM dependencies (imported when needed)
try:
    from .pdf_parser import PDFParser
    _PDFParser_available = True
except ImportError as e:
    _PDFParser_available = False
    PDFParser = None

__all__ = ['TOCProcessor', 'TableProcessor', 'ImageProcessor']

# Only include PDFParser if dependencies are available
if _PDFParser_available:
    __all__.append('PDFParser')