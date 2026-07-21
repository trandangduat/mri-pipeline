# Báo cáo Tổng kết: Cấu trúc lại Kiến trúc (Refactoring) & Kiểm thử TDD

Toàn bộ quá trình làm việc trên nhánh `refactor/improve-architecture` (từ lúc bắt đầu tách nhánh tới hiện tại) nhằm mục đích giải quyết nợ kỹ thuật (tech debt). Chúng ta đã biến một codebase cồng kềnh với các file "God Object" (quá to, ôm đồm mọi thứ) thành một hệ thống Deep Modules tuân thủ SOLID, sạch sẽ, dễ bảo trì và an toàn với hệ thống Test tự động.

## 1. Cấu trúc lại Backend (Pipeline Core)
*   **Xoá bỏ God Object `utils.py`:**
    *   Tách thành `pipeline/hardware.py` (lấy thông tin CPU, RAM hệ điều hành).
    *   Tách thành `pipeline/workspace.py` (quản lý thư mục, cấu trúc outputs, phân quyền file).
    *   Tách thành `pipeline/reports.py` (xử lý file TSV Benchmark, pipeline metrics, json logs).
    *   Tách thành `pipeline/discovery.py` (logic tìm kiếm file MRI đệ quy).
*   **Chia tách `config.py`:** Di dời những định nghĩa không phải cấu hình thuần túy ra ngoài. Tạo `pipeline/registry.py` để chứa `TOOL_DEFS`, `STAGE_ORDER`, và tạo `pipeline/presets.py`.
*   **Tạo tầng Execution độc lập:** Tách logic gọi lệnh hệ điều hành và Docker ra khỏi `runner.py`, tạo `pipeline/executor.py` với `LocalDockerExecutor` và `ExecutionRequest` để cô lập quá trình tương tác subprocess. Tách logic xử lý thông số thống kê ra module `stats.py`.

## 2. Cấu trúc lại Frontend (UI)
*   **Phá bỏ kiến trúc Mixins tại `main.py`:**
    *   Ban đầu `main.py` (`PipelineGUI`) ôm mọi thứ từ dựng giao diện đến nghiệp vụ qua các Mixin lỏng lẻo.
    *   Đã chuyển đổi hoàn toàn sang mô hình **Controllers độc lập**: `ToolsController`, `PipelineController`, `JobsController`, `ProgressController`, `RemoteController`, `ConfigController`, `JobRegistryController` và `ValidationController`.
    *   `main.py` giờ chỉ còn đóng vai trò là "View Container" vẽ layout chính và nhúng (inject) các Controller vào nhau thông qua Object `self.gui`.
*   **Trích xuất Dialogs (Hộp thoại):** Chuyển các class hộp thoại đồ sộ vào `ui/dialogs/remote_browser.py` và `ui/dialogs/job_dialogs.py`.
*   **Giao tiếp phi đồng bộ:** Đưa hệ thống `EventEmitter` vào `ui/events.py` để truyền tải log và thông báo giữa các module (như từ thread background lên progress UI) một cách an toàn mà không bị dính chặt vào vòng lặp của Tkinter.

## 3. Quản lý AI Agents (`AGENTS.md`)
*   Viết lại toàn bộ `AGENTS.md` trở thành nguồn chân lý (Source of Truth) cho mọi hệ thống AI Agent làm việc trên dự án.
*   Quy định rõ ràng triết lý **Deep Modules** của tác giả John Ousterhout, nghiêm cấm các bad-smell như: Feature Envy, Data Clumps.
*   Bổ sung quy trình sử dụng các bộ skill quan trọng (TDD, Code Review, Codebase Design).
*   Cảnh báo an toàn (Zero Tolerance) đối với Server từ xa của giáo sư: cấm can thiệp file ngoài Workspace.

## 4. Xây dựng Hệ thống Kiểm thử (TDD) & Vá lỗi ngầm
*   **Mock Server SSH an toàn:** Thiết lập một Docker container `dummy_ssh` cục bộ tại `tests/dummy_ssh/` làm môi trường test. Việc này cho phép chạy các lệnh Integration Test cho Remote Server mà không cần kết nối tới máy chủ thật, phòng ngừa hoàn toàn rủi ro xóa/phá dữ liệu nghiên cứu.
*   **Truy quét & Vá lỗi hàng loạt thông qua TDD:**
    *   *Attribute Errors:* Khắc phục tình trạng các biến trong UI gọi nhầm `self` thay vì `self.gui` – một di chứng nặng nề của quá trình đập bỏ Mixins. 
    *   *Import Errors:* Phát hiện và sửa lỗi các file UI import các biến tĩnh (`STAGE_ORDER`, `TOOL_DEFS`) sai địa chỉ (vẫn trỏ về `pipeline.config` trong khi chúng đã ở `pipeline.registry`).
    *   *Bug Logic & Formatters:* Fix thuật toán `truncate_middle` trong `formatters.py` bị lỗi cắt chữ kỳ dị khi giới hạn độ dài quá thấp (<= 4 ký tự).
*   **Lưới an toàn (Safety Net):** Viết bộ Test Suite toàn diện, bao phủ cả Backend (`test_config.py`, `test_executor.py`, `test_remote_runner.py`, `test_utils.py`) lẫn UI Controllers (`test_ui.py`, `test_ui_jobs.py`, `test_ui_validation.py`, `test_ui_formatters.py`, `test_ui_progress.py`, `test_ui_remote.py`). 
*   **Kết quả cập nhật:** Sau vòng review/fix bổ sung, test suite hiện có 37 bài test và đã **PASSED 100%** trong virtualenv tạm. Các regression tests mới bao phủ luồng `run_pipeline` gọi `ExecutionRequest`, parse requirements, guardrail remote cleanup, server output path ngoài workspace, và xoá active job trong registry.

## 5. Vòng ổn định sau Code Review
*   **Sửa blocker executor:** `run_pipeline` đã được nối lại với interface mới của `LocalDockerExecutor` bằng `ExecutionRequest`, tránh lỗi runtime khi gọi keyword cũ (`tool_key`, `stage`, `input_file`, ...).
*   **Sửa dependency runtime/dev:** `requirements.txt` chỉ còn dependency runtime (`pandas`, `sv-ttk`, `Pillow`, `paramiko`, `psutil`), còn `pytest` và `pytest-mock` được chuyển sang `requirements-dev.txt`.
*   **Tăng an toàn remote:** `RemoteRunner` có guard chung để chuẩn hóa path remote, chặn workspace rỗng/root, chặn job/output/code/license/config path ngoài workspace, và không cho xóa workspace root.
*   **Giảm coupling UI:** `JobRegistryController` không còn gọi trực tiếp các private method delete/pause/monitor của `JobsController`; thay vào đó đi qua interface public nhỏ.

## Đánh giá Tổng quan
Nhánh `refactor/improve-architecture` đã cải thiện đáng kể kiến trúc của dự án `mri-pipeline`: backend được tách module rõ hơn, UI đã chuyển dần sang controller, có cẩm nang hướng dẫn chuẩn (`AGENTS.md`), và có test suite tự động làm lưới an toàn.

Các nợ còn lại cần theo dõi: một số UI controller vẫn còn lớn và còn gọi private methods lẫn nhau ở các flow ngoài registry delete; `EventEmitter` hiện là synchronous event bus chứ chưa phải async/thread-safe bus; remote path guard đã tốt hơn nhưng mọi thao tác SSH mới trong tương lai vẫn phải đi qua guard trước khi ghi/xóa/chạy lệnh trên path.
