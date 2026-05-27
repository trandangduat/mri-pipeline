#!/usr/bin/env python3
import sys, os, csv

def main():
    if len(sys.argv) != 4:
        print("Usage: normalize_volumes.py <input_csv> <out_subcortical_tsv> <out_cortical_tsv>")
        sys.exit(2)

    input_csv, out_sub, out_cort = sys.argv[1], sys.argv[2], sys.argv[3]
    
    if not os.path.exists(input_csv):
        sys.exit(2)

    with open(input_csv, 'r') as f:
        reader = csv.reader(f)
        rows = list(reader)

    if not rows: sys.exit(2)

    header = rows[0]
    values = rows[1] if len(rows) > 1 else []

    # Ghi file subcortical_volume.tsv
    with open(out_sub, 'w', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(['Structure', 'Volume_mm3'])
        for h, v in zip(header, values):
            if 'cortex' not in h.lower():
                writer.writerow([h, v])

    with open(out_cort, 'w', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(['Structure', 'Volume_mm3'])
        for h, v in zip(header, values):
            if 'cortex' in h.lower():
                writer.writerow([h, v])

if __name__ == "__main__":
    main()
