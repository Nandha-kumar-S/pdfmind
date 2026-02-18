# Project Plan

## Features (feat)
1. **Image Extraction**
   - Extract and save images under their respective sections
   - Include image references in the output structure

2. **LLM Provider Support**
   - Add Anthropic API client integration
   - Make LLM provider configurable (OpenAI/Anthropic)

3. **Table Output Formats**
   - Support both JSON and Markdown table formats
   - Add output format configuration option

4. **CLI Interface**
   - Implement `argparse` for command-line arguments
   - Commands for different operations (parse, extract-toc, etc.)
   - Configuration via CLI flags and/or config files

## Enhancements
1. **TOC Extraction**
   - Fallback to Python-based TOC generation using numerical headings
   - Improve accuracy of heading level detection

2. **Output Options**
   - Add flatten functionality for TOC hierarchy
   - Configurable output formats (nested/flat)

3. **Error Handling**
   - Add retry logic in LLMService
   - Better error messages and logging

## Performance
1. **TOC Processing**
   - Optimize LLM input by sending only numerical headings

## Style & Structure
1. **Code Organization**
   - Split large files into logical modules
   - Create separate modules for TOC, table, and image processing as needed

2. **Documentation**
   - Add docstrings to all public methods
   - Create API documentation
   - Add usage examples
 
## Dependencies
1. **New Dependencies**
   - `anthropic` for Claude API
   - `pytest` for testing
   - `pytest-mock` for mocking