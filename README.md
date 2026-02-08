# PDF Parser

PDF parsing module for clinical protocol documents.

## Installation

```bash
pip install -e .
```

## Usage

```python
from parser import PDFParser

parser = PDFParser("path/to/document.pdf")
markdown, structure = parser.parse()
```

## Dependencies

- docling: PDF to Markdown conversion
- tqdm: Progress bars
- pandas: Table processing
- markdown: Text processing

## Note

This module requires an external `ml` package for LLM functionality (GenAIModel, get_prompt).
