"""Record the immutable image selected for a processing container."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import threading

from .win_process import no_window_kwargs

_inventory_lock = threading.Lock()


def prepare_image_receipt(image: str, container: str, receipt_path: str) -> dict:
    query = subprocess.run(['docker', 'image', 'inspect', image], capture_output=True,
                           text=True, timeout=15, **no_window_kwargs())
    if query.returncode:
        raise RuntimeError('Cannot record Docker image identity: ' + query.stderr.strip())
    inspected = json.loads(query.stdout)
    if len(inspected) != 1 or not inspected[0].get('Id', '').startswith('sha256:'):
        raise RuntimeError('Docker image inspection did not identify one immutable image')
    value = inspected[0]
    receipt = {'requested_image': image, 'image_id': value['Id'],
               'repository_digests': value.get('RepoDigests') or [],
               'container_name': container, 'selection_mode': 'PINNED_IMAGE_ID',
               'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'status': 'PREPARED'}
    save_image_receipt(receipt_path, receipt)
    return receipt


def save_image_receipt(receipt_path: str, receipt: dict) -> None:
    path = Path(receipt_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _inventory_lock:
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
        temporary.replace(path)
        records = [json.loads(p.read_text(encoding='utf-8')) for p in sorted(path.parent.glob('*.json'))]
        lines = ['requested_image\timage_id\trepository_digests\tcontainer_name\tstatus']
        lines.extend('\t'.join([r['requested_image'], r['image_id'], ';'.join(r['repository_digests']),
                               r['container_name'], r['status']]) for r in records)
        inventory = path.parent.parent / 'container_images.txt'
        temporary_inventory = inventory.with_suffix('.txt.tmp')
        temporary_inventory.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        temporary_inventory.replace(inventory)
