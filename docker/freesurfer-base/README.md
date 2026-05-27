# FreeSurfer Base Image (`mri-freesurfer-base`)

## Mô tả
Đây là base image nền tảng cho toàn bộ các công cụ thuộc hệ sinh thái FreeSurfer trong dự án. Image được build từ `freesurfer/freesurfer:7.4.1` (CentOS Vault) và đã được cấu hình sẵn môi trường Python 3 cùng các biến môi trường cần thiết.

## Cấu hình Contract
- `FREESURFER_HOME`: `/usr/local/freesurfer`
- `FS_LICENSE`: `/license/license.txt`
- Base OS: CentOS (Đã patch Vault repository)
