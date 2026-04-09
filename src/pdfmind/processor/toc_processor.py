import re
import copy
import logging
from tqdm import tqdm
import traceback
from typing import List, Dict, Any

from ..utils.common_utils import get_prompt


class TOCProcessor:
    """Handles Table of Contents extraction, processing, and content mapping."""
    
    def __init__(self, llm_service, toc_extraction_method: str = "auto", 
                 max_heading_levels: int = 4, llm_timeout: int = 30):
        self.llm_service = llm_service
        
        # Configuration parameters
        # "llm": Use AI model for extraction
        # "pattern_based": Use regex patterns for numerical headings
        # "auto": Try LLM first, fall back to pattern_based if fails
        self.toc_extraction_method = toc_extraction_method
        self.max_heading_levels = max_heading_levels
        self.llm_timeout = llm_timeout
        
        self.logger = logging.getLogger(__name__)
        
        # Compile regex patterns for different heading levels
        self.heading_patterns = [
            (r'^(\d+)\s+(.+)$', 1),           # 1 Title
            (r'^(\d+\.\d+)\s+(.+)$', 2),       # 1.1 Title  
            (r'^(\d+\.\d+\.\d+)\s+(.+)$', 3),   # 1.1.1 Title
            (r'^(\d+\.\d+\.\d+\.\d+)\s+(.+)$', 4) # 1.1.1.1 Title
        ]
    
    def extract_toc(self, markdown_file):
        """Extracts and structures Table of Contents from markdown content."""
        return self.extract_toc_with_fallback(markdown_file)
    
    def extract_toc_with_fallback(self, markdown_file):
        """Extract TOC with LLM and Python fallback."""
        # Use pattern-based method if explicitly configured
        if self.toc_extraction_method == "pattern_based":
            self.logger.info("Using pattern-based TOC extraction (configured)")
            return self._extract_toc_with_python(markdown_file)
        
        # Try LLM first for "auto" or "llm" methods
        if self.toc_extraction_method in ["auto", "llm"]:
            try:
                return self._extract_toc_with_llm(markdown_file)
            except Exception as e:
                if self.toc_extraction_method == "auto":
                    self.logger.warning(f"LLM TOC extraction failed: {e}")
                    self.logger.info("Falling back to Python-based extraction")
                    return self._extract_toc_with_python(markdown_file)
                else:
                    # toc_extraction_method == "llm" - no fallback, raise the error
                    self.logger.error(f"LLM TOC extraction failed: {e}")
                    raise
        
        # If toc_extraction_method is invalid
        self.logger.error(f"Invalid TOC extraction method: {self.toc_extraction_method}")
        return {"toc": []}
    
    def _extract_toc_with_python(self, markdown_file: str) -> Dict[str, Any]:
        """
        Extract TOC from markdown using Python-based numerical heading detection.

        Args:
            markdown_file: Markdown content as string

        Returns:
            Dictionary with 'toc' key containing hierarchical structure
        """
        try:
            method_name = "pattern-based" if self.toc_extraction_method == "pattern_based" else "Python-based"
            self.logger.info(f"Starting {method_name} TOC extraction")

            # Extract headings from markdown
            headings = self._extract_numerical_headings(markdown_file)

            if not headings:
                self.logger.warning(f"No numerical headings found for {method_name} extraction")
                return {"toc": []}

            # Build hierarchical structure
            toc_structure = self._build_hierarchy(headings)

            self.logger.info(f"Successfully extracted TOC with {len(toc_structure)} top-level sections")
            return {"toc": toc_structure}

        except Exception as e:
            method_name = "pattern-based" if self.toc_extraction_method == "pattern_based" else "Python-based"
            self.logger.error(f"{method_name} TOC extraction failed: {e}")
            return {"toc": [], "extraction_method": f"{method_name}_failed", "error": str(e)}
    
    def _extract_numerical_headings(self, markdown_file: str) -> List[Dict[str, Any]]:
        """Extract numerical headings with their levels and content."""
        headings = []
        lines = markdown_file.splitlines()
        
        for line in lines:
            
            line = line.strip()
            if not line.startswith('## '):
                continue
                
            # Remove ## prefix and clean
            heading_text = line[3:].strip()
            
            # Try each pattern to determine level and extract number
            for pattern, level in self.heading_patterns:
                if level > self.max_heading_levels:
                    continue
                    
                match = re.match(pattern, heading_text)
                if match:
                    number = match.group(1)
                    title = match.group(2).strip()
                    
                    headings.append({
                        'number': number,
                        'title': title,
                        'level': level,
                        'subsections': []
                    })
                    break
        
        return headings
    
    def _build_hierarchy(self, headings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Build hierarchical TOC structure from flat heading list."""
        if not headings:
            return []
        
        # Sort by original order (maintain document sequence)
        toc_structure = []
        stack = []  # Stack to track parent relationships
        
        for heading in headings:
            level = heading['level']
            
            # Pop from stack until we find appropriate parent
            while stack and stack[-1]['level'] >= level:
                stack.pop()
            
            # Add to parent if exists, otherwise it's a top-level section
            if stack:
                parent = stack[-1]
                parent['subsections'].append(heading)
            else:
                toc_structure.append(heading)
            
            # Add current heading to stack
            stack.append(heading)
        
        # Clean up the structure - remove temporary level fields
        self._clean_structure(toc_structure)
        
        return toc_structure
    
    def _clean_structure(self, items: List[Dict[str, Any]]) -> None:
        """Remove temporary fields from TOC structure recursively."""
        for item in items:
            if 'level' in item:
                del item['level']
            if 'subsections' in item and item['subsections']:
                self._clean_structure(item['subsections'])
    
    def _extract_toc_with_llm(self, markdown_file):
        """Extract TOC using LLM service."""
        # Use numerical heading filtering to only send relevant headings to LLM
        headings_data = self._extract_numerical_headings(markdown_file)
        headings = [h['title'] for h in headings_data]

        if not headings:
            self.logger.warning("No numerical headings found for LLM extraction")
            return {"toc": []}

        self.logger.info(f"Found {len(headings)} numerical headings. Sending to AI model for structuring.")
        input_data = 'Headings from protocol document\n\n' + ', '.join(headings)

        toc_prompt = get_prompt('TableOfContentsExtractor', input_data)
        toc = self.llm_service.infer_json(toc_prompt)
        self.logger.info(
            f"Successfully generated ToC with {len(toc.get('toc', []))} top-level sections."
        )
        return toc

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
