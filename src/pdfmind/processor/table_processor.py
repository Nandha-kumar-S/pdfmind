import re
import logging
import markdown
import pandas as pd
import io


class TableProcessor:
    """Handles extraction and conversion of markdown tables to structured JSON format."""
    
    def extract_and_convert_tables(self, text):
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

    def recursively_process_tables(self, section_list):
        """Recursively processes sections to extract tables from text content."""
        for section in section_list:
            original_text = section.get('text', '')
            if original_text and '|' in original_text:
                cleaned_text, cleaned_tables = self.extract_and_convert_tables(original_text)
                section['text'] = cleaned_text
                section['tables'] = cleaned_tables
            else:
                section['text'] = original_text
                section['tables'] = []

            if 'subsections' in section and section['subsections']:
                self.recursively_process_tables(section['subsections'])
        return section_list
