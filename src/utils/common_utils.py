import json
import os
import logging

from pdfmind.prompts import TableOfContentsExtractor

logger = logging.getLogger(__name__)

def get_prompt(prompt_class, input_data = None):
    class_ref = globals()[prompt_class]
    role = getattr(class_ref, 'ROLE', '')
    instruction = getattr(class_ref, 'INSTRUCTION', '')
    input_template = getattr(class_ref, 'INPUT_TEMPLATE', '')

    if input_data is not None:
        # Check if the input is a dictionary or a string
        if isinstance(input_data, dict):
            # If it's a dict, use it directly
            input_dict = input_data
        else:
            # If it's a string, wrap it in the default dictionary structure
            input_dict = {'INPUT_DATA': input_data}

        prompt = f"""{role}
        ### INSTRUCTION: 
        {instruction}
        ### INPUT: 
        {input_template.format(**input_dict)}
        ### OUTPUT:
        """
    else:
        prompt = f"""{role}
        ### INSTRUCTION: 
        {instruction}
        ### OUTPUT:
        """
    return prompt

def save_file(data, output_dir, filename, file_type='json', ensure_ascii=False):
    try:
        os.makedirs(output_dir, exist_ok=True)
        file_path = os.path.join(output_dir, filename)
        
        if file_type == 'json':
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=ensure_ascii)
        elif file_type == 'markdown':
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(str(data))
        else:
            raise ValueError(f"Unsupported file type: {file_type}")

        logger.info(f"Successfully saved data to: {file_path}")
        return file_path
        
    except Exception as e:
        logger.error(f"Failed to save data to {filename}: {str(e)}")
        raise
