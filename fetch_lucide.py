import urllib.request
import cairosvg
import os

icons = {
    'failed': ('circle-x', '#ef4444'),
    'load': ('folder-open', '#1e293b'),
    'pause': ('pause', '#f59e0b'),
    'pending': ('clock', '#64748b'),
    'restart': ('refresh-cw', '#3b82f6'),
    'resume': ('play', '#10b981'),
    'run': ('play', '#10b981'),
    'running': ('loader', '#3b82f6'),
    'save': ('save', '#1e293b'),
    'success': ('circle-check', '#10b981'),
}

for name, (lucide_name, color) in icons.items():
    url = f"https://unpkg.com/lucide-static@latest/icons/{lucide_name}.svg"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            svg_data = response.read().decode('utf-8')
        
        # Replace currentColor with our desired color
        svg_data = svg_data.replace('currentColor', color)
        
        # Save as PNG
        out_path = f"ui/icons/{name}.png"
        cairosvg.svg2png(bytestring=svg_data.encode('utf-8'), write_to=out_path, output_width=20, output_height=20)
        print(f"Downloaded and converted {lucide_name} to {name}.png")
    except Exception as e:
        print(f"Failed to process {name}: {e}")
