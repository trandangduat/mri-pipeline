import urllib.request
import os

icons = {
    'failed': ('cancel', 'ef4444'),
    'download': ('download', '1e293b'),
    'load': ('opened-folder', '1e293b'),
    'pause': ('pause', 'f59e0b'),
    'pending': ('time', '64748b'),
    'pin': ('pin', '1e293b'),
    'restart': ('restart', '3b82f6'),
    'resume': ('play', '10b981'),
    'run': ('play', '10b981'),
    'running': ('loading', '3b82f6'),
    'running_light': ('loading', 'ffffff'),
    'save': ('save', '1e293b'),
    'success': ('ok', '10b981'),
    'trash': ('trash', '1e293b'),
}

for name, (i8_name, color) in icons.items():
    url = f"https://img.icons8.com/ios-filled/20/{color}/{i8_name}.png"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = response.read()
        
        out_path = f"ui/icons/{name}.png"
        with open(out_path, 'wb') as f:
            f.write(data)
        print(f"Downloaded {i8_name} to {name}.png")
    except Exception as e:
        print(f"Failed to process {name} ({i8_name}): {e}")
