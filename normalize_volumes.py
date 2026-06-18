#!/usr/bin/env python3
import sys, os, csv


SUBCORTICAL_STRUCTURES = [
    "total intracranial", "left cerebral white matter", "left lateral ventricle",
    "left inferior lateral ventricle", "left cerebellum white matter",
    "left thalamus", "left caudate", "left putamen", "left pallidum",
    "3rd ventricle", "4th ventricle", "brain-stem", "left hippocampus",
    "left amygdala", "csf", "left accumbens area", "left ventral DC",
    "right cerebral white matter", "right lateral ventricle",
    "right inferior lateral ventricle", "right cerebellum white matter",
    "right thalamus", "right caudate", "right putamen", "right pallidum",
    "right hippocampus", "right amygdala", "right accumbens area",
    "right ventral DC"
]


def main():
    if len(sys.argv) != 6:
        print("Usage: normalize_volumes.py <input_csv> <out_subcortical_tsv> <out_cortical_tsv> <subject_id> <tool>")
        sys.exit(2)

    input_csv, out_sub, out_cort, subject_id, tool = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]

    if not os.path.exists(input_csv):
        sys.exit(2)

    with open(input_csv, 'r') as f:
        reader = csv.reader(f)
        rows = list(reader)

    if not rows:
        sys.exit(2)

    header = rows[0]
    values = rows[1] if len(rows) > 1 else []

    # Skip first column (subject)
    structures = header[1:]
    volumes = values[1:] if len(values) > 1 else []

    with open(out_sub, 'w', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(['subject', 'structure', 'volume_mm3', 'tool'])
        for s, v in zip(structures, volumes):
            if s.lower() in SUBCORTICAL_STRUCTURES:
                writer.writerow([subject_id, s, v, tool])

    with open(out_cort, 'w', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(['subject', 'region', 'hemisphere', 'volume_mm3', 'tool'])
        for s, v in zip(structures, volumes):
            if s.lower() not in SUBCORTICAL_STRUCTURES:
                if s.startswith("left "):
                    region = s[5:]
                    writer.writerow([subject_id, region, "lh", v, tool])
                elif s.startswith("right "):
                    region = s[6:]
                    writer.writerow([subject_id, region, "rh", v, tool])
                else:
                    writer.writerow([subject_id, s, "both", v, tool])


if __name__ == "__main__":
    main()
