import urllib.request

def fetch(i8_name, name, color):
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

fetch('multiply', 'failed', 'ef4444')
