"""
Script to generate PNG from Mermaid diagram.
Requires: pip install requests
"""
import requests
import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def generate_png_from_mermaid():
    """Generate PNG from Mermaid file using mermaid.ink API."""
    script_dir = Path(__file__).parent
    mmd_file = script_dir / "architecture.mmd"
    png_file = script_dir / "architecture.png"
    
    if not mmd_file.exists():
        print(f"Error: {mmd_file} not found")
        return False
    
    # Read Mermaid file
    with open(mmd_file, 'r', encoding='utf-8') as f:
        mermaid_code = f.read()
    
    try:
        # Convert to PNG via mermaid.ink API (base64 encoded)
        print("Generating PNG from Mermaid diagram...")
        import base64
        import urllib.parse
        
        # Encode mermaid code to base64
        mermaid_b64 = base64.b64encode(mermaid_code.encode('utf-8')).decode('utf-8')
        mermaid_url = urllib.parse.quote(mermaid_b64)
        
        # Try different API endpoints
        api_urls = [
            f'https://mermaid.ink/img/{mermaid_url}',
            f'https://mermaid.ink/img/svg/{mermaid_url}',
        ]
        
        response = None
        for url in api_urls:
            try:
                response = requests.get(url, timeout=30)
                if response.status_code == 200:
                    break
            except:
                continue
        
        if not response or response.status_code != 200:
            # Fallback: Try POST method
            response = requests.post(
                'https://mermaid.ink/img',
                json={'code': mermaid_code},
                timeout=30
            )
        
        if response.status_code == 200:
            # Save PNG
            with open(png_file, 'wb') as f:
                f.write(response.content)
            print(f"[OK] PNG generated successfully: {png_file}")
            return True
        else:
            print(f"[ERROR] API returned status {response.status_code}")
            print(f"Response: {response.text[:200]}")
            return False
    except Exception as e:
        print(f"[ERROR] Error generating PNG: {e}")
        print("\nAlternative: Use mermaid-cli or online tool (see README.md)")
        return False

if __name__ == "__main__":
    generate_png_from_mermaid()

