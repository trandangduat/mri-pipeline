# NeuroFLOW — Tổng hợp công cụ, atlas và chức năng

## Ký hiệu và thuật ngữ chuyên ngành

Bảng dưới đây giải thích các bộ công cụ, thuật ngữ chuyên biệt và viết tắt kỹ thuật trong hệ thống NeuroFLOW (đã tinh giản các thuật ngữ tin học và hình ảnh học phổ thông):

| Viết tắt | Tên đầy đủ / Công nghệ | Vai trò và ý nghĩa trong hệ thống |
|---|---|---|
| FS7 / FS8 | FreeSurfer 7 / FreeSurfer 8 | Hai thế hệ bộ công cụ FreeSurfer dùng trong pipeline; FS8 hỗ trợ mạng nơ-ron SynthSeg/SynthStrip/SynthMorph, FS7 sử dụng quy trình chuẩn recon-all. |
| CAT12 | Computational Anatomy Toolbox | Bộ công cụ phân tích hình thái dựa trên SPM/MATLAB, tính toán thể tích và độ dày vỏ não. |
| FastSurfer / VINN | FastSurfer / Voxel-size Independent Neural Network | Pipeline phân đoạn giải phẫu vỏ não và dưới vỏ tốc độ cao bằng học sâu, độc lập với kích thước voxel. |
| ANTs / N4 | Advanced Normalization Tools / N4ITK | Bộ thuật toán hiệu chỉnh độ không đồng nhất từ trường (bias field correction) và đăng ký ảnh. |
| HD-BET | High-Density Brain Extraction Tool | Công cụ bóc tách mô não (skull-stripping) dựa trên mạng nơ-ron tích chập 3D. |
| SynthSeg | Synthesized Segmentation | Mô hình học sâu phân đoạn toàn não cấu trúc dưới vỏ và vỏ não, huấn luyện trên dữ liệu tổng hợp. |
| SynthStrip | Synthesized Skull Stripping | Mô hình học sâu tách não nhanh và chính xác của FreeSurfer. |
| SynthMorph | Synthesized Morphometry Registration | Thuật toán học sâu đăng ký biến dạng ảnh não (deformable/affine registration) vào không gian chuẩn. |
| DKT | Desikan-Killiany-Tourville | Atlas định danh giải phẫu bề mặt vỏ não chuẩn dùng trong FastSurfer và FreeSurfer. |
| MNI152 | Montreal Neurological Institute 152 | Không gian ảnh não mẫu chuẩn (template space) dùng cho phép chiếu và chuẩn hóa atlas. |
| AAL / AAL3 | Automated Anatomical Labeling (v3) | Atlas phân vùng giải phẫu não bộ 166 vùng. |
| IBSR | Internet Brain Segmentation Repository | Atlas phân vùng cấu trúc dưới vỏ trong CAT12 (16 vùng). |
| COBRA | — | Atlas phân vùng giải phẫu dưới vỏ độ phân giải cao trong CAT12 (14 vùng). |
| SUIT | Spatially Unbiased Infratentorial Template | Mẫu và atlas chuyên biệt cho cấu trúc tiểu não. |
| LPBA40 | LONI Probabilistic Brain Atlas | Atlas xác suất vỏ não dựa trên 40 đối tượng trong CAT12 (48 vùng). |
| JHU ICBM-DTI-81 | Johns Hopkins University ICBM DTI | Atlas 36 dải chất trắng dựa trên ảnh khuếch tán từ trường. |
| YBA | Yale Brain Atlas | Atlas bề mặt 696 phân vùng (trích xuất 650 nhãn đặc trưng thực tế). |
| MGZ | Compressed MGH Format | Định dạng dữ liệu thể tích nén chuẩn của hệ sinh thái FreeSurfer. |
| B0–B6 | Baseline Policies 0 to 6 | 7 chính sách điều phối và lập lịch luồng tác vụ của bộ lập lịch NeuroFLOW. |
| TTA | Test-Time Augmentation | Kỹ thuật xoay lật ảnh lúc suy luận để tăng độ chính xác (HD-BET tự tắt khi chạy CPU để tối ưu tốc độ). |

---

## Số liệu tổng hợp hệ thống

| Hạng mục                 | Số lượng          |
| ------------------------ | ----------------- |
| Số tool                  | 47                |
| Số công đoạn             | 9                 |
| Số preset                | 12 + Custom       |
| Atlas subcortical volume | 20                |
| Atlas Cortical volume    | 19                |
| Atlas cortical thickness | 24 |
| Số docker image          | 10                |

---

## 1. Danh mục các công cụ xử lý

### 1.1. Thứ tự 9 công đoạn xử lý

| Thứ tự | Mã công đoạn (`stage`) | Tên hiển thị | Mục tiêu chính |
|---|---|---|---|
| 1 | `reorientation` | Reorientation, resize | Chuẩn hóa chiều không gian (conformed 1mm), điều chỉnh kích thước ảnh gốc |
| 2 | `brain_extraction` | Brain Extraction | Tách xương sọ, tạo ảnh não đã bóc tách mô mềm và mặt nạ não (brain mask) |
| 3 | `segmentation` | Subcortical Segmentation | Phân đoạn giải phẫu các cấu trúc mô não và nhân xám dưới vỏ |
| 4 | `template_registration` | Template Registration | Đăng ký ảnh vào không gian mẫu chuẩn (MNI305/MNI152), tính toán ma trận tọa độ |
| 5 | `bias_correction` | Image standardization | Khử nhiễu độ lệch từ trường (N4/bias correction), chuẩn hóa cường độ tín hiệu |
| 6 | `white_matter_segmentation` | WM Segmentation | Phân đoạn chất trắng, lấp đầy lỗ hổng hình thái (filled volume), tạo mặt nạ WM |
| 7 | `surface_reconstruction` | Surface Reconstruction | Tái dựng bề mặt vỏ não 3D (bề mặt chất trắng - white surface, màng mềm - pial surface) |
| 8 | `surface_registration` | Surface Registration | Đăng ký bề mặt lên mặt cầu chuẩn (spherical registration) để căn chỉnh atlas |
| 9 | `stats_extraction` | Statistics & Atlas Mapping | Tính toán số liệu thống kê (thể tích, độ dày) và chiếu atlas phân vùng |

---

### 1.2. Bảng phân loại 47 công cụ xử lý

Cột **Hỗ trợ GPU**: Có tùy chọn khai thác GPU (CUDA) để tăng tốc độ xử lý.

#### Nhóm CAT12 (Không yêu cầu bản quyền FreeSurfer, vận hành CPU)

Container thực thi: `duattran05/cat12_26_glibc:latest`

| Tên công cụ | Mã công cụ | Công đoạn | Ghi chú & Đầu ra |
|---|---|---|---|
| CAT12 Volume Segmentation | `cat12_volume_segmentation` | `segmentation` | Phân đoạn thể tích voxel, tạo báo cáo XML (`cat_*.xml`, `catROI_*.xml`). Timeout: 6 giờ. |
| CAT12 Full Segmentation | `cat12_full_segmentation` | `segmentation` | Phân đoạn thể tích kèm tái dựng bề mặt vỏ não ENIGMA. Timeout: 12 giờ. |
| CAT12 Volume Stats Extraction | `cat12_volume_stats_extraction` | `stats_extraction` | Trích xuất bảng thể tích `subcortical_volume.tsv` và `cortical_volume.tsv`. |
| CAT12 Full Stats Extraction | `cat12_full_stats_extraction` | `stats_extraction` | Trích xuất đầy đủ thể tích kèm độ dày vỏ não `cat12_cortical_thickness.tsv`. |

#### Nhóm FastSurfer (Yêu cầu bản quyền FreeSurfer)

Container thực thi: `deepmi/fastsurfer:latest` và `mri-fastsurfervinn`

| Tên công cụ | Mã công cụ | Công đoạn | Hỗ trợ GPU | Ghi chú & Đầu ra |
|---|---|---|---|---|
| FastSurfer Reorientation | `fastsurfer_reorientation` | `reorientation` | Không | Chuẩn hóa chiều ảnh và kích thước voxel về `orig.mgz`. |
| FastSurfer Segmentation | `fastsurfer_segmentation` | `segmentation` | Khuyến nghị | Mạng nơ-ron tích chập FastSurferCNN phân đoạn nhanh toàn não (`aparc.DKTatlas+aseg.deep.mgz`). |
| FastSurfer Template Registration | `fastsurfer_template_registration` | `template_registration` | Không | Đăng ký ảnh vào không gian toạ độ mẫu. |
| FastSurfer Standardization | `fastsurfer_standardization` | `bias_correction` | Không | Hiệu chỉnh độ lệch từ trường N4, tạo `norm.mgz`. |
| FastSurfer WM Segmentation | `fastsurfer_wm_segmentation` | `white_matter_segmentation` | Không | Tạo mặt nạ chất trắng và khối lấp đầy `filled.mgz`. |
| FastSurfer Surface Reconstruction | `fastsurfer_surface_reconstruction` | `surface_reconstruction` | Không | Tái dựng bề mặt vỏ não bán cầu não trái/phải (`lh.white`, `rh.white`). |
| FastSurfer Surface Registration | `fastsurfer_surface_registration` | `surface_registration` | Không | Đăng ký hình học mặt cầu vỏ não (`lh.sphere.reg`, `rh.sphere.reg`). |
| FastSurfer Stats Extraction | `fastsurfer_stats_extraction` | `stats_extraction` | Không | Trích xuất toàn diện số liệu bề mặt và thể tích bằng `segstats.py`. |
| FastSurfer Volume Stats Extraction | `fastsurfer_volume_stats_extraction` | `stats_extraction` | Không | Trích xuất chuyên biệt số liệu thể tích (sử dụng trong preset FastSurfer Volume). |
| FastSurferVINN Segmentation | `fastsurfervinn` | `segmentation` | Khuyến nghị | Biến thể mạng VINN độc lập kích thước voxel, hỗ trợ xử lý trực tiếp NIfTI. |

#### Nhóm FreeSurfer 8 (Container `mkdayyyy/mri-fs8-all:latest`, yêu cầu bản quyền)

| Tên công cụ | Mã công cụ | Công đoạn | Hỗ trợ GPU | Ghi chú & Đầu ra |
|---|---|---|---|---|
| FreeSurfer 8 Reorientation | `fs8_reduced54_reorientation` | `reorientation` | Không | Chuyển đổi và chuẩn hóa ảnh bằng `mri_convert --conform`. |
| FreeSurfer 8 Brain Extraction | `fs8_reduced54_brain_extraction` | `brain_extraction` | Không | Bóc tách mô sọ tự động bằng mô hình học sâu `mri_synthstrip`. |
| FreeSurfer 8 Template Registration | `fs8_reduced54_template_registration` | `template_registration` | Không | Đăng ký SynthMorph (`fs-synthmorph-reg`) affine tới MNI305 và phi tuyến tới MNI152. |
| FreeSurfer 8 Bias Correction | `fs8_reduced54_bias_correction` | `bias_correction` | Không | Hiệu chỉnh suy giảm cường độ: `mri_nu_correct.mni --ants-n4`, `AntsDenoiseImageFs`. |
| FreeSurfer 8 WM Segmentation | `fs8_reduced54_wm_segmentation` | `white_matter_segmentation` | Không | Phân đoạn chất trắng `mri_segment`, cắt cuống não, tạo `filled.mgz`. |
| FreeSurfer 8 Surface Reconstruction | `fs8_reduced54_surface_reconstruction` | `surface_reconstruction` | Không | Khởi tạo và làm mịn lưới bề mặt màng mềm và chất trắng. Timeout: 12 giờ. |
| FreeSurfer 8 Surface Registration | `fs8_reduced54_surface_registration` | `surface_registration` | Không | Căn chỉnh bề mặt cầu vỏ não về hệ tọa độ chuẩn fsaverage. |
| FreeSurfer 8 Stats | `fs8_reduced54_stats` | `stats_extraction` | Không | Tính toán độ dày vỏ não và thể tích theo các atlas bề mặt được kích hoạt. |
| SynthSeg (FS8) | `synthseg_freesurfer_fs8` | `segmentation` | Có (`--cpu` hoặc GPU) | Phân đoạn hai chế độ: tích hợp trong chủ thể nếu có `orig.mgz`, hoặc xuất NIfTI độc lập. |
| MNI Atlas Projection (FS8) | `fs8_mni_atlas_projection` | `stats_extraction` | Không | Chiếu atlas thể tích MNI về không gian ảnh đối tượng qua SynthMorph affine (`mri_vol2vol` + `mri_segstats`). |

#### Nhóm FreeSurfer 7 (Container `mkdayyyy/mri-fs7-all:latest`, yêu cầu bản quyền)

| Tên công cụ | Mã công cụ | Công đoạn | Hỗ trợ GPU | Ghi chú & Đầu ra |
|---|---|---|---|---|
| FreeSurfer 7 Reorientation | `fs7_recon_style_reorientation` | `reorientation` | Không | Chuẩn hóa định dạng và kích thước ảnh đối tượng. |
| FreeSurfer 7 Brain Extraction | `fs7_recon_style_brain_extraction` | `brain_extraction` | Không | Bóc tách sọ sau khi đã đăng ký mẫu (chạy sau template registration). |
| FreeSurfer 7 Segmentation | `fs7_recon_style_segmentation` | `segmentation` | Không | Phân đoạn cấu trúc dưới vỏ bằng mô hình xác suất GCA (`mri_ca_label`). |
| FreeSurfer 7 Template Registration | `fs7_recon_style_template_registration` | `template_registration` | Không | Đăng ký toạ độ Talairach tuyến tính (`mri_em_register`). |
| FreeSurfer 7 Bias Correction | `fs7_recon_style_bias_correction` | `bias_correction` | Không | Chuẩn hóa cường độ và hiệu chỉnh từ trường (`mri_ca_normalize`). |
| FreeSurfer 7 WM Segmentation | `fs7_recon_style_wm_segmentation` | `white_matter_segmentation` | Không | Cắt và phân đoạn chất trắng (`wm.mgz`, `filled.mgz`). |
| FreeSurfer 7 Surface Reconstruction | `fs7_recon_style_surface_reconstruction` | `surface_reconstruction` | Không | Tái dựng bề mặt đa giác vỏ não (`mris_make_surfaces`). Timeout: 12 giờ. |
| FreeSurfer 7 Surface Registration | `fs7_recon_style_surface_registration` | `surface_registration` | Không | Đăng ký bề mặt cầu vỏ não (`mris_register`). |
| FreeSurfer 7 Stats | `fs7_recon_style_stats` | `stats_extraction` | Không | Trích xuất toàn diện số liệu bề mặt và dưới vỏ (`mris_anatomical_stats`). |
| FreeSurfer 7 Subcortical Stats | `fs7_recon_style_subcortical_stats` | `stats_extraction` | Không | Chỉ trích xuất thể tích cấu trúc dưới vỏ (`mri_segstats`). |
| MRIConvert (FS7) | `mri_convert_fs7` | `reorientation` | Không | Chuyển đổi linh hoạt giữa DICOM/MGZ/NIfTI, xuất `01_reoriented.nii.gz`. |
| SynthStrip (FS7) | `synthstrip_fs7` | `brain_extraction` | Có | Bóc tách sọ độc lập, xuất ảnh não và mặt nạ nhị phân định dạng NIfTI. |
| SynthSeg (FS7) | `synthseg_freesurfer_fs7` | `segmentation` | Có | Phân đoạn SynthSeg độc lập định dạng NIfTI. |
| MRI Binarize | `mri_binarize` | `white_matter_segmentation` | Không | Nhị phân hóa mặt nạ chất trắng, xuất `06_wm_mask.nii.gz`. |
| Recon-All (FS7) | `recon_all_fs7` | `surface_reconstruction` | Không | Chạy toàn bộ luồng `recon-all -all -parallel` với khả năng khôi phục tiến trình. |
| Surface Stats (FS7) | `surface_stats_fs7` | `surface_registration` | Không | Trích xuất số liệu thống kê bề mặt khi đã có sẵn surfaces và sphere.reg. |
| FreeSurfer Stats Check (FS7) | `freesurfer_stats_fs7` | `stats_extraction` | Không | Đối soát tính toàn vẹn của các bảng thống kê `.tsv`. |

#### Nhóm công cụ độc lập & mô hình học sâu hỗ trợ (Không cần bản quyền FreeSurfer)

| Tên công cụ | Mã công cụ | Công đoạn | Hỗ trợ GPU | Container | Ghi chú kỹ thuật |
|---|---|---|---|---|---|
| Nibabel Reorientation | `nibabel` | `reorientation` | Không | `mri-nibabel-utils` | Chuẩn hóa nhẹ nhàng qua thư viện NiBabel, không phụ thuộc FreeSurfer. |
| HD-BET Brain Extraction | `hdbet` | `brain_extraction` | Có (`0` hoặc `cpu`) | `mri-hdbet` | Tách não bằng mạng nơ-ron học sâu độ chính xác cao. |
| SynthSeg Standalone | `synthseg_standalone` | `segmentation` | Không | `mri-synthseg-standalone` | Phân đoạn học sâu SynthSeg độc lập không cần cài FreeSurfer. |
| ANTs N4 Bias Correction | `ants_n4` | `bias_correction` | Không | `mri-ants` | Khử độ lệch từ trường N4, xuất `05_standardized.nii.gz`. |
| CorticalFlow++ | `corticalflow` | `surface_reconstruction` | Khuyến nghị mạnh | `mri-corticalflow` | Tái dựng bề mặt vỏ não 3D bằng mạng biến dạng đa giác học sâu. |
| SUGAR Registration | `sugar` | `surface_registration` | Khuyến nghị | `sugar` | Đăng ký bề mặt phổ (spectral surface registration) siêu tốc. |

---

### 1.3. Danh sách 12 Preset cấu hình sẵn

Hệ thống cung cấp 12 cấu hình định sẵn tối ưu hóa theo mục tiêu nghiên cứu và công cụ sử dụng:

| Tên Preset | Nhóm công cụ áp dụng | Công đoạn tự động bỏ qua | Vector mặc định được chọn |
|---|---|---|---|
| CAT12 + Volume | 2 công cụ CAT12 volume | Bỏ qua 7 công đoạn trung gian | `cat12_neuromorphometrics`, `cat12_schaefer2018_200parcels_17networks` |
| CAT12 + Cortical Thickness | 2 công cụ CAT12 full | Bỏ qua 7 công đoạn trung gian | `aparc` |
| CAT12 + Volume + Cortical Thickness | 2 công cụ CAT12 full | Bỏ qua 7 công đoạn trung gian | Cả hai nhóm vector trên |
| FreeSurfer 8 + Volume | SynthSeg FS8 + FS8 Stats | `bias_correction`, `white_matter_segmentation`, `surface_reconstruction`, `surface_registration` | `freesurfer_aseg`, `freesurfer_aparc` |
| FreeSurfer 8 + Cortical Thickness | Bộ 9 công cụ FS8 đầy đủ | Không bỏ qua công đoạn nào | `aparc` |
| FreeSurfer 8 + Volume + Cortical Thickness | Bộ 9 công cụ FS8 đầy đủ | Không bỏ qua công đoạn nào | Cả hai nhóm vector trên |
| FreeSurfer 7 + Volume | Bộ công cụ FS7 recon-style + Subcortical Stats | `bias_correction`, `white_matter_segmentation`, `surface_reconstruction`, `surface_registration` | `freesurfer_aseg` |
| FreeSurfer 7 + Cortical Thickness | Bộ 9 công cụ FS7 recon-style đầy đủ | Không bỏ qua công đoạn nào | `aparc` |
| FreeSurfer 7 + Volume + Cortical Thickness | Bộ 9 công cụ FS7 recon-style đầy đủ | Không bỏ qua công đoạn nào | Cả hai nhóm vector trên |
| FastSurfer + Volume | Chuỗi FastSurfer + Volume Stats | `brain_extraction`, `surface_reconstruction`, `surface_registration` | `fastsurfer_dkt` |
| FastSurfer + Cortical Thickness | Chuỗi FastSurfer đầy đủ | Không bỏ qua công đoạn nào | `aparc` |
| FastSurfer + Volume + Cortical Thickness | Chuỗi FastSurfer đầy đủ | Không bỏ qua công đoạn nào | Cả hai nhóm vector trên |
| Custom (Tùy chỉnh) | Người dùng tự chọn từng công đoạn | Linh hoạt theo lựa chọn | Tùy chọn theo nhu cầu |

---

## 2. Danh mục các Atlas và Vector đo lường

Hệ thống quản lý 59 atlas tích hợp, phân loại theo 3 vector đo lường độc lập. Số vùng não được xác thực trực tiếp từ các tệp danh sách đặc trưng giải phẫu trong thư mục `info/`.

### 2.1. Vector độ dày vỏ não (`cortical_thickness`) — 24 Atlas

Đơn vị đo lường: `thickness_mm`. Áp dụng khi thực hiện tái dựng bề mặt vỏ não.

| Tên Atlas | Số vùng đo thực tế | Định dạng tệp tài nguyên | Gói cài đặt / Vị trí lưu trữ |
|---|---|---|---|
| Desikan-Killiany (`aparc`) | 68 (34 mỗi bán cầu) | Phân loại có sẵn (`var_gcs`) | Tích hợp sẵn trong container FS7/FS8/FastSurfer |
| Destrieux (`aparc_a2009s`) | 148 (74 mỗi bán cầu) | Phân loại bề mặt GCS (`asset_gcs`) | Gói tải `atlas-destrieux.zip` |
| Yale Brain Atlas (`yale`) | 650 (nhãn YBA 696) | Nhãn bề mặt fsaverage ANNOT (`asset_annot`) | Gói tải `atlas-yale.zip` |
| Kong 2022 (200 parcels, 17 networks) (`kong`) | 200 | Nhãn bề mặt ANNOT (`asset_annot`) | Gói tải `atlas-kong2022.zip` |
| Schaefer 2018 (20 biến thể: 100 đến 1000 parcels x 7 & 17 networks) | Đúng theo số parcels trong tên (100–1000) | Phân loại bề mặt GCS (`asset_gcs`) | 20 gói tải riêng biệt `atlas-schaefer2018-{parcels}-{networks}.zip` |

---

### 2.2. Vector thể tích dưới vỏ (`subcortical_volume`) — 20 Atlas

Đơn vị đo lường: `volume_mm3` hoặc `volume` (đối với CAT12).

| Tên Atlas | Số vùng | Phương thức trích xuất / Cơ chế hoạt động |
|---|---|---|
| FreeSurfer Aseg (`freesurfer_aseg`) | 64 | Phân đoạn chuẩn dưới vỏ của FreeSurfer (mặc định preset FS7/FS8 Volume) |
| FastSurfer DKT (`fastsurfer_dkt`) | 131 | Phân đoạn toàn não DKT của FastSurfer (mặc định preset FastSurfer Volume) |
| CAT12 Neuromorphometrics (`cat12_neuromorphometrics`) | 33 | Trích xuất từ tệp XML của CAT12 (mặc định preset CAT12 Volume) |
| CAT12 IBSR (`cat12_ibsr`) | 16 | Trích xuất phân vùng cấu trúc dưới vỏ IBSR trong CAT12 |
| CAT12 COBRA (`cat12_cobra`) | 14 | Trích xuất phân vùng COBRA dưới vỏ độ phân giải cao trong CAT12 |
| CAT12 Hammers (`cat12_hammers`) | 23 | Trích xuất phân vùng dưới vỏ Hammers trong CAT12 |
| CAT12 SUIT (`cat12_suit`) | 34 | Trích xuất phân vùng tiểu não SUIT trong CAT12 |
| CAT12 Thalamic Nuclei (`cat12_thalamic_nuclei`) | 28 | Phân vùng các phân nhân của đồi thị trong CAT12 |
| CAT12 Thalamus (`cat12_thalamus`) | 2 | Thể tích đồi thị trái và đồi thị phải trong CAT12 |
| FreeSurfer SCLimbic (MNI152) (`mni_sclimbic`) | 25 | Chiếu atlas thể tích MNI về ảnh chủ thể qua SynthMorph (`sclimbic.t1.nii.gz`) |
| Harvard-Oxford Subcortical (MNI152) | 22 | Chiếu atlas MNI Harvard-Oxford Subcortical (`HarvardOxford-subl-maxprob-thr0-1mm.nii.gz`) |
| Brainnetome 246 (MNI) (`brainnetome246`) | 246 | Chiếu atlas MNI Brainnetome 246 (gồm 36 vùng dưới vỏ và 210 vùng vỏ não) |
| Pauli 2017 Subcortical (MNI) (`pauli_2017`) | 15 | Chiếu atlas MNI độ phân giải cao cho hạch nền và thân não (`pauli_2017_labels.nii.gz`) |
| AAL (MNI) (`aal`) | 166 | Chiếu atlas giải phẫu MNI AAL v3 (`aal.nii.gz`) |
| CerebrA (MNI-ICBM152) (`cerebra`) | 22 | Chiếu atlas giải phẫu dưới vỏ MNI-ICBM152 |
| Tian Subcortex (MNI) (`tian_subcortex`) | 18 | Chiếu atlas phân vùng cấu trúc dưới vỏ Tian Subcortex |
| FS Hippocampal/Amygdala (`fs_hippo_amygdala`) | 36 | Phân đoạn chuyên sâu vùng hồi hải mã và hạch hạnh nhân native của FreeSurfer |
| FS Brainstem Substructures (`fs_brainstem`) | 14 | Phân đoạn chuyên sâu các phân vùng thân não native của FreeSurfer |
| FS Thalamic Nuclei (`fs_thalamic_nuclei`) | 50 | Phân đoạn chuyên sâu 50 phân nhân đồi thị native của FreeSurfer |
| FS SCLimbic Segmentation (`fs_sclimbic`) | 25 | Phân đoạn chuyên sâu hệ viền dưới vỏ native của FreeSurfer |

---

### 2.3. Vector thể tích vỏ não (`cortical_volume`) — 19 Atlas

Đơn vị đo lường: `volume_mm3` hoặc `volume` (đối với CAT12).

| Tên Atlas | Số vùng | Phương thức trích xuất / Cơ chế hoạt động |
|---|---|---|
| FreeSurfer Aparc (`freesurfer_aparc`) | 68 | Thể tích chất xám vỏ não Desikan-Killiany (mặc định preset FS8 Volume) |
| FastSurfer DKT (`fastsurfer_dkt`) | 131 | Thể tích vùng vỏ não DKT của FastSurfer |
| CAT12 Schaefer 100 parcels / 17 networks | 8 | 8 nhóm mạng chức năng vỏ não chính trích xuất từ bảng XML CAT12 |
| CAT12 Schaefer 200 parcels / 17 networks | 8 | 8 nhóm mạng chức năng vỏ não chính (mặc định preset CAT12 Volume) |
| CAT12 Schaefer 400 parcels / 17 networks | 8 | 8 nhóm mạng chức năng vỏ não chính |
| CAT12 Schaefer 600 parcels / 17 networks | 8 | 8 nhóm mạng chức năng vỏ não chính |
| CAT12 AAL3 (`cat12_aal3`) | 62 | Phân vùng thể tích vỏ não AAL3 trích xuất từ CAT12 |
| CAT12 Anatomy3 (`cat12_anatomy3`) | 90 | Phân vùng giải phẫu vỏ não Anatomy v3 trong CAT12 |
| CAT12 Hammers (`cat12_hammers`) | 23 | Phân vùng vỏ não Hammers trong CAT12 |
| CAT12 Julich Brain 3 (`cat12_julichbrain3`) | 106 | Phân vùng cấu trúc tế bào Julich Brain v3 trong CAT12 |
| CAT12 LPBA40 (`cat12_lpba40`) | 48 | Phân vùng xác suất vỏ não LPBA40 trong CAT12 |
| CAT12 Mori (`cat12_mori`) | 50 | Phân vùng vỏ não Mori trong CAT12 |
| Harvard-Oxford Cortical (MNI152) | 96 | Chiếu atlas MNI Harvard-Oxford Cortical (`HarvardOxford-cortl-maxprob-thr0-1mm.nii.gz`) |
| Brainnetome 246 (MNI) (`brainnetome246`) | 246 | Chiếu atlas MNI Brainnetome 246 |
| Juelich (MNI) (`juelich`) | 62 | Chiếu atlas cấu trúc tế bào MNI Juelich (`juelich_maxprob-thr0-1mm.nii.gz`) |
| AAL (MNI) (`aal`) | 166 | Chiếu atlas giải phẫu MNI AAL v3 |
| Schaefer 2018 100 parcels / 7 net (MNI) | 100 | Chiếu atlas MNI phân vùng chức năng Schaefer 100 (`schaefer2018_100_7.nii.gz`) |
| JHU ICBM-DTI-81 White Matter (MNI) | 36 | Chiếu atlas MNI 36 bó sợi chất trắng |
| SUIT Cerebellum (MNI) | 30 | Chiếu atlas MNI 30 tiểu vùng tiểu não |

> [!TIP]
> **Tài nguyên Atlas MNI đi kèm:**
> Thư mục `assets/atlases/mni/` phân phối sẵn đầy đủ các tệp thể tích `.nii.gz` và bảng tra cứu nhãn `_LUT.txt` cho 8 atlas: `sclimbic`, `harvard_oxford_sub`, `harvard_oxford_cort`, `brainnetome246`, `pauli_2017`, `juelich`, `aal`, `schaefer2018_100_7`.

---

## 3. Toàn bộ các chức năng hệ thống

### 3.1. Cấu hình Pipeline, Preset và Workspace

- **12 Preset định sẵn:** Lựa chọn nhanh giữa các quy trình chuẩn (Volume, Cortical Thickness, All) cho CAT12, FreeSurfer 8, FreeSurfer 7, FastSurfer. Khi đổi preset, danh sách công cụ và atlas mặc định tương ứng sẽ được tự động thiết lập lại.
- **Chế độ tùy biến (Custom Mode):** Cho phép người dùng bật/tắt lưới chọn công cụ từng công đoạn. Bất kỳ thay đổi công cụ nào khác với preset sẽ tự động chuyển sang chế độ Custom.
- **Rút gọn thông minh cho CAT12:** Khi chọn các preset của CAT12, giao diện tự động ẩn 7 công đoạn trung gian không sử dụng, chỉ hiển thị 2 công đoạn `segmentation` và `stats_extraction`.
- **Xuất nhập cấu hình Preset (JSON):** Cho phép lưu cấu hình các công cụ đã chọn ra file JSON để tái sử dụng hoặc nạp lại preset đã lưu trước đó.
- **Quản lý không gian làm việc (Workspace JSON):** Lưu và khôi phục toàn bộ trạng thái làm việc (công cụ, atlas, đường dẫn local/server, tài nguyên tính toán, cấu hình lập lịch NeuroFLOW). Tự động suy luận đường dẫn tương ứng giữa máy cá nhân và máy chủ nếu tệp workspace bị thiếu trường.
- **Bố cục hai cột độc lập (Split-Pane Layout):** Cột trái tập trung cấu hình kỹ thuật (công đoạn, atlas, thiết lập nâng cao), cột phải quản lý dữ liệu vào/ra và môi trường thực thi.

---

### 3.2. Kiểm định tương thích công cụ

- **Xác thực trực tiếp trên giao diện:** Trong chế độ Custom, hệ thống liên tục kiểm tra tính liền mạch của chuỗi xử lý. Nếu một công cụ thiếu dữ liệu đầu vào từ các bước trước đó, giao diện sẽ đánh dấu đỏ công đoạn lỗi và hiển thị lý do chính xác (ví dụ: công cụ cần `orig.mgz` nhưng công đoạn Reorientation chưa được kích hoạt).
- **Điều chỉnh thứ tự công đoạn tự động:** Nhận diện công cụ `fs7_recon_style_template_registration` để tự động điều chỉnh chuỗi thực thi đưa bước đăng ký toạ độ lên trước bước tách não theo đúng chuẩn FreeSurfer 7.
- **Ngăn chặn xung đột dòng công cụ:** Cảnh báo khi người dùng kết hợp các công cụ không tương thích giữa các họ công cụ khác nhau (như trộn lẫn bước đăng ký của FreeSurfer 7 với bước dựng bề mặt của FastSurfer).

---

### 3.3. Chuẩn hóa đầu ra và Cấu hình xuất bản

- **Chuẩn hóa tệp xuất bản tự động (**`pipeline/export.py`**):** Cho phép tự động thu gom các tệp thể tích đầu ra chính của từng công đoạn vào một thư mục xuất khẩu chuẩn hóa (mặc định là `exports/`).
- **Tự động chuyển đổi định dạng ảnh:** Hỗ trợ tự động chuyển đổi sang `.nii.gz`, `.nii`, `.mgz` hoặc giữ nguyên định dạng gốc thông qua container `mri_convert_fs7`.
- **Tùy biến tên tệp xuất:** Người dùng có thể tùy biến tên đầu ra cho từng công đoạn:
  - `reorientation.primary` (mặc định: `01_reoriented`)
  - `brain_extraction.primary` (mặc định: `02_brain`)
  - `brain_extraction.mask` (mặc định: `02_brain_mask`)
  - `segmentation.primary` (mặc định: `03_segmentation`)
  - `template_registration.primary` (mặc định: `04_registered`)
  - `template_registration.deformation` (mặc định: `04_deformation_field`)
  - `bias_correction.primary` (mặc định: `05_standardized`)
  - `white_matter_segmentation.primary` (mặc định: `06_white_matter_mask`)
- **Tự động phân quyền tệp trên máy chủ:** Thực hiện sửa quyền tập tin (permissions repair) sau khi xuất bản để đảm bảo người dùng có toàn quyền đọc/ghi kết quả tạo bởi Docker container.

---

### 3.4. Quản lý dữ liệu đầu vào (Đơn lẻ, Lô ảnh, DICOM, Duyệt file)

- **Hỗ trợ đa nguồn dữ liệu:** Lựa chọn nguồn đầu vào trực tiếp từ máy cá nhân (Local) hoặc từ máy chủ từ xa (Server qua kết nối mạng bảo mật).
- **Chế độ xử lý đơn lẻ (Single) và Xử lý hàng loạt (Batch):** Tùy chọn chạy cho một đối tượng cụ thể hoặc tự động xử lý một thư mục chứa nhiều ca chụp.
- **Nhận diện chuỗi ảnh DICOM chuyên dụng:** Tự động phát hiện các thư mục chứa chuỗi lát cắt DICOM (`.dcm`), hiển thị số lát cắt (`slice_count`), gộp thành một chủ thể duy nhất và tự động tạo cờ chuyển đổi phù hợp.
- **Hộp thoại cấu hình Batch chuyên sâu (**`BatchConfigModal`**):**
  - Hỗ trợ 3 chế độ quét thư mục: Quét trực tiếp (`immediate` - độ sâu 1), Một cấp thư mục con (`single_level` - độ sâu 2), và Đệ quy sâu (`recursive` - tối đa 6 cấp).
  - Tự động lưu bộ nhớ đệm kết quả quét (`batchScanCache`) theo đường dẫn và kết nối máy chủ, giúp mở lại tức thì không cần quét lại.
  - Sắp xếp 3 trạng thái (tăng dần, giảm dần, mặc định) trên 4 cột thông tin: Tên đối tượng (Subject), Định dạng (Format), Đường dẫn (Path), và Dung lượng (Size).
  - Kéo giãn điều chỉnh độ rộng cột linh hoạt.
  - Bộ lọc tìm kiếm nhanh theo tên hoặc đường dẫn tương đối.
  - Các nút chọn nhanh: Chọn tất cả mục đang lọc, Bỏ chọn tất cả, và Chọn N đối tượng đầu tiên.
  - Cảnh báo và tự động xử lý khi có xung đột trùng tên chủ thể (`has_multi_subject_conflict`).
- **Trình duyệt máy chủ từ xa trực quan:** Duyệt cây thư mục máy chủ, thanh địa chỉ hiển thị đường dẫn hiện tại, hỗ trợ tạo thư mục mới trực tiếp trên máy chủ, lọc danh sách file/thư mục.

---

### 3.5. Truyền tải dữ liệu, Tải lười và Thu hồi kết quả

- **Cửa sổ truyền tải hai khung:** Hiển thị song song cây thư mục máy cá nhân và cây thư mục máy chủ. Cho phép tích chọn nhiều file/thư mục để tải lên máy chủ, tự động tạo thư mục đích và tùy chọn đặt làm đầu vào pipeline ngay sau khi tải xong.
- **Cơ chế lazy upload thông minh:** Khi chạy pipeline trên máy chủ từ xa với dữ liệu đầu vào nằm trên máy cá nhân, hệ thống không tải ồ ạt toàn bộ dữ liệu lên cùng lúc. Dữ liệu của từng chủ thể chỉ được tải lên máy chủ khi bộ lập lịch chuẩn bị chạy đến chủ thể đó (thông qua tệp đánh dấu `.ready`), kèm cơ chế giới hạn luồng song song để tối ưu băng thông.
- **Theo dõi tiến trình tải lười theo thời gian thực:** Thanh tiến trình cập nhật trạng thái tải từng file mỗi 2 giây, tự động hiển thị và ẩn khi hoàn thành.
- **Thu hồi kết quả xử lý từ xa (**`DownloadOutputsDialog`**):**
  - Tải toàn bộ thư mục kết quả hoặc chỉ thư mục tệp xuất bản từ máy chủ về máy cá nhân qua luồng dữ liệu an toàn.
  - Hiển thị chi tiết tiến độ: phần trăm hoàn thành, tốc độ truyền tải (file/giây), thời gian còn lại dự kiến (ETA), và tên tệp đang xử lý.
  - Cơ chế tải bù (resume): Giữ nguyên các tệp đã tải thành công nếu mạng bị gián đoạn; cho phép tiếp tục tải từ vị trí ngắt mà không cần truyền lại từ đầu.

---

### 3.6. Bộ lập lịch NeuroFLOW và Báo cáo hiệu năng

- **Tích hợp bộ lập lịch tác vụ NeuroFLOW (**`pipeline/neuroflow_adapter.py`**):**
  - Hỗ trợ 7 chính sách hàng đợi từ B0 đến B6:
    - `B0`: Đến trước phục vụ trước (FIFO / FCFS)
    - `B1`: Luân phiên (Round-Robin)
    - `B2`: Ưu tiên theo thứ tự (Priority-based)
    - `B3`: Tác vụ ngắn nhất trước (Shortest Job / Remaining Time First)
    - `B4`: Phân bổ tài nguyên động (Dynamic Resource Allocation)
    - `B5`: Lập lịch dựa trên hồ sơ hiệu năng (Profiling-based schedule)
    - `B6`: Thích ứng đảm bảo chất lượng dịch vụ (Adaptive QoS schedule)
  - Tùy chỉnh số lượng tác vụ xử lý song song tối đa và giai đoạn khởi động thăm dò (warmup phase).
  - Trình kiểm định tệp cấu hình NeuroFLOW (YAML/JSON validator): xác thực tính hợp lệ của cấu hình đồ thị DAG, phân biệt rõ giữa tệp Preset/Profile và tệp Workspace của ứng dụng.
- **Hệ thống báo cáo và bảng số liệu tự động (**`pipeline/reports.py`**):**
  - `stats_vectors_summary.csv`: Tổng hợp các vector đặc trưng của toàn bộ danh sách ảnh trong lô xử lý.
  - `stats_vectors_wide.csv`: Mở rộng toàn bộ các phân vùng giải phẫu (ROI) thành các cột số liệu riêng lẻ, sẵn sàng đưa vào các mô hình học máy và phân tích thống kê đa biến.
  - `benchmark_steps.tsv`: Ghi nhận chi tiết từng bước xử lý của từng chủ thể: thời gian chạy, thời gian build container, mức tiêu thụ RAM đỉnh, RAM trung bình, RAM phân vị 95, mức tải CPU đỉnh, CPU trung bình, CPU phân vị 95.
  - `benchmark_summary.tsv` và `pipeline_metrics.log`: Tổng kết hiệu năng toàn bộ chuỗi tác vụ và thông tin phần cứng máy chủ.

---

### 3.7. Thực thi an toàn và Kiểm tra trước chạy (Preflight Verification)

- **Kiểm tra trước chạy tự động (Preflight Checks):**
  - Chế độ Local (4 bước): Kiểm tra Docker daemon, bản quyền FreeSurfer, mức phân bổ RAM/CPU, và tính khả dụng của các Docker image cần thiết.
  - Chế độ Server (10 bước): Kiểm tra kết nối mạng bảo mật, tài nguyên phần cứng máy chủ, tính hợp lệ của cấu hình, quyền truy cập đường dẫn, Docker daemon, tính khả dụng của Docker image trên máy chủ, mã nguồn đồng bộ, môi trường Python máy chủ, bản quyền FreeSurfer, và khởi chạy worker nền.
- **Nút khắc phục nhanh (Quick Fix):** Cung cấp các thao tác sửa lỗi trực tiếp trên hộp thoại kiểm tra (tự động hạ mức phân bổ RAM, chuyển đổi preset, hoặc chuyển sang trang Tools để tải image/atlas bị thiếu).
- **Kiểm tra dung lượng đĩa an toàn:** Kiểm tra thư mục đầu ra trên máy chủ phải có quyền ghi và dung lượng đĩa trống tối thiểu đạt 10 GB hoặc gấp 20 lần dung lượng dữ liệu đầu vào.
- **Tách biệt tiến trình thực thi (Detached Workers):** Tiến trình xử lý chạy ngầm độc lập với giao diện, không hiện cửa sổ phụ trên Windows, tự ghi nhận nhật ký và chỉ số phần cứng liên tục vào thư mục của từng job.

---

### 3.8. Giám sát Job và Phân tích thời gian thực

- **Phân cụm quản lý Job:** Tách biệt rõ ràng giữa danh sách job chạy trên máy cá nhân (Local Jobs) và job chạy trên máy chủ (Server Jobs), sắp xếp theo thời gian mới nhất, nhãn trạng thái trực quan kèm biểu đồ tròn tỷ lệ hoàn thành.
- **Điều hướng sâu (Deep Linking):** Hỗ trợ mở trực tiếp chi tiết một job cụ thể qua liên kết URL (`/jobs/:jobId`).
- **Đọc dữ liệu phân đoạn tối ưu (Byte-Offset Reading):** Chỉ đọc phần dữ liệu sự kiện, nhật ký và chỉ số phần cứng mới phát sinh theo vị trí byte đã đọc, không tải lại toàn bộ tệp, đảm bảo giao diện luôn mượt mà kể cả với nhật ký dài hàng chục nghìn dòng.
- **Cửa sổ chi tiết từng chủ thể:**
  - Lưới trực quan hiển thị trạng thái từng công đoạn (hoàn thành, đang chạy, bỏ qua, thất bại).
  - Biểu đồ thời gian thực ghi nhận mức tiêu thụ CPU và RAM qua từng giai đoạn.
  - Trình xem console log tích hợp: công tắc ẩn/hiện thông tin nhạy cảm (mật khẩu, khoá SSH), công cụ tìm kiếm từ khóa trong log, tự động cuộn xuống cuối (auto-scroll), và giới hạn số dòng hiển thị.
- **Quản lý vòng đời Job an toàn:** Dừng job (stop) và xóa job (delete) đều yêu cầu xác nhận qua hộp thoại; tuyệt đối không cho phép xóa job đang trong trạng thái vận hành.

---

### 3.9. Quản lý tài nguyên phần cứng, Docker và Môi trường

- **Dò tìm phần cứng tự động:** Tự động phát hiện số lõi CPU, tổng dung lượng RAM, thông tin card đồ họa (GPU model và dung lượng VRAM còn trống) của cả máy cá nhân và máy chủ.
- **Thanh trượt giới hạn RAM và CPU:** Tự động giới hạn mức nhập an toàn (1–100% RAM, không vượt quá tổng số lõi CPU vật lý). Cảnh báo màu vàng khi thiết lập vượt quá 90%.
- **Bật/tắt tăng tốc GPU linh hoạt:** Tự động phát hiện thiết bị CUDA, cho phép bật/tắt GPU và truyền cờ tham số tương ứng xuống từng công cụ hỗ trợ (`--device 0` hoặc `--cpu`).
- **Quản lý 10 Docker Image:** Theo dõi danh sách container đã có và còn thiếu theo đúng các công cụ đang chọn trong cấu hình. Tải container theo luồng sự kiện trực tiếp; hỗ trợ xóa container để giải phóng dung lượng ổ cứng.
- **Quản lý giấy phép FreeSurfer:** Trình chọn và xác thực tệp bản quyền `license.txt`, tự động gắn kết vào các container yêu cầu bản quyền khi khởi chạy.

---

### 3.10. Tiện ích giao diện và Bản phát hành Portable

- **Giao diện đa chế độ:** Hỗ trợ chuyển đổi giao diện sáng/tối (Light/Dark mode) và lưu tùy chọn người dùng.
- **Thu phóng cỡ chữ linh hoạt (Font Scaling):** Cho phép điều chỉnh tỷ lệ kích thước chữ của toàn bộ ứng dụng theo phần trăm (từ 80% đến 125%) với nút đặt lại mặc định nhanh.
- **Hệ thống thông báo Toast:** Hiển thị tức thời các phản hồi thao tác lưu cấu hình, sao chép đường dẫn, ngắt kết nối mạng hoặc lỗi hệ thống.
- **Bản phát hành Windows Portable:** Đóng gói độc lập, giải nén và sử dụng ngay không cần cài đặt; toàn bộ cấu hình, dữ liệu đệm và nhật ký được cô lập trong thư mục của ứng dụng.
- **Tự động giải phóng cổng kết nối:** Cơ chế dọn dẹp tiến trình nền mồ côi (tự động phát hiện và giải phóng cổng 8765 khi khởi động lại ứng dụng).

---

## Phụ lục A. Danh sách 10 Docker Image

| Tên Image | Nhóm công cụ | Yêu cầu License FreeSurfer |
|---|---|---|
| `mkdayyyy/mri-fs7-all:latest` | FreeSurfer 7 | Có |
| `mkdayyyy/mri-fs8-all:latest` | FreeSurfer 8 | Có |
| `deepmi/fastsurfer:latest` / `mri-fastsurfervinn` | FastSurfer | Có |
| `duattran05/cat12_26_glibc:latest` | CAT12 | Không |
| `mri-nibabel-utils` | Tiện ích chuyển đổi NiBabel | Không |
| `mri-hdbet` | Bóc tách sọ não học sâu HD-BET | Không |
| `mri-synthseg-standalone` | Phân đoạn độc lập SynthSeg | Không |
| `mri-ants` | Hiệu chỉnh từ trường ANTs N4 | Không |
| `mri-corticalflow` | Tái dựng bề mặt vỏ não CorticalFlow++ | Không |
| `sugar` | Đăng ký bề mặt phổ SUGAR | Không |

---

## Phụ lục B. Bản đồ các tệp mã nguồn tra cứu

| Mục tiêu tra cứu | Tệp mã nguồn liên quan |
|---|---|
| Định nghĩa công cụ, tham số và thứ tự công đoạn | `pipeline/registry.py` (`TOOL_DEFS`, `STAGE_ORDER`, `FS7_RECON_STYLE_STAGE_ORDER`) |
| Định nghĩa và ánh xạ các Preset pipeline | `pipeline/presets.py` (`PIPELINE_MODES`, `PRESET_CONFIGS`, `normalize_pipeline_mode`) |
| Định nghĩa Atlas, Vector thống kê và Export | `pipeline/config.py` (`STAT_VECTOR_DEFS`, `ATLAS_DEFS`, `EXPORT_OUTPUT_ITEMS`, `ExportConfig`) |
| Quy tắc tương thích công cụ (Tool Contracts) | `pipeline/tool_compat.py` (`TOOL_CONTRACTS`, `TOKEN_LABELS`) |
| Quản lý tính sẵn sàng và gói tải Atlas | `pipeline/atlas_content.py`, `app_backend/atlases.py` (`ATLAS_PACKS`) |
| Xuất bản và chuẩn hóa dữ liệu đầu ra | `pipeline/export.py` (`_export_stage_outputs`, `_copy_or_convert_export`) |
| Báo cáo tổng hợp và đo lường hiệu năng | `pipeline/reports.py` (`write_batch_reports`, `_write_batch_benchmark_reports`) |
| Bộ chuyển đổi lập lịch NeuroFLOW | `pipeline/neuroflow_adapter.py`, `app_backend/neuroflow_config_validator.py` |
| Quản lý thực thi tiến trình và Docker | `pipeline/runner.py`, `pipeline/job_worker.py`, `pipeline/docker_ops.py` |
| Kết nối mạng bảo mật, SFTP và Tải lười | `remote/ssh_client.py`, `remote/remote_runner.py`, `remote/lazy_upload.py` |
| API dịch vụ nền (Backend Endpoints) | `app_backend/server.py`, `app_backend/metadata.py`, `app_backend/jobs.py`, `app_backend/tools.py` |
| Giao diện chính cấu hình Pipeline | `tauri-app/src/pages/PipelinePage.tsx`, `tauri-app/src/stores/pipelineFormStore.ts` |
| Giao diện Giám sát tiến trình (Jobs) | `tauri-app/src/pages/JobsPage.tsx`, `tauri-app/src/stores/jobsStore.ts` |
| Giao diện Quản lý Công cụ & Môi trường | `tauri-app/src/pages/ToolsPage.tsx`, `tauri-app/src/stores/toolsStore.ts` |
| Cấu hình đóng gói Windows Portable | `packaging/windows/README-PORTABLE.md`, `app_backend/paths.py` |
