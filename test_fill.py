import urllib.request
import cairosvg

url = "https://unpkg.com/lucide-static@latest/icons/circle-check.svg"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as response:
    svg_data = response.read().decode('utf-8')

# original: fill="none" stroke="currentColor"
# new: fill="currentColor" stroke="#ffffff"
color = "#10b981"
svg_data = svg_data.replace('fill="none"', f'fill="{color}"')
svg_data = svg_data.replace('stroke="currentColor"', 'stroke="#ffffff"')

out_path = "test_circle_check.png"
cairosvg.svg2png(bytestring=svg_data.encode('utf-8'), write_to=out_path, output_width=20, output_height=20)
print("Saved to", out_path)
