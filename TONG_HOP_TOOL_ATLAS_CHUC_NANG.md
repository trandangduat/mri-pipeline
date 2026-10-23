# NeuroFLOW MRI Pipeline - Tổng hợp danh sách tool, atlas và chức năng  

Tài liệu tổng hợp ba nội dung: **tool đã tích hợp và bước xử lý tương ứng**, **atlas**, **các chức năng hiện có**. Phần chính trình bày khả năng và điều kiện sử dụng; các khối **Tra cứu kỹ thuật** có thể mở để xem danh mục đầy đủ, giới hạn tích hợp và nguồn đối chiếu.

**Cách đọc trạng thái:** “Có tích hợp” nghĩa là có cấu hình và mã xử lý trong dự án. “Cần dữ liệu/đầu vào” nghĩa là còn phụ thuộc image, license, atlas hoặc kết quả bước trước. “Mới khai báo/chưa nối hoàn chỉnh” được ghi riêng, chưa tính là khả năng chạy trọn luồng. Các số lượng dưới đây phản ánh checkout tại commit nêu trên.

**Danh sách ký hiệu/từ viết tắt**

| Ký hiệu / Từ viết tắt | Tên đầy đủ hoặc cách hiểu | Ý nghĩa trong tài liệu |
| --- | --- | --- |
| MRI | Magnetic Resonance Imaging | Chụp cộng hưởng từ; dữ liệu ảnh mà hệ thống xử lý. |
| FS7 / FS8 | FreeSurfer 7 / FreeSurfer 8 | Hai phiên bản FreeSurfer được tích hợp. |
| CAT12 | Computational Anatomy Toolbox 12 | Bộ công cụ xử lý hình thái não. |
| CT | Cortical Thickness | Độ dày vỏ não; đây là nghĩa của CT trong tài liệu. |
| CV | Cortical Volume | Thể tích vỏ não. |
| SV | Subcortical Volume | Thể tích các cấu trúc dưới vỏ. |
| ROI | Region of Interest | Vùng quan tâm để trích xuất chỉ số. |
| MNI | Montreal Neurological Institute | Tên nhóm không gian/template chuẩn; MNI152 và MNI305 là các template cụ thể. |
| LUT | Lookup Table | Bảng ánh xạ mã nhãn và tên vùng. |
| NIfTI | Neuroimaging Informatics Technology Initiative | Định dạng ảnh .nii và .nii.gz. |
| DICOM | Digital Imaging and Communications in Medicine | Chuẩn dữ liệu ảnh y khoa; một series gồm nhiều file/slice. |
| CPU | Central Processing Unit | Bộ xử lý trung tâm. |
| GPU | Graphics Processing Unit | Bộ xử lý đồ họa; dùng để tăng tốc các bước có hỗ trợ. |
| RAM | Random Access Memory | Bộ nhớ chính của máy chạy pipeline. |
| API | Application Programming Interface | Giao diện gọi chức năng backend. |
| CLI | Command-Line Interface | Giao diện dòng lệnh. |
| UI | User Interface | Giao diện người dùng. |
| SSH | Secure Shell | Kết nối và thực thi lệnh trên Server. |
| SFTP | SSH File Transfer Protocol | Truyền file qua SSH. |
| NA | Not Available | Giá trị thiếu hoặc không có dữ liệu phù hợp trong vector. |

<details>
<summary><strong>Mở danh sách từ viết tắt và ký hiệu kỹ thuật bổ sung</strong></summary>

| Từ viết tắt / ký hiệu | Tên đầy đủ hoặc cách hiểu | Ý nghĩa trong tài liệu |
| --- | --- | --- |
| ANTs | Advanced Normalization Tools | Bộ công cụ có thuật toán hiệu chỉnh bias field được sử dụng trong hệ thống. |
| CNN | Convolutional Neural Network | Mạng nơ-ron tích chập. |
| VINN | Voxel-size Independent Neural Network | Tên mô hình phân đoạn trong FastSurfer. |
| WM | White Matter | Chất trắng. |
| DKT | Desikan–Killiany–Tourville | Hệ phân vùng dùng trong FastSurfer. |
| GCA | Gaussian Classifier Atlas | Atlas/bộ phân loại dùng trong quy trình FreeSurfer. |
| GCS | Đuôi file classifier của FreeSurfer | Dữ liệu bộ phân loại atlas bề mặt, được dùng bởi lệnh gán nhãn. |
| RAS | Right–Anterior–Superior | Quy ước hướng trục ảnh mà wrapper NiBabel dùng khi chuẩn hóa hướng canonical. |
| MGH / MGZ | Định dạng volume FreeSurfer / dạng nén của MGH | Dữ liệu ảnh được nhận hoặc tạo trong các luồng FreeSurfer. |
| MCR | MATLAB Compiler Runtime | Runtime đi kèm image để chạy CAT12 standalone. |
| ICBM | International Consortium for Brain Mapping | Tên xuất hiện trong một số template/atlas chuẩn. |
| DTI | Diffusion Tensor Imaging | Ảnh tensor khuếch tán; xuất hiện trong tên atlas ICBM-DTI-81. |
| JHU | Johns Hopkins University | Tên đơn vị xuất hiện trong tên atlas JHU. |
| AAL / AAL3 | Automated Anatomical Labeling / phiên bản 3 | Nhóm atlas phân vùng giải phẫu. |
| YBA | Yale Brain Atlas | Nhóm atlas Yale; xuất hiện trong tên file/feature list. |
| DICM | Dấu nhận diện trong header DICOM | Chuỗi dùng để nhận diện một số file DICOM không có đuôi. |
| CUDA | Compute Unified Device Architecture | Nền tảng tính toán GPU của NVIDIA. |
| I/O | Input/Output | Đọc/ghi dữ liệu. |
| OOM | Out of Memory | Tình trạng hết bộ nhớ. |
| PID | Process Identifier | Mã định danh tiến trình. |
| ID | Identifier | Mã định danh, ví dụ Subject ID hoặc Job ID. |
| ETA | Estimated Time of Arrival | Thời gian dự kiến còn lại của thao tác truyền dữ liệu. |
| FIFO | First In, First Out | Nguyên tắc vào trước, xử lý trước trong các policy tương ứng. |
| SSE | Server-Sent Events | Luồng sự kiện từ backend đến giao diện. |
| HTTP | Hypertext Transfer Protocol | Giao thức của API backend. |
| CORS | Cross-Origin Resource Sharing | Cơ chế kiểm soát yêu cầu khác origin. |
| SHA-256 | Secure Hash Algorithm, 256 bit | Hàm băm dùng cho fingerprint/chữ ký nội dung theo từng luồng. |
| URL | Uniform Resource Locator | Địa chỉ tài nguyên, ví dụ đường tải atlas. |
| CSV | Comma-Separated Values | Bảng dữ liệu phân tách bằng dấu phẩy. |
| TSV | Tab-Separated Values | Bảng dữ liệu phân tách bằng ký tự tab. |
| JSON | JavaScript Object Notation | Định dạng cấu hình và dữ liệu API. |
| JSONL | JSON Lines | Mỗi dòng là một đối tượng JSON, dùng cho event/observation. |
| YAML / YML | YAML Ain’t Markup Language / đuôi file .yml | Định dạng preset/profile NeuroFLOW. |
| XML | Extensible Markup Language | Định dạng report/ROI của CAT12. |
| OS | Operating System | Hệ điều hành. |
| WSL | Windows Subsystem for Linux | Môi trường Linux trong Windows. |
| POSIX | Portable Operating System Interface | Nhóm giao diện hệ điều hành được một số nhánh code sử dụng. |
| MPS | Metal Performance Shaders | Công nghệ tăng tốc của Apple, được nhắc trong giới hạn hỗ trợ GPU. |
| DMG | Disk image của macOS | Định dạng ảnh đĩa dùng để phân phối ứng dụng macOS. |
| ZIP | Định dạng tệp nén | Dùng cho gói atlas và thao tác import. |
| CI | Continuous Integration | Tự động build/kiểm tra và tạo artifact qua workflow. |
| NSIS | Nullsoft Scriptable Install System | Công cụ tạo bộ cài Windows trong luồng đóng gói. |
| GiB / MiB | Gibibyte / Mebibyte | Đơn vị dung lượng nhị phân: 2^30 byte / 2^20 byte. |

</details>

**Mục lục**

1. [Danh sách các tool đã tích hợp & các bước hỗ trợ](#1-các-tool-đã-tích-hợp-và-các-bước-hỗ-trợ)
2. [Danh sách các atlas được hỗ trợ](#2-các-atlas)
3. [Danh sách các chức năng hiện có](#3-các-chức-năng-hiện-có)

## 1. Danh sách các tool đã tích hợp & các bước hỗ trợ

Code có **48 mục tool/wrapper** thuộc **9 nhóm bước**, dùng **10 Docker image**; **47 wrapper hiển thị** trong bộ chọn bước, một wrapper SynthSeg FS8 cũ được ẩn. Một phần mềm có thể được tách thành nhiều wrapper theo bước; đây không phải 48 phần mềm độc lập.

Hệ thống có **4 bộ công cụ xử lý chính** và các công cụ bổ trợ có thể lựa chọn trong chế độ Custom. Mỗi bộ công cụ hỗ trợ các bước và các loại kết quả khác nhau.

### 1.1. Các bộ công cụ chính

| Bộ công cụ | Các bước xử lý được hỗ trợ | Kết quả hỗ trợ |
| --- | --- | --- |
| **FreeSurfer 7 (FS7)** | Chuyển đổi/chuẩn hóa hình học; đăng ký template; tách não; phân đoạn; chuẩn hóa cường độ; phân đoạn chất trắng; tái tạo và đăng ký bề mặt; thống kê/ánh xạ atlas. | Thể tích, độ dày vỏ não hoặc kết hợp. Preset chỉ tính thể tích hiện lấy thể tích dưới vỏ. |
| **FreeSurfer 8 (FS8)** | Chuyển đổi/chuẩn hóa hình học; SynthStrip tách não; SynthSeg phân đoạn; SynthMorph đăng ký template; chuẩn hóa cường độ; phân đoạn chất trắng; tái tạo và đăng ký bề mặt; thống kê và chiếu atlas MNI. | Thể tích, độ dày vỏ não hoặc kết hợp. Preset thể tích dùng chuỗi bước rút gọn. |
| **FastSurfer** | Chuẩn hóa hình học; CNN/VINN phân đoạn và tạo mask; đăng ký template; chuẩn hóa cường độ; phân đoạn chất trắng; tái tạo và đăng ký bề mặt; thống kê DKT/aseg và atlas bề mặt. | Thể tích, độ dày vỏ não hoặc kết hợp. |
| **CAT12** | Tiền xử lý và phân đoạn trong CAT12; tạo bề mặt/độ dày ở chế độ đầy đủ; trích xuất thống kê từ kết quả CAT12. | Có preset thể tích, độ dày hoặc kết hợp; xuất TSV thickness ở Full. Đường từ TSV thickness sang vector CT theo atlas chưa nối hoàn chỉnh, xem phần 2.4. Nhiều công đoạn gộp trong segmentation và stats. |

### 1.2. Các công cụ bổ trợ

| Công cụ | Bước hỗ trợ và vai trò |
| --- | --- |
| MRI Convert FreeSurfer 7 | Chuyển đổi định dạng MRI; lệnh riêng dùng để tạo ảnh NIfTI cho chuỗi Custom. |
| NiBabel | Đưa ảnh về hướng canonical/RAS và ghi NIfTI; wrapper này không tự resample ảnh về kích thước voxel/isotropic mới. |
| SynthStrip FreeSurfer 7; HD-BET | Tách não và tạo mặt nạ não. |
| SynthSeg FreeSurfer 7/8; SynthSeg Standalone | Phân đoạn và xuất số đo thể tích; wrapper gọi bước chuẩn hóa thống kê. Bản FS8 có nhánh chạy trong cây subject và nhánh NIfTI riêng. |
| FastSurferVINN | Wrapper prediction riêng cho phân đoạn; khác chuỗi preset FastSurfer nhiều stage. Việc gom thống kê phụ thuộc thư mục stats mà prediction tạo ra. |
| ANTs N4 | Hiệu chỉnh sai lệch cường độ ảnh do bias field. |
| MRI Binarize FreeSurfer 7 | Tạo mặt nạ chất trắng. |
| Recon-All FreeSurfer 7 | Chạy quy trình recon-all, bao gồm nhiều công đoạn tái tạo bề mặt bên trong. |
| Surface Stats FreeSurfer 7 | Ánh xạ atlas bề mặt và thống kê. |
| FreeSurfer Stats FreeSurfer 7 | Kiểm tra các bảng thống kê thể tích đã được tạo ở bước trước. |
| MNI Atlas Projection FreeSurfer 8 | Đưa atlas thể tích về không gian ảnh cá thể bằng affine/nearest-neighbor rồi tính thống kê. Wrapper riêng cần norm.mgz đã có; không tự bổ sung vào mọi preset FS7/FastSurfer/CAT12. |
| CorticalFlow++ | Có wrapper gọi prediction để tạo white/pial; chưa có preset chuẩn hoặc cầu nối định dạng đã được kiểm chứng với các bước FreeSurfer/SUGAR. |
| SUGAR | Có wrapper đăng ký cho hai bán cầu, đọc cây subject FreeSurfer; chưa có preset chuẩn riêng. |

### 1.3. Các thành phần hỗ trợ vận hành

Các thành phần dưới đây phục vụ thực thi, truyền dữ liệu và báo cáo:

| Thành phần | Vai trò hỗ trợ |
| --- | --- |
| **Docker** | Chạy tool trong container; pull/build/kiểm tra image; giới hạn tài nguyên và thu log, trạng thái, số đo container. |
| **NeuroFLOW** | Lập lịch task theo phụ thuộc và ngân sách tài nguyên khi bật scheduler. Có adapter và cấu hình trong dự án; cần package NeuroFLOW hoặc source tương ứng trong môi trường chạy. |
| **Paramiko / SSH / SFTP** | Kết nối Server, thực thi lệnh nền, duyệt file, truyền input/output và đọc trạng thái job. |
| **psutil** | Đọc thông tin tài nguyên/tiến trình ở các luồng kiểm tra môi trường và theo dõi có sử dụng thư viện này. |
| **Pandas / NumPy** | Tổng hợp số liệu và báo cáo benchmark trong các script liên quan; xuất XLSX còn phụ thuộc Excel writer của môi trường. |

### 1.4. Cấu hình chạy và điều kiện hỗ trợ

- Có **12 preset**: với 4 bộ công cụ chính, mỗi bộ công cụ chính có 3 mục tiêu **Volume**, **Cortical Thickness**, **Volume + Cortical Thickness**. Chế độ **Custom** cho phép chọn tool cho từng bước và kiểm tra tương thích.
- Các bước thực chạy phụ thuộc preset; quy trình chỉ tính thể tích có thể bỏ bước bề mặt. FS7 có thứ tự đăng ký template trước tách não và phân đoạn.
- Các wrapper FS7, FS8 và FastSurfer được registry yêu cầu **FreeSurfer license**. CPU/GPU được hỗ trợ tùy tool và từng lệnh.
- CorticalFlow++ và SUGAR có wrapper tích hợp, không có preset chuẩn riêng; cần đầu vào phù hợp.
- Tên preset cho biết mục tiêu cấu hình. Riêng CAT12 CT và một số lựa chọn atlas còn có giới hạn ở đường tạo vector; không suy từ tên preset rằng mọi chỉ số đã đầy đủ.

### 1.5. Tra cứu kỹ thuật về tool

<details>
<summary><strong>Mở danh mục 48 wrapper, ma trận bước, preset, Docker image và nguồn đối chiếu</strong></summary>

#### Chín nhóm bước xử lý

| Mã bước | Tên giao diện | Vai trò |
| --- | --- | --- |
| `reorientation` | Reorientation, resize | Chuyển đổi, định hướng, conform/chuẩn hóa hình học tùy tool. |
| `brain_extraction` | Brain Extraction | Tách não, tạo brain image/mask. |
| `segmentation` | Subcortical Segmentation | Phân đoạn; một số tool đồng thời phân vùng vỏ hoặc xử lý nhiều công đoạn. |
| `template_registration` | Template Registration | Đăng ký template, Talairach/SynthMorph transform tùy pipeline. |
| `bias_correction` | Image standardization | Bias correction, chuẩn hóa cường độ, chuẩn bị ảnh cho surface. |
| `white_matter_segmentation` | WM Segmentation | Chất trắng, mask, filled volume. |
| `surface_reconstruction` | Surface Reconstruction | White/pial surface, độ dày và hình thái tùy tool. |
| `surface_registration` | Surface Registration | Đăng ký surface, sphere registration hoặc atlas. |
| `stats_extraction` | Statistics & Atlas Mapping | Thống kê, atlas mapping, chuẩn bị vector. |

**Ngoại lệ:** FS7 recon-style chạy template registration trước brain extraction và segmentation. Đồ thị phụ thuộc/preset là căn cứ thực thi; bảng trên không phải thứ tự cố định.

#### Ma trận công cụ và bước xử lý

| Bước | FreeSurfer 7 | FreeSurfer 8 | FastSurfer | CAT12 |
| --- | --- | --- | --- | --- |
| Reorientation | MRI Convert + conform | MRI Convert + conform | MRI Convert + FastSurfer conform | Nội bộ CAT12; không có stage riêng. |
| Brain extraction | Recon-style, brainmask | SynthStrip | Mask tạo trong prediction/segmentation; bỏ stage riêng. | Nội bộ CAT12. |
| Segmentation | Atlas/GCA recon-style | SynthSeg | CNN/VINN, DKT + aseg, corpus callosum | Volume hoặc Full Segmentation. |
| Template registration | Talairach/recon-style | SynthMorph; affine/warp ở luồng đầy đủ | Talairach của FastSurfer/recon-surf | Nội bộ CAT12. |
| Standardization | Chuẩn hóa và ảnh cho surface | Bias, normalize, mask, denoise | N4/Talairach ở bước liên quan; normalize/mask | Nội bộ CAT12. |
| WM segmentation | Segment/edit WM, fill | Segment/edit WM, fill | Recon-all/recon-surf | Nội bộ CAT12. |
| Surface reconstruction | Tessellation/topology/white; hoàn thiện ở bước sau | White/pial/thickness | Recon-surf, white/pial/thickness | Full bật surface; Volume tắt. |
| Surface registration | Smooth/inflate/sphere/register | Smooth/inflate/sphere/register | FastSurfer registration | Nội bộ CAT12. |
| Statistics/atlas | Aseg, aparc, surface atlas | SynthSeg/aseg, surface atlas, projection MNI | DKT/aseg, volume, surface atlas | Report/ROI XML, surface, chuẩn hóa TSV. |

**License:** registry yêu cầu FreeSurfer license cho wrapper FS7/FS8/FastSurfer, kể cả một số bước chuyển đổi. CAT12 và tool không có cờ needs_license không yêu cầu FreeSurfer license ở mức registry.

**GPU:** có lựa chọn CPU/GPU, nhưng khả năng tùy lệnh. SynthSeg FS8 trong cây subject hiện có --cpu cố định. Bật GPU không có nghĩa mọi bước chạy GPU.

#### Danh sách 12 preset và cấu hình mặc định

Bảng lấy từ pipeline/presets.py. CV = cortical volume; SV = subcortical volume; CT = cortical thickness.

| Preset | Stage đã chọn | Thống kê | Atlas mặc định |
| --- | --- | --- | --- |
| CAT12 + Volume | 2 | CV, SV | SV: `cat12_neuromorphometrics`; CV: `cat12_schaefer2018_200parcels_17networks` |
| CAT12 + Cortical Thickness | 2 | CT; vector chưa nối trực tiếp từ TSV CAT12 | CT: `aparc` |
| CAT12 + Volume + Cortical Thickness | 2 | CV, SV, CT; CT có giới hạn reader | SV: `cat12_neuromorphometrics`; CV: `cat12_schaefer2018_200parcels_17networks`; CT: `aparc` |
| FreeSurfer 8 + Volume | 3 | CV, SV | SV: `freesurfer_aseg`; CV: `freesurfer_aparc` |
| FreeSurfer 8 + Cortical Thickness | 9 | CT | CT: `aparc` |
| FreeSurfer 8 + Volume + Cortical Thickness | 9 | CV, SV, CT | SV: `freesurfer_aseg`; CV: `freesurfer_aparc`; CT: `aparc` |
| FreeSurfer 7 + Volume | 5 | SV | SV: `freesurfer_aseg` |
| FreeSurfer 7 + Cortical Thickness | 9 | CT | CT: `aparc` |
| FreeSurfer 7 + Volume + Cortical Thickness | 9 | CV, SV, CT | SV: `freesurfer_aseg`; CV: `freesurfer_aparc`; CT: `aparc` |
| FastSurfer + Volume | 6 | CV, SV | SV: `fastsurfer_dkt`; CV: `fastsurfer_dkt` |
| FastSurfer + Cortical Thickness | 8 | CT | CT: `aparc` |
| FastSurfer + Volume + Cortical Thickness | 8 | CV, SV, CT | SV: `fastsurfer_dkt`; CV: `fastsurfer_dkt`; CT: `aparc` |
| Custom | 0 | Tùy cấu hình | Tùy cấu hình |

- **FS7 + Volume chỉ yêu cầu SV**, không phải cả CV + SV.
- **FS8 + Volume:** reorientation → SynthSeg → stats; bỏ surface.
- **FS7 + Volume:** reorientation → template registration → brain extraction → segmentation → subcortical stats.
- **FastSurfer + Volume:** giữ registration/standardization/WM, bỏ surface reconstruction/registration.
- **CAT12:** gom nhiều công đoạn vào segmentation và stats; 2 stage không có nghĩa chỉ có 2 thao tác nội bộ.
- **Custom:** chọn tool theo bước, bỏ bước không chọn, kiểm tra compatibility đầu vào/đầu ra.
- Có alias cũ: FS7, FS8, Volume, Volume & Cortical Thickness.

#### Danh mục đầy đủ 48 wrapper theo bước

Một họ phần mềm có nhiều wrapper theo stage. Cột license là yêu cầu **FreeSurfer license của ứng dụng**.


##### Reorientation, resize (`reorientation`)

| Khóa tool | Tên hiển thị | Docker image | FS license | Hiển thị |
| --- | --- | --- | --- | --- |
| `fastsurfer_reorientation` | FastSurfer Reorientation | `duattran05/mri-fastsurfervinn:latest` | Có | Có |
| `fs8_reduced54_reorientation` | FreeSurfer 8 Reorientation | `mkdayyyy/mri-fs8-all:latest` | Có | Có |
| `fs7_recon_style_reorientation` | FreeSurfer 7 Reorientation | `mkdayyyy/mri-fs7-all:latest` | Có | Có |
| `mri_convert_fs7` | MRI Convert FreeSurfer7 | `mkdayyyy/mri-fs7-all:latest` | Có | Có |
| `nibabel` | NiBabel | `duattran05/mri-nibabel-utils:latest` | Không | Có |

##### Brain Extraction (`brain_extraction`)

| Khóa tool | Tên hiển thị | Docker image | FS license | Hiển thị |
| --- | --- | --- | --- | --- |
| `fs8_reduced54_brain_extraction` | FreeSurfer 8 Brain Extraction | `mkdayyyy/mri-fs8-all:latest` | Có | Có |
| `fs7_recon_style_brain_extraction` | FreeSurfer 7 Brain Extraction | `mkdayyyy/mri-fs7-all:latest` | Có | Có |
| `synthstrip_fs7` | SynthStrip FreeSurfer7 | `mkdayyyy/mri-fs7-all:latest` | Có | Có |
| `hdbet` | HD-BET | `duattran05/mri-hdbet:latest` | Không | Có |

##### Subcortical Segmentation (`segmentation`)

| Khóa tool | Tên hiển thị | Docker image | FS license | Hiển thị |
| --- | --- | --- | --- | --- |
| `cat12_volume_segmentation` | CAT12 Volume Segmentation | `duattran05/cat12_26_glibc:latest` | Không | Có |
| `cat12_full_segmentation` | CAT12 Full Segmentation | `duattran05/cat12_26_glibc:latest` | Không | Có |
| `fastsurfer_segmentation` | FastSurfer Segmentation | `duattran05/mri-fastsurfervinn:latest` | Có | Có |
| `fs8_reduced54_segmentation` | FreeSurfer 8 SynthSeg | `mkdayyyy/mri-fs8-all:latest` | Có | Nội bộ/ẩn |
| `fs7_recon_style_segmentation` | FreeSurfer 7 Atlas Segmentation | `mkdayyyy/mri-fs7-all:latest` | Có | Có |
| `synthseg_freesurfer_fs8` | FreeSurfer 8 SynthSeg | `mkdayyyy/mri-fs8-all:latest` | Có | Có |
| `synthseg_freesurfer_fs7` | SynthSeg FreeSurfer7 | `mkdayyyy/mri-fs7-all:latest` | Có | Có |
| `synthseg_standalone` | SynthSeg Standalone | `duattran05/mri-synthseg-standalone:latest` | Không | Có |
| `fastsurfervinn` | FastSurferVINN | `duattran05/mri-fastsurfervinn:latest` | Có | Có |

##### Template Registration (`template_registration`)

| Khóa tool | Tên hiển thị | Docker image | FS license | Hiển thị |
| --- | --- | --- | --- | --- |
| `fastsurfer_template_registration` | FastSurfer Template Registration | `duattran05/mri-fastsurfervinn:latest` | Có | Có |
| `fs8_reduced54_template_registration` | FreeSurfer 8 Template Registration | `mkdayyyy/mri-fs8-all:latest` | Có | Có |
| `fs7_recon_style_template_registration` | FreeSurfer 7 Template Registration | `mkdayyyy/mri-fs7-all:latest` | Có | Có |

##### Image standardization (`bias_correction`)

| Khóa tool | Tên hiển thị | Docker image | FS license | Hiển thị |
| --- | --- | --- | --- | --- |
| `fastsurfer_standardization` | FastSurfer Standardization | `duattran05/mri-fastsurfervinn:latest` | Có | Có |
| `fs8_reduced54_bias_correction` | FreeSurfer 8 Image Standardization | `mkdayyyy/mri-fs8-all:latest` | Có | Có |
| `fs7_recon_style_bias_correction` | FreeSurfer 7 Image Standardization | `mkdayyyy/mri-fs7-all:latest` | Có | Có |
| `ants_n4` | ANTs N4 | `duattran05/mri-ants:latest` | Không | Có |

##### WM Segmentation (`white_matter_segmentation`)

| Khóa tool | Tên hiển thị | Docker image | FS license | Hiển thị |
| --- | --- | --- | --- | --- |
| `fastsurfer_wm_segmentation` | FastSurfer WM Segmentation | `duattran05/mri-fastsurfervinn:latest` | Có | Có |
| `fs8_reduced54_wm_segmentation` | FreeSurfer 8 WM Segmentation | `mkdayyyy/mri-fs8-all:latest` | Có | Có |
| `fs7_recon_style_wm_segmentation` | FreeSurfer 7 WM Segmentation | `mkdayyyy/mri-fs7-all:latest` | Có | Có |
| `mri_binarize` | MRI Binarize FreeSurfer7 | `mkdayyyy/mri-fs7-all:latest` | Có | Có |

##### Surface Reconstruction (`surface_reconstruction`)

| Khóa tool | Tên hiển thị | Docker image | FS license | Hiển thị |
| --- | --- | --- | --- | --- |
| `fastsurfer_surface_reconstruction` | FastSurfer Surface Reconstruction | `duattran05/mri-fastsurfervinn:latest` | Có | Có |
| `fs8_reduced54_surface_reconstruction` | FreeSurfer 8 Surface Reconstruction | `mkdayyyy/mri-fs8-all:latest` | Có | Có |
| `fs7_recon_style_surface_reconstruction` | FreeSurfer 7 Surface Reconstruction | `mkdayyyy/mri-fs7-all:latest` | Có | Có |
| `recon_all_fs7` | Recon-All FreeSurfer7 | `mkdayyyy/mri-fs7-all:latest` | Có | Có |
| `corticalflow` | CorticalFlow++ | `duattran05/mri-corticalflow:latest` | Không | Có |

##### Surface Registration (`surface_registration`)

| Khóa tool | Tên hiển thị | Docker image | FS license | Hiển thị |
| --- | --- | --- | --- | --- |
| `fastsurfer_surface_registration` | FastSurfer Surface Registration | `duattran05/mri-fastsurfervinn:latest` | Có | Có |
| `fs8_reduced54_surface_registration` | FreeSurfer 8 Surface Registration | `mkdayyyy/mri-fs8-all:latest` | Có | Có |
| `fs7_recon_style_surface_registration` | FreeSurfer 7 Surface Registration | `mkdayyyy/mri-fs7-all:latest` | Có | Có |
| `surface_stats_fs7` | Surface Stats FreeSurfer7 | `mkdayyyy/mri-fs7-all:latest` | Có | Có |
| `sugar` | SUGAR | `ninganme/sugar:latest` | Không | Có |

##### Statistics & Atlas Mapping (`stats_extraction`)

| Khóa tool | Tên hiển thị | Docker image | FS license | Hiển thị |
| --- | --- | --- | --- | --- |
| `cat12_volume_stats_extraction` | CAT12 Volume Stats Extraction | `duattran05/cat12_26_glibc:latest` | Không | Có |
| `cat12_full_stats_extraction` | CAT12 Full Stats Extraction | `duattran05/cat12_26_glibc:latest` | Không | Có |
| `fastsurfer_stats_extraction` | FastSurfer Stats Extraction | `duattran05/mri-fastsurfervinn:latest` | Có | Có |
| `fastsurfer_volume_stats_extraction` | FastSurfer Volume Stats Extraction | `duattran05/mri-fastsurfervinn:latest` | Có | Có |
| `fs8_mni_atlas_projection` | MNI Atlas Projection (FS8) | `mkdayyyy/mri-fs8-all:latest` | Có | Có |
| `fs8_reduced54_stats` | FreeSurfer 8 Stats | `mkdayyyy/mri-fs8-all:latest` | Có | Có |
| `fs7_recon_style_stats` | FreeSurfer 7 Stats | `mkdayyyy/mri-fs7-all:latest` | Có | Có |
| `fs7_recon_style_subcortical_stats` | FreeSurfer 7 Subcortical Stats | `mkdayyyy/mri-fs7-all:latest` | Có | Có |
| `freesurfer_stats_fs7` | FreeSurfer Stats FreeSurfer7 | `mkdayyyy/mri-fs7-all:latest` | Có | Có |

#### Docker image đang sử dụng

| Image | Số wrapper dùng chung |
| --- | --- |
| `duattran05/cat12_26_glibc:latest` | 4 |
| `duattran05/mri-ants:latest` | 1 |
| `duattran05/mri-corticalflow:latest` | 1 |
| `duattran05/mri-fastsurfervinn:latest` | 10 |
| `duattran05/mri-hdbet:latest` | 1 |
| `duattran05/mri-nibabel-utils:latest` | 1 |
| `duattran05/mri-synthseg-standalone:latest` | 1 |
| `mkdayyyy/mri-fs7-all:latest` | 17 |
| `mkdayyyy/mri-fs8-all:latest` | 11 |
| `ninganme/sugar:latest` | 1 |

#### Điều kiện, giới hạn và nguồn đối chiếu

CorticalFlow++ và SUGAR có command builder, chưa có preset chuẩn riêng. Compatibility theo token chưa chứng minh mọi định dạng surface ghép trực tiếp được.

Có docker/ants-n3-bias và Dockerfile nền FreeSurfer, nhưng **ANTs N3 chưa có mục chọn trong TOOL_DEFS**. Dockerfile/script thử nghiệm không được tính thành chức năng UI đã tích hợp.

| Hạng mục | Điều kiện/giới hạn |
| --- | --- |
| Tool | 48 wrapper không phải 48 phần mềm hoặc mọi tổ hợp Custom đã chạy thực nghiệm. |
| FS7 Volume | Preset chỉ yêu cầu SV. |
| CAT12 CT | Có TSV thickness; vector CT hiện đọc bảng stats kiểu FreeSurfer, chưa đọc TSV CAT12 trực tiếp. |
| FS8 CT chọn atlas khác | Stage stats vẫn kiểm tra lh/rh.aparc.stats; chỉ chọn Schaefer/Kong/Yale có thể thiếu file aparc và thất bại trên subject mới. |
| Custom | Compatibility kiểm tra token đầu vào/đầu ra, chưa chứng minh mọi định dạng thực tế tương thích. |
| Phiên bản image | Registry dùng tag latest; tên FS7/FS8 là họ tích hợp, không khóa digest hoặc chứng minh phiên bản binary đang cài. |
| GPU | Có bước CPU-only/--cpu cố định; không có cam kết mọi bước GPU hoặc Apple MPS/Metal. |

**Nguồn đối chiếu**

| Nội dung | Nguồn |
| --- | --- |
| Tool/image/stage/command | [pipeline/registry.py](../pipeline/registry.py) |
| Preset | [pipeline/presets.py](../pipeline/presets.py) |
| Compatibility | [pipeline/tool_compat.py](../pipeline/tool_compat.py), [tests/test_tool_compat.py](../tests/test_tool_compat.py) |
| Wrapper bên trong image | [docker](../docker/) — đối chiếu run_tool.py và Dockerfile; image đã pull có thể khác checkout. |
| Thực thi và chuẩn hóa | [pipeline/runner.py](../pipeline/runner.py), [normalize_volumes.py](../normalize_volumes.py) |

</details>

## 2. Danh sách các atlas được hỗ trợ

Atlas được chia theo **loại dữ liệu và mục tiêu thống kê**. Danh mục cấu hình có **59 khóa atlas**; một số khóa mới có khai báo, nên cần phân biệt với atlas đã có cơ chế xử lý và đủ dữ liệu.

| Nhóm trong danh mục | Số khóa riêng biệt | Phạm vi |
| --- | --- | --- |
| Surface CT | 24 | Aparc, Destrieux, Yale, Kong 200 và 20 Schaefer. |
| FreeSurfer volume | 2 | Aseg và Aparc. |
| FastSurfer volume | 1 | DKT, dùng cho cả CV và SV. |
| CAT12 volume | 16 | Đọc ROI/report của CAT12. |
| MNI projection | 12 | 8 khóa có khai báo volume để builder chiếu; 4 khóa còn thiếu khai báo volume. |
| FreeSurfer native subregions | 4 | Mới có cấu hình/spec, chưa đủ đường phân đoạn và reader riêng. |

Một khóa dùng cho cả CV và SV chỉ được tính một lần. Tổng 59 không bao gồm 3 biến thể Kong tùy chọn chưa thuộc danh mục chuẩn.

### 2.1. Atlas bề mặt cho độ dày vỏ não

| Atlas | Các biến thể trong hệ thống |
| --- | --- |
| **Desikan–Killiany** | aparc; atlas độ dày mặc định của các preset hiện tại. |
| **Destrieux** | aparc.a2009s. |
| **Yale Brain Atlas** | Biến thể mang tên YBA 696 parcels. |
| **Kong 2022** | 200 parcels / 17 networks. |
| **Schaefer 2018** | 100–1000 parcels, bước 100; mỗi mức có 7 hoặc 17 networks, tổng cộng **20 biến thể**. |

Cơ chế ánh xạ surface trong phần này chủ yếu nằm ở các wrapper FreeSurfer/FastSurfer; không áp dụng đồng loạt cho CAT12 chỉ vì dùng chung bộ chọn atlas.

Có **23 gói atlas bề mặt** với cơ chế tải/import: 20 Schaefer, Destrieux, Kong 200 và Yale. Biến thể Kong 100/300/400 mới có định nghĩa tùy chọn, chưa thuộc danh mục chuẩn.

### 2.2. Atlas thể tích theo bộ công cụ

| Bộ công cụ | Atlas | Loại thống kê theo cấu hình |
| --- | --- | --- |
| FreeSurfer | Aseg; Aparc | Thể tích dưới vỏ; thể tích vỏ não tương ứng. |
| FastSurfer | DKT/aseg | Thể tích vỏ não và dưới vỏ. |
| CAT12 | Neuromorphometrics | Thể tích dưới vỏ. |
| CAT12 | Schaefer 100/200/400/600 parcels, 17 networks | Thể tích vỏ não. |
| CAT12 | AAL3, Anatomy3, Julich Brain 3, LPBA40, Mori | Thể tích vỏ não. |
| CAT12 | Hammers | Thể tích vỏ não và dưới vỏ. |
| CAT12 | IBSR, COBRA, SUIT, Thalamic Nuclei, Thalamus | Thể tích dưới vỏ theo phân loại trong code. |

CAT12 có **16 khóa atlas thể tích**. Khả năng có đủ chỉ số theo vùng phụ thuộc kết quả ROI mà image CAT12 thực tế tạo ra và tên feature có khớp hay không. Bốn khóa CAT12 Schaefer hiện đều dùng feature list 8 mục; chưa coi là vector đủ 100/200/400/600 parcels.

### 2.3. Atlas MNI và các mục chưa hoàn chỉnh

| Nhóm | Atlas | Trạng thái hỗ trợ |
| --- | --- | --- |
| **Có cơ chế chiếu atlas MNI qua FS8** | SCLimbic, Harvard–Oxford Subcortical/Cortical, Brainnetome 246, Pauli 2017, Juelich, AAL, Schaefer 100 / 7. | SCLimbic tham chiếu volume trong image FS8, cần kiểm tra image thực tế. Cả 7 atlas ngoài còn thiếu NIfTI trong checkout; cần bổ sung đúng file và xác minh không gian template trước khi sử dụng kết quả. |
| **Mới có khai báo MNI, chưa đủ đường chạy** | CerebrA, Tian Subcortex, JHU ICBM-DTI-81 White Matter, SUIT Cerebellum. | Chưa khai báo volume/NIfTI cần thiết để builder thực hiện projection. |
| **Mới có khai báo phân vùng dưới vỏ chuyên biệt** | Hippocampal/Amygdala Subregions, Brainstem Substructures, Thalamic Nuclei, native SCLimbic của FreeSurfer. | Chưa xác định được đường tạo phân đoạn và đọc kết quả chuyên biệt hoàn chỉnh. |

**Lưu ý khi đọc kết quả:** số vùng trong tên atlas có thể khác số đặc trưng của vector đang dùng. Ví dụ Yale mang tên 696 nhưng feature list hiện có 650 mục; cả bốn biến thể CAT12 Schaefer hiện chỉ có 8 mục và các tên feature chứa 7Networks dù tên khóa ghi 17 networks. Giá trị thiếu được ghi **NA**, không thay bằng 0.

### 2.4. Tra cứu kỹ thuật về atlas

<details>
<summary><strong>Mở danh mục 59 khóa atlas, số đặc trưng, dữ liệu còn thiếu và nguồn đối chiếu</strong></summary>

#### Biến thể và cách sử dụng atlas bề mặt

- Khóa **schaefer2018 = 200 parcels / 7 networks**.
- Schaefer surface khác atlas MNI volume schaefer2018_100_7.
- Gói Schaefer **400 / 17** được đánh dấu gói tải mặc định; atlas CT mặc định trong preset hiện là **aparc**. Hai mặc định này có phạm vi khác nhau.
- Yale pack có thêm Yale_Brain_Atlas_*.annot; đường CT yale dùng cặp YBA_696_*_new.annot.
- Kong **100/300/400 / 17** có định nghĩa tùy chọn ở lớp availability, không thuộc 59 atlas chuẩn. Chỉ thêm file chưa đủ chứng minh có đường chạy hoàn chỉnh: còn cần picker, vector spec và registry.

#### Điều kiện thống kê CAT12

CAT12 có **16 khóa volume atlas**. Có tên trong danh mục không đảm bảo image CAT12 nào cũng xuất đủ ROI tương ứng: parser lấy dữ liệu report/ROI XML thực tế.

CAT12 Full trích thickness từ ROI XML; nếu không có, parser có thể lấy trung bình từng bán cầu và toàn bộ từ file surface. Kết quả được ghi vào cat12_cortical_thickness.tsv. Đây là khả năng xuất dữ liệu thickness, chưa phải bằng chứng có vector CT theo vùng đầy đủ.

Bộ tạo vector CT hiện chỉ đọc lh/rh.<atlas>.stats kiểu FreeSurfer; **chưa đọc trực tiếp cat12_cortical_thickness.tsv**. Vì thế preset CAT12 CT mặc định aparc có thể xuất vector 68 phần tử toàn NA khi chỉ có bảng CAT12. Kiểm tra nhỏ bằng dữ liệu tạm xác nhận trường hợp này; các test xuất TSV CAT12 thành công không kiểm chứng bước nối sang vector.

Bốn feature list CAT12 Schaefer 100/200/400/600 đều có 8 tên giống nhau, chứa 7Networks, không phải danh sách đủ parcels/17 networks như tên khóa. Chúng được liệt kê đúng hiện trạng, chưa xem là vector atlas đầy đủ.

#### Phạm vi sử dụng atlas theo bộ công cụ

| Bộ công cụ | Có cơ chế xử lý trong mã | Điều kiện/giới hạn cần giữ rõ |
| --- | --- | --- |
| FS7 | Aseg/Aparc volume; surface CT với bộ atlas bề mặt. | Preset Volume chỉ SV; CT cần cây subject/surface và dữ liệu atlas phù hợp. |
| FS8 | Aseg/Aparc volume; surface CT; projection MNI trong stats hoặc wrapper riêng. | Preset Volume không chạy surface. Khi bật CT nhưng không chọn aparc, stage stats vẫn yêu cầu lh/rh.aparc.stats; subject mới có thể thất bại dù atlas khác đã tạo stats. |
| FastSurfer | DKT/aseg volume; surface CT và ánh xạ atlas ở chuỗi đầy đủ. | DKT volume và aparc CT là hai lựa chọn khác nhau; không tự có projection MNI chỉ vì atlas MNI xuất hiện trong danh mục chung. |
| CAT12 | Volume theo ROI/report; xuất TSV thickness ở Full. | Chưa có bước ánh xạ toàn bộ atlas surface FreeSurfer hoặc reader vector CT trực tiếp từ TSV CAT12. |

Bộ chọn thống kê/atlas dùng danh mục chung theo CT/CV/SV; content check không thay thế việc kiểm tra atlas có builder/reader phù hợp với tool đang chạy.

#### Chi tiết projection atlas MNI

| Atlas MNI | Khóa | Tình trạng |
| --- | --- | --- |
| SCLimbic | mni_sclimbic | Có lệnh projection; spec trỏ volume trong image FS8, cần kiểm tra nội dung image thực tế. |
| Harvard–Oxford Subcortical | harvard_oxford_subcortical | Có projection; cần NIfTI/LUT. |
| Harvard–Oxford Cortical | harvard_oxford_cortical | Có projection; cần NIfTI/LUT. |
| Brainnetome 246 | brainnetome246 | Có projection; trong nhóm CV và SV. |
| Pauli 2017 | pauli_2017 | Có projection; cần NIfTI/LUT. |
| Juelich | juelich | Có projection; cần NIfTI/LUT. |
| AAL | aal | Có projection; trong nhóm CV và SV. |
| Schaefer 100 / 7 | schaefer2018_100_7 | Projection volume MNI, khác classifier surface. |
| CerebrA | cerebra | Có vector spec; thiếu volume/NIfTI trong spec, builder bỏ qua atlas này. |
| Tian Subcortex | tian_subcortex | Có vector spec; thiếu volume/NIfTI trong spec, builder bỏ qua. |
| JHU ICBM-DTI-81 White Matter | jhu_icbm_dti81 | Có vector spec; thiếu volume/NIfTI; code xếp nhóm CV dù tên là white matter. |
| SUIT Cerebellum | suit_cerebellum | Có vector spec; thiếu volume/NIfTI; code xếp nhóm CV. |

Projection hiện dùng **affine registration** và **nearest-neighbor resampling**, sau đó mri_segstats. Không diễn giải thành nonlinear atlas projection chỉ vì bước FS8 khác có sinh warp.

Tên/spec ghi MNI152, nhưng lệnh registration lấy mni305.cor.mgz hoặc bản stripped từ image. Tài liệu chỉ xác nhận cơ chế lệnh; chưa xác nhận atlas MNI152 và template thực dùng đồng nhất không gian. Có đủ NIfTI/LUT vẫn cần kiểm chứng bước này trên image/dữ liệu thực tế.

#### Dữ liệu có trong checkout và cơ chế cài đặt

- 24 atlas surface có feature list; 23 atlas dùng asset ngoài có đủ **46 file cần thiết cho hai bán cầu**. Các file này có nội dung nhị phân, không phải file rỗng hoặc Git LFS pointer; chưa thay thế kiểm thử ánh xạ trên ảnh thật.
- Aparc dùng classifier đi kèm image FreeSurfer, không có pack tải riêng. Pack Yale có thêm file ngoài cặp mà builder CT đang dùng.
- Cả 7 atlas MNI ngoài có khai báo đường NIfTI đều còn thiếu NIfTI tại checkout; LUT/manifest có sẵn không đủ để thực hiện projection.
- Import trên trang Tools ghi vào vùng dữ liệu **surface atlas**. Dù bộ import chấp nhận .nii.gz/.txt, việc import file MNI qua đây chưa chứng minh file được đặt vào thư mục MNI mà builder đọc.
- Content check chỉ kiểm file tồn tại, chưa kiểm file rỗng, định dạng, nhãn, không gian hoặc mức đầy đủ của ROI. Bốn spec MNI thiếu khai báo volume và bốn spec native vẫn có thể báo available vì không có đường asset cần kiểm.
- Surface availability tìm từng file ở nhiều thư mục, nhưng executor mount một thư mục atlas được chọn. Nếu asset bị chia giữa data directory và bundled resource, thông báo available chưa bảo đảm container thấy đủ file.
- MNI executor có biến override MRI_PIPELINE_MNI_ATLAS_DIR; content check và đồng bộ remote vẫn dựa đường cấu hình/resource tương ứng. Đổi biến mount chưa đảm bảo mọi lớp kiểm tra tìm cùng một thư mục.
- Đồng bộ atlas Server nằm trong đường upload code. Khi chữ ký code không đổi, đường tái sử dụng có thể trả về trước khi đồng bộ atlas mới chọn; cần kiểm tra dữ liệu đã có trên Server. File cùng kích thước cũng có thể bị bỏ qua mà chưa so checksum.

#### Các khóa native subregion mới có khai báo

Bốn khóa native subregion có vector spec với requires_native_segmentation=True nhưng chưa thấy stage riêng tạo native segmentation hoặc reader chuyên biệt hoàn chỉnh:

- **fs_hippo_amygdala:** hippocampal/amygdala subregions.
- **fs_brainstem:** brainstem substructures.
- **fs_thalamic_nuclei:** thalamic nuclei.
- **fs_sclimbic:** native SCLimbic segmentation.

Chúng được ghi để đủ danh mục; **chưa coi là chức năng phân đoạn chuyên biệt hoàn chỉnh**.

#### Danh mục đầy đủ 59 khóa atlas và số đặc trưng

CT = cortical thickness; CV = cortical volume; SV = subcortical volume. **Số feature** là số dòng có nội dung trong feature list ở checkout, không mặc nhiên bằng số vùng trong tên atlas. “Đủ file kiểm tra” chưa xác nhận runtime.

| Khóa atlas | Tên | Loại | Số feature | Tình trạng nội dung/đường chạy |
| --- | --- | --- | --- | --- |
| `aparc` | Desikan-Killiany (aparc) | CT | 68 | Đủ file kiểm tra; vẫn cần image/output phù hợp |
| `aparc_a2009s` | Destrieux (aparc.a2009s) | CT | 148 | Đủ file kiểm tra; vẫn cần image/output phù hợp |
| `freesurfer_aseg` | FreeSurfer Aseg Atlas | SV | 64 | Theo output pipeline; feature list có sẵn |
| `freesurfer_aparc` | FreeSurfer Aparc Cortical Volumes | CV | 68 | Theo output pipeline; feature list có sẵn |
| `fastsurfer_dkt` | FastSurfer DKT Atlas | CV, SV | 131 | Theo output pipeline; feature list có sẵn |
| `yale` | Yale Brain Atlas - 696 parcels | CT | 650 | Đủ file kiểm tra; vẫn cần image/output phù hợp |
| `kong` | Kong 2022 - 200 parcels / 17 networks | CT | 200 | Đủ file kiểm tra; vẫn cần image/output phù hợp |
| `schaefer2018_100parcels_7networks` | Schaefer 2018 - 100 parcels / 7 networks | CT | 100 | Đủ file kiểm tra; vẫn cần image/output phù hợp |
| `schaefer2018_100parcels_17networks` | Schaefer 2018 - 100 parcels / 17 networks | CT | 100 | Đủ file kiểm tra; vẫn cần image/output phù hợp |
| `schaefer2018` | Schaefer 2018 - 200 parcels / 7 networks | CT | 200 | Đủ file kiểm tra; vẫn cần image/output phù hợp |
| `schaefer2018_200parcels_17networks` | Schaefer 2018 - 200 parcels / 17 networks | CT | 200 | Đủ file kiểm tra; vẫn cần image/output phù hợp |
| `schaefer2018_300parcels_7networks` | Schaefer 2018 - 300 parcels / 7 networks | CT | 300 | Đủ file kiểm tra; vẫn cần image/output phù hợp |
| `schaefer2018_300parcels_17networks` | Schaefer 2018 - 300 parcels / 17 networks | CT | 300 | Đủ file kiểm tra; vẫn cần image/output phù hợp |
| `schaefer2018_400parcels_7networks` | Schaefer 2018 - 400 parcels / 7 networks | CT | 400 | Đủ file kiểm tra; vẫn cần image/output phù hợp |
| `schaefer2018_400parcels_17networks` | Schaefer 2018 - 400 parcels / 17 networks | CT | 400 | Đủ file kiểm tra; vẫn cần image/output phù hợp |
| `schaefer2018_500parcels_7networks` | Schaefer 2018 - 500 parcels / 7 networks | CT | 500 | Đủ file kiểm tra; vẫn cần image/output phù hợp |
| `schaefer2018_500parcels_17networks` | Schaefer 2018 - 500 parcels / 17 networks | CT | 500 | Đủ file kiểm tra; vẫn cần image/output phù hợp |
| `schaefer2018_600parcels_7networks` | Schaefer 2018 - 600 parcels / 7 networks | CT | 600 | Đủ file kiểm tra; vẫn cần image/output phù hợp |
| `schaefer2018_600parcels_17networks` | Schaefer 2018 - 600 parcels / 17 networks | CT | 600 | Đủ file kiểm tra; vẫn cần image/output phù hợp |
| `schaefer2018_700parcels_7networks` | Schaefer 2018 - 700 parcels / 7 networks | CT | 700 | Đủ file kiểm tra; vẫn cần image/output phù hợp |
| `schaefer2018_700parcels_17networks` | Schaefer 2018 - 700 parcels / 17 networks | CT | 700 | Đủ file kiểm tra; vẫn cần image/output phù hợp |
| `schaefer2018_800parcels_7networks` | Schaefer 2018 - 800 parcels / 7 networks | CT | 800 | Đủ file kiểm tra; vẫn cần image/output phù hợp |
| `schaefer2018_800parcels_17networks` | Schaefer 2018 - 800 parcels / 17 networks | CT | 800 | Đủ file kiểm tra; vẫn cần image/output phù hợp |
| `schaefer2018_900parcels_7networks` | Schaefer 2018 - 900 parcels / 7 networks | CT | 900 | Đủ file kiểm tra; vẫn cần image/output phù hợp |
| `schaefer2018_900parcels_17networks` | Schaefer 2018 - 900 parcels / 17 networks | CT | 900 | Đủ file kiểm tra; vẫn cần image/output phù hợp |
| `schaefer2018_1000parcels_7networks` | Schaefer 2018 - 1000 parcels / 7 networks | CT | 1000 | Đủ file kiểm tra; vẫn cần image/output phù hợp |
| `schaefer2018_1000parcels_17networks` | Schaefer 2018 - 1000 parcels / 17 networks | CT | 1000 | Đủ file kiểm tra; vẫn cần image/output phù hợp |
| `cat12_neuromorphometrics` | CAT12 Neuromorphometrics | SV | 33 | Có reader; phụ thuộc ROI/output image CAT12 |
| `cat12_schaefer2018_100parcels_17networks` | CAT12 Schaefer 2018 - 100 parcels / 17 networks | CV | 8 | Có reader; feature list 8 mục chứa 7Networks, chưa đủ biến thể ghi trong tên |
| `cat12_schaefer2018_200parcels_17networks` | CAT12 Schaefer 2018 - 200 parcels / 17 networks | CV | 8 | Có reader; feature list 8 mục chứa 7Networks, chưa đủ biến thể ghi trong tên |
| `cat12_schaefer2018_400parcels_17networks` | CAT12 Schaefer 2018 - 400 parcels / 17 networks | CV | 8 | Có reader; feature list 8 mục chứa 7Networks, chưa đủ biến thể ghi trong tên |
| `cat12_schaefer2018_600parcels_17networks` | CAT12 Schaefer 2018 - 600 parcels / 17 networks | CV | 8 | Có reader; feature list 8 mục chứa 7Networks, chưa đủ biến thể ghi trong tên |
| `cat12_aal3` | CAT12 AAL3 | CV | 62 | Có reader; phụ thuộc ROI/output image CAT12 |
| `cat12_anatomy3` | CAT12 Anatomy3 | CV | 90 | Có reader; phụ thuộc ROI/output image CAT12 |
| `cat12_cobra` | CAT12 COBRA | SV | 14 | Có reader; phụ thuộc ROI/output image CAT12 |
| `cat12_hammers` | CAT12 Hammers | CV, SV | 23 | Có reader; phụ thuộc ROI/output image CAT12 |
| `cat12_ibsr` | CAT12 IBSR | SV | 16 | Có reader; phụ thuộc ROI/output image CAT12 |
| `cat12_julichbrain3` | CAT12 Julich Brain 3 | CV | 106 | Có reader; phụ thuộc ROI/output image CAT12 |
| `cat12_lpba40` | CAT12 LPBA40 | CV | 48 | Có reader; phụ thuộc ROI/output image CAT12 |
| `cat12_mori` | CAT12 Mori | CV | 50 | Có reader; phụ thuộc ROI/output image CAT12 |
| `cat12_suit` | CAT12 SUIT | SV | 34 | Có reader; phụ thuộc ROI/output image CAT12 |
| `cat12_thalamic_nuclei` | CAT12 Thalamic Nuclei | SV | 28 | Có reader; phụ thuộc ROI/output image CAT12 |
| `cat12_thalamus` | CAT12 Thalamus | SV | 2 | Có reader; phụ thuộc ROI/output image CAT12 |
| `mni_sclimbic` | FreeSurfer SCLimbic (MNI152 projection) | SV | 25 | Spec trỏ volume trong image FS8; chưa xác minh nội dung image |
| `harvard_oxford_subcortical` | Harvard-Oxford Subcortical (MNI152 projection) | SV | 22 | Thiếu file: `HarvardOxford-subl-maxprob-thr0-1mm.nii.gz` |
| `harvard_oxford_cortical` | Harvard-Oxford Cortical (MNI152 projection) | CV | 96 | Thiếu file: `HarvardOxford-cortl-maxprob-thr0-1mm.nii.gz` |
| `cerebra` | CerebrA (MNI-ICBM152 projection) | SV | 22 | Chỉ spec; chưa khai báo atlas volume |
| `brainnetome246` | Brainnetome 246 (MNI projection) | CV, SV | 246 | Thiếu file: `BN_Atlas_246_1mm.nii.gz` |
| `pauli_2017` | Pauli 2017 Subcortical Atlas (MNI projection) | SV | 15 | Thiếu file: `pauli_2017_labels.nii.gz` |
| `juelich` | Juelich Atlas (MNI projection) | CV | 62 | Thiếu file: `juelich_maxprob-thr0-1mm.nii.gz` |
| `aal` | AAL Atlas (MNI projection) | CV, SV | 166 | Thiếu file: `aal.nii.gz` |
| `schaefer2018_100_7` | Schaefer 2018 - 100 parcels / 7 networks (MNI projection) | CV | 100 | Thiếu file: `schaefer2018_100_7.nii.gz` |
| `tian_subcortex` | Tian Subcortical Atlas (MNI projection) | SV | 18 | Chỉ spec; chưa khai báo atlas volume |
| `jhu_icbm_dti81` | JHU ICBM-DTI-81 White Matter (MNI projection) | CV | 36 | Chỉ spec; chưa khai báo atlas volume |
| `suit_cerebellum` | SUIT Cerebellum (MNI projection) | CV | 30 | Chỉ spec; chưa khai báo atlas volume |
| `fs_hippo_amygdala` | FreeSurfer Hippocampal/Amygdala Subregions | SV | 36 | Chỉ spec; chưa có bước native chuyên biệt đầy đủ |
| `fs_brainstem` | FreeSurfer Brainstem Substructures | SV | 14 | Chỉ spec; chưa có bước native chuyên biệt đầy đủ |
| `fs_thalamic_nuclei` | FreeSurfer Thalamic Nuclei | SV | 50 | Chỉ spec; chưa có bước native chuyên biệt đầy đủ |
| `fs_sclimbic` | FreeSurfer SCLimbic Segmentation | SV | 25 | Chỉ spec; chưa có bước native chuyên biệt đầy đủ |

Các điểm cần giữ nguyên khi sử dụng:

- Yale ghi **696** trong tên, feature list YBA_696parcels_feats.txt hiện có **650 mục**.
- CAT12 Schaefer **100/200/400/600 / 17** đều có **8 feature** giống nhau, chứa tên 7Networks; chưa phản ánh đủ các biến thể ghi trong tên.
- Aseg/SCLimbic/DKT có số feature phụ thuộc bộ chỉ số và chuẩn hóa; không suy chiều vector chỉ từ tên atlas.
- Thiếu dữ liệu được điền **NA** và có cảnh báo; có file vector không nghĩa là vector đủ giá trị.
- Khi bật CV/SV, generator còn tạo vector FreeSurfer mặc định bên cạnh atlas đã chọn. Với CAT12 hoặc nguồn khác, cột mặc định có thể không khớp và nhiều NA; không coi mọi cột xuất ra là kết quả đúng của atlas đã chọn.
- Các NIfTI MNI chưa có trong checkout không được xem là đã cài chỉ vì LUT được Git quản lý.

#### Điều kiện, giới hạn và nguồn đối chiếu

| Hạng mục | Điều kiện/giới hạn |
| --- | --- |
| Atlas | 59 khóa gồm cả spec chưa đủ đường chạy; đọc trạng thái từng nhóm. |
| Availability | File tồn tại chưa đảm bảo generator/reader. Atlas thiếu khai báo volume vẫn có thể được content check báo available. |
| MNI asset | Checkout thiếu một số NIfTI; bảng atlas nêu tên thiếu. |
| Native subregion | 4 khóa FS subregion chưa thấy đường phân đoạn/reader riêng hoàn chỉnh. |
| Projection | Dùng affine. Builder chọn template từ file MNI305 trong image dù biến/nhãn có chữ MNI152; cần xác minh không gian trước diễn giải kết quả. |
| Vector | Chiều theo feature list, có thể nhiều/toàn NA nếu nguồn không khớp. |
| CAT12 CT | Xuất TSV riêng; reader vector CT chưa đọc trực tiếp TSV này. |

#### Phạm vi kiểm chứng của bản tổng hợp

Đã đối chiếu registry, preset, command builder, executor/mount, metadata, parser thống kê, feature list, asset, API/UI, Dockerfile, script và packaging. Nhóm test trọng yếu gồm **122 test trong 13 module** về preset FS7/FS8/FastSurfer/CAT12, hợp đồng tool, atlas availability/pack, MNI projection, chuẩn hóa và vector; tất cả qua. Hai kiểm tra nhỏ bằng dữ liệu tạm xác nhận giới hạn CAT12 TSV → vector CT và FS8 CT chỉ chọn atlas khác aparc.

Test đơn vị kiểm chứng cấu hình, lệnh và parser bằng dữ liệu mẫu/mocks; không chứng minh toàn bộ image, phép đăng ký atlas hoặc kết quả y sinh đã được kiểm thử đầu cuối. Danh mục “có” trong báo cáo luôn đi kèm phạm vi và điều kiện nêu trên.

**Nguồn đối chiếu**

| Nội dung | Nguồn |
| --- | --- |
| Atlas/config/export items | [pipeline/config.py](../pipeline/config.py) |
| Atlas availability | [pipeline/atlas_content.py](../pipeline/atlas_content.py) |
| Nguồn dữ liệu atlas MNI | [atlas_sources.csv](../assets/atlases/mni/atlas_sources.csv) |
| Vector/feature/missing | [pipeline/stats.py](../pipeline/stats.py), [info](../info/) |
| Chuẩn hóa CAT12 | [normalize_volumes.py](../normalize_volumes.py), [tests/test_cat12_volume_normalization.py](../tests/test_cat12_volume_normalization.py), [tests/test_cat12_atlas_normalization.py](../tests/test_cat12_atlas_normalization.py) |
| Atlas pack, thư mục và đồng bộ | [app_backend/atlases.py](../app_backend/atlases.py), [pipeline/runner.py](../pipeline/runner.py), [remote/remote_runner.py](../remote/remote_runner.py) |
| Metadata/bộ chọn | [app_backend/metadata.py](../app_backend/metadata.py), [tests/test_atlas_content.py](../tests/test_atlas_content.py) |

</details>

## 3. Danh sách các chức năng hiện có

Phần này liệt kê **85 khả năng trong 11 nhóm**, bao gồm **chức năng người dùng**, **cơ chế vận hành tự động**, **khả năng backend/CLI** và **tiện ích phát triển/bảo trì**. Không giới hạn phạm vi trong một lần chạy pipeline. Tên chức năng dùng tiếng Anh; mô tả nêu rõ khả năng, phạm vi sử dụng và điều kiện cần thiết.

**Phạm vi sử dụng:** **UI** = có thao tác/thành phần giao diện; **Auto** = hệ thống tự thực hiện; **Backend/CLI** = gọi qua API, cấu hình hoặc dòng lệnh; **Dev/Script/Build** = phục vụ phát triển, kiểm tra và phân phối. Có component/API chưa nối hoàn chỉnh được ghi rõ, không xem là chức năng UI đã sẵn sàng.

### 3.1. Pipeline & Workspace Configuration

| Function | Mô tả, phạm vi và điều kiện sử dụng |
| --- | --- |
| **Pipeline Mode & Preset Selection** | **UI.** Chọn FS7, FS8, FastSurfer, CAT12 và mục tiêu thể tích/độ dày; áp dụng bộ tool và atlas mặc định theo preset. |
| **Custom Tool Selection & Compatibility Validation** | **UI + Auto.** Chọn/bỏ bước trong Custom; phát hiện thiếu đầu vào hoặc tổ hợp tool không tương thích và chặn khởi chạy khi có xung đột. |
| **Stats & Atlas Mapping** | **UI.** Chọn loại thống kê và atlas cho từng loại; hỗ trợ tìm atlas, thêm/bỏ lựa chọn, xem lý do atlas chưa khả dụng. |
| **Load / Save Preset** | **UI.** Nhập/xuất preset JSON gồm pipeline mode và tool đã chọn; thông báo khi file preset không hợp lệ. |
| **Load / Save Workspace** | **UI.** Nhập/xuất preset JSON gồm lưu input/output, danh sách ảnh, runtime, tool, atlas và những thiết lập NeuroFLOW ;thông báo khi file preset không hợp lệ. |
| **NeuroFLOW Configuration Import & Validation** | **UI + Auto.** Chọn preset/profile YAML/YML/JSON, phân biệt hai loại cấu hình, kiểm tra cấu trúc và tính tương thích cấu hình trước khi dùng scheduler. |
| **CPU, RAM & GPU Configuration** | **UI + Auto.** Đặt threads, phần trăm RAM, CPU/GPU theo máy Local hoặc Server; giới hạn threads theo số lõi phát hiện và cảnh báo mức dùng cao. |
| **Preflight Checks & Resource Suggestions** | **UI + Auto.** Kiểm tra cấu hình, tài nguyên, image, atlas, license và môi trường; khi thiếu RAM có thể áp dụng gợi ý tăng RAM/đổi preset, hoặc tải atlas còn thiếu từ dialog. |

### 3.2. Input Discovery & Batch Configuration

| Function | Mô tả, phạm vi và điều kiện sử dụng |
| --- | --- |
| **Single / Batch Input** | **UI + Backend.** Chọn một ảnh hoặc batch từ Local/Server; backend nhận NIfTI, MGH/MGZ và DICOM. |
| **Input Folder Watch** | **Backend/worker.** Theo dõi thư mục input để phát hiện ảnh mới, bỏ file .tmp và xử lý theo đợt; dừng theo yêu cầu hoặc khi có marker hoàn tất mà không còn ảnh mới. Chưa hỗ trợ NeuroFLOW và chưa có nút bật riêng trên form; khác Lazy Upload. |
| **DICOM Series Detection** | **Auto.** Nhận diện thư mục series và số slice, gom series thành một đầu vào; một số file không có đuôi được nhận diện bằng header DICOM. |
| **Local / Server File Browser** | **UI.** Duyệt file/thư mục Local và Server, tìm lọc, refresh và tạo thư mục trên Server. |
| **Batch Scan Modes, Cache & Rescan** | **UI.** Quét trực tiếp, một cấp thư mục con hoặc đệ quy tối đa 6 cấp trong browser batch; giữ cache scan trong phiên và cho phép quét lại. |
| **Batch Filtering, Sorting & Selection** | **UI.** Tìm theo subject/path, sắp xếp theo subject/format/path/size, chọn/bỏ tất cả kết quả đang lọc hoặc chọn N ảnh đầu; điều chỉnh độ rộng cột. |
| **Subject ID Generation & Duplicate Handling** | **Auto; Backend/CLI có ánh xạ riêng.** Sinh ID từ tên/path, chuẩn hóa ký tự, phát hiện nhãn trùng và tạo hậu tố chống trùng khi lập danh sách subject. |
| **Input, Staging & Output Locations** | **UI.** Chọn riêng nguồn input, thư mục staging upload và vị trí output Local/Server; có thể áp dụng vị trí Server đã duyệt làm input. |

### 3.3. Upload & Download

| Function | Mô tả, phạm vi và điều kiện sử dụng |
| --- | --- |
| **Manual Upload / Staging** | **UI.** Hỗ trợ chọn nhiều file/thư mục và upload cây thư mục vào vị trí đích. |
| **Lazy Upload** | **Auto.** Gửi từng ảnh khi scheduler cần, giới hạn số upload đồng thời, dùng dữ liệu tạm và marker sẵn sàng. Cần Server + Local input + NeuroFLOW và backend client còn chạy. |
| **Upload Progress Tracking** | **Backend/API; UI chưa nối hoàn chỉnh.** Có snapshot phần trăm/trạng thái từng ảnh và component hiển thị, nhưng cách truyền mã job từ UI chưa khớp khóa backend nên chưa coi là luồng hiển thị đã hoàn chỉnh. |
| **Upload Cancellation & Partial Cleanup** | **Backend/API.** Có yêu cầu hủy orchestrator và thử dọn dữ liệu upload dở; chưa thấy nút hủy upload riêng gọi API này trong giao diện hiện tại. |
| **Download Outputs & Job Artifacts** | **UI.** Tải output và artifact job Server về thư mục Local theo job; dùng vị trí output thực tế và hỗ trợ thư mục con khi được cấu hình. |
| **Download Progress, Speed & ETA** | **UI.** Thể hiện bước kết nối/đếm file/sao chép, số file đã tải, file hiện tại và ước lượng tốc độ/thời gian còn lại khi có dữ liệu. |
| **Download Cancellation & File-level Resume** | **UI.** Stop download giữ các file đã tải; Resume/Retry bỏ qua file có cùng kích thước và tải lại file thiếu/khác kích thước. Chưa có resume theo byte hoặc xác minh checksum. |

### 3.4. Execution & Recovery

| Function | Mô tả, phạm vi và điều kiện sử dụng |
| --- | --- |
| **Local Background Execution** | **UI + Auto.** Khởi chạy worker riêng và Docker trên máy Local; lưu registry, cấu hình, trạng thái, event và log để theo dõi lại. |
| **Detached Remote Execution** | **UI + Auto.** Chạy worker nền trên Server độc lập với phiên SSH; job đã có input sẵn có thể tiếp tục khi client mất kết nối. |
| **Active Job Warning** | **UI.** Khi danh sách đã biết có job đang chạy trên cùng runtime, hiển thị Job Already Running; người dùng chọn Cancel hoặc tiếp tục. Đây không phải khóa cứng cấm chạy nhiều job. |
| **Cancel Preflight** | **UI.** Hủy dialog/stream khởi chạy bằng nút hoặc Esc, tránh nhận kết quả UI muộn sau khi hủy; không bảo đảm rollback bước môi trường đã thực hiện hoặc job đã kịp khởi động. |
| **Stop Job** | **UI + Auto.** Gửi yêu cầu dừng Local/Server sau xác nhận. Worker/executor kiểm tra yêu cầu và có thể hủy container đang chạy; không chỉ chờ xong toàn bộ stage. |
| **Checkpoint & Resume** | **Backend/CLI.** Lưu trạng thái từng bước, kiểm tra file output đã tồn tại và bỏ qua bước có kết quả khi resume; form chính chưa có nút Resume Pipeline riêng. |
| **Restart Pipeline** | **Backend/config.** Có chế độ xóa output subject liên quan rồi chạy lại; không nhầm với Resume Download hoặc Reconnect. Chưa có lựa chọn riêng trên form chính. |
| **Stage Timeout & Output Validation** | **Auto.** Giới hạn thời gian chạy theo request/tool, dọn container khi timeout và kiểm tra output mong đợi; exit code thành công nhưng thiếu output vẫn được báo lỗi. |

### 3.5. NeuroFLOW Scheduling

| Function | Mô tả, phạm vi và điều kiện sử dụng |
| --- | --- |
| **Dependency-aware Task Scheduling** | **Auto khi bật NeuroFLOW.** Lập lịch theo phụ thuộc giữa các bước/ảnh; có preset/profile chuẩn cho FS7/FS8/FastSurfer, CAT12/Custom cần cấu hình phù hợp. |
| **Concurrency & Resource Budgets** | **UI + Auto.** Giới hạn số task đồng thời, ngân sách CPU/RAM và thông tin GPU; chọn task khi tài nguyên cho phép và lọc profile theo giới hạn threads. |
| **Scheduling Policy Selection** | **UI; Local hỗ trợ truyền lựa chọn.** Có B0–B6. Luồng start Server hiện chưa chuyển lựa chọn policy vào cấu hình job, nên phía Server quay về policy mặc định B6. |
| **Warmup, Retry, Estimation & I/O Limits** | **Backend/config; UI có một phần điều khiển.** Có warmup, retry, giữ OOM bounds, ước lượng balanced/conservative/aggressive và hạn chế task nặng I/O. Không phải mọi field đều có control riêng trên UI. |
| **Scheduler State Persistence & Observations** | **Auto.** Tạo/lưu workspace SQLite, có đường nạp lại workspace cùng job, ghi quan sát thực thi và phản hồi kết quả task cho scheduler. Không đồng nghĩa có nút khôi phục toàn bộ job trên UI. |

### 3.6. Job Monitoring & Reconnect

| Function | Mô tả, phạm vi và điều kiện sử dụng |
| --- | --- |
| **Background Job Discovery & Tracking** | **UI + Auto.** Đọc registry Local/quét job nền trong workspace Server và attach lại để lấy trạng thái, log, kết quả của tất cả các job. |
| **Connection Status & Manual Reconnect** | **UI.** Hỗ trợ Retry/Reconnect thủ công khi server bị ngắt kết nối; không tự nối lại UI toàn diện. |
| **Job List & Adaptive Refresh** | **UI + Auto.** Chia Local/Server, sắp theo thời điểm bắt đầu, refresh thủ công và polling thích ứng; dừng polling ở một số trạng thái terminal/offline, giữ kết quả trước khi refresh lỗi. |
| **Batch Summary & Status Chart** | **UI.** Đếm số subject thành công/thất bại/đang chạy/chưa chạy/đã dừng để hiển thị biểu đồ. |
| **Subject Grid / List, Search & Sort** | **UI.** Chuyển Grid/List, tìm subject, lọc trạng thái và đổi thứ tự theo thời điểm chạy hoặc thứ tự input. |
| **Subject Details & Stage Timeline** | **UI.** Mở chi tiết từng subject, xem bước hiện tại, trạng thái từng stage, thời gian bắt đầu/kết thúc/thời lượng và lỗi. |
| **Log Search, Raw View & Clear** | **UI.** Mở rộng/thu log, tìm lọc, bật raw log, làm sạch ký tự terminal và xóa phần log đang hiển thị; Clear không xóa file log gốc. |
| **CPU / RAM Metrics & Sparklines** | **UI + Auto.** Xem số đo/biểu đồ CPU-RAM, thời gian và container theo subject/stage khi có dữ liệu; backend hỗ trợ lấy metrics theo subject/input. |
| **Run Configuration Snapshot** | **UI.** Xem cấu hình pipeline đã sử dụng để chạy job. |
| **Delete Jobs** | **UI; Backend/API.** Xóa job có xác nhận; UI chặn xóa job chạy hoặc khi mất kết nối. |

### 3.7. Outputs, Statistics & Reporting

| Function | Mô tả, phạm vi và điều kiện sử dụng |
| --- | --- |
| **Output Workspace Validation** | **Auto.** Kiểm khả năng tạo/ghi thư mục và dung lượng trống trước xử lý; có ngưỡng dung lượng tối thiểu theo kích thước input và quy tắc hiện tại. |
| **Output Organization & Permission Repair** | **Auto.** Sắp volume, stats và log vào thư mục thích hợp, giữ cây FreeSurfer/export; thử sửa quyền file do container tạo để host đọc/ghi được khi phù hợp. |
| **Statistics Normalization** | **Auto.** Đọc kết quả SynthSeg, FreeSurfer, FastSurfer, CAT12 và chuẩn hóa bảng thống kê theo vùng/bán cầu/atlas. CAT12 Full xuất bảng thickness riêng; chưa nối trực tiếp bảng này sang vector CT theo atlas. |
| **Feature Vector Generation** | **Auto.** Sinh vector, bảng feature có thứ tự cố định, CSV và manifest mô tả cột/feature list; hỗ trợ nhiều atlas và loại thống kê khi có reader phù hợp. Khi bật CV/SV còn sinh vector FreeSurfer mặc định; cần kiểm tra cảnh báo và dữ liệu từng cột. |
| **Missing Feature Warnings** | **Auto.** Chuẩn hóa dữ liệu thiếu/không hợp lệ thành NA, ghi cảnh báo số feature thiếu; không tự biến dữ liệu thiếu thành 0. |
| **Batch Summary & Wide-format Tables** | **Auto.** Xuất bảng vector gộp và bảng trải feature thành cột, kèm tên ảnh/path/trạng thái cho các input trong batch. |
| **Custom Output Export** | **Backend/CLI.** Đặt thư mục/tên/format output, copy hoặc chuyển sang định dạng hỗ trợ; form chạy chính hiện tắt export tùy chỉnh mặc định. |
| **Benchmark & Resource Reports** | **Auto.** Ghi thời gian xử lý, CPU/RAM peak/average/p95, kết quả theo bước/subject/batch, thông tin host và cấu hình phục vụ đánh giá hiệu năng. |

### 3.8. Environment, Tools & Atlas Management

| Function | Mô tả, phạm vi và điều kiện sử dụng |
| --- | --- |
| **Local / Server Environment Inspection** | **UI + Backend.** Xem Python, Docker và phần cứng CPU/RAM/GPU; Server có kiểm tra venv/pip và Docker daemon. Mức kiểm tra Local/Server không hoàn toàn giống nhau. |
| **Docker Image Inventory & Sizes** | **UI.** Gom tool dùng chung image, phân biệt đã có/chưa có/đang tải, xem dung lượng sử dụng và kích thước nội dung/tải khi backend lấy được thông tin. |
| **Image Preparation & Build Fallback** | **Backend/CLI.** Chuẩn bị image đã chọn qua chế độ riêng: kiểm tra image, thử pull và fallback build khi registry có Dockerfile/context phù hợp. Không phải mọi lần Start Pipeline đều tự build hoặc mọi tool đều có fallback. |
| **Local Image Pull Progress** | **UI.** Tải image Local, stream log/trạng thái layer và thông báo lỗi. Không mặc nhiên tải image ở mọi lần Start Pipeline. |
| **Background Server Image Pull** | **UI + Auto.** Pull image trên Server bằng tiến trình nền, theo dõi trạng thái/log theo offset và kiểm tra lại khi mở trang Tools. |
| **Docker Image Removal** | **UI.** Gỡ image trên runtime đã chọn sau xác nhận và làm mới trạng thái; không phải gỡ tool khỏi mã nguồn. |
| **Atlas Pack Download & Import** | **UI.** Tải/giải nén pack có tiến độ, import ZIP hoặc folder, xem số file đã có/còn thiếu và cài pack từ dialog preflight khi resolve được pack. |
| **Atlas Availability Checks** | **Auto + UI.** Kiểm feature list/asset, vô hiệu hóa lựa chọn thiếu nội dung kèm lý do; đủ file chưa chứng minh atlas có generator/reader hoàn chỉnh. |
| **FreeSurfer License Validation & Staging** | **UI + Auto; API upload.** Chọn file, lưu/upload qua API, đưa license vào môi trường chạy và kiểm tra bằng luồng preflight/container tương ứng. |
| **Remote Code & Selected Atlas Synchronization** | **Auto.** Có đường upload code/config và atlas đã chọn. Khi tái sử dụng chữ ký code không đổi, bước này có thể bỏ qua atlas mới chọn; bỏ qua file cùng kích thước cũng chưa xác minh checksum. Cần kiểm tra asset đã có trên Server. |
| **Remote Python & Environment Provisioning** | **Auto khi chuẩn bị remote job; Backend.** Tạo/tái sử dụng venv, chuẩn bị pip/dependency; khi cần có đường cài managed Python 3.11 trong workspace cho NeuroFLOW, phụ thuộc điều kiện máy chủ. |

### 3.9. Connection & Data Protection

| Function | Mô tả, phạm vi và điều kiện sử dụng |
| --- | --- |
| **SSH Key / Password Authentication** | **UI + Backend.** Cấu hình host/port/user, remote Python/workspace và xác thực bằng key hoặc password; kiểm tra kết nối trước khi dùng Server. |
| **SSH Host-Key Trust & Change Detection** | **UI + Auto.** Xác nhận fingerprint host mới, lưu known-hosts và phát hiện/từ chối host key đã thay đổi theo luồng hiện có. |
| **SSH Key Permissions & WSL Compatibility** | **Auto.** Kiểm key tồn tại/quyền truy cập; có xử lý key trên Windows/WSL và bản tạm với quyền phù hợp trong trường hợp cần thiết. |
| **SSH Connection Reuse, Keepalive & Retry** | **Auto.** Pool kết nối, giới hạn channel, keepalive và retry/backoff một số lỗi kết nối; lỗi xác thực được xử lý khác. Đây không phải auto-reconnect của UI. |
| **Backend Request Protection** | **Auto.** Kiểm peer loopback, origin/CORS và token ở luồng desktop; validate JSON/body size và request. Health endpoint có cách xử lý riêng. |
| **Secret Redaction** | **Auto.** Che thông tin nhạy cảm trong các cấu hình, registry summary và thông báo/log có áp dụng redaction; workspace lưu từ UI không đưa password vào payload lưu. |
| **Workspace & Archive Path Checks** | **Auto.** Kiểm phạm vi đường dẫn cho thao tác job/output tương ứng, tránh một số đường dẫn archive không hợp lệ; tải thư mục bỏ qua symlink. Không coi đây là kiểm chứng an toàn tuyệt đối cho mọi input. |

### 3.10. Desktop Experience & Operations

| Function | Mô tả, phạm vi và điều kiện sử dụng |
| --- | --- |
| **Page Navigation & Session State** | **UI.** Điều hướng Pipeline/Tools/Jobs và chi tiết job; giữ một số state qua store trong phiên, chuyển đến job vừa khởi chạy sau khi xác nhận thành công. |
| **Theme & Font Scale Preferences** | **UI.** Theme sáng/tối/theo hệ thống, cỡ chữ 80–120%, lưu lựa chọn hiển thị qua lần mở lại; không mặc nhiên tự lưu mọi field cấu hình pipeline. |
| **Resizable Layout & Dialog Controls** | **UI.** Kéo giãn hai khung cấu hình, chỉnh cột batch, mở/đóng modal, Esc ở các dialog có hỗ trợ và toast/thông báo thao tác. |
| **Copy Input / Output / Download Paths** | **UI.** Sao chép đường dẫn input/output ở job detail và đường dẫn kết quả đã tải từ download dialog vào clipboard. |
| **Startup Health & Capability Diagnostics** | **Auto + UI.** Kiểm backend và thành phần runtime trước khi hiện main window ở bản đóng gói; báo thiếu thành phần/lỗi khởi động, ghi log backend để chẩn đoán. |
| **Bundled Backend Lifecycle** | **Auto.** Khởi chạy backend đi kèm, worker dùng executable ở bản đóng gói; đóng app dừng backend sidecar. Windows có cơ chế hạn chế hiện console từ các tiến trình phụ được cấu hình. |
| **Portable / Installed App Data Storage** | **Auto; cấu hình môi trường.** Tách resource bất biến khỏi data/config/job/license/log ghi được; hỗ trợ bố trí portable và thư mục dữ liệu ứng dụng cài đặt. |
| **Cross-platform Packaging & CI Artifacts** | **Dev/Build.** Windows portable và NSIS installer, Linux AppImage, macOS app/DMG; có workflow build/artifact. CI hiện có nhánh unsigned/internal test, không coi mọi artifact đã ký/notarize. |

### 3.11. Developer & Maintenance Utilities

| Function | Mô tả, phạm vi và điều kiện sử dụng |
| --- | --- |
| **Backend Dependency Diagnostics** | **Backend/CLI.** Chế độ check kiểm import các dependency quan trọng và trả kết quả chẩn đoán; phục vụ kiểm tra bản đóng gói hoặc môi trường backend. |
| **Stale Development Backend Cleanup** | **Dev/Script.** Tiện ích phát hiện và dọn backend phát triển cũ trên cổng cấu hình; phân biệt với tiến trình khác chiếm cổng. Không phải nút dọn toàn bộ job. |
| **Standalone Pipeline & Image Smoke Scripts** | **Dev/Script.** Có script chạy/kiểm thử trực tiếp FS7, FS8, FastSurfer, CAT12 và một số container; không đồng nghĩa mỗi script là một preset UI đã tích hợp. |
| **Atlas Release Asset Packaging** | **Dev/Script.** Tạo ZIP cho các surface atlas pack để phục vụ phân phối/tải/import; khác với chức năng tạo atlas khoa học mới. |
| **Cross-run Benchmark Aggregation** | **Dev/Script.** Đọc benchmark đã xuất từ nhiều run, tổng hợp theo bước/tool/số lõi và ghi CSV/XLSX; cần dữ liệu/dependency tương ứng, chưa có nút tổng hợp riêng trên UI. |

**Điều kiện quan trọng:** Orchestrator Lazy Upload cho Server + Local input cần NeuroFLOW bật và backend client còn hoạt động; phần hiển thị tiến độ vẫn có giới hạn nêu ở trên. Resume pipeline, Resume Download và Reconnect là các khả năng khác nhau. Các khóa atlas chỉ có khai báo và tổ hợp tool chưa kiểm thử được phân biệt ở phần 1–2.

### 3.12. Technical Reference

<details>
<summary><strong>Mở mô tả đầy đủ: cơ chế xử lý, policy, API/CLI và tham số</strong></summary>

#### Additional Operational Capabilities

- Workspace có nút lưu/tải trên header; preset và workspace là hai định dạng với phạm vi khác nhau. Workspace hiện không lưu đầy đủ mọi field nâng cao của NeuroFLOW.
- Khi start và danh sách hiện tại đã biết có job đang chạy cùng target, UI cảnh báo nhưng cho phép tiếp tục; không xem là cơ chế khóa tài nguyên toàn hệ thống.
- Kiểm output workspace thử ghi file và kiểm dung lượng trống. Quy tắc hiện tại dùng ngưỡng tối thiểu 10 GiB hoặc 20 lần kích thước input, lấy mức lớn hơn; đây là quy tắc kiểm tra, không phải bảo đảm đủ đĩa cho mọi pipeline.
- Sau xử lý, hệ thống tổ chức volume/stats/log và thử sửa quyền host trong các trường hợp phù hợp.
- Đường upload code ưu tiên atlas đã chọn, nhưng có thể không được gọi khi tái sử dụng chữ ký code cũ. Thay đổi atlas hoặc tải asset mới chưa đảm bảo tự đồng bộ lại; so cùng kích thước không tương đương xác minh checksum.
- Server có đường chuẩn bị Python/venv/pip/dependency; managed Python phụ thuộc nền tảng và công cụ mạng có trên máy chủ.
- UI Jobs có Grid/List, sắp Run order/Input order, tìm/lọc subject, chi tiết stage/metrics, copy path và Clear log hiển thị.
- Đọc log/event/metrics có offset, polling thích ứng và giới hạn lịch sử trong bộ nhớ UI; không đồng nghĩa xóa dữ liệu log trên đĩa.
- Bản đóng gói có log/chẩn đoán khởi động, phân tách data/resource và kiểm dependency; tiện ích dọn backend cũ chỉ dành cho phát triển.
- Có cơ chế tạo NSIS installer Windows, pack atlas ZIP, smoke script và tổng hợp benchmark CSV/XLSX; phân loại là khả năng build/script.

#### Audit Boundaries & Incomplete Connections

- Rà soát bao phủ các module giao diện, backend/API, pipeline/worker, SSH, cấu hình, wrapper Docker, script và packaging đang được Git quản lý; không tính thư viện node_modules, mã sinh tự động hay kế hoạch chưa triển khai thành tính năng sản phẩm.
- Đã chạy 122 test trọng yếu sẵn có về preset, hợp đồng tool, nội dung atlas, projection và chuẩn hóa/vector thống kê; tất cả qua. Đây là kiểm chứng ở mức mã/test, chưa phải chạy toàn bộ pipeline y sinh, image, SSH hoặc artifact đa nền tảng.
- CAT12 CT, FS8 CT không chọn atlas mặc định, dữ liệu MNI và đồng bộ atlas Server có giới hạn được ghi rõ ở phần 1–2; không suy từ việc test qua rằng các đường này đã chạy đầy đủ trên MRI thực tế.
- Chỉ có tên hàm/component chưa đủ chứng minh có luồng UI hoàn chỉnh. Trường hợp tiến độ lazy upload và truyền policy Server được ghi giới hạn ngay trong bảng chức năng.
- Không thêm tên code hoặc link file nguồn vào các bảng chức năng; phần tra cứu giữ API/CLI và artifact cần thiết để mô tả khả năng kỹ thuật.

#### Environment & Configuration

##### Environment Checks & Docker Image Management

- Xem image trên Local/Server.
- Gom wrapper dùng chung image.
- Trạng thái đã có/chưa có/đang tải; kích thước và thông tin backend trả về.
- Pull từ UI; Local stream log/progress, xử lý trạng thái layer.
- Server pull chạy nền, đọc trạng thái/log theo offset.
- Refresh image; làm mới khi có download.
- Remove image có xác nhận.
- Kiểm Docker executable/daemon/version.
- Python/host/CPU/RAM/GPU/runtime capability.
- CLI **--ensure-images-only**; lớp pipeline có pull/build/check theo registry/Dockerfile.
- Preflight remote báo thiếu image và hướng sang Tools; không tự tải mọi image ở mọi luồng start.
- Docker/image lớn được quản lý riêng, không gói tất cả vào app.

##### Atlas Pack Management

- Xem 23 surface pack, trạng thái cài, file thiếu, số file đã có/tổng.
- Download ZIP, tiến độ tải/giải nén.
- Import ZIP hoặc folder.
- Tìm asset từ data ghi được, resource đóng gói, checkout dev.
- Override thư mục surface atlas bằng biến môi trường; base URL release cấu hình được.
- Kiểm feature list/asset trước chạy, báo tên atlas thiếu.
- MNI NIfTI/LUT không thuộc 23 surface pack; cần đúng file hoặc image.
- Content check chưa đảm bảo có generator/reader phù hợp.

##### FreeSurfer License Handling

- UI yêu cầu license khi tool needs_license.
- Browse license.txt, xóa lựa chọn.
- API upload/lưu license.
- Stage license Local/Server.
- Remote kiểm license thành bước riêng trước upload/ghi job config.
- Lỗi license sai/thiếu ở preflight.
- Redaction trong các luồng log/config/error có hỗ trợ.

##### Preset & Workspace Management

- Load Preset JSON và Save Preset qua native save dialog.
- UI preset lưu mode/selected tools; không mặc nhiên là bản sao toàn workspace.
- UI có Save Workspace / Load Workspace; backend còn có lưu/liệt kê/load workspace và preset.
- Backend export JSON ra path.
- Workspace chứa input/runtime/output/tool/stats/atlas/remote/NeuroFLOW theo schema.
- Redact secret/password khi lưu/export qua backend.
- Validate request, số/tùy chọn, tool key, path, license, atlas, compatibility.
- Validate preset/profile NeuroFLOW và báo lỗi theo loại.
- Form/store/query cache trong phiên không có nghĩa mọi field tự lưu qua lần mở app sau.

##### Pipeline Steps & Output Statistics

- Chọn preset của FS7, FS8, FastSurfer hoặc CAT12; dùng Custom khi cần chọn tool theo bước.
- Chọn loại thống kê và atlas tương ứng; có thể chọn nhiều atlas cho một loại thống kê.
- Kiểm tra tương thích giữa các bước và điều kiện nội dung atlas trước khi chạy.
- Phạm vi bước và preset được trình bày ở phần 1; danh mục atlas ở phần 2.

##### CPU, GPU & RAM Configuration

- Cấu hình threads, phần trăm RAM, CPU/GPU.
- Default form: **RAM 80%, 4 threads, GPU off, concurrency 2, B6, retry 3**.
- Docker memory limit theo cấu hình; CLI mô tả 100% là bỏ memory limit container.


#### Input & Data Transfer

##### Input Formats & Sources

- Input **Local** hoặc **Server**; nguồn Server cần runtime Server và kết nối.
- **Single input** hoặc **batch input**.
- Backend nhận volume **.nii, .nii.gz, .mgz, .mgh**.
- DICOM **.dcm, .dicom, .ima**; nhận một số file không đuôi qua magic header DICM.
- Nhận diện thư mục DICOM series như một đầu vào thay vì đếm từng slice thành subject.
- Chuẩn hóa lựa chọn file DICOM thành thư mục series khi chuẩn bị request.
- Backend nhận nhiều định dạng hơn bộ lọc file picker MRI hiện tại.
- Có request danh sách file cụ thể; UI batch có thể tạo danh sách.
- CAT12 chỉ nhận volume .nii/.nii.gz/.mgz/.mgh trong command builder; không nhận trực tiếp DICOM folder như luồng chuyển đổi FreeSurfer.

##### Local / Server File Browser

- File/folder picker native.
- Browser remote qua SFTP: mở thư mục, lên thư mục cha, nhập path, refresh, lọc danh sách.
- Tạo thư mục remote.
- Hiển thị tên/path/định dạng và metadata file mà browser trả về.
- Nhận diện DICOM series, số slice ở luồng duyệt hỗ trợ.
- Chọn input, staging và output Server.
- Modal hai khung Local/Server để duyệt và upload thủ công.
- Khóa hoặc báo không khả dụng khi cần Server nhưng chưa kết nối.

##### Batch Input Selection

- Quét trực tiếp, quét một cấp thư mục con, quét đệ quy.
- Re-scan.
- Cache scan trong phiên để giảm quét lại khi mở/đóng modal.
- Tìm/lọc danh sách ảnh.
- Chọn/bỏ chọn subject; có điều khiển chọn số lượng.
- Hiển thị Subject ID, format, relative path.
- Thay đổi độ rộng cột bảng batch.
- Sinh subject ID từ tên/path/dataset root, chuẩn hóa ký tự, thêm hậu tố khi trùng.
- Backend/CLI nhận subject_id_map để ánh xạ tên đầu ra.
- Lưu danh sách chọn/cấu hình batch vào request.

##### Upload / Manual Staging

- Chọn một/nhiều file hoặc thư mục Local và upload SFTP.
- Upload cây thư mục, tạo thư mục đích.
- Chọn/tạo đích bằng modal hai khung.
- Dùng thư mục đã upload làm input Server.
- API staging trả kết quả và số đường dẫn upload.
- License, job config và tài nguyên code được chuẩn bị qua luồng riêng của ứng dụng.


#### Execution & Scheduling

##### Preflight Checks

- Preflight so RAM cấp phát với peak từ profile.
- Thiếu RAM: gợi ý tăng phần trăm hoặc preset nhẹ hơn theo kết quả backend.
- Stream preflight cấu hình, tài nguyên, image, license, sync code, môi trường, worker tùy runtime.
- Hủy preflight bằng nút/Esc; không đồng nghĩa rollback toàn bộ bước môi trường đã xong.
- Thiếu atlas: có nút tải pack trong dialog khi resolve được pack.

##### Local Job Execution

- Docker chạy trên máy Local.
- Worker là tiến trình riêng; POSIX có session riêng, Windows có cờ process cho worker nền.
- Registry job trên đĩa, đọc lại khi backend/giao diện mở lại.
- Theo dõi status, PID, events, log, metrics từ file.
- Bản đóng gói dùng backend/worker executable; bản dev dùng Python module.
- Vẫn cần Docker daemon và image phù hợp.

##### Detached Remote Execution

- SSH host/port/username; key path hoặc password.
- Remote Python và workspace tùy chỉnh.
- Test SSH, lấy phần cứng Server.
- Kiểm tra Python, Docker, GPU và môi trường theo luồng tương ứng.
- Chuẩn bị virtual environment/dependency; runner có cơ chế managed Python 3.11/micromamba khi cần.
- Đồng bộ code và tài nguyên cần thiết.
- Chữ ký SHA-256 + code_manifest.json giúp dùng lại code nếu chữ ký không đổi. Chữ ký hiện không bao gồm danh sách atlas đã chọn hoặc toàn bộ asset atlas; nhánh dùng lại có thể bỏ qua upload asset mới.
- Chuẩn bị license, job config và metadata.
- Start detached bằng setsid, fallback nohup.
- Status/log/events lưu trên Server để đọc lại.
- Liệt kê job nền trong workspace, attach để theo dõi, download hoặc stop.
- Job có input sẵn trên Server không cần client giữ SSH liên tục để tính toán tiếp.

##### NeuroFLOW Scheduling

- Bật/tắt NeuroFLOW.
- 9 cặp preset/profile YAML: FS7/FS8/FastSurfer × 3 mục tiêu.
- CAT12 chưa có mapping mặc định; muốn dùng cấu hình riêng cần cặp preset/profile phù hợp.
- Custom dùng scheduler khi có cấu hình phù hợp.
- Chọn/validate YAML/YML/JSON cho preset hoặc profile.
- Stage dependency, nhiều task/subject khi đủ tài nguyên.
- Policy B0–B6.
- Tổng CPU threads, threads mỗi task, ngân sách RAM, concurrency.
- GPU và memory/device class khi bật.
- Lọc profile theo thread limit.
- Warmup: concurrency ban đầu, số lần thành công an toàn trước tăng, concurrency tối thiểu.
- Retry 0–5 theo validation, delay tăng dần cho transient error.
- Cấu hình giữ OOM bounds khi manual retry.
- Estimation: balanced, conservative, aggressive.
- Giới hạn task nặng I/O.
- Workspace SQLite, observation runtime, artifact tài nguyên.
- Có field ở request/config không nghĩa tất cả có control UI riêng.

##### Scheduling Policies

Phạm vi: UI và adapter có lựa chọn B0–B6; cả luồng start Local và luồng tạo job Server đều chuyển policy đã chọn vào job_config.json.

| Policy | Tên | Đặc điểm được UI mô tả |
| --- | --- | --- |
| B0 | Sequential FIFO | Một task, thứ tự sẵn sàng/được thêm, profile tĩnh. |
| B1 | Parallel FIFO First-Fit | FIFO song song, cấu hình khả thi đầu tiên, profile tĩnh. |
| B2 | Shortest Processing Time First-Fit | Runtime ước tính ngắn trước, profile tĩnh. |
| B3 | Static Critical-Path First-Fit | Ưu tiên đường găng, profile tĩnh. |
| B4 | Static Critical-Path Protected Backfill | Đường găng/backfill, chọn CPU/GPU, không adaptive estimation. |
| B5 | Adaptive FIFO Resource Scheduler | Ước lượng và concurrency thích nghi, FIFO. |
| B6 | Full NeuroFLOW | Policy đầy đủ, mặc định UI. |

Ứng dụng truyền policy/config vào dependency NeuroFLOW; thuật toán chi tiết nằm trong dependency đó.

##### Lazy Upload

**Luồng được triển khai: Runtime Server + Input Local + NeuroFLOW.**

1. Tạo job/config Server, ánh xạ Local path sang staging path.
2. Khi stage đầu được scheduler đưa vào chạy, worker phát **image_awaiting_input**.
3. Orchestrator trong backend máy người dùng đọc event, gửi ảnh/DICOM folder qua SFTP.
4. Dữ liệu đang gửi dùng hậu tố **.part**.
5. Upload xong rename sang path chính, ưu tiên atomic nếu được hỗ trợ; ghi marker **.ready**.
6. Worker chờ marker trước khi xử lý.

Các khả năng kèm theo:

- Upload khi scheduler cần, tránh chờ toàn batch được chuyển trước.
- Giới hạn upload đồng thời: mặc định orchestrator 2, start flow truyền theo neuroflow_max_concurrent_tasks.
- Trạng thái từng ảnh: pending, uploading, ready, failed, cancelled.
- Phần trăm theo byte; DICOM folder cộng dồn các file.
- Có component tiến độ upload và API snapshot; hiện cách truyền mã job từ component chưa khớp khóa lưu orchestrator nên đường hiển thị chưa hoàn chỉnh.
- API hủy upload có thể hủy handle và thử dọn .part khi dùng đúng mã job; chưa thấy nút hủy upload riêng trên UI.
- Lỗi đọc event do SSH được ghi log và vòng đọc tiếp tục thử.
- Adapter chờ marker tối đa mặc định **3.600 giây**, có kiểm tra stop.

**Giới hạn:** backend máy người dùng phải còn chạy và còn truy cập Local input để gửi ảnh chưa upload. Đóng desktop đóng gói sẽ dừng backend này; server worker có thể chạy tiếp nhưng ảnh thiếu input phải chờ. Chưa thấy tự phục hồi orchestrator sau backend restart hoặc resume upload theo byte.

Cờ lazy upload được đặt cho Server + Local, nhưng orchestrator chỉ start khi NeuroFLOW bật. Không mặc nhiên xem Server + Local + tắt NeuroFLOW là luồng lazy upload hoàn chỉnh.

##### Lazy Watch / Input Folder Watch

- Worker có **lazy-watch**: theo dõi input_dir, bỏ file .tmp và xử lý ảnh mới theo đợt; kết thúc khi dừng hoặc có .upload_done mà không còn file mới. Đây là khả năng worker/backend, **khác lazy upload và chưa hỗ trợ NeuroFLOW**.


#### Job Tracking & Management

##### Background Job Tracking & Reconnect

- Jobs gom Local/Server, chia theo runtime.
- Đọc registry Local và quét job nền Server sau khi kết nối để theo dõi tiếp.
- Route chi tiết **/jobs/:jobId**.
- Events/log/metrics có offset, cho phép lấy delta.
- Jobs UI polling khoảng **20 giây** ở danh sách, **30 giây** khi xem job đang chạy; terminal job dừng polling chi tiết.
- Backend down thì dừng polling tương ứng; SSH down có thể tiếp tục refresh Local.
- Có trạng thái kết nối, báo lỗi và đường Retry/Reconnect.
- **UI khôi phục thủ công:** Retry backend, Reconnect SSH từ Pipeline Configuration. Không mô tả thành auto-reconnect toàn diện.
- SSH client có connection pool, giới hạn channel, phát hiện transport chết và retry lớp kết nối; khác với chính sách UI.
- Desktop hiện không có close-guard ngăn thoát; đóng app đóng gói dừng backend sidecar. Worker detached là tiến trình khác, nhưng lazy upload cần client vẫn chịu giới hạn ở phần lazy upload (xem chức năng Lazy Upload tại mục 3.3).

##### Job & Subject Progress, Logs & Metrics

- Job Local/Server, sắp xếp theo lúc bắt đầu.
- Job card có trạng thái, thời điểm, tiến độ batch.
- Biểu đồ batch và số subject thành công/thất bại/đang chạy/chưa chạy/đã dừng theo dữ liệu.
- Chi tiết job có snapshot pipeline mode, tool, threads, RAM, device và các field summary đã lưu.
- Tool thực tế trong request summary; fallback preset nếu cần.
- Theo dõi từng subject.
- Tìm subject, lọc trạng thái, sắp theo thời điểm bắt đầu/thứ tự input.
- Stage hiện tại, tiến độ và thông tin bước.
- Thời điểm bắt đầu/kết thúc, thời lượng, lỗi.
- Log theo offset; tìm kiếm và chế độ raw log.
- Metrics CPU/RAM theo thời gian; API lọc subject/input.
- Refresh thủ công và polling.
- Có API **/jobs/stream** cùng API snapshot/event/log/metrics.
- Báo cáo batch giữ cả ảnh chưa bắt đầu.

##### Stop / Resume / Restart

- Stop job Local/Server qua stop marker.
- Worker/executor kiểm tra yêu cầu dừng; executor có thể hủy container đang chạy. Không chỉ dừng sau khi stage kết thúc, nhưng vẫn phụ thuộc thời điểm nhận yêu cầu.
- Checkpoint/tracker **pipeline_state.json**.
- Backend/CLI có **resume**: kiểm tra state/output, bỏ bước hoàn thành, chạy phần còn thiếu.
- Backend có **restart**: xóa đầu ra liên quan theo code rồi chạy lại.
- Resume pipeline, Resume download, Reconnect SSH là ba chức năng khác nhau.
- Form chạy chính hiện không gửi lựa chọn Resume/Restart pipeline riêng như field tài nguyên; dùng đường API/CLI/config phù hợp.

##### Delete Jobs

- Delete có xác nhận; UI chặn xóa job chạy, chặn thao tác khi kết nối cần thiết không khả dụng.


#### Results & Download

##### Processing Outputs

- Thư mục theo subject/batch/run.
- Volume trung gian/cuối tùy stage.
- Cây FreeSurfer **mri/, surf/, label/, stats/** ở nhánh tương ứng.
- White/pial/thickness/sphere registration tùy pipeline.
- Segmentation/brain mask/WM mask/transform tùy tool.
- CAT12 report/ROI XML, tissue/segmentation và surface trong full mode.
- .stats, CSV/TSV và log.
- Không phải preset nào cũng sinh tất cả output; Volume-only bỏ surface.
- Với job Local, giao diện cung cấp thông tin vị trí output trên máy.

##### Statistics & Feature Vectors

- Volume từ SynthSeg CSV, FS/FastSurfer stats, CAT12 XML.
- **subcortical_volume.tsv**, **cortical_volume.tsv** khi có dữ liệu.
- CAT12 per-atlas TSV, **cat12_cortical_thickness.tsv** ở full mode.
- Nhiều atlas cho mỗi loại thống kê.
- Mapping vùng/alias/hemisphere/giá trị vào feature list.
- Thứ tự feature theo **info/*_feats.txt**.
- Vector .txt, **`*_features.tsv`** có index/feature/value.
- CSV **stats/vectors/stats_vectors.csv** theo subject.
- Batch **stats_vectors_summary.csv**: vector trong ô.
- Batch **stats_vectors_wide.csv**: mỗi feature một cột.
- Giữ mri_name, file_path, run_status, cả ảnh chưa bắt đầu.
- Thiếu/không hợp lệ → **NA**, cảnh báo số feature thiếu.
- Không tự nội suy feature thiếu hoặc đổi NA thành 0.

##### Custom Output Export

Có ở backend/CLI; **form chính hiện gửi export_config.enabled=false**.

- Bật/tắt, folder export, tên theo loại output.
- Giữ định dạng gốc **same**, hoặc **.nii.gz**, **.mgz**.
- Copy hoặc convert theo pipeline/export.py.
- 8 nhóm output: reoriented MRI, brain image, brain mask, segmentation, registered MRI, deformation field, standardized MRI, WM mask.
- Chỉ export được loại mà stage/tool thực sự sinh file.

##### Download Outputs & Resume Download

- SFTP download kết quả job Server.
- Chọn thư mục Local, tạo thư mục con theo job.
- Attach bằng remote output thực tế, không chỉ mặc định trong job folder.
- Stream bước connect, count, download, complete/error.
- Số file đã tải/tổng file, tốc độ/ETA trên UI khi có mẫu tiến độ.
- Hủy download và Resume/Retry.
- **Resume ở mức file:** bỏ qua file Local cùng kích thước; tải lại file thiếu/khác kích thước. Không có bằng chứng resume giữa file theo byte hoặc so checksum.
- Bỏ qua symlink khi tải cây thư mục.
- Tải kèm job config/metadata/status, events, run.log, launcher.log, exit code, finished time và các artifact NeuroFLOW được liệt kê trong runner.
- API hỗ trợ download_subdir.
- Với job Local, UI có thông tin vị trí output, không cần SFTP.

##### Benchmark & Resource Reporting

- Duration từng stage/toàn pipeline, build/preparation time theo kết quả bước.
- Peak/average/p95 CPU và RAM.
- Metrics log, báo cáo theo bước/subject/batch.
- Thông tin host/cấu hình trong báo cáo theo code.
- **neuroflow_observations.tsv**, **neuroflow_observations.jsonl**, **neuroflow_workspace.sqlite**.
- Script **aggregate_benchmarks.py**, workspace benchmark CPU1–CPU5.


#### Desktop UI & Control Interfaces

##### Desktop UI, Theme & Font Scale

- Tauri + React; Pipeline/Tools/Jobs.
- Light/dark/system; lưu theme, theo dõi theme hệ thống.
- Font scale **80%, 90%, 100%, 110%, 120%**; tăng/giảm/reset, lưu lựa chọn.
- Header/footer status hệ thống/kết nối.
- Toast/lỗi, modal xác nhận, preflight, upload/download progress.
- Tìm/thêm/bỏ atlas theo statistic; disable atlas thiếu nội dung kèm lý do.
- Tooltip/trường bắt buộc, native picker, remote browser, dual-pane transfer.
- Footer Documentation/GitHub hiện trỏ GitHub chung; chưa coi là cổng tài liệu sản phẩm hoàn chỉnh.

##### Backend API

| Nhóm | Endpoint chính |
| --- | --- |
| Health/metadata/capability | /health; /metadata; /capabilities/runtime; /environment/local |
| Request/license | /run-request/prepare; /licenses/upload |
| Local job | /jobs/local; /jobs/local/start; /jobs/local/start/stream; /jobs/local/stop; /jobs/local/delete |
| Local tracking | /jobs/local/events; /jobs/local/log; /jobs/local/metrics; /jobs/stream |
| Workspace/preset | /config/workspaces; /config/workspaces/load; /config/workspaces/save; /config/presets; /config/presets/load; /config/presets/save |
| Export/validate config | /config/export; /config/neuroflow/validate |
| Browser | /local/browse; /remote/browse; /remote/mkdir |
| SSH/environment | /remote/validate; /remote/trust-host; /remote/environment |
| Server job | /remote/jobs; /remote/jobs/start/stream; /remote/jobs/stop; /remote/jobs/delete |
| Server tracking | /remote/jobs/events; /remote/jobs/log; /remote/jobs/metrics |
| Upload | /remote/jobs/upload/stage; /remote/jobs/upload/state; /remote/jobs/upload/cancel |
| Download | /remote/jobs/download/stream; /remote/jobs/download/cancel |
| Image | /tools/local/images; /tools/local/pull; /tools/local/remove; /tools/server/pull/status; nhiều endpoint có thêm target Local/Server |
| Atlas | /atlases/status; /atlases/download/stream; /atlases/import |

Các stream tương ứng dùng SSE. Endpoint backend không đồng nghĩa có một nút UI độc lập.

##### Pipeline & Worker CLI

Pipeline entry: **pipeline_runner.py**. Backend CLI có server/worker cho bản đóng gói.

- --input-file, --input-dir.
- --output-dir, --license-dir.
- --device cpu|gpu, --threads, --ram-percent.
- --resume, --stop-file, --non-recursive.
- --json-events.
- --ensure-images-only.
- --export-config, --subject-id-map, --stats-vector-config.
- Option chọn tool được tạo theo stage trong pipeline/cli.py.
- Worker có --job-config, --lazy-watch; khác option của pipeline entry.


#### Connection Security & Secret Redaction

- Backend native khởi tạo với token, kiểm tra request/loopback/origin/CORS.
- SSH host lạ phải xác nhận SHA-256 fingerprint.
- Host key thay đổi: phát hiện/từ chối theo luồng hiện có.
- Known-hosts, kiểm quyền/key path, chuẩn bị key cho WSL/Windows khi cần.
- Redact secret ở config/registry summary/error có hỗ trợ.
- Kiểm remote job/output nằm trong workspace ở thao tác tương ứng.
- Tài liệu này không chứa credential thực tế.


#### Desktop Packaging & Backend Startup

- Windows portable folder, script app/backend, PyInstaller backend, executable/shortcut/data.
- Linux AppImage có native shell/backend.
- macOS app/DMG, đường build arm64/x64, xử lý thư viện kèm.
- GitHub Actions Windows/Unix/Linux/macOS.
- Resource bất biến tách data/config/log/job/output ghi được.
- Startup health/runtime capability, báo lỗi khi backend thiếu thành phần.
- Backend log chẩn đoán.
- Windows hạn chế console nháy lên từ tiến trình phụ theo cơ chế code.
- Docker/GPU runtime/image vẫn là yêu cầu ngoài bộ app.
- Có cơ chế ký theo script; tài liệu packaging ghi build nội bộ có thể unsigned. Chưa khẳng định mọi artifact đã ký/notarize/kiểm chứng phát hành.


#### Operating Conditions & Limitations

| Chức năng | Điều kiện/giới hạn |
| --- | --- |
| Lazy upload | Cần NeuroFLOW, Server + Local input, backend client hoạt động. |
| Reconnect | UI dùng Retry/Reconnect thủ công; job nền tiếp tục là khả năng khác. |
| Download resume | Mức file/cùng kích thước; không byte-resume/checksum. |
| Lazy-watch | Worker/backend, chưa hỗ trợ NeuroFLOW; khác lazy upload. |
| Export tùy chỉnh | Backend/CLI có; form chính đang tắt mặc định. |
| Thoát desktop | Dừng backend sidecar; upload cần client không được đảm bảo tiếp tục. |
| Release | Có build đa nền tảng, chưa khẳng định artifact đã ký/notarize/kiểm thử từng OS. |


</details>

Bản tổng hợp dựa trên mã nguồn tại commit nêu ở đầu; chưa thay thế việc kiểm thử toàn bộ tổ hợp tool, image và atlas trên dữ liệu MRI thực tế.