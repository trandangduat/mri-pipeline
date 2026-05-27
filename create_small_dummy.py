import nibabel as nib
import numpy as np

# Create a 64x64x64 volume of random noise (or just zeros with a sphere)
data = np.zeros((64, 64, 64), dtype=np.float32)
# Add some structure so segmentation doesn't completely fail (just in case)
data[16:48, 16:48, 16:48] = 100.0

affine = np.eye(4)
img = nib.Nifti1Image(data, affine)
nib.save(img, 'data/sub-003_small.nii.gz')
print("Created data/sub-003_small.nii.gz")
