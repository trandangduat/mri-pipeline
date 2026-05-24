# Phân Công Công Việc Nhóm 3 Người

## Điều Chỉnh Quan Trọng Về Dependency

Phân công cũ có một vấn đề: một số công cụ bị chia sai theo tên bước pipeline thay vì chia theo dependency.

Cần sửa lại như sau:

- `SynthStrip` là công cụ thuộc hệ sinh thái FreeSurfer, thường chạy bằng lệnh `mri_synthstrip`. Vì vậy không nên giao `SynthStrip` cho người khác tách khỏi FreeSurfer.
- `mri_convert` cũng thuộc FreeSurfer.
- `SynthSeg` có 2 hướng chạy khác nhau:
  - Chạy qua FreeSurfer bằng lệnh `mri_synthseg`.
  - Chạy bằng repo/package SynthSeg standalone riêng.
- Vì vậy cần tách rõ `SynthSeg FreeSurfer` và `SynthSeg standalone`, không gọi chung chung là `SynthSeg`.

Nguyên tắc mới: **chia việc theo software stack/dependency**, không chia đơn thuần theo bước pipeline.

## Mục Tiêu Giai Đoạn Hiện Tại

Nhóm tập trung đóng gói các công cụ thành Docker image chạy độc lập trước. Sau khi image ổn định mới tích hợp backend pipeline và GUI.

Các output quan trọng cần sinh thật:

- `subcortical_volume.tsv`
- `cortical_volume.tsv`

Hai file này có thể sinh từ:

- `mri_synthseg` trong FreeSurfer.
- SynthSeg standalone.
- FastSurferVINN.

## Contract Chung Cho Mọi Image

Tất cả image phải tuân thủ contract chung để sau này backend gọi dễ dàng.

### Volume Mount Chuẩn

```bash
-v /host/input:/input
-v /host/output:/output
-v /host/work:/work
```

Nếu cần license, ví dụ FreeSurfer/FastSurfer:

```bash
-v /host/license:/license
```

### Command Chuẩn

Mỗi image cần có wrapper `run_tool`:

```bash
run_tool \
  --input /input/sub-001_T1w.nii.gz \
  --output-dir /output/sub-001 \
  --work-dir /work/sub-001 \
  --subject-id sub-001 \
  --threads 8 \
  --device cpu
```

Nếu chạy GPU:

```bash
docker run --rm --gpus all ...
```

### Output Chuẩn

```text
outputs/
└── sub-001/
    ├── logs/
    │   └── <tool_name>.log
    ├── work/
    │   └── <tool_output_files>
    └── stats/
        ├── subcortical_volume.tsv
        └── cortical_volume.tsv
```

### Exit Code Chuẩn

```text
0: chạy thành công
1: lỗi input hoặc config
2: lỗi khi chạy tool
3: tool chạy xong nhưng thiếu output bắt buộc
```

## Cách Chia Việc Để Không Bị Chờ Nhau

Không chia `FreeSurfer`, `SynthStrip`, `mri_convert`, `mri_synthseg` cho nhiều người khác nhau. Tất cả phần phụ thuộc FreeSurfer phải do một người sở hữu.

Mỗi thành viên sở hữu một software stack độc lập:

- Thành viên 1: FreeSurfer stack.
- Thành viên 2: Standalone segmentation stack.
- Thành viên 3: Non-FreeSurfer preprocessing stack.

Cách chia này giúp mỗi người có thể build, test, viết README và debug tool của mình độc lập.

## Thành Viên 1: FreeSurfer Stack

Người phụ trách: `Baor`

### Phạm vi phụ trách

Toàn bộ công cụ phụ thuộc FreeSurfer:

- `mri_convert`
- `mri_synthstrip`
- `mri_synthseg`
- Talairach/template registration nếu nhóm dùng FreeSurfer cho bước registration

### Lý do gom vào một người

Các công cụ này đều phụ thuộc FreeSurfer, cùng cần xử lý license, biến môi trường `FREESURFER_HOME`, `SUBJECTS_DIR`, cùng kiểu mount dữ liệu và cùng base image. Nếu chia cho nhiều người thì sẽ bị trùng Dockerfile, trùng license handling và dễ lệch command.

### Cấu trúc thư mục

```text
docker/freesurfer-base/
├── Dockerfile
└── README.md

docker/freesurfer-mri-convert/
├── Dockerfile
├── run_tool.py
├── README.md
└── test_mri_convert.sh

docker/freesurfer-synthstrip/
├── Dockerfile
├── run_tool.py
├── README.md
└── test_synthstrip.sh

docker/freesurfer-synthseg/
├── Dockerfile
├── run_tool.py
├── normalize_volumes.py
├── README.md
└── test_synthseg_freesurfer.sh
```

Các image có thể cùng dùng base image `mri-freesurfer-base:latest`, nhưng vẫn có wrapper riêng cho từng tool.

### Tên image cần build

```text
mri-freesurfer-base:latest
mri-mri-convert:latest
mri-synthstrip:latest
mri-synthseg-freesurfer:latest
```

### Output bắt buộc

`mri_convert`:

```text
outputs_test/member1/sub-001/work/01_reoriented.nii.gz
outputs_test/member1/sub-001/logs/mri_convert.log
```

`mri_synthstrip`:

```text
outputs_test/member1/sub-001/work/02_synthstrip_brain.nii.gz
outputs_test/member1/sub-001/work/02_synthstrip_brain_mask.nii.gz
outputs_test/member1/sub-001/logs/synthstrip.log
```

`mri_synthseg`:

```text
outputs_test/member1/sub-001/work/03_freesurfer_synthseg_segmentation.nii.gz
outputs_test/member1/sub-001/work/03_freesurfer_synthseg_volumes.tsv
outputs_test/member1/sub-001/stats/subcortical_volume.tsv
outputs_test/member1/sub-001/stats/cortical_volume.tsv
outputs_test/member1/sub-001/logs/synthseg_freesurfer.log
```

### Test command mẫu

```bash
docker run --rm \
  -v ./data:/input \
  -v ./outputs_test/member1:/output \
  -v ./work/member1:/work \
  -v ./license:/license \
  mri-synthstrip:latest \
  run_tool \
  --input /input/sub-001_T1w.nii.gz \
  --output-dir /output/sub-001 \
  --work-dir /work/sub-001 \
  --subject-id sub-001 \
  --threads 8 \
  --device cpu
```

### Sản phẩm bàn giao

- FreeSurfer base image.
- Image `mri-mri-convert:latest`.
- Image `mri-synthstrip:latest`.
- Image `mri-synthseg-freesurfer:latest`.
- License handling rõ ràng.
- README cho từng image.
- Test script cho từng image.
- TSV volume chuẩn hóa từ `mri_synthseg` nếu output tool hỗ trợ.

## Thành Viên 2: Standalone Segmentation Stack

Người phụ trách: `duaajt`

### Phạm vi phụ trách

Các công cụ segmentation không phụ thuộc trực tiếp vào FreeSurfer stack của thành viên 1:

- SynthSeg standalone từ repo/package riêng.
- FastSurferVINN.
- Normalize volume output từ hai tool này.

### Lý do phân công

Thành viên 2 tập trung vào nhóm tool sinh volume thật nhưng không đụng vào FreeSurfer image của thành viên 1. Đây là hướng độc lập để so sánh với `mri_synthseg` của FreeSurfer.

### Cấu trúc thư mục

```text
docker/synthseg-standalone/
├── Dockerfile
├── run_tool.py
├── normalize_volumes.py
├── README.md
└── test_synthseg_standalone.sh

docker/fastsurfervinn/
├── Dockerfile
├── run_tool.py
├── normalize_volumes.py
├── README.md
└── test_fastsurfervinn.sh
```

### Tên image cần build

```text
mri-synthseg-standalone:latest
mri-fastsurfervinn:latest
```

### Output bắt buộc

SynthSeg standalone:

```text
outputs_test/member2/sub-001/work/03_synthseg_standalone_segmentation.nii.gz
outputs_test/member2/sub-001/work/03_synthseg_standalone_volumes.tsv
outputs_test/member2/sub-001/stats/subcortical_volume.tsv
outputs_test/member2/sub-001/stats/cortical_volume.tsv
outputs_test/member2/sub-001/logs/synthseg_standalone.log
```

FastSurferVINN:

```text
outputs_test/member2/sub-001/work/03_fastsurfervinn_segmentation.nii.gz
outputs_test/member2/sub-001/work/03_fastsurfervinn_volumes.tsv
outputs_test/member2/sub-001/stats/subcortical_volume.tsv
outputs_test/member2/sub-001/stats/cortical_volume.tsv
outputs_test/member2/sub-001/logs/fastsurfervinn.log
```

### Format TSV chuẩn

`subcortical_volume.tsv`:

```tsv
subject	structure	volume_mm3	tool
sub-001	Left-Hippocampus	3821	SynthSegStandalone
sub-001	Right-Hippocampus	3764	SynthSegStandalone
```

`cortical_volume.tsv`:

```tsv
subject	region	hemisphere	volume_mm3	tool
sub-001	superiorfrontal	lh	15432	FastSurferVINN
sub-001	superiorfrontal	rh	14987	FastSurferVINN
```

### Test command mẫu

```bash
docker run --rm \
  -v ./data:/input \
  -v ./outputs_test/member2:/output \
  -v ./work/member2:/work \
  mri-synthseg-standalone:latest \
  run_tool \
  --input /input/sub-001_T1w.nii.gz \
  --output-dir /output/sub-001 \
  --work-dir /work/sub-001 \
  --subject-id sub-001 \
  --threads 8 \
  --device cpu
```

Nếu FastSurferVINN cần license hoặc GPU, README phải ghi rõ:

```bash
-v ./license:/license
--gpus all
```

### Sản phẩm bàn giao

- Image `mri-synthseg-standalone:latest`.
- Image `mri-fastsurfervinn:latest`.
- Script normalize volume cho từng tool.
- TSV volume thật từ ít nhất một trong hai tool.
- README và test script đầy đủ.

## Thành Viên 3: Non-FreeSurfer Preprocessing Stack

Người phụ trách: `khang`

### Phạm vi phụ trách

Các công cụ preprocessing không phụ thuộc FreeSurfer:

- NiBabel utilities cho reorientation/resize fallback.
- HD-BET.
- ANTs `N4BiasFieldCorrection` hoặc `N3BiasFieldCorrection`.
- ANTs registration nếu nhóm chọn hướng registration không dùng FreeSurfer.

### Lý do phân công

Thành viên 3 không phụ trách `SynthStrip` nữa vì `SynthStrip` nằm trong FreeSurfer stack. Như vậy thành viên 3 có thể làm độc lập bằng các công cụ non-FreeSurfer, không đụng base image/license của thành viên 1.

### Cấu trúc thư mục

```text
docker/nibabel-utils/
├── Dockerfile
├── run_tool.py
├── README.md
└── test_nibabel_utils.sh

docker/hdbet/
├── Dockerfile
├── run_tool.py
├── README.md
└── test_hdbet.sh

docker/ants/
├── Dockerfile
├── run_tool.py
├── README.md
└── test_ants.sh
```

### Tên image cần build

```text
mri-nibabel-utils:latest
mri-hdbet:latest
mri-ants:latest
```

### Output bắt buộc

NiBabel reorientation/resize fallback:

```text
outputs_test/member3/sub-001/work/01_nibabel_reoriented.nii.gz
outputs_test/member3/sub-001/logs/nibabel_utils.log
```

HD-BET:

```text
outputs_test/member3/sub-001/work/02_hdbet_brain.nii.gz
outputs_test/member3/sub-001/work/02_hdbet_brain_mask.nii.gz
outputs_test/member3/sub-001/logs/hdbet.log
```

ANTs N4/N3:

```text
outputs_test/member3/sub-001/work/05_standardized.nii.gz
outputs_test/member3/sub-001/logs/ants_n4.log
```

ANTs registration nếu làm trong giai đoạn này:

```text
outputs_test/member3/sub-001/work/04_registered.nii.gz
outputs_test/member3/sub-001/logs/ants_registration.log
```

### Test command mẫu

```bash
docker run --rm \
  -v ./data:/input \
  -v ./outputs_test/member3:/output \
  -v ./work/member3:/work \
  mri-ants:latest \
  run_tool \
  --input /input/sub-001_T1w.nii.gz \
  --output-dir /output/sub-001 \
  --work-dir /work/sub-001 \
  --subject-id sub-001 \
  --threads 8 \
  --device cpu
```

### Sản phẩm bàn giao

- Image `mri-nibabel-utils:latest`.
- Image `mri-hdbet:latest`.
- Image `mri-ants:latest`.
- Brain extraction output từ HD-BET.
- Standardized image từ ANTs N4/N3.
- Registration output nếu nhóm chọn ANTs registration.
- README và test script đầy đủ.

## Timeline Làm Song Song

### Ngày 1: Skeleton Docker

- Thành viên 1: tạo skeleton FreeSurfer base, mri_convert, synthstrip, synthseg FreeSurfer.
- Thành viên 2: tạo skeleton SynthSeg standalone và FastSurferVINN.
- Thành viên 3: tạo skeleton NiBabel, HD-BET, ANTs.

### Ngày 2: Build Image Và Chạy Help

- Thành viên 1: build FreeSurfer stack và chạy `mri_convert --help`, `mri_synthstrip --help`, `mri_synthseg --help` nếu tool hỗ trợ.
- Thành viên 2: build SynthSeg standalone/FastSurferVINN và chạy help/test nhỏ.
- Thành viên 3: build NiBabel/HD-BET/ANTs và chạy help/test nhỏ.

### Ngày 3: Chạy Với MRI Test Thật

- Thành viên 1: chạy FreeSurfer stack với `data/sub-001_T1w.nii.gz`.
- Thành viên 2: chạy standalone segmentation stack với `data/sub-001_T1w.nii.gz`.
- Thành viên 3: chạy non-FreeSurfer preprocessing stack với `data/sub-001_T1w.nii.gz`.

### Ngày 4: Chuẩn Hóa Output Và Log

- Thành viên 1: chuẩn hóa output FreeSurfer stack.
- Thành viên 2: chuẩn hóa TSV volume từ SynthSeg standalone/FastSurferVINN.
- Thành viên 3: chuẩn hóa output preprocessing non-FreeSurfer.

### Ngày 5: Review Chéo

- Thành viên 1 test image của thành viên 2.
- Thành viên 2 test image của thành viên 3.
- Thành viên 3 test image của thành viên 1.

## Quy Định Để Không Bị Chồng Việc

- Thành viên 3 không làm `SynthStrip`; `SynthStrip` thuộc FreeSurfer stack của thành viên 1.
- Thành viên 1 không làm SynthSeg standalone; thành viên 1 chỉ làm `mri_synthseg` trong FreeSurfer.
- Thành viên 2 không sửa FreeSurfer base image của thành viên 1.
- Nếu cần đổi contract chung, cả nhóm thống nhất trước rồi từng người tự sửa image của mình.
- Mỗi người test output trong thư mục riêng:
  - `outputs_test/member1/`
  - `outputs_test/member2/`
  - `outputs_test/member3/`
- `build_all.sh`, `test_all.sh`, backend orchestrator và GUI chỉ làm sau khi từng stack chạy độc lập.

## Checklist Cuối Giai Đoạn Đóng Gói

- Thành viên 1 có FreeSurfer stack chạy được.
- Thành viên 1 có `mri_synthstrip` chạy được.
- Thành viên 1 có `mri_synthseg` chạy được hoặc ghi rõ blocker.
- Thành viên 2 có SynthSeg standalone hoặc FastSurferVINN chạy được.
- Thành viên 2 sinh được TSV volume thật từ ít nhất một tool.
- Thành viên 3 có HD-BET chạy được hoặc ghi rõ blocker.
- Thành viên 3 có ANTs N4/N3 chạy được.
- Mỗi stack có README và test script.
- Mỗi stack ghi log đúng thư mục.
- Có ít nhất một `subcortical_volume.tsv` thật.
- Có ít nhất một `cortical_volume.tsv` thật.

## Sau Khi Đóng Gói Xong

Sau khi các stack đã ổn định, nhóm mới chuyển sang:

1. Viết backend Docker runner.
2. Viết pipeline orchestrator gọi từng image theo lựa chọn tool.
3. Viết CLI chạy end-to-end.
4. Nối GUI với backend.
5. Đóng gói phần mềm hoàn chỉnh.

Kết luận: phân công theo dependency stack sẽ tránh việc thành viên 1 và thành viên 3 cùng đụng FreeSurfer. Đây là cách chia hợp lý hơn cho giai đoạn đóng gói công cụ.
