import os
import json
import logging
from pathlib import Path
from datetime import datetime    
from docling.document_converter import DocumentConverter

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from .utils.common_utils import get_prompt, save_file
from .utils.llm_utils.llm_service import LLMService
from .processor import TOCProcessor, TableProcessor, ImageProcessor

class PDFParser:
    def __init__(self):
        self.llm_service = LLMService()
        self.toc_processor = TOCProcessor(self.llm_service)
        self.table_processor = TableProcessor()
        self.image_processor = ImageProcessor()

    def convert_pdf_to_markdown(self, pdf_path):
        logging.info(f"Starting PDF to Markdown conversion for {pdf_path}")
        try:
            source_path = Path(pdf_path)
            if not source_path.is_file():
                raise FileNotFoundError(f"Source file not found: {source_path}")

            converter = DocumentConverter()
            result = converter.convert(source_path)
            result = result.document.export_to_markdown()
            logging.info("Successfully converted PDF to Markdown in memory.")
            return result
        except Exception as e:
            logging.error(f"Error during PDF to Markdown conversion: {e}")
            return None

    def parse(self, pdf_path, save_intermediate_files=False):
        logging.info("Starting PDF parsing process")

        # Convert PDF to markdown
        markdown_file = self.convert_pdf_to_markdown(pdf_path)
        
        # Extract ToC from markdown
        toc_data = self.toc_processor.extract_toc(markdown_file)

        # Merge ToC with content
        semantic_parsed_pdf = self.toc_processor.merge_toc_and_content(toc_data, markdown_file)

        # Extract tables from document structure
        logging.info("Extracting tables from document structure...")
        semantic_parsed_pdf['toc'] = self.table_processor.recursively_process_tables(semantic_parsed_pdf['toc'])
        semantic_parsed_pdf['non_toc'] = self.table_processor.recursively_process_tables(semantic_parsed_pdf['non_toc'])
        
        if save_intermediate_files:
            output_dir = os.path.join('output', datetime.now().strftime('%Y_%m_%d_%H_%M_%S'))
            os.makedirs(output_dir, exist_ok=True)

            save_file(markdown_file, output_dir, 'markdown.md')
            save_file(toc_data, output_dir, 'toc_data.json')
            save_file(semantic_parsed_pdf, output_dir, 'semantic_parsed_pdf.json')
        logging.info("PDF parsing process completed")
        return semantic_parsed_pdf