import urllib.request
import cairosvg
import os

icons = {
    'failed': ('circle-x', '#ef4444', 'fill_circle'),
    'load': ('folder-open', '#1e293b', 'fill'),
    'pause': ('pause', '#f59e0b', 'fill_no_stroke'),
    'pending': ('clock', '#64748b', 'fill_circle'),
    'restart': ('refresh-cw', '#3b82f6', 'stroke_only'),
    'resume': ('play', '#10b981', 'fill_no_stroke'),
    'run': ('play', '#10b981', 'fill_no_stroke'),
    'running': ('loader', '#3b82f6', 'stroke_only'),
    'save': ('save', '#1e293b', 'fill'),
    'success': ('badge-check', '#10b981', 'fill_circle'),
}

for name, (lucide_name, color, style) in icons.items():
    url = f"https://unpkg.com/lucide-static@latest/icons/{lucide_name}.svg"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            svg_data = response.read().decode('utf-8')
        
        # Apply styles
        if style == 'fill_circle':
            # fill the whole icon color, stroke white
            svg_data = svg_data.replace('fill="none"', f'fill="{color}"')
            svg_data = svg_data.replace('stroke="currentColor"', 'stroke="#ffffff"')
        elif style == 'fill':
            svg_data = svg_data.replace('fill="none"', f'fill="{color}"')
            svg_data = svg_data.replace('stroke="currentColor"', 'stroke="#ffffff"')
        elif style == 'fill_no_stroke':
            svg_data = svg_data.replace('fill="none"', f'fill="{color}"')
            svg_data = svg_data.replace('stroke="currentColor"', 'stroke="none"')
            # Also need to make sure the paths that are strokes get some thickness or it's a polygon
        elif style == 'stroke_only':
            svg_data = svg_data.replace('stroke="currentColor"', f'stroke="{color}"')
            
        out_path = f"ui/icons/{name}.png"
        cairosvg.svg2png(bytestring=svg_data.encode('utf-8'), write_to=out_path, output_width=20, output_height=20)
        print(f"Downloaded and converted {lucide_name} to {name}.png with style {style}")
    except Exception as e:
        print(f"Failed to process {name}: {e}")
