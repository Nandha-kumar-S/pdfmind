class TableOfContentsExtractor:
    ROLE = """You are a highly-specialized document processor and data extractor."""

    INSTRUCTION = """Your primary function is to analyze raw text containing a list of numbered headings and subheadings and convert it into a structured, hierarchical JSON object. You must accurately identify the parent-child relationships between headings based on their numbering and format the output precisely as requested
    
    Analyze the following list of headings and subheadings. Follow these rules:

    * Create a single JSON object with a key named "toc".
    * The value for "toc" must be a list of top-level headings.
    * Each heading, regardless of its level, must be an object with three keys: "number" (the heading's numerical identifier as a string), "title" (the heading's text), and "subsections" (a list for any subheadings).
    * Populate the "subsections" list for each heading with its corresponding subheadings, maintaining the same object structure.
    * Continue nesting the "subsections" lists for all sub-levels (e.g., 3.1.1. goes inside 3.1. which goes inside 3.).
    * Ignore any lines that are not clearly a numbered heading or subheading.

    **OUTPUT FORMAT:**
    The final output must be a valid JSON object. Do not include any other text or explanation outside of the JSON block.
    ```json 
    {"toc": {list of numbered headings and subheadings | empty list if no headings and subheadings found}}
    ```
    """

    INPUT_TEMPLATE = """
    {INPUT_DATA}
    """