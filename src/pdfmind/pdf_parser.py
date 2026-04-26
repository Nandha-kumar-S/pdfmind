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
    def __init__(self, toc_extraction_method: str = "auto", 
                 max_heading_levels: int = 4, llm_timeout: int = 30,
                 image_min_width: int = 100, image_min_height: int = 100,
                 image_min_bytes: int = 2048, image_convert_to_png: bool = True):
        self.llm_service = LLMService()
        self.toc_processor = TOCProcessor(
            self.llm_service, 
            toc_extraction_method=toc_extraction_method,
            max_heading_levels=max_heading_levels,
            llm_timeout=llm_timeout
        )
        self.table_processor = TableProcessor()
        self.image_processor = ImageProcessor(
            min_width=image_min_width,
            min_height=image_min_height,
            min_bytes=image_min_bytes,
            convert_to_png=image_convert_to_png
        )

    def convert_pdf_to_markdown(self, pdf_path):
        logging.info(f"Starting PDF to Markdown conversion for {pdf_path}")
        try:
            source_path = Path(pdf_path)
            if not source_path.is_file():
                raise FileNotFoundError(f"Source file not found: {source_path}")

            converter = DocumentConverter()
            result = converter.convert(source_path)
            markdown = result.document.export_to_markdown()
            logging.info("Successfully converted PDF to Markdown in memory.")
            return markdown, result.document
        except Exception as e:
            logging.error(f"Error during PDF to Markdown conversion: {e}")
            return None, None

    def parse(self, pdf_path, save_intermediate_files=False):
        logging.info("Starting PDF parsing process")

        # Convert PDF to markdown
        markdown_file, docling_document = self.convert_pdf_to_markdown(pdf_path)

        # Set docling document and pdf_path for coordinate tracking
        self.toc_processor.docling_document = docling_document
        self.toc_processor.pdf_path = pdf_path

        # Extract ToC from markdown
        toc_data = self.toc_processor.extract_toc(markdown_file)

        # Merge ToC with content
        semantic_parsed_pdf = self.toc_processor.merge_toc_and_content(toc_data, markdown_file)

        # Extract tables from document structure
        logging.info("Extracting tables from document structure...")
        semantic_parsed_pdf['toc'] = self.table_processor.recursively_process_tables(semantic_parsed_pdf['toc'])
        semantic_parsed_pdf['non_toc'] = self.table_processor.recursively_process_tables(semantic_parsed_pdf['non_toc'])

        # Extract images from PDF
        logging.info("Extracting images from PDF...")
        images = self.image_processor.extract_all_images(pdf_path)

        # Map images to sections
        if images:
            logging.info("Mapping images to sections...")
            semantic_parsed_pdf = self.image_processor.map_images_to_sections(images, semantic_parsed_pdf)

        # Extract captions for images
        if images:
            logging.info("Extracting image captions...")
            semantic_parsed_pdf = self.image_processor.extract_captions(semantic_parsed_pdf, pdf_path)

        # Save images to disk if saving intermediate files
        output_dir = None
        if save_intermediate_files:
            output_dir = os.path.join('output', datetime.now().strftime('%Y_%m_%d_%H_%M_%S'))
            os.makedirs(output_dir, exist_ok=True)

            save_file(markdown_file, output_dir, 'markdown.md')
            save_file(toc_data, output_dir, 'toc_data.json')

            # Save images
            if images:
                self.image_processor.save_images(images, output_dir, semantic_parsed_pdf)

            # Clean bytes from the data before serialization
            def clean_image_bytes(data):
                if isinstance(data, dict):
                    if 'bytes' in data:
                        del data['bytes']
                    for key, value in data.items():
                        clean_image_bytes(value)
                elif isinstance(data, list):
                    for item in data:
                        clean_image_bytes(item)

            clean_image_bytes(semantic_parsed_pdf)
            save_file(semantic_parsed_pdf, output_dir, 'semantic_parsed_pdf.json')

        logging.info("PDF parsing process completed")
        return semantic_parsed_pdf