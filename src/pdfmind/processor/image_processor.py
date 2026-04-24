import logging
import os
import re
from typing import List, Dict, Any
from pathlib import Path
import fitz  # PyMuPDF


class ImageProcessor:
    """Handles extraction and processing of images from PDF documents using PyMuPDF."""

    def __init__(self, min_width: int = 100, min_height: int = 100,
                 min_bytes: int = 2048, convert_to_png: bool = True):
        """
        Initialize the image processor.

        Args:
            min_width: Minimum image width in pixels
            min_height: Minimum image height in pixels
            min_bytes: Minimum image size in bytes
            convert_to_png: If True, convert all images to PNG; if False, keep native formats
        """
        self.min_width = min_width
        self.min_height = min_height
        self.min_bytes = min_bytes
        self.convert_to_png = convert_to_png
        self.logger = logging.getLogger(__name__)

    def extract_all_images(self, pdf_path: str) -> List[Dict[str, Any]]:
        """
        Extract all images from PDF using PyMuPDF.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            List of image metadata dictionaries
        """
        if not Path(pdf_path).exists():
            self.logger.error(f"PDF file not found: {pdf_path}")
            return []

        images = []
        try:
            doc = fitz.open(pdf_path)

            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images(full=True)
                image_info_list = page.get_image_info(hashes=True)

                # Create a mapping from xref to image info for bbox lookup
                info_by_xref = {info.get('xref', info.get('number', 0)): info for info in image_info_list}

                for img in image_list:
                    # img is a tuple: (xref, smask, width, height, bpc, colorspace, alt_colorspace, name, filter, bbox)
                    xref = img[0]
                    if xref == 0:
                        continue

                    try:
                        # Extract image data
                        base_image = doc.extract_image(xref)

                        if not base_image:
                            continue

                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]

                        # Get dimensions from tuple
                        width = img[2]
                        height = img[3]

                        # Get bbox using get_image_rects (more reliable than get_image_info)
                        rects = page.get_image_rects(xref)
                        if rects:
                            bbox = list(rects[0])
                        else:
                            # Fallback to image_info if get_image_rects fails
                            img_info = info_by_xref.get(xref, {})
                            bbox = img_info.get('bbox', [0, 0, 0, 0])

                        images.append({
                            'page': page_num + 1,  # 1-indexed
                            'bbox': bbox,  # [x0, y0, x1, y1]
                            'dimensions': [width, height],
                            'format': image_ext.upper(),
                            'xref': xref,
                            'bytes': image_bytes
                        })
                    except Exception as e:
                        self.logger.warning(f"Error processing image on page {page_num + 1} (xref={xref}): {e}")
                        continue

            doc.close()
            self.logger.info(f"Extracted {len(images)} images from PDF")
            return images

        except Exception as e:
            self.logger.error(f"Error extracting images from PDF: {e}")
            return []

    def map_images_to_sections(self, images: List[Dict[str, Any]], toc_structure: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map images to TOC sections based on page and y-coordinate.

        Args:
            images: List of image metadata dictionaries
            toc_structure: Dictionary with 'toc' and 'non_toc' keys

        Returns:
            Updated toc_structure with images added to sections
        """
        # Initialize images array for all sections
        def init_images_array(sections):
            for section in sections:
                section['images'] = []
                if 'subsections' in section and section['subsections']:
                    init_images_array(section['subsections'])

        init_images_array(toc_structure.get('toc', []))
        if 'non_toc' in toc_structure:
            for section in toc_structure['non_toc']:
                section['images'] = []

        if not images:
            return toc_structure

        # Flatten TOC to get all sections with their coordinates
        flat_sections = []

        def collect_sections(sections, parent_start_page=1, parent_start_y=0):
            for i, section in enumerate(sections):
                flat_sections.append(section)

                # Process subsections
                if 'subsections' in section and section['subsections']:
                    collect_sections(section['subsections'],
                                   section.get('start_page', parent_start_page),
                                   section.get('start_y', parent_start_y))

        collect_sections(toc_structure.get('toc', []))

        # Sort sections by start_page and start_y
        flat_sections.sort(key=lambda x: (x.get('start_page', 1), x.get('start_y', 0)))

        # For each image, find the appropriate section
        for image in images:
            image_page = image['page']
            image_y = image['bbox'][1]  # y0 coordinate

            # Find section where image belongs
            assigned_section = None

            # First, try to find a section on the same page
            for section in flat_sections:
                section_page = section.get('start_page', 1)
                section_y = section.get('start_y', 0)

                if image_page == section_page:
                    # Same page: check y-coordinate
                    if image_y >= section_y:
                        assigned_section = section
                    else:
                        # Image is before this section on the same page
                        break

            # If no section found on same page, find the last section before this page
            if not assigned_section:
                for section in flat_sections:
                    section_page = section.get('start_page', 1)
                    if section_page < image_page:
                        assigned_section = section
                    elif section_page > image_page:
                        break

            # If no section assigned, it's before the first section
            if not assigned_section:
                # Add to non_toc
                if 'non_toc' not in toc_structure:
                    toc_structure['non_toc'] = []
                # Find first non_toc section or create one
                if not toc_structure['non_toc']:
                    toc_structure['non_toc'].append({
                        'number': None,
                        'title': 'Header',
                        'subsections': [],
                        'text': '',
                        'tables': [],
                        'images': []
                    })
                toc_structure['non_toc'][0]['images'].append(image)
                continue

            # Add image to the assigned section
            assigned_section['images'].append(image)

        return toc_structure

    def save_images(self, images: List[Dict[str, Any]], output_dir: str, toc_structure: Dict[str, Any]) -> Dict[str, str]:
        """
        Save images to hierarchical directory structure.

        Args:
            images: List of image metadata dictionaries
            output_dir: Base output directory
            toc_structure: Dictionary with 'toc' and 'non_toc' keys

        Returns:
            Dictionary mapping image paths to metadata
        """
        if not images:
            return {}

        image_path_map = {}
        images_dir = os.path.join(output_dir, 'images')
        os.makedirs(images_dir, exist_ok=True)

        try:
            from PIL import Image
            import io
        except ImportError:
            self.logger.error("Pillow not installed. Cannot save images.")
            return {}

        # Counter for global/uncategorized images
        global_counter = 1

        # Process images in each section
        def process_sections(sections, section_path_prefix=""):
            nonlocal global_counter

            for section in sections:
                if 'images' not in section or not section['images']:
                    if 'subsections' in section and section['subsections']:
                        process_sections(section['subsections'], section_path_prefix)
                    continue

                # Create directory for this section
                section_title = section.get('title', 'untitled')
                # Sanitize section title for filename
                sanitized_title = re.sub(r'[^\w\s-]', '', section_title).strip().replace(' ', '_')
                if sanitized_title:
                    section_dir = os.path.join(images_dir, sanitized_title)
                else:
                    section_dir = os.path.join(images_dir, 'global')

                os.makedirs(section_dir, exist_ok=True)

                # Save images in this section
                for i, image in enumerate(section['images'], 1):
                    try:
                        image_bytes = image['bytes']

                        # Determine format
                        if self.convert_to_png:
                            output_format = 'PNG'
                            ext = 'png'
                        else:
                            output_format = image['format']
                            ext = image['format'].lower()

                        # Generate filename
                        filename = f"image_{i:03d}.{ext}"
                        filepath = os.path.join(section_dir, filename)

                        # Convert if needed
                        if self.convert_to_png and image['format'] != 'PNG':
                            img = Image.open(io.BytesIO(image_bytes))
                            img.save(filepath, format='PNG')
                        else:
                            with open(filepath, 'wb') as f:
                                f.write(image_bytes)

                        # Update image metadata with path
                        image['path'] = os.path.relpath(filepath, output_dir).replace('\\', '/')
                        image_path_map[image['path']] = image

                    except Exception as e:
                        self.logger.error(f"Error saving image {i} in section {section_title}: {e}")

                # Process subsections
                if 'subsections' in section and section['subsections']:
                    process_sections(section['subsections'], section_path_prefix)

        # Process TOC sections
        process_sections(toc_structure.get('toc', []))

        # Process non_toc sections
        if 'non_toc' in toc_structure:
            # Create global directory for non_toc images
            os.makedirs(os.path.join(images_dir, 'global'), exist_ok=True)
            
            for section in toc_structure['non_toc']:
                if 'images' not in section or not section['images']:
                    continue

                for i, image in enumerate(section['images'], global_counter):
                    try:
                        image_bytes = image['bytes']

                        if self.convert_to_png:
                            output_format = 'PNG'
                            ext = 'png'
                        else:
                            output_format = image['format']
                            ext = image['format'].lower()

                        filename = f"image_{i:03d}.{ext}"
                        filepath = os.path.join(images_dir, 'global', filename)

                        if self.convert_to_png and image['format'] != 'PNG':
                            img = Image.open(io.BytesIO(image_bytes))
                            img.save(filepath, format='PNG')
                        else:
                            with open(filepath, 'wb') as f:
                                f.write(image_bytes)

                        image['path'] = os.path.relpath(filepath, output_dir).replace('\\', '/')
                        image_path_map[image['path']] = image
                        global_counter += 1

                    except Exception as e:
                        self.logger.error(f"Error saving non_toc image {i}: {e}")

        self.logger.info(f"Saved {len(image_path_map)} images to {images_dir}")
        return image_path_map

    def extract_captions(self, toc_structure: Dict[str, Any], pdf_path: str) -> Dict[str, Any]:
        """
        Extract heuristic captions for images (text below images).

        Args:
            toc_structure: Dictionary with 'toc' and 'non_toc' keys
            pdf_path: Path to the PDF file

        Returns:
            Updated toc_structure with caption_candidate added to images
        """
        if not Path(pdf_path).exists():
            return toc_structure

        try:
            doc = fitz.open(pdf_path)

            def process_sections(sections):
                for section in sections:
                    if 'images' not in section or not section['images']:
                        if 'subsections' in section and section['subsections']:
                            process_sections(section['subsections'])
                        continue

                    for image in section['images']:
                        page_num = image['page'] - 1  # Convert to 0-indexed
                        if page_num >= len(doc):
                            continue

                        page = doc[page_num]
                        bbox = image['bbox']

                        # Expand bbox downward by 20px for caption area
                        caption_bbox = [bbox[0], bbox[3], bbox[2], bbox[3] + 20]

                        # Extract text in caption area
                        try:
                            caption_text = page.get_text("text", clip=caption_bbox).strip()
                            if caption_text:
                                image['caption_candidate'] = caption_text
                        except:
                            pass

                    if 'subsections' in section and section['subsections']:
                        process_sections(section['subsections'])

            process_sections(toc_structure.get('toc', []))

            if 'non_toc' in toc_structure:
                for section in toc_structure['non_toc']:
                    if 'images' not in section or not section['images']:
                        continue

                    for image in section['images']:
                        page_num = image['page'] - 1
                        if page_num >= len(doc):
                            continue

                        page = doc[page_num]
                        bbox = image['bbox']
                        caption_bbox = [bbox[0], bbox[3], bbox[2], bbox[3] + 20]

                        try:
                            caption_text = page.get_text("text", clip=caption_bbox).strip()
                            if caption_text:
                                image['caption_candidate'] = caption_text
                        except:
                            pass

            doc.close()
            self.logger.info("Successfully extracted image captions")
            return toc_structure

        except Exception as e:
            self.logger.error(f"Error extracting captions: {e}")
            return toc_structure