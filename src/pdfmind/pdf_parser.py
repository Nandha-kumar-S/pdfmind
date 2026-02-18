import re
import copy
import os
import json
import logging
from pathlib import Path
from datetime import datetime    
import traceback
from tqdm import tqdm
from docling.document_converter import DocumentConverter
import markdown
import pandas as pd
import io

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from utils.common_utils import get_prompt, save_file
from utils.llm_utils.llm_service import LLMService

class PDFParser:
    def __init__(self):
        self.llm_service = LLMService()

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

    def extract_toc(self, markdown_file):
        heading_pattern = re.compile(r"^\s*(?:##)\s+(.*)")
        headings = []

        try:
            lines_list = markdown_file.splitlines()
            for line in lines_list:
                match = heading_pattern.match(line)
                if match:
                    heading_text = match.group(1).strip()
                    headings.append(heading_text)
            
            logging.info(f"Found {len(headings)} potential headings. Sending to AI model for structuring.")
            input_data = 'Headings from protocol document\n\n' + ', '.join(headings)
            
            toc_prompt = get_prompt('TableOfContentsExtractor', input_data)
            toc = self.llm_service.infer_json(toc_prompt)
            logging.info(
                f"Successfully generated ToC with {len(toc.get('toc', []))} top-level sections."
            )
            return toc
                    
        except Exception as e:
            logging.error(f"An unexpected error occurred during ToC extraction: {e}")
            print(traceback.print_exc())
            return {"toc": []}

    def _flatten_toc(self, toc_nodes, flat_list):
        """Recursively flattens the ToC structure into a single list."""
        for node in toc_nodes:
            flat_list.append(node)
            if 'subsections' in node and node['subsections']:
                self._flatten_toc(node['subsections'], flat_list)

    def _map_content_to_toc(self, toc_nodes, content_map):
        """Recursively traverses the ToC and adds the 'text' key from the content map."""
        for node in toc_nodes:
            title = node.get('title')
            if title in content_map:
                node['text'] = content_map[title]
            else:
                node['text'] = ""  # Ensure text key exists
            if 'subsections' in node and node['subsections']:
                self._map_content_to_toc(node['subsections'], content_map)

    def _process_non_toc_chunks(self, text_chunk):
        """Parses a chunk of text for informal '##' headings and their content."""
        structured_chunk = []
        current_title = None
        current_content = []

        for line in text_chunk:
            if line.strip().startswith('## '):
                # If we were tracking a title, save its content first
                if current_title:
                    structured_chunk.append({
                        'number': None,
                        'title': current_title,
                        'subsections': [],
                        'text': '\n'.join(current_content).strip()
                    })
                
                # Start the new section
                current_title = line.strip().lstrip('## ').strip()
                current_content = []
            elif current_title:
                current_content.append(line)

        # Save the last section of the chunk
        if current_title:
            structured_chunk.append({
                'number': None,
                'title': current_title,
                'subsections': [],
                'text': '\n'.join(current_content).strip()
            })
        
        return structured_chunk

    def merge_toc_and_content(self, toc_data, markdown_file):
        """
        Extracts content for each ToC entry directly from the markdown file
        and merges it into the ToC structure.
        """
        markdown_lines = markdown_file.splitlines()

        # Handle case where there is no valid ToC
        if not isinstance(toc_data, dict) or not toc_data.get('toc'):
            logging.warning("No valid ToC data found. Processing entire document as non-ToC content.")
            non_toc_content = self._process_non_toc_chunks(markdown_lines)
            return {'toc': [], 'non_toc': non_toc_content}

        logging.info("Starting content extraction and merging process...")
        # 1. Flatten the ToC to get an ordered list of all sections
        flat_toc = []
        self._flatten_toc(toc_data['toc'], flat_toc)
        last_toc_title = flat_toc[-1]['title'] if flat_toc else None

        # 2. Create a list of normalized heading keys for robust matching
        normalized_headings = []
        for node in flat_toc:
            # Normalize by removing dots, spaces, and lowercasing
            normalized_key = f"##{node['number']}{node['title']}".replace('.', '').replace(' ', '').lower()
            normalized_headings.append({
                'title': node['title'],
                'key': normalized_key
            })

        # 3. Iterate through the markdown to extract content between headings
        content_map = {}
        current_content = []
        current_title = None

        for line in tqdm(markdown_lines, desc="   Extracting content", unit="line", leave=False):
            is_any_heading = line.strip().startswith('## ')

            # Check if the line is a known ToC heading
            matched_toc_heading = None
            if is_any_heading:
                line_content = line.strip().lstrip('## ').strip()
                normalized_line_key = f"##{line_content}".replace('.', '').replace(' ', '').lower()
                for heading_info in normalized_headings:
                    if heading_info['key'] == normalized_line_key:
                        matched_toc_heading = heading_info
                        break

            # --- Decision Logic ---
            # A section break occurs if we find a known ToC heading OR if we're in the last section and find any heading.
            is_section_break = matched_toc_heading is not None or (current_title == last_toc_title and is_any_heading)

            if is_section_break:
                # Save the content of the previous section.
                if current_title:
                    content_map[current_title] = '\n'.join(current_content).strip()
                
                # If the break was caused by a known heading, start the new section.
                if matched_toc_heading:
                    current_title = matched_toc_heading['title']
                    current_content = []
                else:
                    # If it was an informal heading breaking the last section, stop collecting.
                    current_title = None
                    current_content = []
            
            # Otherwise, if we are in an active section, collect the line as content.
            elif current_title:
                current_content.append(line)

        # Save the content of the very last section after the loop finishes
        if current_title:
            content_map[current_title] = '\n'.join(current_content).strip()

        # 4. Map the extracted content back into the original ToC structure
        logging.info(f"Extracted content for {len(content_map)} sections. Mapping to ToC structure.")
        toc_copy = copy.deepcopy(toc_data)
        self._map_content_to_toc(toc_copy['toc'], content_map)

        # 5. Find and process non-ToC content (header and footer)
        first_toc_heading_key = f"##{flat_toc[0]['number']}{flat_toc[0]['title']}".replace('.', '').replace(' ', '').lower()
        last_toc_heading_key = f"##{flat_toc[-1]['number']}{flat_toc[-1]['title']}".replace('.', '').replace(' ', '').lower()
        
        first_heading_index = -1
        last_heading_index = -1

        for i, line in enumerate(markdown_lines):
            if line.strip().startswith('## '):
                normalized_line = f"##{line.strip().lstrip('## ').strip()}".replace('.', '').replace(' ', '').lower()
                if first_heading_index == -1 and normalized_line == first_toc_heading_key:
                    first_heading_index = i
                if normalized_line == last_toc_heading_key:
                    last_heading_index = i

        header_chunk = markdown_lines[:first_heading_index]
        # To find the end of the last section, we search for the next '##' after it starts
        footer_start_index = -1
        if last_heading_index != -1:
            for i in range(last_heading_index + 1, len(markdown_lines)):
                if markdown_lines[i].strip().startswith('## '):
                    footer_start_index = i
                    break
            # If no '##' is found after the last section, the footer starts from the end of the file
            if footer_start_index == -1:
                footer_start_index = len(markdown_lines)

        footer_chunk = markdown_lines[footer_start_index:]

        non_toc_content = self._process_non_toc_chunks(header_chunk) + self._process_non_toc_chunks(footer_chunk)
        
        # Prepend non-ToC header content and append footer content
        semantic_parsed_pdf = {'toc': toc_copy['toc'], 'non_toc': non_toc_content}

        return semantic_parsed_pdf

    def _extract_and_convert_tables(self, text):
        """Extracts markdown tables from text and converts them to structured JSON format."""
        # This regex looks for a header row, a separator row, and one or more body rows.
        table_pattern = re.compile(r'(^\|.*\|$\n^\|[-|: ]+\|$\n(?:^\|.*\|$\n?)+)', re.MULTILINE)
        
        tables_json = []
        non_table_text = text
        
        # Use a placeholder strategy to safely extract tables and text
        matches = list(table_pattern.finditer(text))
        for i, match in enumerate(reversed(matches)):
            table_md = match.group(0)
            placeholder = f"__TABLE_PLACEHOLDER_{i}__"
            non_table_text = non_table_text[:match.start()] + placeholder + non_table_text[match.end():]

            try:
                html = markdown.markdown(table_md, extensions=['tables'])
                df = pd.read_html(io.StringIO(html))[0]
                df.fillna('', inplace=True)
                
                table_data = {
                    'columns': [str(col) for col in df.columns],
                    'data': df.values.tolist()
                }
                tables_json.insert(0, table_data) # Insert at the beginning to maintain order
            except Exception as e:
                logging.warning(f"Could not parse a markdown table. Error: {e}. Re-inserting as text.")
                non_table_text = non_table_text.replace(placeholder, table_md)

        # Clean up any remaining placeholders
        for i in range(len(tables_json)):
             non_table_text = non_table_text.replace(f"__TABLE_PLACEHOLDER_{i}__", "")
                
        return non_table_text.strip(), tables_json

    def _recursively_process_tables(self, section_list):
        """Recursively processes sections to extract tables from text content."""
        for section in section_list:
            original_text = section.get('text', '')
            if original_text and '|' in original_text:
                cleaned_text, cleaned_tables = self._extract_and_convert_tables(original_text)
                section['text'] = cleaned_text
                section['tables'] = cleaned_tables
            else:
                section['text'] = original_text
                section['tables'] = []
            
            if 'text' in section:
                del section['text']

            if 'subsections' in section and section['subsections']:
                self._recursively_process_tables(section['subsections'])
        return section_list

    def parse(self, pdf_path, save_intermediate_files=False):
        logging.info("Starting PDF parsing process")

        # Convert PDF to markdown
        markdown_file = self.convert_pdf_to_markdown(pdf_path)
        
        # Extract ToC from markdown
        toc_data = self.extract_toc(markdown_file)

        # Merge ToC with content
        semantic_parsed_pdf = self.merge_toc_and_content(toc_data, markdown_file)

        # Extract tables from document structure
        logging.info("Extracting tables from document structure...")
        semantic_parsed_pdf['toc'] = self._recursively_process_tables(semantic_parsed_pdf['toc'])
        semantic_parsed_pdf['non_toc'] = self._recursively_process_tables(semantic_parsed_pdf['non_toc'])
        
        if save_intermediate_files:
            output_dir = os.path.join('output', datetime.now().strftime('%Y_%m_%d_%H_%M_%S'))
            os.makedirs(output_dir, exist_ok=True)

            save_file(markdown_file, output_dir, 'markdown.md')
            save_file(toc_data, output_dir, 'toc_data.json')
            # save_file(semantic_parsed_pdf, output_dir, 'semantic_parsed_pdf.json')
        logging.info("PDF parsing process completed")
        return semantic_parsed_pdf