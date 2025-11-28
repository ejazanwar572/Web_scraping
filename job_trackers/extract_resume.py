import pypdf
import sys
from pathlib import Path

def extract_text_from_pdf(pdf_path, output_path):
    try:
        reader = pypdf.PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        
        with open(output_path, "w") as f:
            f.write(text)
        print(f"Successfully extracted {len(text)} characters to {output_path}")
        return text
    except Exception as e:
        print(f"Error extracting text: {e}")
        return None

if __name__ == "__main__":
    # Adjust paths relative to where the script is run
    base_dir = Path(__file__).parent
    pdf_path = base_dir / "resume.pdf"
    output_path = base_dir / "resume_text.txt"
    
    if not pdf_path.exists():
        print(f"Error: {pdf_path} does not exist.")
        sys.exit(1)
        
    extract_text_from_pdf(str(pdf_path), str(output_path))
