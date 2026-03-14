"""
Generate PNG from PlantUML ERD diagram.

Uses PlantUML web service to render the diagram.
"""
import sys
import urllib.parse
import requests

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

def generate_png_from_plantuml(puml_file: str, output_file: str):
    """Generate PNG from PlantUML file using web service."""
    try:
        import zlib
        import base64
        
        # Read PlantUML source
        with open(puml_file, 'r', encoding='utf-8') as f:
            puml_source = f.read()
        
        print(f"📄 Read PlantUML source from: {puml_file}")
        print(f"📊 Source length: {len(puml_source)} characters")
        
        # PlantUML encoding: deflate + base64 with URL-safe characters
        compressed = zlib.compress(puml_source.encode('utf-8'))
        encoded = base64.b64encode(compressed).decode('utf-8')
        # Replace URL-unsafe characters
        encoded = encoded.replace('+', '-').replace('/', '_')
        
        # PlantUML web service URL
        # Format: http://www.plantuml.com/plantuml/png/<encoded_source>
        url = f"http://www.plantuml.com/plantuml/png/{encoded}"
        
        print(f"🌐 Requesting PNG from PlantUML web service...")
        print(f"   Encoded length: {len(encoded)} characters")
        
        # Request PNG
        response = requests.get(url, timeout=30)
        
        if response.status_code == 200:
            # Save PNG
            with open(output_file, 'wb') as f:
                f.write(response.content)
            
            file_size = len(response.content)
            print(f"✅ Successfully generated PNG: {output_file}")
            print(f"   File size: {file_size:,} bytes ({file_size / 1024:.2f} KB)")
            return True
        else:
            print(f"❌ Error: HTTP {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    puml_file = "docs/erd.puml"
    output_file = "docs/erd.png"
    
    print("=" * 60)
    print("PlantUML ERD PNG Generator")
    print("=" * 60)
    
    success = generate_png_from_plantuml(puml_file, output_file)
    
    if success:
        print("\n✅ ERD PNG generated successfully!")
        print(f"   View: {output_file}")
    else:
        print("\n❌ Failed to generate ERD PNG")
        print("   You can view the PlantUML source in VS Code with PlantUML extension")
        print("   or use an online PlantUML viewer: http://www.plantuml.com/plantuml/uml/")
        sys.exit(1)

