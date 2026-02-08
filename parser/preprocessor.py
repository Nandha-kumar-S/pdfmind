import json
import logging
from tqdm import tqdm
import pandas as pd
import markdown
import re
import io
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class PDFPreprocessor:
    def __init__(self, min_text_length=50):
        self.min_text_length = min_text_length
        logging.info(f"Preprocessor initialized. Minimum text length to keep a section: {self.min_text_length}")

    def _recursively_filter_sections(self, section_list):
        if not isinstance(section_list, list):
            return []

        filtered_list = []
        for section in section_list:
            # First, recursively filter the children of the current section
            if 'subsections' in section and section['subsections']:
                section['subsections'] = self._recursively_filter_sections(section['subsections'])

            # Now, decide if the current section should be kept
            title = section.get('title', '').lower()
            is_toc_entry = 'table of contents' in title

            has_meaningful_text = len(section.get('text', '').strip()) > self.min_text_length
            has_children = bool(section.get('subsections'))

            # Keep the section if it's not a ToC entry AND it either has text or has children.
            if not is_toc_entry and (has_meaningful_text or has_children):
                filtered_list.append(section)
        
        return filtered_list

    def _extract_and_convert_tables(self, text):
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
        for section in section_list:
            original_text = section.get('text', '')
            if original_text and '|' in original_text:
                cleaned_text, cleaned_tables = self._extract_and_convert_tables(original_text)
                section['cleaned_text'] = cleaned_text
                section['cleaned_tables'] = cleaned_tables
            else:
                section['cleaned_text'] = original_text
                section['cleaned_tables'] = []
            
            if 'text' in section:
                del section['text']

            if 'subsections' in section and section['subsections']:
                self._recursively_process_tables(section['subsections'])
        return section_list

    def preprocess(self, structured_data):
        logging.info("Starting preprocessing...")
        if not isinstance(structured_data, dict) or ('toc' not in structured_data and 'non_toc' not in structured_data):
            logging.error("Invalid input format. Expected a dictionary with 'toc' and/or 'non_toc' keys.")
            return {}

        # Step 1: Filter out empty/irrelevant sections
        processed_toc = self._recursively_filter_sections(structured_data.get('toc', []))
        processed_non_toc = self._recursively_filter_sections(structured_data.get('non_toc', []))

        # Step 2: Separate tables from text for all remaining sections
        logging.info("Separating tables from text content...")
        processed_toc = self._recursively_process_tables(processed_toc)
        processed_non_toc = self._recursively_process_tables(processed_non_toc)

        final_structure = {
            'toc': processed_toc,
            'non_toc': processed_non_toc
        }
        preprocessed_pdf = [item for sublist in final_structure.values() for item in sublist]

        logging.info("Preprocessing complete.")
        return preprocessed_pdf

    def save_tables_for_testing(self, structured_data, output_dir='output/lzzt/tables_test'):
        """
        Recursively traverses the data and saves any found tables as CSV files for easy verification.
        """
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            logging.info(f"Created testing directory: {output_dir}")

        def _recursive_save(sections):
            for section in sections:
                if 'cleaned_tables' in section and section['cleaned_tables']:
                    for i, table_data in enumerate(section['cleaned_tables']):
                        try:
                            # Sanitize the title to create a valid filename
                            title = section.get('title', 'untitled')
                            safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')
                            filename = f"{safe_title}_{i}.csv"
                            filepath = os.path.join(output_dir, filename)

                            df = pd.DataFrame(table_data['data'], columns=table_data['columns'])
                            df.to_csv(filepath, index=False)
                        except Exception as e:
                            logging.error(f"Could not save table {i} from section '{title}'. Error: {e}")
                
                if 'subsections' in section and section['subsections']:
                    _recursive_save(section['subsections'])

        logging.info("Saving extracted tables to CSV for testing...")
        _recursive_save(structured_data.get('toc', []))
        _recursive_save(structured_data.get('non_toc', []))
        logging.info("Finished saving tables.")