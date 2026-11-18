# Báo cáo Day 09 — Đỗ Quốc Học, 2A202603175

## 1. Kết luận trước
Pipeline kết luận **HOLD** (mã thoát 10). Vào 224 ảnh, intake loại 22 ảnh nên **202 ảnh** đi tiếp và được xuất thành bản **nháp** `submission/export/clean_v1/`. Chưa được phát hành vì sau khi người duyệt mô phỏng xem 80 ảnh (ngân sách), vẫn còn **38/202 ảnh (18,81%)** có cảnh báo chưa được duyệt, vượt ngưỡng 10%. Không còn lỗi bắt buộc nào (`n_errors = 0`).

## 2. Lỗi và phân việc
Số liệu từ `02_error_list_v1` (lỗi trước khi sửa, lô 224 ảnh; mã ở bước intake tính trên 224 ảnh, các mã còn lại trên 202 ảnh):

| Mã lỗi | Số ảnh/dòng | Ai sửa | Vì sao |
|---|---:|---|---|
| DUP_IMAGE_EXACT | 8 | máy | trùng md5, xoá ảnh trùng, giữ ảnh đầu tiên |
| DUP_IMAGE_NEAR | 4 | máy | phash <= 12, loại ảnh trùng gần đúng |
| LEAK_TEST | 5 | máy | trùng ảnh test/val, loại để không làm số liệu đẹp giả |
| CORRUPT_IMAGE / BAD_SIZE | 2 / 3 | máy | ảnh hỏng, cạnh ngắn < 250 px: loại |
| BAD_CLASS_ID | 6 | máy | xoá dòng có id lớp ngoài 0..3 |
| BAD_FORMAT | 3 | máy | xoá dòng thiếu cột / nan |
| BOX_ZERO | 4 | máy | xoá dòng box rộng/cao bằng 0 |
| DUP_BOX | 7 | máy | xoá dòng box lặp |
| BOX_OUT_OF_IMAGE | 8 | máy | cắt box về trong ảnh (hoặc xoá nếu nằm hẳn ngoài) |
| BAD_CLASS_NAME | 2 | máy | ghi lại `names` trong data.yaml |
| MISSING_LABEL_FILE | 6 | **người** | máy không được bịa nhãn, ghi `needs_label` |
| POSSIBLE_MISSING / WRONG_CLASS / LOOSE_BOX / FALSE_POS | 53 / 18 / 28 / 29 | **người** | lỗi ngữ nghĩa, model chỉ cho ý kiến thứ hai |
| BOX_TINY / BOX_HUGE / EMPTY_LABEL / CLASS_RARE | 6 / 3 / 12 / 4 | người | cảnh báo, không tự sửa |

Hàng đợi `05_review_queue.csv` xếp theo điểm ưu tiên: ảnh `NEEDS_LABEL` (trọng số 10) đứng đầu vì chỉ người mới gán được nhãn, rồi đến ảnh có nhiều cảnh báo nặng (`POSSIBLE_WRONG_CLASS` 3, `POSSIBLE_MISSING` 2, `POSSIBLE_FALSE_POS` 2) và dòng bị xoá tự động (`FIXED_DROP_LINE`). Hàng đợi có 125 ảnh nhưng ngân sách chỉ 80 ảnh, nên 45 ảnh không được xem và người chỉ xử lý được khoảng 64% hàng đợi.

## 3. Calibration (2 ngưỡng)
Số liệu từ `submission/calibration/calibration_report.md` (calib 39 ảnh).

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **12** | DUP_IMAGE_NEAR: P 1,00 / R 0,50 → P 1,00 / R 0,67 | Precision vẫn 1,00 và DUP_IMAGE_EXACT không đổi, recall tăng từ 0,50 lên 0,67. Giá trị 10–14 cho cùng kết quả (một vùng phẳng) nên chọn giữa vùng. Không chọn 16 dù recall calib là 0,83. |
| `second_opinion.conf` | 0.25 | **0.6** | WRONG_CLASS P 0,56→0,62 (R 0,83); MISSING P 0,50→0,57 (R 1,00); LOOSE_BOX P 0,29→0,20, R 0,40→0,20; FALSE_POS không đổi (P 0,31 / R 1,00) | Giữ recall của MISSING = 1,00 và WRONG_CLASS = 0,83 (hai lỗi nặng nhất), đồng thời tăng precision để bớt báo động giả cho người duyệt. Đánh đổi: LOOSE_BOX tệ hơn. |

**Chỗ calibration có thể đánh lừa:** `phash_dist = 16` cho recall cao nhất trên calib (0,83), nhưng trên lô raw thật số ảnh bị loại nhảy từ `LEAK_TEST` 5 → 11 và `DUP_IMAGE_NEAR` 4 → 7 (ở 20 thì `LEAK_TEST` = 105 và `DUP_IMAGE_EXACT` giảm còn 4). Calib chỉ có 6 cặp gần trùng nên con số 0,83 chỉ là 1 cặp chênh lệch, còn ở raw ngưỡng 16 bắt đầu gộp nhầm ảnh khác nhau. Tương tự `second_opinion.conf = 0.8` cho kết luận **Release** (16/202 = 7,92% ảnh còn cảnh báo) nhưng chỉ vì ngưỡng cao làm biến mất cảnh báo (recall MISSING giảm 1,00 → 0,75), không phải vì nhãn sạch hơn. Thử `conf` 0.5 / 0.6 / 0.7 / 0.8 cho tỉ lệ cảnh báo 21,78% / 18,81% / 14,36% / 7,92%.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
(a) Chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb` (không có người duyệt): kết luận **REWORK — còn 6 lỗi bắt buộc chưa xử lý**, mã thoát **20**, log in "KHÔNG xuất: còn lỗi bắt buộc (Rework)" và thư mục `work/exp_nb` không được tạo. 6 lỗi đó là 6 ảnh `MISSING_LABEL_FILE`; máy không tự bịa nhãn nên chỉ người mới gỡ được.

(b) Điểm mù (có bằng chứng từ calibration):
1. **Ảnh trùng biến đổi mạnh:** ở `phash_dist = 12` calib bỏ sót 2/6 ảnh `DUP_IMAGE_NEAR` (recall 0,67). Tăng ngưỡng để bắt thì lại gộp nhầm ở raw (xem mục 3).
2. **Box lỏng:** `POSSIBLE_LOOSE_BOX` ở conf 0.6 chỉ có P 0,20 / R 0,20, tức máy gần như không bắt được box lỏng nhẹ.
3. **Báo động giả nhiều:** `POSSIBLE_FALSE_POS` precision chỉ 0,31 trên calib (nhãn người đúng nhưng model nhỏ/lớn đều không thấy vật) nên tốn ngân sách người duyệt.
4. Lỗi nhầm lớp mà cả model lớn cũng nhầm (xe tải ↔ bus) sẽ không được cờ vì hai bên đồng ý với nhau; mục này là suy luận, chưa kiểm chứng trên dữ liệu.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Chưa chạy (phần tùy chọn). Bản nháp `submission/export/clean_v1/` đã sẵn sàng để train sau.

## 6. Quyết định và ghi chú AI
(a) **Quyết định: HOLD** (bản nháp, không phát hành). Để thành Release cần đưa tỉ lệ ảnh còn cảnh báo chưa duyệt xuống dưới 10% (tức duyệt thêm ít nhất 18 trong số 38 ảnh còn cảnh báo, hoặc tăng ngân sách duyệt trong dự án thật), và gán nhãn cho 6 ảnh thiếu file nhãn. Tôi không hạ cảnh báo bằng cách nâng `conf` lên 0.8 vì làm vậy chỉ che lỗi.

(b) Ghi chú AI: **có dùng AI** (Antigravity) hỗ trợ viết 4 module.
- Prompt chính: "Bắt đầu làm bài thực hành này cho tôi... làm đúng theo yêu cầu", kèm đọc docstring và test của từng module.
- Cách kiểm: chạy `pytest` từng module rồi toàn bộ (79 test xanh), chạy `make calibrate`, `pipeline.run` và so sánh số ảnh bị loại trên raw ở nhiều `phash_dist`.
- Một lần AI sai/lỗi: khi chỉnh `pipeline.yaml` lần đầu, AI dùng đường dẫn tương đối nên ghi file thất bại (sai thư mục làm việc) và pipeline chạy với ngưỡng cũ; AI phát hiện qua log và sửa lại. AI cũng để sót một điều kiện thừa `if gone or True` trong `autofix.py` rồi dọn đi.
