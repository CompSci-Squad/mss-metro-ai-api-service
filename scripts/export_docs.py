#!/usr/bin/env python3
"""
Script to export FastAPI documentation to various formats.
Usage: python scripts/export_docs.py
"""

import json
import sys
from pathlib import Path

# Add project root to path to import app
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Output directory for documentation
DOCS_DIR = project_root / "docs" / "api"


def ensure_docs_dir():
    """Create docs directory if it doesn't exist"""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"📁 Output directory: {DOCS_DIR.absolute()}\n")


def export_openapi_json():
    """Export OpenAPI schema as JSON"""
    from app.main import app
    
    openapi_schema = app.openapi()
    
    output_file = DOCS_DIR / "openapi.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(openapi_schema, f, indent=2, ensure_ascii=False)
    
    print(f"✓ OpenAPI JSON exported to: {output_file.absolute()}")
    return output_file


def export_openapi_yaml():
    """Export OpenAPI schema as YAML"""
    try:
        import yaml
    except ImportError:
        print("⚠ PyYAML not installed. Install with: pip install pyyaml")
        return None
    
    from app.main import app
    
    openapi_schema = app.openapi()
    
    output_file = DOCS_DIR / "openapi.yaml"
    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(openapi_schema, f, sort_keys=False, allow_unicode=True)
    
    print(f"✓ OpenAPI YAML exported to: {output_file.absolute()}")
    return output_file


def export_redoc_html():
    """Export standalone ReDoc HTML"""
    from app.main import app
    
    openapi_schema = app.openapi()
    openapi_json = json.dumps(openapi_schema, ensure_ascii=False)
    
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>{app.title} - API Documentation</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
    <style>
        body {{
            margin: 0;
            padding: 0;
        }}
    </style>
</head>
<body>
    <redoc spec-url='#'></redoc>
    <script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
    <script>
        const spec = {openapi_json};
        Redoc.init(spec, {{}}, document.querySelector('redoc'));
    </script>
</body>
</html>
"""
    
    output_file = DOCS_DIR / "index.html"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"✓ ReDoc HTML exported to: {output_file.absolute()}")
    return output_file


def export_swagger_html():
    """Export standalone Swagger UI HTML"""
    from app.main import app
    
    openapi_schema = app.openapi()
    openapi_json = json.dumps(openapi_schema, ensure_ascii=False)
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{app.title} - Swagger UI</title>
    <link rel="stylesheet" type="text/css" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css" />
    <style>
        html {{
            box-sizing: border-box;
            overflow: -moz-scrollbars-vertical;
            overflow-y: scroll;
        }}
        *, *:before, *:after {{
            box-sizing: inherit;
        }}
        body {{
            margin: 0;
            padding: 0;
        }}
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-standalone-preset.js"></script>
    <script>
        window.onload = function() {{
            const spec = {openapi_json};
            
            window.ui = SwaggerUIBundle({{
                spec: spec,
                dom_id: '#swagger-ui',
                deepLinking: true,
                presets: [
                    SwaggerUIBundle.presets.apis,
                    SwaggerUIStandalonePreset
                ],
                plugins: [
                    SwaggerUIBundle.plugins.DownloadUrl
                ],
                layout: "StandaloneLayout"
            }});
        }};
    </script>
</body>
</html>
"""
    
    output_file = DOCS_DIR / "swagger.html"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"✓ Swagger UI HTML exported to: {output_file.absolute()}")
    return output_file


def main():
    print("=" * 60)
    print("VIRAG-BIM API Documentation Exporter")
    print("=" * 60)
    print()
    
    # Ensure output directory exists
    ensure_docs_dir()
    
    # Export all formats
    print("Exporting documentation...")
    print()
    
    export_openapi_json()
    export_openapi_yaml()
    export_redoc_html()
    export_swagger_html()
    
    print()
    print("=" * 60)
    print("Export completed!")
    print("=" * 60)
    print()
    print("You can now share these files from docs/api/:")
    print("  • openapi.json    - OpenAPI JSON schema")
    print("  • openapi.yaml    - OpenAPI YAML schema")
    print("  • index.html      - Interactive ReDoc documentation (recommended)")
    print("  • swagger.html    - Interactive Swagger UI documentation")
    print()
    print("The HTML files are standalone and can be opened in any browser!")


if __name__ == "__main__":
    main()
